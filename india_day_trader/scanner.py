"""FYERS-backed NSE/BSE 5-minute Opening Range Breakout scanner.

This module emits research alerts only. It deliberately contains no broker order API.
"""
import argparse
import json
import os
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv

from .discord_alerts import send_discord
from .risk import plan_trade, position_size

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parent
DEFAULT_WATCHLIST = ROOT / "watchlist.json"
DEFAULT_STATE = Path(os.getenv("INDIA_TRADER_STATE_PATH", ".cache/india_trader_alert_state.json"))


def load_watchlist(path=DEFAULT_WATCHLIST):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def completed_candles(raw_candles, now, interval_minutes=5):
    """Convert FYERS epoch candles to IST and discard any still-forming candle."""
    if not raw_candles:
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(raw_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    now = now.astimezone(IST)
    df = df[(df["datetime"].dt.date == now.date()) &
            ((df["datetime"] + pd.Timedelta(minutes=interval_minutes)) <= now)]
    return df[["datetime", "open", "high", "low", "close", "volume"]].sort_values("datetime").reset_index(drop=True)


def build_orb_signal(candles, instrument, settings, now=None):
    """Return one ORB signal from completed bars, otherwise None."""
    if candles is None or candles.empty:
        return None
    now = (now or datetime.now(IST)).astimezone(IST)
    df = candles.copy().sort_values("datetime").reset_index(drop=True)
    df["datetime"] = pd.to_datetime(df["datetime"])
    if df["datetime"].dt.tz is None:
        df["datetime"] = df["datetime"].dt.tz_localize(IST)
    else:
        df["datetime"] = df["datetime"].dt.tz_convert(IST)
    df = df[df["datetime"].dt.date == now.date()].reset_index(drop=True)
    if df.empty:
        return None

    market_open = time(9, 15)
    opening_range_end = time(9, 15 + int(settings.get("opening_range_minutes", 15)))
    entry_start = time.fromisoformat(settings.get("entry_start", "09:45"))
    entry_end = time.fromisoformat(settings.get("last_entry", "14:45"))
    if not (entry_start <= now.time() <= entry_end):
        return None

    clock = df["datetime"].dt.time
    opening = df[(clock >= market_open) & (clock < opening_range_end)]
    post_open = df[clock >= opening_range_end]
    if len(opening) < int(settings.get("opening_range_bars", 3)):
        return None
    if len(df) < int(settings.get("min_total_bars", 8)) or len(post_open) < 1:
        return None

    or_high = float(opening["high"].max())
    or_low = float(opening["low"].min())
    bar = post_open.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else None
    if prev is None:
        return None

    period = int(settings.get("ema_period", 20))
    ema = float(df["close"].ewm(span=period, adjust=False).mean().iloc[-1])
    use_vwap = bool(instrument.get("use_vwap", instrument.get("segment") == "equity"))
    use_volume = bool(instrument.get("use_volume", instrument.get("segment") == "equity"))
    vwap = None
    if use_vwap:
        volume_sum = float(df["volume"].clip(lower=0).sum())
        if volume_sum <= 0:
            return None
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        vwap = float((typical * df["volume"].clip(lower=0)).sum() / volume_sum)

    volume_multiple = None
    if use_volume:
        prior_volumes = df.iloc[:-1]["volume"].tail(int(settings.get("volume_lookback", 20)))
        baseline = float(prior_volumes.median()) if not prior_volumes.empty else 0.0
        current_volume = float(bar["volume"])
        if baseline <= 0:
            return None
        volume_multiple = current_volume / baseline
        if volume_multiple < float(settings.get("min_relative_volume", 1.25)):
            return None

    crossed_up = float(prev["close"]) <= or_high and float(bar["close"]) > or_high
    crossed_down = float(prev["close"]) >= or_low and float(bar["close"]) < or_low
    rr = float(settings.get("target_rr", 2.0))
    candidates = []
    if crossed_up and float(bar["close"]) > ema and (vwap is None or float(bar["close"]) > vwap):
        candidates.append(("long", float(bar["close"]), float(bar["low"])))
    if crossed_down and float(bar["close"]) < ema and (vwap is None or float(bar["close"]) < vwap):
        candidates.append(("short", float(bar["close"]), float(bar["high"])))
    if not candidates:
        return None

    side, entry, stop = candidates[0]
    plan = plan_trade(side, entry, stop, rr)
    if not plan:
        return None
    max_stop_pct = float(settings.get("max_stop_pct", 2.0))
    if plan["risk_points"] / entry * 100.0 > max_stop_pct:
        return None

    capital = settings.get("account_capital_inr")
    qty = None
    if instrument.get("segment") == "equity" and capital:
        qty = position_size(entry, stop, capital,
                            settings.get("risk_per_trade_pct", 0.5),
                            settings.get("max_exposure_pct", 20.0))

    return {
        "symbol": instrument["symbol"],
        "name": instrument.get("name", instrument["symbol"]),
        "segment": instrument.get("segment", "equity"),
        **plan,
        "quantity": qty,
        "or_high": or_high,
        "or_low": or_low,
        "ema": ema,
        "vwap": vwap,
        "relative_volume": volume_multiple,
        "candle_time": bar["datetime"].strftime("%Y-%m-%d %H:%M %Z"),
        "signal_date": now.date().isoformat(),
        "strategy": "orb_15m_5m_v1",
    }


def fetch_symbol_candles(fyers, symbol, today):
    response = fyers.history(data={
        "symbol": symbol,
        "resolution": "5",
        "date_format": "1",
        "range_from": today.isoformat(),
        "range_to": today.isoformat(),
        "cont_flag": "1",
    })
    if not isinstance(response, dict) or response.get("s") != "ok":
        reason = response.get("message", response.get("code", "unknown FYERS error")) if isinstance(response, dict) else "invalid response"
        raise RuntimeError(f"FYERS history failed for {symbol}: {reason}")
    return response.get("candles", [])


def load_state(path):
    if not path.exists():
        return {"sent": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state.get("sent"), dict):
            return {"sent": {}}
        return state
    except (OSError, json.JSONDecodeError):
        return {"sent": {}}


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temp.replace(path)


def in_market_window(now):
    now = now.astimezone(IST)
    return now.weekday() < 5 and time(9, 45) <= now.time() <= time(14, 45)


def run_scan(dry_run=False, now=None, watchlist_path=DEFAULT_WATCHLIST, state_path=DEFAULT_STATE):
    load_dotenv()
    now = (now or datetime.now(IST)).astimezone(IST)
    if not in_market_window(now):
        print(f"Outside signal window: {now:%Y-%m-%d %H:%M %Z}")
        return []

    client_id = os.getenv("FYERS_CLIENT_ID", "").strip()
    access_token = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not client_id or not access_token:
        raise SystemExit("Missing FYERS_CLIENT_ID or FYERS_ACCESS_TOKEN environment secret.")
    if not dry_run and not webhook:
        raise SystemExit("Missing DISCORD_WEBHOOK_URL environment secret.")

    from fyers_apiv3 import fyersModel
    fyers = fyersModel.FyersModel(client_id=client_id, token=access_token, is_async=False, log_path="")
    config = load_watchlist(watchlist_path)
    settings = config.get("strategy", {})
    state = load_state(state_path)
    sent = state["sent"]
    emitted = []

    for instrument in config.get("instruments", []):
        if not instrument.get("enabled", True):
            continue
        symbol = instrument["symbol"]
        key = f"{now.date().isoformat()}|{symbol}|orb_15m_5m_v1"
        if key in sent:
            continue
        try:
            raw = fetch_symbol_candles(fyers, symbol, now.date())
            bars = completed_candles(raw, now, 5)
            signal = build_orb_signal(bars, instrument, settings, now)
            if not signal:
                continue
            emitted.append(signal)
            if dry_run:
                print(json.dumps(signal, default=str))
                continue
            send_discord(webhook, signal)
            sent[key] = {"sent_at": now.isoformat(), "side": signal["side"], "entry": signal["entry"]}
            save_state(state_path, state)
            print(f"Discord alert sent: {symbol} {signal['side']}")
        except Exception as exc:  # isolate one bad symbol; keep scanning the rest
            print(f"ERROR {symbol}: {type(exc).__name__}: {exc}")
    return emitted


def main():
    parser = argparse.ArgumentParser(description="India intraday ORB signal scanner (alerts only)")
    parser.add_argument("--dry-run", action="store_true", help="print signals and do not send Discord alerts")
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    args = parser.parse_args()
    run_scan(args.dry_run, watchlist_path=Path(args.watchlist), state_path=Path(args.state))


if __name__ == "__main__":
    main()
