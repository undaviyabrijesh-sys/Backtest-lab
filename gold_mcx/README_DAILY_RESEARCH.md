# MCX GOLD / GOLDM opening-gap research (daily-data phase)

This phase obtains **official MCX daily FUTCOM bhavcopy** rows for `GOLD` and `GOLDM`, plus Yahoo hourly proxies for COMEX gold (`GC=F`) and USD/INR (`INR=X`). The workflow is configured for the isolated `gold-mcx-arbitrage-research` branch and does not change `main` or any live strategy.

## What the test answers

- How much of the MCX same-contract opening gap is associated with global gold and USD/INR price changes since the prior MCX close?
- Does the residual fair-value direction, simple gap fade, or gap momentum direction have better **same-session open-to-close** results?
- Do the conclusions survive chronological 60% train / 20% validation / 20% holdout splits and 8 / 15 / 25 / 40 bp round-trip cost sensitivity?
- Are the outcomes materially different for `GOLD` and `GOLDM`?

The contract used for each next-session event is chosen using **the prior session's volume**, avoiding same-day volume look-ahead. The MCX `PreviousClose` is preferred for the same contract; if unavailable, the previous observed session's same-contract close is used.

## Data sources and important caveats

- **MCX:** official `GetDateWiseBhavCopy` endpoint, `InstrumentName=FUTCOM`; rows filtered to symbols `GOLD` and `GOLDM`. The downloader uses a browser-impersonating HTTP client because MCX's Akamai protection can reject plain requests. Requests are spaced by 1.6 seconds, raw responses are date-checked, and a resumable cache is used during the run.
- **Global gold proxy:** Yahoo `GC=F`, hourly COMEX gold continuous futures. This is **not XAUUSD spot**, and continuous-futures roll basis can affect returns.
- **FX proxy:** Yahoo `INR=X`, hourly USD/INR spot. This is **not USDINR futures** and its coverage / timestamps may differ from MCX.
- Yahoo hourly history is limited to roughly 730 days, so this first aligned study covers approximately the last two years even though MCX has older history.
- MCX daily bars can test the opening-gap attribution and open-to-close direction, but **cannot** test 15 / 30 / 60 / 120-minute execution, stop/target sequencing, spreads, or intraday slippage.
- Daily `Open` is the first reported trade, not proof that a hypothetical order could have filled there at precisely 09:00.
- Cost levels are sensitivities, not a verified broker-specific all-in cost model.

## Run locally

```bash
pip install pandas numpy yfinance curl_cffi
python -m unittest discover -s gold_mcx -p 'test_*.py' -v
python gold_mcx/download_daily_sources.py --start 2024-11-01 --end 2026-11-20 --out-dir data/daily --delay 1.6 --resume
python gold_mcx/daily_gap_backtest.py --mcx data/daily/mcx_gold_goldm_daily.csv --global data/daily/global_hourly.csv --out data/results/daily_gap
```

The GitHub Actions workflow runs those steps and commits the downloaded daily inputs and results to this research branch. The workflow does not buy paid data or submit user contact information to sample forms.

## Interpretation gate

A positive daily-bar result is only a hypothesis, not a production signal. Require a separate intraday test using timestamped 1-minute MCX GOLD and GOLDM plus synchronized XAUUSD / USDINR before claiming an executable edge. A true risk-free arbitrage claim is not appropriate: the MCX leg is closed during much of the global price-discovery window.
