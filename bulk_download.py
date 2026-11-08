"""Bulk downloader for NIFTY and SENSEX across FYERS-supported candle intervals."""
import argparse
import os
import time
from datetime import date
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from download import fetch_history

SYMBOLS = ["NSE:NIFTY50-INDEX", "BSE:SENSEX-INDEX"]
# All standard historical candle resolutions documented by FYERS (excluding seconds).
RESOLUTIONS = ["1", "2", "3", "5", "10", "15", "20", "30", "45", "60", "120", "180", "240", "D", "1W", "1M"]

def download_one(fyers, symbol, resolution, start, end, outdir):
    chunk_days = 100 if resolution not in ("D", "1D", "1W", "1M") else 366
    frames = []
    # Small pause between calls; fail clearly on entitlement/auth/rate errors.
    cursor = start
    from datetime import timedelta
    while cursor <= end:
        finish = min(cursor + timedelta(days=chunk_days - 1), end)
        try:
            part = fetch_history(fyers, symbol, resolution, cursor, finish, chunk_days=chunk_days)
        except Exception as exc:
            raise RuntimeError(f"{symbol} {resolution} {cursor}..{finish}: {exc}") from exc
        if not part.empty:
            frames.append(part)
        cursor = finish + timedelta(days=1)
        time.sleep(0.25)
    result = (pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
              if frames else pd.DataFrame(columns=["datetime","timestamp","open","high","low","close","volume"]))
    path = Path(outdir) / f"{symbol.replace(':','_')}_{resolution}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(path, index=False)
    print(f"COMPLETE {symbol} resolution={resolution}: {len(result)} candles -> {path}", flush=True)
    return len(result)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--intraday-start", type=date.fromisoformat, required=True)
    p.add_argument("--daily-start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    p.add_argument("--outdir", default="data")
    p.add_argument("--symbols", nargs="*", default=SYMBOLS)
    p.add_argument("--resolutions", nargs="*", default=RESOLUTIONS)
    a = p.parse_args()
    if a.intraday_start > a.end or a.daily_start > a.end:
        raise SystemExit("Start date must not be after end date")
    load_dotenv()
    client, token = os.getenv("FYERS_CLIENT_ID"), os.getenv("FYERS_ACCESS_TOKEN")
    if not client or not token:
        raise SystemExit("Missing FYERS_CLIENT_ID or FYERS_ACCESS_TOKEN environment secret")
    from fyers_apiv3 import fyersModel
    fyers = fyersModel.FyersModel(client_id=client, token=token, is_async=False, log_path="")
    total = 0
    for symbol in a.symbols:
        for resolution in a.resolutions:
            start = a.daily_start if resolution in ("D", "1D", "1W", "1M") else a.intraday_start
            total += download_one(fyers, symbol, resolution, start, a.end, a.outdir)
    print(f"ALL DOWNLOADS COMPLETE: {total} candles across {len(a.symbols)} symbols x {len(a.resolutions)} resolutions")

if __name__ == "__main__":
    main()
