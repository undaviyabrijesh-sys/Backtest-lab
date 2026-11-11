# India Day Trader — Yahoo Finance + Discord (research / alerting MVP)

This is a first India-market adaptation inspired by the modular workflow in Jakeschincariol/day-trader-skill (MIT). It is being developed in this repository's india-day-trader branch so the existing main branch and historical backtester remain unchanged.

## What is implemented in v1

- NSE/BSE watchlist: NIFTY 50, NIFTY BANK, SENSEX and a starter set of liquid NSE equities.
- 5-minute candles from Yahoo Finance via yfinance, processed in Asia/Kolkata time. Yahoo is unofficial, best-effort and may be delayed or incomplete.
- 15-minute opening range (09:15–09:30) breakout confirmation on a fully closed 5-minute candle.
- EMA trend filter; VWAP and relative-volume filters for equities (disabled for index symbols where volume/VWAP may be unsuitable).
- Indicative stop from the confirmation candle extreme and 2R target.
- Optional INR share sizing when account capital is explicitly configured.
- Discord webhook alerts with per-symbol/per-day de-duplication state.
- Offline unit tests for signal logic, risk sizing, candle completion and market-hour gating.

## Safety boundary

This MVP is alert-only. It does not place, modify or cancel broker orders. The entry is the completed confirmation candle close and is a reference price, not a guaranteed fill. The current implementation is not a validated profitable strategy and must be paper-traded and backtested with brokerage, STT, GST, exchange charges, stamp duty, slippage and realistic fill assumptions before live use. It does not yet scan option contracts or construct option-premium orders.

## Required GitHub Actions secrets

Only one repository Actions secret is required for the Yahoo Finance alert workflow:

- `DISCORD_WEBHOOK_URL` — webhook URL for the Discord channel where alerts should appear. Keep it private.

Yahoo Finance does not require a broker login or API key. The scanner defaults to `MARKET_DATA_SOURCE=yahoo`; it no longer requires FYERS client IDs, tokens, app secrets or PINs. Do not add FYERS credentials for this workflow.

## Yahoo Finance data limitations

- NSE equities use Yahoo symbols such as `RELIANCE.NS`; BSE equities use `.BO`. NIFTY 50, NIFTY BANK and SENSEX use Yahoo index symbols.
- The adapter requests 5-minute candles for the current session and discards bars that have not fully closed.
- Yahoo's intraday history is limited (5-minute data is generally available for up to about 60 days), and requests can be rate-limited or return gaps. See the `yfinance` history documentation: https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html
- Yahoo Finance is not an official exchange feed or broker API. Data may be delayed, missing, adjusted or revised and has no execution-grade SLA. These alerts are for research and paper monitoring only; verify prices independently. Do not use them for automated/live order execution.

## GitHub Actions

The workflow .github/workflows/india-day-trader-alerts.yml has a manual trigger and a weekday 15-minute schedule in UTC. The scanner itself only evaluates entries between 09:45 and 14:45 IST. GitHub only runs scheduled workflows from the default branch, and the manual Run workflow button also requires the workflow to exist on the default branch. While this work remains on the development branch, the pull-request CI workflow runs the offline tests; after tests and secrets are verified, merge the development branch into the default branch to activate manual and scheduled alert runs.

The 15-minute job cadence checks the four most recent completed 5-minute bars and ignores breakouts more than 15 minutes past candle close. This reduces GitHub Actions usage while keeping the signal logic on 5-minute candles. GitHub-hosted schedules are best-effort and can be delayed. Do not treat them as a low-latency execution feed. The workflow caches the de-duplication state between runs to avoid repeated alerts for the same symbol on the same trading date.

## Configuration

Edit india_day_trader/watchlist.json to enable/disable instruments and tune the research parameters. Leave account_capital_inr as null until the intended trading capital is decided. When configured, the sizing estimate uses 0.5% of capital as risk and caps notional exposure at 20% per trade by default; this is a research estimate, not an instruction to trade.

## Next validation stages

