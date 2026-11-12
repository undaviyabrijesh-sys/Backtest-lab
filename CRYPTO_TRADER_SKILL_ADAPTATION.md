# Crypto intraday setup research — day-trader-skill adaptation

Adapts five setup concepts from Jakeschincariol/day-trader-skill for Binance USD-M perpetual markets.

## Intraday rules
Default timeframe is 15 minutes (configurable to 5m, 15m, 30m or 1h):
- 20-bar close breakout above the preceding 20 closes.
- Bull flag: at least 2% rise across 10 bars, followed by five closes in a range no wider than 1.5%.
- EMA20 reclaim.
- Wilder RSI(14) below 30.
- Oversold bounce: prior RSI below 30 and latest completed close higher.

Only completed bars are scanned. These are unoptimized starting parameters. The scanner selects the top 10 eligible USDT perpetuals by 24h quote volume.

## Boundaries
Research candidates only; long-side; no entry, stop, target, leverage, sizing, Discord or execution. Crypto is 24/7, so no arbitrary opening-range clock is imposed. Before promotion, backtest fees, funding, spread, slippage, liquidation risk, same-bar ambiguity and out-of-sample performance.

## Run
```bash
python -m crypto_trader.scanner --limit 10 --interval 15m
python -m pytest -q
```
No profitability claim is made.