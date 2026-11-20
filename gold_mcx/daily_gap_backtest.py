#!/usr/bin/env python3
"""Daily MCX open-gap attribution and same-session directional event study.

This is a daily-bar research proxy, not an intraday backtest or arbitrage model.
"""
from __future__ import annotations
import argparse
import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

IST, NY = ZoneInfo("Asia/Kolkata"), ZoneInfo("America/New_York")


def mcx_close_time(d: date) -> time:
    # MCX bullion session follows US daylight-saving close convention.
    noon_ny = datetime.combine(d, time(12, 0), NY)
    return time(23, 30) if noon_ny.dst().total_seconds() else time(23, 55)


def metrics(returns: pd.Series) -> dict:
    r = pd.to_numeric(returns, errors="coerce").dropna()
    if r.empty:
        return {k: np.nan for k in ("trades", "win_rate_pct", "mean_net_pct",
               "median_net_pct", "profit_factor", "total_net_pct", "compounded_net_pct",
               "max_drawdown_pct")}
    wins, losses = r[r > 0], r[r < 0]
    equity = (1 + r / 100).cumprod()
    drawdown = (equity / equity.cummax() - 1).min() * 100
    return {"trades": int(len(r)), "win_rate_pct": float((r > 0).mean() * 100),
            "mean_net_pct": float(r.mean()), "median_net_pct": float(r.median()),
            "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) else float("inf"),
            "total_net_pct": float(r.sum()), "compounded_net_pct": float((equity.iloc[-1] - 1) * 100),
            "max_drawdown_pct": float(drawdown)}


def load_global(path: str) -> dict[str, pd.DataFrame]:
    g = pd.read_csv(path)
    g["timestamp"] = pd.to_datetime(g["timestamp"], utc=True, errors="coerce")
    g["close"] = pd.to_numeric(g["close"], errors="coerce")
    g = g.dropna(subset=["timestamp", "close"]).sort_values("timestamp")
    out = {}
    for instrument, part in g.groupby("instrument"):
        part = part.copy()
        part["end_utc"] = part.timestamp + pd.Timedelta(hours=1)
        out[instrument] = part.reset_index(drop=True)
    return out


def completed_close_asof(series: pd.DataFrame, when_ist: pd.Timestamp, max_stale_min: int):
    instant = when_ist.tz_convert("UTC")
    completed = series[series.end_utc <= instant]
    if completed.empty:
        return None
    row = completed.iloc[-1]
    age_minutes = (instant - row.end_utc).total_seconds() / 60
    return float(row.close) if age_minutes <= max_stale_min and row.close > 0 else None