1. Verify Yahoo symbol mapping and candle coverage for every enabled symbol; compare sample candles against a broker/exchange source before relying on the feed.
2. Backtest ORB variants on historical 5-minute data with realistic transaction costs and same-bar stop/target ambiguity handled conservatively.
3. Add replay results and an auditable trade journal.
4. Add additional setups only as separate experimental strategies (PDH/PDL, VWAP reclaim, CRT, liquidity sweep and Fibonacci) and validate each independently.
5. Add NIFTY/Bank NIFTY/SENSEX options only after underlying signals and option-chain/contract selection are validated.


## Historical ORB research

The ORB backtester is available as `python -m india_day_trader.backtest_orb --input data/NSE_RELIANCE-EQ_5.csv`. It enters at the next 5-minute candle open after the close-confirmed breakout, uses the sweep/confirmation candle extreme for the stop, assumes stop-first if stop and target are both touched in one candle, and closes any open trade at the final session candle. It reports gross/net points, estimated slippage and all-in transaction-cost assumptions, R multiples, profit factor, drawdown, monthly P&L and consecutive losses.

Run a declared 36-variant grid using `python -m india_day_trader.research_matrix --input data/NSE_RELIANCE-EQ_5.csv`. The grid varies target RR (1R, 1.5R, 2R, 3R), EMA period (9, 20, 50) and filter mode (EMA only, VWAP, VWAP + relative volume). It uses an earliest-70% / latest-30% chronological split and ranks variants by later out-of-sample results. A variant is only flagged for review when it has at least 20 out-of-sample trades, positive expectancy and profit factor above 1.0. This flag is not a strategy approval.

The default 10 bps per-side cost and 2 bps per-side slippage are generic research assumptions, not a verified FYERS tariff. Configure them using the real instrument, turnover, exchange, statutory charges and broker plan before interpreting results. These tools backtest the underlying OHLC series; index underlying point P&L is not option-premium P&L. Option strategies need contract selection, expiry, spread, lot size, premium data and execution modelling separately.


## Discord signal outcome tracking

After a signal alert is delivered, its reference setup is kept in `.cache/india_trader_alert_state.json`. Each scheduled run checks only newly completed 5-minute candles after the signal candle. It posts a Discord status message when the reference stop or target is touched, or when the position is flattened at the configured `force_flat_time` (default 15:20 IST); monitoring accepts delayed workflow starts until 16:00 IST. If both stop and target are touched in the same candle, stop is counted first. A signal still marked open when a new session begins is reported as an unresolved data gap rather than inventing an exit.

This is OHLC-based paper tracking, not broker order tracking. The initial entry uses the breakout confirmation candle close as a reference. Your actual fill can differ, especially because GitHub Actions may be delayed. Status P&L is before brokerage, taxes, slippage and actual-fill reconciliation. Do not use it as an account statement.


## Experimental PDH/PDL liquidity-sweep strategy

A second, research-only strategy is available as `india_day_trader.pdh_pdl_sweep`. It uses the prior completed session's high and low, detects a 5-minute sweep that closes back inside the prior-day level, and requires the following candle to break the sweep candle's opposite edge before entry. It shares the conservative stop-first same-candle handling and cost/slippage model with the ORB backtester.

This module is not wired into the live scanner or Discord signal stream. Run tests and historical replay first; do not promote it to live alerts based on synthetic fixtures. Use at least six to twelve months of clean 5-minute data and separate in-sample/out-of-sample sessions before judging it.


## Run a real historical research job

The historical research workflow currently remains FYERS-based and is not usable until a supported data credential is configured. The live alert scanner is switched to Yahoo Finance; this does not automatically convert the historical research downloader. It uploads the candle file, trade ledgers and JSON summaries as a 90-day artifact; it does not commit market data to Git.

Start with one highly liquid cash-equity symbol such as `NSE:RELIANCE-EQ`. For index symbols, the output is in underlying index points and is not equivalent to futures or option-premium P&L. Use instrument-appropriate transaction-cost assumptions. The job requires at least two distinct sessions for the out-of-sample matrix. FYERS history coverage is account-plan and symbol dependent.
