#!/usr/bin/env python3
"""Collect MCX GOLD/GOLDM daily bhavcopy and aligned hourly global proxies.

MCX is official daily FUTCOM OHLC. GC=F and INR=X are Yahoo proxies, not
XAUUSD spot and USDINR futures. No paid data or user contact details used.
"""
from __future__ import annotations
import argparse
import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from curl_cffi import requests as curl_requests
import yfinance as yf

LOG = logging.getLogger("gold_mcx_download")
MCX_URL = "https://www.mcxindia.com/market-data/bhavcopy/GetDateWiseBhavCopy"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.mcxindia.com/market-data/bhavcopy",
    "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin",
}


def parse_date(value, fallback: date) -> date:
    if value is None or str(value).strip() == "":
        return fallback
    s = str(value).strip()
    for fmt in ("%d %b %Y", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {s!r}")


def number(value) -> float:
    try:
        return float(str(value).strip().replace(",", "")) if value not in (None, "", "-") else 0.0
    except (TypeError, ValueError):
        return 0.0


def fetch_mcx(start: date, end: date, out: Path, delay: float, resume: bool) -> pd.DataFrame:
    out.parent.mkdir(parents=True, exist_ok=True)
    cache = out.with_name("mcx_daily_cache.csv")
    cached = pd.read_csv(cache, parse_dates=["date"]) if resume and cache.exists() else pd.DataFrame()
    if not cached.empty:
        cached["date"] = pd.to_datetime(cached.date).dt.strftime("%Y-%m-%d")
        done = set(pd.to_datetime(cached.date).dt.date)
        rows = cached.to_dict("records")
    else:
        done, rows = set(), []

    session = curl_requests.Session(impersonate="chrome")
    audit = []
    dates = pd.date_range(start, end, freq="B").date
    for i, d in enumerate(dates, 1):
        if d in done:
            continue
        payload, err = None, None
        for attempt in range(4):
            try:
                response = session.get(
                    MCX_URL,
                    params={"InstrumentName": "FUTCOM", "fromDate": d.strftime("%d/%m/%Y")},
                    headers=HEADERS, timeout=40,
                )
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:120]}")
                payload = response.json()
                break
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                time.sleep(min(3 * (attempt + 1), 12))
        if payload is None:
            LOG.warning("%s failed: %s", d, err)
            audit.append({"date": d.isoformat(), "status": "failed", "error": err})
            if delay:
                time.sleep(delay)
            continue

        data = payload.get("Data") or []
        kept, returned = 0, set()
        for item in data:
            symbol = str(item.get("Symbol", "")).strip().upper()
            if symbol not in {"GOLD", "GOLDM"}:
                continue
            actual = parse_date(item.get("DateDisplay") or item.get("Date") or item.get("TradeDate"), d)
            returned.add(actual.isoformat())
            if actual != d:  # Do not mislabel a stale cached MCX response.
                continue
            rows.append({
                "date": d.isoformat(), "instrument": symbol,
                "contract": symbol, "expiry": str(item.get("ExpiryDate", "")).strip(),
                "open": number(item.get("Open")), "high": number(item.get("High")),
                "low": number(item.get("Low")), "close": number(item.get("Close")),
                "prev_close": number(item.get("PreviousClose")),
                "volume": number(item.get("Volume")),
                "open_interest": number(item.get("OpenInterest")),
            })
            kept += 1
        audit.append({"date": d.isoformat(), "status": "ok" if kept else "empty_or_no_gold",
                      "source_rows": len(data), "gold_rows": kept, "returned_dates": sorted(returned)})
        if i % 50 == 0:
            LOG.info("MCX %d/%d business days; %d GOLD/GOLDM rows", i, len(dates), len(rows))
            pd.DataFrame(rows).drop_duplicates(["date", "instrument", "expiry"]).to_csv(cache, index=False)
        if delay:
            time.sleep(delay)

    if not rows:
        raise RuntimeError("No MCX GOLD/GOLDM rows downloaded.")
    df = pd.DataFrame(rows).drop_duplicates(["date", "instrument", "expiry"], keep="last")
    df = df.sort_values(["date", "instrument", "expiry"])
    df.to_csv(out, index=False)
    cache.unlink(missing_ok=True)
    manifest = {
        "source": "MCX official GetDateWiseBhavCopy endpoint",
        "endpoint": MCX_URL, "filter": "FUTCOM / GOLD / GOLDM",
        "start": start.isoformat(), "end": end.isoformat(),
        "rows": len(df), "dates": int(df.date.nunique()),
        "symbols": sorted(df.instrument.unique().tolist()), "request_audit": audit,
        "note": "Daily bars only; no intraday path, executable quote, or bid/ask.",
    }
    out.with_name("mcx_daily_manifest.json").write_text(json.dumps(manifest, indent=2))
    return df


