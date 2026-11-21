# NIFTY & SENSEX Backtest Lab

Historical candle downloader and event-driven backtester for FYERS v3. No live orders.

## Setup
1. Python 3.10+; `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` locally (never commit it).
3. Set `FYERS_CLIENT_ID`, `FYERS_SECRET_KEY`, `FYERS_REDIRECT_URI` from your FYERS app.
4. Run `python auth.py login`; open the printed URL, sign in to FYERS and copy the full redirect URL or auth_code.
5. Run `python auth.py exchange` and paste the redirect URL/code. This stores the access token locally.
6. Run `python download.py --symbol NSE:NIFTY50-INDEX --start 2025-01-01 --end 2025-02-01 --resolution 15`.
7. Run `python backtest.py --input data/NSE_NIFTY50-INDEX_15.csv`.

For SENSEX use `BSE:SENSEX-INDEX`; verify symbols in FYERS Symbol Master. Historical availability, candle limits, and index entitlements depend on FYERS. Date ranges are inclusive in the CLI; downloader fetches chunks and deduplicates timestamps. Data is written to CSV (not tracked by git). This starter backtests the *underlying index*, not option premiums.

## Strategy implemented
Previous trading day's high and low form levels. On 15-minute bars, a candle must **close** beyond the level, and the *next* candle must break the signal candle's high (long) or low (short). Both bullish and bearish setups are permitted at either level. Stop is the signal candle's opposite extreme; target is 2R. Entry is at the trigger level, unless next candle opens beyond it (then entry is at open). Stop-first assumption if stop and target touch on the same candle. One open position at a time, and close positions at the last candle of the session. Assumes zero slippage and fees by default. Signal candle's high/low must be strictly crossed. No future bars used to form levels.

This is a research baseline, not a validated profitable strategy. Backtests must account for fees, slippage, lot sizes, options premiums and expiry effects before considering real trading.


## GitHub Actions (recommended)
The workflow `.github/workflows/fyers-backtest.yml` runs manually from the Actions tab:
1. Open repository Settings -> Secrets and variables -> Actions -> New repository secret.
2. Add `FYERS_CLIENT_ID` and `FYERS_ACCESS_TOKEN`. Use your FYERS app client ID and current access token. Never put secrets in workflow files or commit them.
3. Open Actions -> FYERS Historical Download & Backtest -> Run workflow.
4. Enter symbol, candle resolution, start/end dates and R multiple. Downloaded candles and `trades.csv` are saved as a downloadable workflow artifact for 30 days.

FYERS access tokens are time-limited and commonly need renewal. When the workflow reports an authentication error, generate a fresh token locally with `python auth.py login` / `python auth.py exchange`, then replace the `FYERS_ACCESS_TOKEN` repository secret. For now this is manual dispatch only: scheduled runs are intentionally disabled because an expired token would make unattended runs fail.

To run: use the repository's Actions tab; no API credentials should ever be pasted into chat or committed.


## Bulk historical download (NIFTY + SENSEX)
The Actions workflow now downloads both index symbols across all documented FYERS candle intervals:
- Seconds: 5S, 10S, 15S, 30S, 45S (where plan-entitled; only recent 30 trading days).
- Intraday: 1, 2, 3, 5, 10, 15, 20, 30, 45, 60, 120, 180, 240 minutes.
- EOD: D, 1W, 1M.

Run Actions -> "Download All NIFTY & SENSEX Historical Data" -> Run workflow. Defaults are set for a Standard-plan starting point: intraday 2025-11-08 and daily 2021-01-01, ending 2026-11-07. Change dates if your FYERS plan permits more history. FYERS currently documents Standard access as approximately 1 year intraday and 5 years daily; Prime offers 5+ years intraday and 25+ years daily. Historical data is subject to symbol availability and account entitlements. Seconds data is only available for the most recent 30 trading days on eligible plans. See the official [FYERS historical-data limits](https://fyers.in/api-docs/v3/api/market-data/historical-data).

The workflow uploads CSV files as a 90-day artifact. It does not push market data into Git (large datasets should not be committed to the repository). No backtest is run by the bulk-download workflow yet; first validate the downloaded files and coverage.


## India Day Trader (development)

An India-market intraday scanner with FYERS candle data and Discord research alerts is under development on the `india-day-trader` branch. See [README_INDIA_DAY_TRADER.md](README_INDIA_DAY_TRADER.md) for setup, secrets and safety limits. This work is kept off `main` until tested.


## FYERS Standard-plan options data (NIFTY + SENSEX)

The options workflow is separate from the index downloader because expired F&O has tighter Standard-plan limits.

1. Run **Actions → FYERS NIFTY & SENSEX Options Data → Run workflow** with mode `discover`. It calls FYERS expiry-date and expired-contract catalogue APIs and creates `expired_options_contract_catalogue.csv` for NIFTY and SENSEX.
2. Download that artifact and select exact option symbols (CE/PE, expiry and strikes) into a one-column CSV named `options_symbols.csv` with header `symbol`.
3. Run the same workflow with mode `download`, paste the selected exact symbols as a comma-separated list, choose resolution and dates, and keep `max_requests` at 10 or below.
4. The workflow requests OHLCV plus open interest and option Greeks (where FYERS returns them), then uploads CSVs as a 90-day artifact.

**Standard-plan constraints (verified against current FYERS documentation):**
- Standard Data API: 5 requests/second, 50/minute and 5,000/day.
- Active instrument historical candles: rolling last 1 year intraday and last 5 years daily, subject to instrument availability.
- Expired F&O: daily history for last 2 years; only 10 expired-F&O intraday history requests per day. Each contract/date chunk consumes one request. Intraday requests are chunked to at most 100 calendar days.
- Therefore, do not expect a complete multi-year 1-minute options database to download in one day on Standard. Prioritise representative ATM/near-ATM CE and PE contracts and build the historical set in daily batches.
- Greeks may be null for some candles. The downloader preserves nulls; it does not forward-fill or replace them with zero.
- Missing data is not fabricated. A valid `no_data` response is recorded as an empty result.

The bulk index workflow now uses Standard-eligible candle intervals only (1m through 240m plus daily/weekly/monthly); it no longer requests seconds candles, which Standard does not include. Default index coverage is the rolling 1-year intraday window and 5-year daily window. It is a manual workflow so a refreshed FYERS access token can be supplied through GitHub Actions secrets.

Required repository Actions secrets for both workflows: `FYERS_CLIENT_ID` and current `FYERS_ACCESS_TOKEN`. The local FYERS app connection in another application does not automatically populate GitHub Actions secrets. Never commit credentials or paste tokens into chat.
