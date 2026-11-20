#!/usr/bin/env python3
"""Event-study backtest for overnight XAUUSD -> MCX GOLD/GOLDM repricing.

Input: one normalized CSV with columns:
timestamp,instrument,contract,open,high,low,close
Timestamps must be ISO-8601 with timezone or local IST (naive timestamps are treated as IST).
instrument values: XAUUSD, USDINR, GOLD, GOLDM.
MCX rows must be intraday bars; XAUUSD and USDINR must cover the overnight window.
This is an event study, not a risk-free arbitrage simulator.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

IST = "Asia/Kolkata"

def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"timestamp", "instrument", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    ts = pd.to_datetime(df["timestamp"], errors="coerce")
    if ts.isna().any():
        raise ValueError("Unparseable timestamps found")
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(IST, ambiguous="NaT", nonexistent="shift_forward")
    else:
        ts = ts.dt.tz_convert(IST)
    df["timestamp"] = ts
    df["instrument"] = df["instrument"].str.upper().str.strip()
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
    df = df.sort_values("timestamp").drop_duplicates(["instrument", "contract", "timestamp"] if "contract" in df else ["instrument", "timestamp"])
    df["session_date"] = df["timestamp"].dt.date
    return df

def last_before(g: pd.DataFrame, ts: pd.Timestamp):
    x = g[g.timestamp <= ts]
    return None if x.empty else x.iloc[-1]

def first_after(g: pd.DataFrame, ts: pd.Timestamp):
    x = g[g.timestamp >= ts]
    return None if x.empty else x.iloc[0]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out", default="gold_mcx_results")
    p.add_argument("--mcx-open", default="09:00")
    p.add_argument("--mcx-close", default="23:30")
    p.add_argument("--hold-minutes", type=int, nargs="+", default=[15, 30, 60, 120])
    p.add_argument("--cost-bps-roundtrip", type=float, default=8.0,
                   help="Placeholder round-trip cost in bps; replace with broker/contract-specific charges.")
    args = p.parse_args()
    df = load(args.input)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    rows = []
    for instrument in ["GOLD", "GOLDM"]:
        mcx = df[df.instrument == instrument].copy()
        if mcx.empty: 
            continue
        # Select the most liquid contract per session if volume is present; otherwise
        # use the first contract seen and require user to supply a pre-filtered front-month series.
        for d, day in mcx.groupby("session_date"):
            day = day.sort_values("timestamp")
            if "contract" in day and day["contract"].nunique() > 1:
                if "volume" in day:
                    chosen = day.groupby("contract")["volume"].sum().idxmax()
                    day = day[day.contract == chosen]
                else:
                    raise ValueError(f"{instrument} {d}: multiple contracts; provide volume or pre-filter front month")
            close_bar = day.iloc[-1]
            # Previous MCX session close and current MCX session open are paired below.
        dates = sorted(mcx.session_date.unique())
        for i in range(1, len(dates)):
            prev_d, cur_d = dates[i-1], dates[i]
            prev = mcx[mcx.session_date == prev_d].sort_values("timestamp")
            cur = mcx[mcx.session_date == cur_d].sort_values("timestamp")
            if prev.empty or cur.empty: continue
            prev_close = float(prev.iloc[-1].close)
            cur_open = float(cur.iloc[0].open)
            open_gap = cur_open / prev_close - 1
            open_ts = cur.iloc[0].timestamp
            # Global overnight return: last available observation at/before previous MCX close
            # to first available observation at/after current MCX open.
            x = df[df.instrument == "XAUUSD"].sort_values("timestamp")
            fx = df[df.instrument == "USDINR"].sort_values("timestamp")
            x0 = last_before(x, prev.iloc[-1].timestamp)
            x1 = last_before(x, open_ts)
            f0 = last_before(fx, prev.iloc[-1].timestamp)
            f1 = last_before(fx, open_ts)
            if any(v is None for v in [x0, x1, f0, f1]): continue
            xret = float(x1.close / x0.close - 1)
            fxret = float(f1.close / f0.close - 1)
            fair_ret = (1 + xret) * (1 + fxret) - 1
            record = dict(instrument=instrument, date=str(cur_d), contract=str(cur.iloc[0].get("contract", "")),
                          prev_mcx_close=prev_close, mcx_open=cur_open, mcx_open_gap_pct=open_gap*100,
                          xauusd_overnight_pct=xret*100, usdinr_overnight_pct=fxret*100,
                          synthetic_fair_return_pct=fair_ret*100,
                          opening_mispricing_pct=(fair_ret-open_gap)*100)
            for mins in args.hold_minutes:
                cutoff = open_ts + pd.Timedelta(minutes=mins)
                future = cur[cur.timestamp >= cutoff]
                if future.empty: continue
                px = float(future.iloc[0].close)
                # Long/short direction from fair value minus observed opening gap.
                side = 1 if fair_ret > open_gap else -1
                gross = side * (px / cur_open - 1)
                net = gross - args.cost_bps_roundtrip / 10000
                record[f"ret_{mins}m_gross_pct"] = gross*100
                record[f"ret_{mins}m_net_pct"] = net*100
                record[f"side_{mins}m"] = "LONG" if side == 1 else "SHORT"
            rows.append(record)
    if not rows:
        raise SystemExit("No paired sessions. Check instrument names, timestamps and overlapping history.")
    res = pd.DataFrame(rows)
    res.to_csv(out / "event_study.csv", index=False)
    summaries = []
    for inst, g in res.groupby("instrument"):
        for mins in args.hold_minutes:
            col = f"ret_{mins}m_net_pct"
            if col not in g: continue
            v = g[col].dropna()
            if v.empty: continue
            wins = v[v > 0]
            losses = v[v < 0]
            summaries.append(dict(instrument=inst, holding_minutes=mins, trades=len(v),
                                  win_rate_pct=(v > 0).mean()*100, mean_net_pct=v.mean(),
                                  median_net_pct=v.median(),
                                  profit_factor=(wins.sum()/abs(losses.sum())) if len(losses) else np.inf,
                                  total_net_pct=v.sum()))
    pd.DataFrame(summaries).to_csv(out / "summary.csv", index=False)
    print(pd.DataFrame(summaries).to_string(index=False))
    print(f"\nWrote {out/'event_study.csv'} and {out/'summary.csv'}")

if __name__ == "__main__":
    main()
