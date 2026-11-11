"""Discord webhook delivery using only Python's standard library."""
import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def format_alert(signal):
    side = signal["side"].upper()
    qty = signal.get("quantity")
    qty_text = f"{qty} shares (estimate)" if qty else "Not configured — set account capital first"
    fields = [
        {"name": "Instrument", "value": signal["name"] + "\n" + signal["symbol"], "inline": True},
        {"name": "Setup", "value": f"15m Opening Range Breakout / {side}", "inline": True},
        {"name": "Reference entry", "value": f"{signal['entry']:.2f}", "inline": True},
        {"name": "Stop loss", "value": f"{signal['stop']:.2f}", "inline": True},
        {"name": "Target", "value": f"{signal['target']:.2f} ({signal['rr']:.1f}R)", "inline": True},
        {"name": "Risk / share", "value": f"{signal['risk_points']:.2f}", "inline": True},
        {"name": "Indicative quantity", "value": qty_text, "inline": False},
        {"name": "Confirmation candle", "value": signal["candle_time"], "inline": False},
    ]
    return {
        "embeds": [{
            "title": f"🇮🇳 INTRADAY SIGNAL — {signal['name']} — {side}",
            "description": (
                "Paper/research alert only. Entry is the last completed 5-minute candle close, "
                "not a guaranteed fill. Verify live price, liquidity, charges and slippage before acting. "
                "No order has been placed."
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
