"""FYERS expired-options catalogue and Standard-plan-safe candle downloader.

The Standard plan permits only 10 expired-F&O intraday history requests per day.
This script enforces that ceiling locally. One request = one contract + one
date chunk. It never places orders and never silently substitutes missing data.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

UNDERLYINGS = {
    "NIFTY": "NSE:NIFTY50-INDEX",
    "SENSEX": "BSE:SENSEX-INDEX",
}
CORE = ["timestamp", "open", "high", "low", "close", "volume"]
OPTION_SUFFIX = re.compile(r"(CE|PE)$")


def make_client():
    load_dotenv()
    client_id = os.getenv("FYERS_CLIENT_ID", "").strip()
    token = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
    if not client_id or not token:
        raise SystemExit("Set FYERS_CLIENT_ID and FYERS_ACCESS_TOKEN in .env or environment.")
    from fyers_apiv3 import fyersModel
    return fyersModel.FyersModel(client_id=client_id, token=token, is_async=False, log_path="")


def discover_contracts(fyers, start: date, end: date, outdir: str) -> Path:
    """Discover expired option symbols by expiry; catalogue only, no candle calls."""
    if start > end:
        raise ValueError("start must be <= end")
    rows = []
    for label, underlying in UNDERLYINGS.items():
        cursor = start
        expiries = []
        while cursor <= end:
            finish = min(cursor + timedelta(days=365), end)
            response = fyers.expiry_dates(data={
                "symbol": underlying, "range_from": cursor.isoformat(),
                "range_to": finish.isoformat(), "date_format": "1",
            })
            if response.get("s") != "ok":
                raise RuntimeError(f"Expiry lookup failed for {label}: {response}")
            expiries.extend(response.get("data", {}).get("expiry_dates", {}).get("options", []))
            cursor = finish + timedelta(days=1)
            time.sleep(0.25)
        for expiry in sorted(set(expiries)):
            response = fyers.history_underlying_symbols(data={
                "symbol": underlying, "expiry_date": expiry,
            })
            if response.get("s") != "ok":
                print(f"SKIP catalogue {label} {expiry}: {response.get('message', response.get('code'))}")
                continue
            symbols = response.get("data", {}).get("contracts", {}).get("options", [])
            for symbol in symbols:
                match = OPTION_SUFFIX.search(symbol)
                if not match:
                    continue
                # Keep the exact FYERS symbol as the canonical identifier.
                rows.append({
                    "underlying": label, "underlying_symbol": underlying,
                    "expiry": expiry, "option_type": match.group(1), "symbol": symbol,
                })
            time.sleep(0.25)
    frame = pd.DataFrame(rows).drop_duplicates(["symbol"]).sort_values(
        ["underlying", "expiry", "symbol"]
    ) if rows else pd.DataFrame(columns=[
        "underlying", "underlying_symbol", "expiry", "option_type", "symbol"
    ])
    path = Path(outdir) / "expired_options_contract_catalogue.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    print(f"CATALOGUED {len(frame)} expired option contracts -> {path}")
    print("Catalogue discovery does not download OHLC candles; select contracts in a symbols file.")
    return path


def read_symbols(path: str) -> list[str]:
    file = Path(path)
    if not file.exists():
        raise SystemExit(f"Symbols file not found: {file}")
    if file.suffix.lower() == ".csv":
        frame = pd.read_csv(file)
        if "symbol" not in frame.columns:
            raise SystemExit("CSV must contain a 'symbol' column with exact FYERS option symbols.")
        values = frame["symbol"].dropna().astype(str).tolist()
    else:
        values = [line.strip() for line in file.read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#")]
    return list(dict.fromkeys(values))


def fetch_expired(fyers, symbol: str, resolution: str, start: date, end: date,
                  include_oi: bool, include_greeks: bool) -> pd.DataFrame:
    response = fyers.fno_historical_data(data={
        "symbol": symbol, "resolution": str(resolution), "date_format": "1",
        "range_from": start.isoformat(), "range_to": end.isoformat(),
        "include_oi": "1" if include_oi else "0",
        "include_greeks": "1" if include_greeks else "0",
    })
    status = response.get("s")
    if status == "no_data":
        return pd.DataFrame()
    if status != "ok":
        raise RuntimeError(f"{symbol} {start}..{end}: {response.get('message', response)}")
    columns = response.get("columns") or CORE
    frame = pd.DataFrame(response.get("candles", []), columns=columns)
    if frame.empty:
        return frame
    frame["datetime"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    return frame


def download_selected(fyers, symbols: list[str], start: date, end: date,
                      resolution: str, max_requests: int, outdir: str,
                      include_oi: bool, include_greeks: bool) -> None:
    if start > end:
        raise ValueError("start must be <= end")
    is_intraday = resolution not in {"D", "1D", "1W", "1M"}
    if is_intraday and not 1 <= max_requests <= 10:
        raise SystemExit("Standard plan expired-F&O intraday max-requests must be 1..10 per day.")
    chunk_days = 100 if is_intraday else 366
    remaining = max_requests if is_intraday else 5000
    root = Path(outdir)
    root.mkdir(parents=True, exist_ok=True)
    for symbol in symbols:
        cursor = start
        frames = []
        out = root / (re.sub(r"[^A-Za-z0-9_-]+", "_", symbol) + f"_{resolution}.csv")
        if out.exists():
            try:
                frames.append(pd.read_csv(out))
            except Exception:
                print(f"WARNING existing file unreadable, rebuilding: {out}")
        while cursor <= end and remaining > 0:
            finish = min(cursor + timedelta(days=chunk_days - 1), end)
            try:
                part = fetch_expired(fyers, symbol, resolution, cursor, finish,
                                     include_oi, include_greeks)
            except Exception as exc:
                print(f"ERROR {exc}")
                if is_intraday and ("limit" in str(exc).lower() or "429" in str(exc)):
                    print("Stopping to protect the Standard-plan daily request allowance.")
                    return
                raise
            if not part.empty:
                frames.append(part)
            remaining -= 1
            print(f"REQUEST USED: {symbol} {cursor}..{finish}; remaining budget={remaining}")
            cursor = finish + timedelta(days=1)
            time.sleep(0.25)
        if frames:
            merged = pd.concat(frames, ignore_index=True, sort=False)
            if "timestamp" in merged.columns:
                merged = merged.drop_duplicates("timestamp").sort_values("timestamp")
            merged.to_csv(out, index=False)
            print(f"SAVED {symbol}: {len(merged)} rows -> {out}")
        if remaining <= 0:
            print("Daily request budget reached. Re-run on a later day to continue remaining contracts.")
            break


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["discover", "download"])
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    p.add_argument("--outdir", default="data/options")
    p.add_argument("--symbols-file", help="CSV with a symbol column or newline-separated symbols.")
    p.add_argument("--resolution", default="5", help="1, 5, 15, 60, D, 1W etc.")
    p.add_argument("--max-requests", type=int, default=10,
                   help="Expired F&O intraday candle requests today (Standard cap: 10).")
    p.add_argument("--include-oi", action="store_true")
    p.add_argument("--include-greeks", action="store_true")
    a = p.parse_args()
    fyers = make_client()
    if a.mode == "discover":
        discover_contracts(fyers, a.start, a.end, a.outdir)
    else:
        if not a.symbols_file:
            raise SystemExit("download mode requires --symbols-file after selecting contracts from the catalogue.")
        symbols = read_symbols(a.symbols_file)
        if not symbols:
            raise SystemExit("No option symbols found in symbols file.")
        download_selected(fyers, symbols, a.start, a.end, a.resolution,
                          a.max_requests, a.outdir, a.include_oi, a.include_greeks)


if __name__ == "__main__":
    main()
