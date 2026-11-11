"""Yahoo Finance-backed NSE/BSE 5-minute Opening Range Breakout scanner.

Yahoo intraday data is unofficial and may be delayed or incomplete. Research/paper alerts only.
"""
import argparse
import json
import os
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv

from .discord_alerts import send_discord, send_discord_status
from .yahoo_source import fetch_yahoo_candles
from .risk import plan_trade, position_size
from .tracker import advance_signal

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
    """Return the newest recent ORB signal from completed bars, otherwise None."""
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
    if len(df) < int(settings.get("min_total_bars", 8)) or post_open.empty:
        return None

    or_high = float(opening["high"].max())
    or_low = float(opening["low"].min())
    period = int(settings.get("ema_period", 20))
    ema_series = df["close"].ewm(span=period, adjust=False).mean()
    use_vwap = bool(instrument.get("use_vwap", instrument.get("segment") == "equity"))
    use_volume = bool(instrument.get("use_volume", instrument.get("segment") == "equity"))
    rr = float(settings.get("target_rr", 2.0))
    max_stop_pct = float(settings.get("max_stop_pct", 2.0))
    max_age = int(settings.get("max_signal_age_minutes", 10))
    lookback = int(settings.get("signal_lookback_bars", 2))

    # A 15-minute GitHub Actions cadence can observe the preceding completed bar too.
    for idx in reversed(post_open.index[-lookback:]):
        bar = df.iloc[idx]
        bar_close_time = bar["datetime"] + pd.Timedelta(minutes=5)
        if now - bar_close_time > pd.Timedelta(minutes=max_age):
            continue
        if idx <= 0:
            continue
        prev = df.iloc[idx - 1]
        ema = float(ema_series.iloc[idx])
        vwap = None
        if use_vwap:
            prefix = df.iloc[:idx + 1]
            volume_sum = float(prefix["volume"].clip(lower=0).sum())
            if volume_sum <= 0:
                continue
            typical = (prefix["high"] + prefix["low"] + prefix["close"]) / 3.0
            vwap = float((typical * prefix["volume"].clip(lower=0)).sum() / volume_sum)

        volume_multiple = None
        if use_volume:
            prior_volumes = df.iloc[:idx]["volume"].tail(int(settings.get("volume_lookback", 20)))
            baseline = float(prior_volumes.median()) if not prior_volumes.empty else 0.0
            current_volume = float(bar["volume"])
            if baseline <= 0:
                continue
            volume_multiple = current_volume / baseline
            if volume_multiple < float(settings.get("min_relative_volume", 1.25)):
                continue

        crossed_up = float(prev["close"]) <= or_high and float(bar["close"]) > or_high
        crossed_down = float(prev["close"]) >= or_low and float(bar["close"]) < or_low
        candidates = []
        if crossed_up and float(bar["close"]) > ema and (vwap is None or float(bar["close"]) > vwap):
            candidates.append(("long", float(bar["close"]), float(bar["low"])))
        if crossed_down and float(bar["close"]) < ema and (vwap is None or float(bar["close"]) < vwap):
            candidates.append(("short", float(bar["close"]), float(bar["high"])))
        if not candidates:
            continue

        side, entry, stop = candidates[0]
        plan = plan_trade(side, entry, stop, rr)
        if not plan or plan["risk_points"] / entry * 100.0 > max_stop_pct:
            continue

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
            "signal_timestamp": bar["datetime"].isoformat(),
            "signal_age_minutes": round((now - bar_close_time).total_seconds() / 60.0, 1),
            "signal_date": now.date().isoformat(),
            "strategy": "orb_15m_5m_v1",
        }
    return None

def fetch_symbol_candles(instrument, now):
    """Fetch today's 5-minute bars from Yahoo Finance and normalize to IST."""
    return fetch_yahoo_candles(instrument, now=now)


def load_state(path):
    if not path.exists():
        return {"sent": {}, "open_signals": {}, "closed_signals": []}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            return {"sent": {}, "open_signals": {}, "closed_signals": []}
        state.setdefault("sent", {})
        state.setdefault("open_signals", {})
        state.setdefault("closed_signals", [])
        return state
    except (OSError, json.JSONDecodeError):
        return {"sent": {}, "open_signals": {}, "closed_signals": []}


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temp.replace(path)


def in_market_window(now):
    now = now.astimezone(IST)
    return now.weekday() < 5 and time(9, 30) <= now.time() <= time(16, 0)


