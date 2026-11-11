# India Day Trader — FYERS + Discord (research / alerting MVP)

This is a first India-market adaptation inspired by the modular workflow in Jakeschincariol/day-trader-skill (MIT). It is being developed in this repository's india-day-trader branch so the existing main branch and historical backtester remain unchanged.

## What is implemented in v1

- NSE/BSE watchlist: NIFTY 50, NIFTY BANK, SENSEX and a starter set of liquid NSE equities.
- 5-minute candles from FYERS v3, processed in Asia/Kolkata time.
- 15-minute opening range (09:15–09:30) breakout confirmation on a fully closed 5-minute candle.
- EMA trend filter; VWAP and relative-volume filters for equities (disabled for index symbols where volume/VWAP may be unsuitable).
- Indicative stop from the confirmation candle extreme and 2R target.
- Optional INR share sizing when account capital is explicitly configured.
- Discord webhook alerts with per-symbol/per-day de-duplication state.
- Offline unit tests for signal logic, risk sizing, candle completion and market-hour gating.

## Safety boundary

This MVP is alert-only. It does not place, modify or cancel broker orders. The entry is the completed confirmation candle close and is a reference price, not a guaranteed fill. The current implementation is not a validated profitable strategy and must be paper-traded and backtested with brokerage, STT, GST, exchange charges, stamp duty, slippage and realistic fill assumptions before live use. It does not yet scan option contracts or construct option-premium orders.

## Required GitHub Actions secrets

In this repository go to Settings -> Secrets and variables -> Actions -> New repository secret and add:

- FYERS_CLIENT_ID — FYERS app ID (not the trading login ID).
- FYERS_ACCESS_TOKEN — current FYERS v3 access token. FYERS documents that individual-app tokens expire daily at 6:30 AM IST; generate a new token after 6:30 AM on each trading day and update this GitHub secret. Do not commit it or paste it in chat.
- DISCORD_WEBHOOK_URL — webhook URL for the Discord channel where alerts should appear. Keep it private.

The existing requirements.txt already contains FYERS, pandas, dotenv and pytest dependencies.

## Run locally

    pip install -r requirements.txt
    export FYERS_CLIENT_ID="..."
    export FYERS_ACCESS_TOKEN="..."
    export DISCORD_WEBHOOK_URL="..."
    python -m pytest -q
    python -m india_day_trader.scanner --dry-run

On Windows PowerShell, use $env:FYERS_CLIENT_ID="..." etc. A local .env file is also supported by python-dotenv and must never be committed.

## GitHub Actions

The workflow .github/workflows/india-day-trader-alerts.yml has a manual trigger and a weekday 10-minute schedule in UTC. The scanner itself only evaluates entries between 09:45 and 14:45 IST. GitHub only runs scheduled workflows from the default branch, and the manual Run workflow button also requires the workflow to exist on the default branch. While this work remains on the development branch, the pull-request CI workflow runs the offline tests; after tests and secrets are verified, merge the development branch into the default branch to activate manual and scheduled alert runs.

The 10-minute job cadence checks the two most recent completed 5-minute bars and ignores breakouts more than 10 minutes past candle close. GitHub-hosted schedules are best-effort and can be delayed. Do not treat them as a low-latency execution feed. The workflow caches the de-duplication state between runs to avoid repeated alerts for the same symbol on the same trading date.

## Configuration

Edit india_day_trader/watchlist.json to enable/disable instruments and tune the research parameters. Leave account_capital_inr as null until the intended trading capital is decided. When configured, the sizing estimate uses 0.5% of capital as risk and caps notional exposure at 20% per trade by default; this is a research estimate, not an instruction to trade.

## Next validation stages

1. Verify FYERS symbol names and live candle coverage for every enabled symbol.
2. Backtest ORB variants on historical 5-minute data with realistic transaction costs and same-bar stop/target ambiguity handled conservatively.
3. Add replay results and an auditable trade journal.
4. Add additional setups only as separate experimental strategies (PDH/PDL, VWAP reclaim, CRT, liquidity sweep and Fibonacci) and validate each independently.
5. Add NIFTY/Bank NIFTY/SENSEX options only after underlying signals and option-chain/contract selection are validated.
