"""Cost-aware historical backtester for the India 15m ORB / 5m close-confirmation setup.

Research tool only. It models the underlying instrument, not option-premium execution.
"""
import argparse
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

IST = ZoneInfo("Asia/Kolkata")
REQUIRED = {"datetime", "open", "high", "low", "close", "volume"}


def normalize_candles(candles):
    missing = REQUIRED.difference(candles.columns)
    if missing:
        raise ValueError(f"Missing candle columns: {sorted(missing)}")
    df = candles.copy()
    parsed = pd.to_datetime(df["datetime"])
    if parsed.dt.tz is None:
        parsed = parsed.dt.tz_localize(IST)
    else:
        parsed = parsed.dt.tz_convert(IST)
    df["datetime"] = parsed
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["datetime", "open", "high", "low", "close"])
    df = df.sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)
    if (df["high"] < df["low"]).any():
        raise ValueError("Found candle high below candle low")
    if (df["volume"].dropna() < 0).any():
        raise ValueError("Found negative volume")
    return df


def _cost_adjusted_fills(side, raw_entry, raw_exit, slippage_bps):
    slip = float(slippage_bps) / 10000.0
    if side == "long":
        return raw_entry * (1 + slip), raw_exit * (1 - slip)
    return raw_entry * (1 - slip), raw_exit * (1 + slip)


def _exit_trade(session, rows, start_idx, side, entry, stop, target,
                cost_bps_per_side, slippage_bps_per_side, signal_time):
    """Walk forward from entry bar; if both levels touch, stop is assumed first."""
    exit_price = None
    exit_reason = None
    exit_time = None
    for j in range(start_idx, len(rows)):
        bar = rows.iloc[j]
        is_last = j == len(rows) - 1
        if side == "long":
            stop_hit = float(bar["low"]) <= stop
            target_hit = float(bar["high"]) >= target
        else:
            stop_hit = float(bar["high"]) >= stop
            target_hit = float(bar["low"]) <= target

        if stop_hit:
            # Stops fill at the worse of the stop and an opening gap.
            open_price = float(bar["open"])
            exit_price = min(stop, open_price) if side == "long" else max(stop, open_price)
            exit_reason = "stop"
        elif target_hit:
            # Conservative limit-fill assumption: no price improvement through a gap.
            exit_price = target
            exit_reason = "target"
        elif is_last:
            exit_price = float(bar["close"])
            exit_reason = "eod"
        else:
            continue
        exit_time = bar["datetime"]
        break

    if exit_price is None:
        return None
    fill_entry, fill_exit = _cost_adjusted_fills(
        side, entry, exit_price, slippage_bps_per_side
    )
    direction = 1.0 if side == "long" else -1.0
    gross_points = (exit_price - entry) * direction
    slippage_points = (entry - fill_entry) * direction + (fill_exit - exit_price) * direction
    transaction_cost_points = (abs(fill_entry) + abs(fill_exit)) * float(cost_bps_per_side) / 10000.0
    net_points = gross_points - slippage_points - transaction_cost_points
    initial_risk = abs(entry - stop)
    return {
        "session": str(session),
        "side": side,
        "signal_time": str(signal_time),
        "entry_time": str(rows.iloc[start_idx]["datetime"]),
        "exit_time": str(exit_time),
        "entry": float(entry),
        "stop": float(stop),
        "target": float(target),
        "exit": float(exit_price),
        "exit_reason": exit_reason,
        "risk_points": float(initial_risk),
        "gross_points": float(gross_points),
        "slippage_points": float(slippage_points),
        "transaction_cost_points": float(transaction_cost_points),
        "net_points": float(net_points),
        "gross_r": float(gross_points / initial_risk),
        "net_r": float(net_points / initial_risk),
        "bars_held": int(j - start_idx + 1),
    }


