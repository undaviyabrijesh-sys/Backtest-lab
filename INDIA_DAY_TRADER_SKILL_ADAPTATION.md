# India intraday setup research — day-trader-skill adaptation

Adapts five setup concepts for NSE/BSE cash equities and index underlyings.

## Intraday rules
Default timeframe is 5-minute completed candles, restricted to the latest regular session:
- 20-bar close breakout above the preceding 20 closes.
- Bull flag: at least 0.8% rise across 10 bars, followed by five closes in a range no wider than 0.6%.
- EMA20 reclaim.
- Wilder RSI(14) below 30.
- Oversold bounce.

Thresholds are unoptimized research starting points. NIFTY 50, BANK NIFTY and SENSEX are classified as INDIA_INDEX; cash equities as INDIA_CASH_EQUITY.

## Boundaries
Long-side research candidates only. No entry/SL/TP, quantity, leverage, broker execution or Discord alerts. Session boundaries prevent overnight gaps being mixed into patterns. Index-underlying signals are not options trades; options require historical contract, expiry, strike, premium, spread and lot-size data plus realistic execution modelling.

Backtests must include Indian transaction taxes/fees, slippage, gaps, circuit limits, holidays, corporate actions and survivorship bias. Yahoo intraday data is unofficial and may be incomplete. No profitability claim is made.