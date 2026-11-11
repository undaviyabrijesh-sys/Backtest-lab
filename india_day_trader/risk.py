"""INR risk and share-quantity calculations. No order placement lives here."""
from math import floor


def position_size(entry, stop, capital_inr, risk_pct=0.5, max_exposure_pct=20.0):
    """Return a conservative whole-share quantity, or None if inputs are unusable."""
    values = (entry, stop, capital_inr, risk_pct, max_exposure_pct)
    if any(value is None for value in values):
        return None
    entry, stop, capital_inr, risk_pct, max_exposure_pct = map(float, values)
    per_share_risk = abs(entry - stop)
    if entry <= 0 or per_share_risk <= 0 or capital_inr <= 0 or risk_pct <= 0:
        return None
    risk_budget = capital_inr * risk_pct / 100.0
    exposure_cap = capital_inr * max_exposure_pct / 100.0
    qty_by_risk = floor(risk_budget / per_share_risk)
    qty_by_exposure = floor(exposure_cap / entry)
    quantity = min(qty_by_risk, qty_by_exposure)
    return quantity if quantity >= 1 else None


def plan_trade(side, entry, stop, rr=2.0):
    """Build an indicative bracket plan from a completed candle close."""
    entry, stop, rr = float(entry), float(stop), float(rr)
    if rr <= 0:
        raise ValueError("rr must be positive")
    if side == "long":
        risk = entry - stop
        if risk <= 0:
            return None
        target = entry + rr * risk
    elif side == "short":
        risk = stop - entry
        if risk <= 0:
            return None
        target = entry - rr * risk
    else:
        raise ValueError("side must be 'long' or 'short'")
    return {"side": side, "entry": entry, "stop": stop, "target": target,
            "risk_points": risk, "rr": rr}