def yahoo_hourly(ticker: str, instrument: str, start: date, end: date) -> pd.DataFrame:
    LOG.info("Yahoo hourly fetch %s", ticker)
    raw = yf.download(ticker, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                      interval="1h", auto_adjust=False, progress=False, threads=False)
    if raw is None or raw.empty:
        raise RuntimeError(f"No Yahoo hourly history for {ticker}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.columns = [str(c).lower().replace(" ", "_") for c in raw.columns]
    raw.index = pd.to_datetime(raw.index, utc=True, errors="coerce")
    raw = raw[~raw.index.isna()].sort_index()
    cols = ["open", "high", "low", "close"]
    if any(c not in raw.columns for c in cols):
        raise RuntimeError(f"{ticker}: OHLC columns missing")
    result = raw[cols].apply(pd.to_numeric, errors="coerce").dropna().reset_index()
    result = result.rename(columns={result.columns[0]: "timestamp"})
    result["timestamp"] = pd.to_datetime(result.timestamp, utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    result["instrument"], result["contract"] = instrument, ticker
    return result[["timestamp", "instrument", "contract", *cols]]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2024-11-01")
    p.add_argument("--end", default=date.today().isoformat())
    p.add_argument("--out-dir", default="data/daily")
    p.add_argument("--delay", type=float, default=1.6)
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    start, end = date.fromisoformat(a.start), date.fromisoformat(a.end)
    if end < start:
        raise ValueError("--end must not precede --start")
    folder = Path(a.out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    mcx = fetch_mcx(start, end, folder / "mcx_gold_goldm_daily.csv", a.delay, a.resume)

    # Yahoo intraday data generally has a ~730-day lookback ceiling.
    global_start = max(start, end - timedelta(days=729))
    gold = yahoo_hourly("GC=F", "GOLD_PROXY", global_start, end)
    fx = yahoo_hourly("INR=X", "USDINR", global_start, end)
    glob = pd.concat([gold, fx], ignore_index=True).sort_values(["instrument", "timestamp"])
    glob.to_csv(folder / "global_hourly.csv", index=False)
    (folder / "global_manifest.json").write_text(json.dumps({
        "source": "Yahoo Finance via yfinance",
        "series": {"GOLD_PROXY": "GC=F COMEX gold continuous futures (not XAUUSD spot)",
                   "USDINR": "INR=X USD/INR spot (not USDINR futures)"},
        "interval": "1h", "requested_start": global_start.isoformat(), "requested_end": end.isoformat(),
        "rows": {k: int(v) for k, v in glob.groupby("instrument").size().to_dict().items()},
        "first_timestamp": glob.timestamp.min(), "last_timestamp": glob.timestamp.max(),
        "caveats": ["Unofficial vendor interface; history may be revised.",
                    "Hourly bars and GC continuous roll basis are imperfect proxies."]
    }, indent=2))
    LOG.info("Completed MCX rows=%d; global hourly rows=%d", len(mcx), len(glob))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
