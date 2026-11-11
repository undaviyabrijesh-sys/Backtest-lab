from india_day_trader.discord_alerts import format_alert, format_status_alert


def base_signal(segment="equity"):
    return {
        "symbol": "NSE:TEST-EQ",
        "name": "TEST",
        "segment": segment,
        "side": "long",
        "entry": 100.0,
        "stop": 99.0,
        "target": 102.0,
        "risk_points": 1.0,
        "rr": 2.0,
        "candle_time": "2026-11-10 10:00 IST",
        "signal_age_minutes": 0.0,
    }


def test_index_alert_discloses_no_derivative_contract_mapping():
    payload = format_alert(base_signal("index"))
    embed = payload["embeds"][0]
    assert "underlying-index level only" in embed["description"]
    quantity = next(x for x in embed["fields"] if x["name"] == "Indicative quantity")
    assert "derivative contract" in quantity["value"]


def test_equity_alert_has_reference_entry_and_stop():
    payload = format_alert(base_signal("equity"))
    fields = {x["name"]: x["value"] for x in payload["embeds"][0]["fields"]}
    assert fields["Reference entry"] == "100.00"
    assert fields["Stop loss"] == "99.00"


def test_status_alert_includes_paper_outcome_not_fill_confirmation():
    signal = {**base_signal(), "exit_price": 99.0, "pnl_points": -1.0,
              "r_multiple": -1.0, "exit_time": "2026-11-10 10:05 IST"}
    payload = format_status_alert(signal, "STOP_LOSS_HIT")
    embed = payload["embeds"][0]
    assert "STOP LOSS HIT" in embed["title"]
    assert "does not confirm" in embed["description"]
    pnl = next(x for x in embed["fields"] if x["name"] == "Paper P&L")
    assert "-1.00 points" in pnl["value"]
