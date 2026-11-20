# MCX Gold / Gold Mini Overnight Repricing Research

This is an isolated research branch. It does not place orders and does not modify `main`.

## Research question
When MCX is closed, do changes in international XAUUSD and USDINR explain the next MCX GOLD/GOLDM opening gap? If a residual opening mispricing remains, does it predict returns over the next 15/30/60/120 minutes after realistic costs?

This is **not automatically arbitrage**: MCX is closed during the overnight move, so the strategy is exposed to gap, execution, basis, currency and contract risk.

## Data needed
Prepare one normalized CSV with:
`timestamp,instrument,contract,open,high,low,close,volume`

- `instrument`: XAUUSD, USDINR, GOLD, GOLDM
- `timestamp`: ISO timestamp; timezone-aware preferred. Naive timestamps are interpreted as Asia/Kolkata.
- XAUUSD: consistent broker/source feed; note spot CFD/OTC is not a centralized exchange tape.
- USDINR: ideally a source whose trading hours and price convention are documented.
- GOLD and GOLDM: actual MCX futures contracts, not a back-adjusted continuous series unless contract rolls are explicitly flagged.
- Include at least 12 months, preferably 2 years, with overlapping timestamps. For MCX use 1-minute bars; for XAUUSD and USDINR use 1-minute bars.
- For multi-contract MCX data, include `volume`; the script selects the highest-volume contract per session. Better still, provide a pre-filtered front-month series and document roll dates.

Do not mix spot gold, COMEX futures and MCX futures without preserving each instrument's identity. Do not use CFD tick volume as exchange volume.

## Run
```bash
pip install pandas numpy
python gold_mcx/overnight_event_study.py --input data/gold_mcx_1m.csv --out results/gold_mcx --cost-bps-roundtrip 8
```

The 8 bps cost is only a placeholder. Replace it with broker-specific brokerage, exchange charges, GST, stamp duty, CTT, bid/ask spread and slippage. Run sensitivity at multiple cost assumptions.

Outputs:
- `event_study.csv`: per-session overnight returns, synthetic INR fair-value return, MCX opening gap, residual mispricing and post-open returns.
- `summary.csv`: trade count, win rate, average/median net return and profit factor by instrument and holding horizon.

## Important interpretation / limitations
- Synthetic fair-value return is a simplified return proxy: (1 + XAUUSD return) × (1 + USDINR return) − 1. It is not a complete MCX fair-value price. Import duties, GST treatment, local premiums, purity, contract basis, expiry, carry, financing and settlement conventions affect the absolute price.
- The strategy direction is long if the synthetic overnight return exceeds the MCX opening gap, otherwise short. This is a hypothesis for testing, not a validated signal.
- The current prototype measures close-to-open repricing and post-open mark returns. It does not yet model order-book fills, stop/target intrabar sequencing, margin, lot rounding, contract expiry delivery rules or market impact.
- It assumes the earliest available MCX bar is the opening execution reference. Validate exchange session timestamps and missing bars before interpreting results.
- Use chronological train/validation/holdout splits. Freeze parameters before the holdout. Report all sessions, including no-trade and missing-data counts.
- A credible result must beat a simple MCX opening buy/hold baseline and remain positive after conservative costs across both GOLD and GOLDM and multiple market regimes.

## Data sourcing status (2026-11-20)
- XAUUSD: a free 1-minute evaluation sample is publicly listed by GetData; it is broker CFD data, not centralized exchange volume. Full archive is paid.
- MCX: MCX's own historical feed is available on request and provides historical order-book/trade-book data for selected contracts; it is not a free public 1-minute OHLC archive.
- USDINR: public/free synchronized 1-minute coverage suitable for a full multi-year test has not yet been verified.
- Therefore no performance result is claimed until all three synchronized feeds and MCX contract data are loaded and audited.

## Next validation stages
1. Data audit: timezone, gaps, duplicates, stale bars, contract rolls and session calendar.
2. Event study: overnight XAUUSD/USDINR vs MCX opening gap.
3. Tradable tests: entry at next executable quote, exits at 15/30/60/120 minutes, cost and slippage sensitivity.
4. Walk-forward and untouched holdout evaluation.
5. Only if robust: paper trade; never label the result risk-free arbitrage.