def run_backtest(candles, rr=2.0, cost_bps_per_side=10.0,
                 slippage_bps_per_side=2.0, opening_range_minutes=15,
                 ema_period=20, use_vwap=False, use_volume=False,
                 min_relative_volume=1.25, volume_lookback=20,
                 max_stop_pct=2.0, max_trades_per_session=1):
    """Run one-or-more sessions. Entry is next completed bar open after confirmation."""
    if rr <= 0 or cost_bps_per_side < 0 or slippage_bps_per_side < 0:
        raise ValueError("RR must be positive and cost/slippage cannot be negative")
    if max_trades_per_session < 1:
        raise ValueError("max_trades_per_session must be at least 1")
    df = normalize_candles(candles)
    if df.empty:
        return pd.DataFrame()
    df["session"] = df["datetime"].dt.date
    trades = []

    for session, day in df.groupby("session", sort=True):
        day = day.reset_index(drop=True)
        local_time = day["datetime"].dt.time
        opening_end_minutes = 15 + int(opening_range_minutes)
        end_hour, end_minute = divmod(opening_end_minutes, 60)
        from datetime import time
        opening = day[(local_time >= time(9, 15)) &
                      (local_time < time(end_hour, end_minute))]
        expected_or_bars = max(1, int(opening_range_minutes) // 5)
        if len(opening) < expected_or_bars:
            continue
        or_high = float(opening["high"].max())
        or_low = float(opening["low"].min())
        post_indices = day.index[local_time >= time(end_hour, end_minute)].tolist()
        if len(post_indices) < 2:
            continue

        day["ema"] = day["close"].ewm(span=int(ema_period), adjust=False).mean()
        trades_today = 0
        idx = post_indices[0]
        while idx < len(day) - 1 and trades_today < max_trades_per_session:
            signal = day.iloc[idx]
            previous = day.iloc[idx - 1]
            signal_time = signal["datetime"]
            close = float(signal["close"])
            ema = float(signal["ema"])
            vwap = None
            if use_vwap:
                prefix = day.iloc[:idx + 1]
                vol = prefix["volume"].clip(lower=0).fillna(0)
                total_vol = float(vol.sum())
                if total_vol <= 0:
                    idx += 1
                    continue
                typical = (prefix["high"] + prefix["low"] + prefix["close"]) / 3.0
                vwap = float((typical * vol).sum() / total_vol)
            if use_volume:
                prior_volume = day.iloc[:idx]["volume"].tail(int(volume_lookback)).dropna()
                baseline = float(prior_volume.median()) if not prior_volume.empty else 0.0
                current_volume = float(signal["volume"]) if pd.notna(signal["volume"]) else 0.0
                if baseline <= 0 or current_volume / baseline < min_relative_volume:
                    idx += 1
                    continue

            side = None
            if (float(previous["close"]) <= or_high and close > or_high
                    and close > ema and (vwap is None or close > vwap)):
                side = "long"
                stop = float(signal["low"])
            elif (float(previous["close"]) >= or_low and close < or_low
                    and close < ema and (vwap is None or close < vwap)):
                side = "short"
                stop = float(signal["high"])

            if side is None:
                idx += 1
                continue

            entry_bar_idx = idx + 1
            raw_entry = float(day.iloc[entry_bar_idx]["open"])
            risk = raw_entry - stop if side == "long" else stop - raw_entry
            if risk <= 0 or raw_entry <= 0 or risk / raw_entry * 100.0 > max_stop_pct:
                idx += 1
                continue
            target = raw_entry + rr * risk if side == "long" else raw_entry - rr * risk

            trade = _exit_trade(
                session, day, entry_bar_idx, side, raw_entry, stop, target,
                cost_bps_per_side, slippage_bps_per_side, signal_time
            )
            if trade:
                trades.append(trade)
                trades_today += 1
                # No overlapping positions. Resume after the exit bar.
                exit_idx = day.index[day["datetime"] == pd.Timestamp(trade["exit_time"])].tolist()
                idx = (exit_idx[0] + 1) if exit_idx else entry_bar_idx + 1
            else:
                idx += 1

    return pd.DataFrame(trades)


def summarize(trades):
    if trades is None or trades.empty:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0,
            "net_points": 0.0, "profit_factor": None, "expectancy_net_r": 0.0,
            "max_drawdown_points": 0.0, "max_consecutive_losses": 0,
            "total_cost_points": 0.0,
        }
    ordered = trades.sort_values(["session", "entry_time"]).reset_index(drop=True)
    net = ordered["net_points"].astype(float)
    wins = net[net > 0]
    losses = net[net < 0]
    positive_sum = float(wins.sum())
    negative_sum = abs(float(losses.sum()))
    equity = net.cumsum()
    peaks = equity.cummax().clip(lower=0)
    drawdown = peaks - equity
    max_consecutive_losses = current_losses = 0
    for value in net:
        if value < 0:
            current_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, current_losses)
        else:
            current_losses = 0

    monthly = {}
    for _, trade in ordered.iterrows():
        month = str(trade["entry_time"])[:7]
        monthly[month] = monthly.get(month, 0.0) + float(trade["net_points"])
    return {
        "trades": int(len(ordered)),
        "wins": int((net > 0).sum()),
        "losses": int((net < 0).sum()),
        "breakeven": int((net == 0).sum()),
        "win_rate_pct": round(100.0 * float((net > 0).mean()), 2),
        "gross_points": round(float(ordered["gross_points"].sum()), 4),
        "total_cost_points": round(float(
            ordered["slippage_points"].sum() + ordered["transaction_cost_points"].sum()
        ), 4),
        "net_points": round(float(net.sum()), 4),
        "profit_factor": round(positive_sum / negative_sum, 4) if negative_sum else None,
        "expectancy_net_r": round(float(ordered["net_r"].mean()), 4),
        "average_net_r": round(float(ordered["net_r"].mean()), 4),
        "max_drawdown_points": round(float(drawdown.max()), 4),
        "max_consecutive_losses": int(max_consecutive_losses),
        "monthly_net_points": {k: round(v, 4) for k, v in sorted(monthly.items())},
    }


def main():
    parser = argparse.ArgumentParser(description="Cost-aware India ORB 5-minute backtest")
    parser.add_argument("--input", required=True, help="CSV with datetime, open, high, low, close, volume")
    parser.add_argument("--output", default="data/india_orb_trades.csv")
    parser.add_argument("--summary", default="data/india_orb_summary.json")
    parser.add_argument("--rr", type=float, default=2.0)
    parser.add_argument("--cost-bps-per-side", type=float, default=10.0,
                        help="Effective all-in cost assumption per side, in basis points")
    parser.add_argument("--slippage-bps-per-side", type=float, default=2.0,
                        help="Adverse slippage assumption per side, in basis points")
    parser.add_argument("--use-vwap", action="store_true")
    parser.add_argument("--use-volume", action="store_true")
    parser.add_argument("--ema-period", type=int, default=20)
    parser.add_argument("--max-stop-pct", type=float, default=2.0)
    args = parser.parse_args()

    trades = run_backtest(
        pd.read_csv(args.input), rr=args.rr,
        cost_bps_per_side=args.cost_bps_per_side,
        slippage_bps_per_side=args.slippage_bps_per_side,
        use_vwap=args.use_vwap, use_volume=args.use_volume,
        ema_period=args.ema_period, max_stop_pct=args.max_stop_pct,
    )
    out = Path(args.output)
    summary_path = Path(args.summary)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    trades.to_csv(out, index=False)
    report = summarize(trades)
    summary_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Trades saved: {out}")
    print(f"Summary saved: {summary_path}")


if __name__ == "__main__":
    main()