def build_events(mcx_path: str, global_path: str, max_stale_min: int = 120) -> pd.DataFrame:
    m = pd.read_csv(mcx_path)
    m["date"] = pd.to_datetime(m["date"], errors="coerce").dt.date
    for col in ("open", "high", "low", "close", "prev_close", "volume"):
        m[col] = pd.to_numeric(m[col], errors="coerce")
    m["instrument"] = m.instrument.astype(str).str.upper().str.strip()
    m = m.dropna(subset=["date", "instrument", "expiry"])
    # Ignore MCX no-trade / carried-forward rows, but retain them in source CSV audit.
    m = m[(m.open > 0) & (m.close > 0) & (m.prev_close > 0) & (m.volume > 0)]
    globals_ = load_global(global_path)
    if not {"GOLD_PROXY", "USDINR"}.issubset(globals_):
        raise ValueError("Expected GOLD_PROXY and USDINR rows in global hourly file")

    results = []
    for instrument, all_rows in m.groupby("instrument"):
        all_rows = all_rows.sort_values(["date", "expiry"])
        leaders = (all_rows.groupby(["date", "expiry"], as_index=False).volume.sum()
                   .sort_values(["date", "volume", "expiry"], ascending=[True, False, True])
                   .drop_duplicates("date").set_index("date")["expiry"].to_dict())
        dates = sorted(all_rows.date.unique())
        for idx in range(1, len(dates)):
            prior_date, current_date = dates[idx - 1], dates[idx]
            expiry = leaders.get(prior_date)
            if not expiry:
                continue
            today = all_rows[(all_rows.date == current_date) & (all_rows.expiry == expiry)]
            prior = all_rows[(all_rows.date == prior_date) & (all_rows.expiry == expiry)]
            if today.empty or prior.empty:
                continue
            cur, prev = today.iloc[0], prior.iloc[-1]
            # PreviousClose is same-contract-specific. Only fallback to prior same-contract close.
            previous_close = float(cur.prev_close) if cur.prev_close > 0 else float(prev.close)
            if previous_close <= 0:
                continue
            gap = float(cur.open) / previous_close - 1
            prior_close_time = pd.Timestamp(datetime.combine(prior_date, mcx_close_time(prior_date)), tz=IST)
            current_open_time = pd.Timestamp(datetime.combine(current_date, time(9, 0)), tz=IST)
            gold0 = completed_close_asof(globals_["GOLD_PROXY"], prior_close_time, max_stale_min)
            gold1 = completed_close_asof(globals_["GOLD_PROXY"], current_open_time, max_stale_min)
            fx0 = completed_close_asof(globals_["USDINR"], prior_close_time, max_stale_min)
            fx1 = completed_close_asof(globals_["USDINR"], current_open_time, max_stale_min)
            if any(v is None for v in (gold0, gold1, fx0, fx1)):
                continue
            gold_return, fx_return = gold1 / gold0 - 1, fx1 / fx0 - 1
            fair_return = (1 + gold_return) * (1 + fx_return) - 1
            residual = fair_return - gap
            open_to_close = float(cur.close) / float(cur.open) - 1
            results.append({
                "date": current_date.isoformat(), "instrument": instrument, "expiry": str(expiry),
                "prev_close": previous_close, "open": float(cur.open), "high": float(cur.high),
                "low": float(cur.low), "close": float(cur.close),
                "open_gap_pct": gap * 100, "comex_gold_proxy_pct": gold_return * 100,
                "usdinr_pct": fx_return * 100, "synthetic_fair_return_pct": fair_return * 100,
                "opening_residual_pct": residual * 100, "open_to_close_pct": open_to_close * 100,
                "fair_value_side": "LONG" if residual > 0 else "SHORT",
                "gap_fade_side": "SHORT" if gap > 0 else "LONG",
                "gap_momentum_side": "LONG" if gap > 0 else "SHORT",
            })
    events = pd.DataFrame(results)
    if events.empty:
        raise RuntimeError("No aligned events. Check MCX rows, Yahoo coverage and max stale threshold.")
    return events.sort_values(["date", "instrument"]).reset_index(drop=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mcx", default="data/daily/mcx_gold_goldm_daily.csv")
    p.add_argument("--global", dest="global_path", default="data/daily/global_hourly.csv")
    p.add_argument("--out", default="data/results/daily_gap")
    p.add_argument("--max-stale-minutes", type=int, default=120)
    a = p.parse_args()
    output = Path(a.out)
    output.mkdir(parents=True, exist_ok=True)
    events = build_events(a.mcx, a.global_path, a.max_stale_minutes)
    events.to_csv(output / "daily_events.csv", index=False)

    # Date-level split shared by GOLD and GOLDM; no strategy parameters are fitted.
    dates = sorted(events.date.unique())
    first, second = int(len(dates) * .6), int(len(dates) * .8)
    split = {d: ("train" if i < first else "validation" if i < second else "holdout")
             for i, d in enumerate(dates)}
    events["split"] = events.date.map(split)
    summaries = []
    for instrument, group in events.groupby("instrument"):
        for segment in ("all", "train", "validation", "holdout"):
            sample = group if segment == "all" else group[group.split == segment]
            for strategy, col in (("fair_value_residual", "fair_value_side"),
                                  ("gap_fade", "gap_fade_side"),
                                  ("gap_momentum", "gap_momentum_side")):
                direction = np.where(sample[col].eq("LONG"), 1.0, -1.0)
                gross = direction * sample.open_to_close_pct.to_numpy()
                for cost_bps in (8.0, 15.0, 25.0, 40.0):
                    net = gross - cost_bps / 100.0
                    row = {"instrument": instrument, "segment": segment, "strategy": strategy,
                           "roundtrip_cost_bps": cost_bps}
                    row.update(metrics(pd.Series(net)))
                    summaries.append(row)
    summary = pd.DataFrame(summaries)
    summary.to_csv(output / "summary.csv", index=False)

    attribution = []
    for instrument, group in events.groupby("instrument"):
        attribution.append({
            "instrument": instrument, "events": len(group),
            "corr_open_gap_vs_synthetic_pct": group.open_gap_pct.corr(group.synthetic_fair_return_pct),
            "corr_open_gap_vs_comex_pct": group.open_gap_pct.corr(group.comex_gold_proxy_pct),
            "corr_open_gap_vs_usdinr_pct": group.open_gap_pct.corr(group.usdinr_pct),
            "mean_abs_residual_pct": group.opening_residual_pct.abs().mean(),
        })
    attribution_df = pd.DataFrame(attribution)
    attribution_df.to_csv(output / "attribution.csv", index=False)
    manifest = {
        "study": "MCX daily opening-gap attribution and same-session open-to-close direction",
        "events": len(events), "start": events.date.min(), "end": events.date.max(),
        "instruments": sorted(events.instrument.unique().tolist()),
        "split": "chronological 60% train / 20% validation / 20% holdout by event date",
        "execution": "daily MCX open to close; not a 09:00 guaranteed fill",
        "proxy_series": {"gold": "Yahoo GC=F COMEX continuous futures; not XAUUSD spot",
                         "fx": "Yahoo INR=X USD/INR spot; not USDINR futures"},
        "cost_sensitivity_bps": [8, 15, 25, 40],
        "limitations": [
            "Daily data cannot test 15/30/60/120-minute exits, intrabar stops or executable spreads.",
            "Gold proxy futures basis and roll effects can contaminate the synthetic fair return.",
            "USD/INR spot proxy is not the traded currency futures series.",
            "Costs are sensitivities, not broker-specific all-in costs.",
            "Not risk-free arbitrage; MCX is closed during much of the global repricing window.",
        ],
    }
    (output / "study_manifest.json").write_text(json.dumps(manifest, indent=2))
    print("ATTRIBUTION")
    print(attribution_df.to_string(index=False))
    print("\nHOLDOUT RESULTS (25 bps round-trip sensitivity)")
    print(summary[(summary.segment == "holdout") & (summary.roundtrip_cost_bps == 25)]
          .to_string(index=False))
    print(f"\nWrote results to {output}")


if __name__ == "__main__":
    main()
