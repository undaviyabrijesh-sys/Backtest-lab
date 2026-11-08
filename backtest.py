"""Prior-day high/low close-break + next-bar trigger, 2R target."""
import argparse
import json
from pathlib import Path
import pandas as pd

def run_backtest(candles, rr=2.0):
    df = candles.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True).dt.tz_convert("Asia/Kolkata")
    df = df.sort_values("datetime").reset_index(drop=True)
    if df.empty:
        return pd.DataFrame()
    df["session"] = df["datetime"].dt.date
    days = df.groupby("session").agg(day_high=("high", "max"), day_low=("low", "min"))
    days["prev_high"] = days["day_high"].shift(1)
    days["prev_low"] = days["day_low"].shift(1)
    df = df.join(days[["prev_high", "prev_low"]], on="session")
    trades = []
    position = None
    for i, bar in df.iterrows():
        last_bar = i == len(df)-1 or df.iloc[i+1]["session"] != bar["session"]
        if position is not None:
            # Conservative: on entry candle, entry must occur before exit.
            # If trigger and stop both touched, assume stop first.
            stop_hit = bar["low"] <= position["stop"] if position["side"] == "long" else bar["high"] >= position["stop"]
            target_hit = bar["high"] >= position["target"] if position["side"] == "long" else bar["low"] <= position["target"]
            if stop_hit or target_hit or last_bar:
                price = position["stop"] if stop_hit else position["target"] if target_hit else bar["close"]
                position.update(exit_time=str(bar["datetime"]), exit_price=float(price),
                                pnl_points=float(price-position["entry"]) * (1 if position["side"] == "long" else -1))
                position["r_multiple"] = position["pnl_points"] / position["risk"]
                trades.append(position)
                position = None
            continue
        if last_bar or pd.isna(bar["prev_high"]):
            continue
        # Only the next bar after a signal can trigger.
        if i == 0 or df.iloc[i-1]["session"] != bar["session"]:
            continue
        signal = df.iloc[i-1]
        levels = (float(bar["prev_high"]), float(bar["prev_low"]))
        for level in levels:
            for side in ("long", "short"):
                valid = (signal["close"] > level and signal["open"] <= level) if side == "long" else (signal["close"] < level and signal["open"] >= level)
                if not valid:
                    continue
                trigger = float(signal["high"] if side == "long" else signal["low"])
                touched = bar["high"] > trigger if side == "long" else bar["low"] < trigger
                if not touched:
                    continue
                entry = max(float(bar["open"]), trigger) if side == "long" else min(float(bar["open"]), trigger)
                stop = float(signal["low"] if side == "long" else signal["high"])
                risk = entry-stop if side == "long" else stop-entry
                if risk <= 0:
                    continue
                target = entry + rr*risk if side == "long" else entry-rr*risk
                position = dict(side=side, level=level, entry_time=str(bar["datetime"]),
                                entry=entry, stop=stop, target=target, risk=risk)
                # Conservative treatment if stop is touched in trigger bar.
                stop_hit = bar["low"] <= stop if side == "long" else bar["high"] >= stop
                target_hit = bar["high"] >= target if side == "long" else bar["low"] <= target
                if stop_hit or target_hit:
                    price = stop if stop_hit else target
                    position.update(exit_time=str(bar["datetime"]), exit_price=float(price),
                                    pnl_points=float(price-entry)*(1 if side == "long" else -1))
                    position["r_multiple"] = position["pnl_points"]/risk
                    trades.append(position)
                    position = None
                break
            if position is not None or (trades and trades[-1]["entry_time"] == str(bar["datetime"])):
                break
    if position is not None:
        bar = df.iloc[-1]
        price = float(bar["close"])
        position.update(exit_time=str(bar["datetime"]), exit_price=price,
                        pnl_points=(price-position["entry"])*(1 if position["side"] == "long" else -1))
        position["r_multiple"] = position["pnl_points"]/position["risk"]
        trades.append(position)
    return pd.DataFrame(trades)

def summary(trades):
    if trades.empty:
        return {"trades": 0, "net_points": 0.0}
    pnl = trades["pnl_points"]
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    equity = pnl.cumsum()
    return {"trades": len(trades), "win_rate_pct": round(100*len(wins)/len(trades), 2),
            "net_points": round(float(pnl.sum()), 2),
            "profit_factor": round(float(wins.sum() / abs(losses.sum())), 3) if len(losses) else None,
            "max_drawdown_points": round(float((equity.cummax().clip(lower=0)-equity).max()), 2)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--rr", type=float, default=2.0)
    a = p.parse_args()
    trades = run_backtest(pd.read_csv(a.input), a.rr)
    output = Path("data/trades.csv")
    output.parent.mkdir(exist_ok=True)
    trades.to_csv(output, index=False)
    print(json.dumps(summary(trades), indent=2))
    print("Trades:", output)

if __name__ == "__main__":
    main()