def in_entry_window(now):
    now = now.astimezone(IST)
    return now.weekday() < 5 and time(9, 45) <= now.time() <= time(14, 45)


def run_scan(dry_run=False, now=None, watchlist_path=DEFAULT_WATCHLIST, state_path=DEFAULT_STATE):
    load_dotenv()
    now = (now or datetime.now(IST)).astimezone(IST)
    if not in_market_window(now):
        print(f"Outside monitoring window: {now:%Y-%m-%d %H:%M %Z}")
        return []

    data_source = os.getenv("MARKET_DATA_SOURCE", "yahoo").strip().lower()
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if data_source != "yahoo":
        raise SystemExit(f"Unsupported MARKET_DATA_SOURCE={data_source!r}; currently supported: yahoo.")
    if not dry_run and not webhook:
        raise SystemExit("Missing DISCORD_WEBHOOK_URL environment secret.")

    config = load_watchlist(watchlist_path)
    settings = config.get("strategy", {})
    state = load_state(state_path)
    sent = state["sent"]
    open_signals = state["open_signals"]
    closed_signals = state["closed_signals"]
    emitted = []

    for instrument in config.get("instruments", []):
        if not instrument.get("enabled", True):
            continue
        symbol = instrument["symbol"]
        key = f"{now.date().isoformat()}|{symbol}|orb_15m_5m_v1"
        try:
            # An open reference signal takes priority over discovering a new one.
            if symbol in open_signals:
                open_signal = open_signals[symbol]
                if open_signal.get("signal_date") != now.date().isoformat():
                    unresolved = dict(open_signal)
                    unresolved.update({
                        "status": "UNRESOLVED",
                        "outcome": "DATA_GAP",
                        "exit_time": now.isoformat(),
                    })
                    if dry_run:
                        print(json.dumps({"event": "DATA_GAP", "signal": unresolved}, default=str))
                    else:
                        send_discord_status(webhook, unresolved, "DATA_GAP")
                        open_signals.pop(symbol, None)
                        closed_signals.append(unresolved)
                        state["closed_signals"] = closed_signals[-500:]
                        save_state(state_path, state)
                    continue

                bars = fetch_symbol_candles(instrument, now)
                advanced, event = advance_signal(
                    open_signal, bars, now=now,
                    flat_time=settings.get("force_flat_time", "15:20")
                )
                if event:
                    if dry_run:
                        print(json.dumps({"event": event, "signal": advanced}, default=str))
                    else:
                        # Persist closure only after Discord acknowledges the status message,
                        # so a failed webhook is retried on the next scan.
                        send_discord_status(webhook, advanced, event)
                        open_signals.pop(symbol, None)
                        closed_signals.append(advanced)
                        state["closed_signals"] = closed_signals[-500:]
                        save_state(state_path, state)
                elif not dry_run and advanced != open_signal:
                    open_signals[symbol] = advanced
                    save_state(state_path, state)
                continue

            if not in_entry_window(now) or key in sent:
                continue

            bars = fetch_symbol_candles(instrument, now)
            signal = build_orb_signal(bars, instrument, settings, now)
            if not signal:
                continue
            emitted.append(signal)
            if dry_run:
                print(json.dumps(signal, default=str))
                continue

            # Deliver first, then persist: a failed Discord webhook must not silently consume a signal.
            send_discord(webhook, signal)
            signal["last_checked_timestamp"] = signal["signal_timestamp"]
            signal["status"] = "OPEN"
            sent[key] = {
                "sent_at": now.isoformat(),
                "side": signal["side"],
                "entry": signal["entry"],
            }
            open_signals[symbol] = signal
            save_state(state_path, state)
            print(f"Discord alert sent: {symbol} {signal['side']}")
        except Exception as exc:  # isolate one bad symbol; keep scanning the rest
            print(f"ERROR {symbol}: {type(exc).__name__}: {exc}")
    return emitted

def main():
    parser = argparse.ArgumentParser(description="India intraday ORB signal scanner (Yahoo Finance, alerts only)")
    parser.add_argument("--dry-run", action="store_true", help="print signals and do not send Discord alerts")
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    args = parser.parse_args()
    run_scan(args.dry_run, watchlist_path=Path(args.watchlist), state_path=Path(args.state))


if __name__ == "__main__":
    main()
