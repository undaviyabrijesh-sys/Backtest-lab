# India market — day-trader-skill setup adaptation

This change adapts the daily setup concepts documented in [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) for Indian NSE/BSE cash-equity research. The source project is MIT-licensed; the logic here is a clean reimplementation, not copied source code.

## Included research candidates

- 20-trading-session closing-high breakout
- Bull flag: 10-session impulse above 10%, followed by five completed closes within a 5% range
- EMA20 reclaim
- Wilder RSI(14) oversold
- Oversold bounce

All signals use completed daily candles and are tagged `RESEARCH_CANDIDATE`. The module is deliberately separate from the existing 5-minute ORB scanner and Discord alert workflow. The existing ORB already represents the source skill's session-breakout family in an India-specific intraday form; its NYSE-specific clock assumptions are not imported.

## India-specific boundaries

- Lookbacks count trading sessions, not calendar days.
- This first adaptation is long-only and intended for NSE/BSE cash-equity symbols such as `RELIANCE.NS`; it does not create F&O or options trades.
- No entry price, stop-loss, target, quantity, leverage, broker order, or Discord alert is generated.
- Corporate actions, survivorship bias, liquidity, circuit limits, price bands, gaps, and exchange holidays must be handled in a full historical test.
- Yahoo Finance is not an official exchange feed; verify any historical or live candles against a reliable broker/exchange source.

## Validation plan

1. Run offline unit tests in CI.
2. Replay at least 3–5 years of point-in-time NSE equity data, including delisted symbols where available.
3. Model brokerage, STT, GST, exchange charges, stamp duty, slippage, gaps and realistic next-session fills.
4. Use chronological train/validation/test splits and report trade count, expectancy, profit factor, drawdown, exposure, holding time and sector concentration.
5. Compare each setup independently and in combinations; do not optimize on the final holdout.
6. Keep the module research-only until out-of-sample and paper-trading evidence supports promotion.

No profitability claim is made by this adaptation.
