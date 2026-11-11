"""Discord webhook delivery using only Python's standard library."""
import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def format_alert(signal):
    side = signal["side"].upper()
    qty = signal.get("quantity")
    if qty:
        qty_text = f"{qty} shares (estimate)"
    elif signal.get("segment") == "index":
        qty_text = "Not applicable — derivative contract selection is not implemented"
    else:
        qty_text = "Not configured — set account capital first"
    fields = [
        {"name": "Instrument", "value": signal["name"] + "\n" + signal["symbol"], "inline": True},
        {"name": "Setup", "value": f"15m Opening Range Breakout / {side}", "inline": True},
        {"name": "Reference entry", "value": f"{signal['entry']:.2f}", "inline": True},
        {"name": "Stop loss", "value": f"{signal['stop']:.2f}", "inline": True},
        {"name": "Target", "value": f"{signal['target']:.2f} ({signal['rr']:.1f}R)", "inline": True},
        {"name": "Risk / unit", "value": f"{signal['risk_points']:.2f}", "inline": True},
        {"name": "Indicative quantity", "value": qty_text, "inline": False},
        {"name": "Confirmation candle", "value": signal["candle_time"], "inline": True},
        {"name": "Alert delay", "value": f"{signal.get('signal_age_minutes', 0):.1f} min after candle close", "inline": True},
    ]
    return {
        "embeds": [{
            "title": f"🇮🇳 INTRADAY SIGNAL — {signal['name']} — {side}",
            "description": (
                "Paper/research alert only. Entry is the breakout confirmation candle close. The system tracks this reference setup and posts a TP/SL/EOD outcome update; it does not confirm your actual fill. "
                + ("This is an underlying-index level only; no futures/options contract has been selected. " if signal.get("segment") == "index" else "")
                + "Verify live price, liquidity, charges and slippage before acting. No order has been placed."
            ),
            "color": 5763719 if side == "LONG" else 15548997,
            "fields": fields,
            "footer": {"text": "India Day Trader • ORB v1 • Educational/research use only"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }


def send_discord(webhook_url, signal, timeout=15):
    if not webhook_url:
        raise ValueError("DISCORD_WEBHOOK_URL is not configured")
    body = json.dumps(format_alert(signal)).encode("utf-8")
    request = Request(webhook_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace")
        raise RuntimeError(f"Discord webhook rejected the alert ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Discord webhook: {exc}") from exc


def format_status_alert(signal, event):
    """Format a paper outcome/status update; not a broker fill confirmation."""
    labels = {
        "STOP_LOSS_HIT": "STOP LOSS HIT",
        "TARGET_HIT": "TARGET HIT",
        "EOD_EXIT": "SESSION FLAT",
        "DATA_GAP": "TRACKING GAP — MANUAL REVIEW",
    }
    title = labels.get(event, event.replace("_", " "))
    pnl = signal.get("pnl_points")
    pnl_text = f"{float(pnl):+.2f} points ({float(signal.get('r_multiple') or 0):+.2f}R)" if pnl is not None else "Not calculated — outcome unresolved"
    exit_text = f"{float(signal['exit_price']):.2f}" if signal.get("exit_price") is not None else "Not available"
    fields = [
        {"name": "Instrument", "value": signal.get("name", signal["symbol"]), "inline": True},
        {"name": "Side", "value": str(signal.get("side", "unknown")).upper(), "inline": True},
        {"name": "Reference entry", "value": f"{float(signal['entry']):.2f}", "inline": True},
        {"name": "Stop / target", "value": f"{float(signal['stop']):.2f} / {float(signal['target']):.2f}", "inline": True},
        {"name": "Exit reference", "value": exit_text, "inline": True},
        {"name": "Paper P&L", "value": pnl_text, "inline": True},
        {"name": "Outcome time", "value": str(signal.get("exit_time", "Not available")), "inline": False},
    ]
    return {
        "embeds": [{
            "title": f"📊 {title} — {signal.get('name', signal['symbol'])}",
            "description": "OHLC-based paper tracking only. This does not confirm that a broker order was placed or filled. Stop is assumed first when stop and target are touched in the same 5-minute candle.",
            "color": 15548997 if event == "STOP_LOSS_HIT" else 5763719,
            "fields": fields,
            "footer": {"text": "India Day Trader • Paper signal tracking • Not execution confirmation"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }


def send_discord_status(webhook_url, signal, event, timeout=15):
    if not webhook_url:
        raise ValueError("DISCORD_WEBHOOK_URL is not configured")
    body = json.dumps(format_status_alert(signal, event)).encode("utf-8")
    request = Request(webhook_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace")
        raise RuntimeError(f"Discord webhook rejected the status update ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach Discord webhook: {exc}") from exc
