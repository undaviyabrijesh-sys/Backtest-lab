# Crypto setup research — adaptation of day-trader-skill

This research module takes setup concepts from [Jakeschincariol/day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill), an MIT-licensed collection of modular trading skills. We are adapting the documented setup rules, not importing its US-equity session assumptions or broker-execution workflow.

## What is being adapted

The source `trader-scanner` documents five daily close-based candidates:
- 20-day closing-high breakout
- bull flag: a >10% impulse followed by a five-bar consolidation within a 5% range
- reclaim of the 20-day EMA
- RSI(14) oversold
- oversold bounce

The new `crypto_trader.skill_setups` module reimplements these as long-side research candidates using completed Binance USD-M perpetual daily candles. The scanner dynamically selects the top 10 eligible USDT-margined perpetuals by 24-hour quote volume.

## What is deliberately not copied

The source skill's opening-range breakout is based on the NYSE 09:30 open and the first 15 minutes. Crypto trades 24/7 and has no equivalent universal opening bell, so that rule is not transplanted using an arbitrary UTC boundary. The source skill's entry, exit, time-machine and risk-management stages are useful workflow patterns, but stock-specific assumptions (NYSE hours, whole-share sizing, Alpaca order tickets, US equity symbols) need separate crypto implementations and validation.

## Current boundary

- Discovery only: candidates are labelled `RESEARCH_CANDIDATE`.
- Long-side only in this first adaptation, matching the source skill's documented entry timer.
- No entry, stop, target, leverage, position size, Discord alert, or order is generated.
- No candidate is promoted to alerts until a separate historical backtest includes fees, funding, spread, slippage, stop/target same-candle ambiguity and out-of-sample validation.
- Binance public USD-M Futures endpoints are used read-only; no API key is required.

## Run

```bash
python -m crypto_trader.scanner --limit 10
python -m pytest -q
```

## Attribution and license

The original skill repository is MIT licensed. This module is a clean reimplementation of the documented setup concepts. The original repository and its license are retained as attribution; no original source files are copied into this project.
