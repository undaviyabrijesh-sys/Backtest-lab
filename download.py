"""Download FYERS v3 candles in bounded chunks, with deduplication."""
import argparse
import os
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

def fetch_history(fyers, symbol, resolution, start, end, chunk_days=60):
    if start > end:
        raise ValueError("start must not be later than end")
    frames = []
    cursor = start
    while cursor <= end:
        finish = min(cursor + timedelta(days=chunk_days - 1), end)
        query = {"symbol": symbol, "resolution": str(resolution), "date_format": "1",
                 "range_from": cursor.isoformat(), "range_to": finish.isoformat(), "cont_flag": "1"}
        response = fyers.history(data=query)
        if response.get("s") != "ok":
            raise RuntimeError(f"FYERS history failed for {cursor} to {finish}: {response.get('message', response.get('code', 'unknown error'))}")
        candles = response.get("candles", [])
        if candles:
            frames.append(pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"]))
        cursor = finish + timedelta(days=1)
    if not frames:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    result = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    result["datetime"] = pd.to_datetime(result["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    return result[["datetime", "timestamp", "open", "high", "low", "close", "volume"]]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="NSE:NIFTY50-INDEX")
    p.add_argument("--resolution", default="15")
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    a = p.parse_args()
    load_dotenv()
    client, token = os.getenv("FYERS_CLIENT_ID"), os.getenv("FYERS_ACCESS_TOKEN")
    if not client or not token:
        raise SystemExit("Set FYERS_CLIENT_ID and FYERS_ACCESS_TOKEN in local .env; run auth.py first")
    from fyers_apiv3 import fyersModel
    fyers = fyersModel.FyersModel(client_id=client, token=token, is_async=False, log_path="")
    df = fetch_history(fyers, a.symbol, a.resolution, a.start, a.end)
    output = Path("data") / f"{a.symbol.replace(':', '_')}_{a.resolution}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        old = pd.read_csv(output)
        df = pd.concat([old, df], ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    df.to_csv(output, index=False)
    print(f"Saved {len(df)} unique candles to {output}")

if __name__ == "__main__":
    main()
