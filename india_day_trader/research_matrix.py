"""Chronological parameter research for India ORB.

The grid compares a small, declared set of variants and reports a later-date
out-of-sample segment. It is not an optimizer and must not be read as a guarantee.
"""
import argparse
import itertools
import json
from pathlib import Path

import pandas as pd

from .backtest_orb import normalize_candles, run_backtest, summarize


def chronological_split(candles, train_fraction=0.70):
    if not 0.5 <= float(train_fraction) < 1.0:
        raise ValueError("train_fraction must be >= 0.5 and < 1.0")
    df = normalize_candles(candles)
    if df.empty:
        return df.copy(), df.copy()
    sessions = sorted(df["datetime"].dt.date.unique())
    if len(sessions) < 2:
        raise ValueError("At least two distinct trading sessions are required for out-of-sample testing")
    cut = max(1, min(len(sessions) - 1, int(len(sessions) * train_fraction)))
    train_sessions = set(sessions[:cut])
    train = df[df["datetime"].dt.date.isin(train_sessions)].copy()
    test = df[~df["datetime"].dt.date.isin(train_sessions)].copy()
    return train, test


def default_variants():
    variants = []
    for rr, ema, filter_mode in itertools.product(
        (1.0, 1.5, 2.0, 3.0),
        (9, 20, 50),
        ("ema_only", "vwap", "vwap_volume"),
    ):
        variants.append({
            "name": f"RR{rr:g}_EMA{ema}_{filter_mode}",
            "rr": rr,
            "ema_period": ema,
            "use_vwap": filter_mode in ("vwap", "vwap_volume"),
            "use_volume": filter_mode == "vwap_volume",
        })
    return variants


def run_matrix(candles, cost_bps_per_side=10.0, slippage_bps_per_side=2.0,
               train_fraction=0.70, variants=None, min_oos_trades=20):
    train, test = chronological_split(candles, train_fraction)
    variants = variants or default_variants()
    results = []
    for variant in variants:
        params = {
            "rr": float(variant["rr"]),
            "ema_period": int(variant["ema_period"]),
            "use_vwap": bool(variant.get("use_vwap", False)),
            "use_volume": bool(variant.get("use_volume", False)),
            "cost_bps_per_side": float(cost_bps_per_side),
            "slippage_bps_per_side": float(slippage_bps_per_side),
        }
        train_metrics = summarize(run_backtest(train, **params))
        test_metrics = summarize(run_backtest(test, **params))
        enough_oos = test_metrics["trades"] >= int(min_oos_trades)
        results.append({
            "variant": variant["name"],
            **params,
            "in_sample_trades": train_metrics["trades"],
            "in_sample_net_points": train_metrics["net_points"],
            "in_sample_expectancy_net_r": train_metrics["expectancy_net_r"],
            "in_sample_profit_factor": train_metrics["profit_factor"],
            "out_sample_trades": test_metrics["trades"],
            "out_sample_net_points": test_metrics["net_points"],
            "out_sample_expectancy_net_r": test_metrics["expectancy_net_r"],
            "out_sample_profit_factor": test_metrics["profit_factor"],
            "out_sample_win_rate_pct": test_metrics["win_rate_pct"],
            "out_sample_max_drawdown_points": test_metrics["max_drawdown_points"],
            "out_sample_max_consecutive_losses": test_metrics["max_consecutive_losses"],
            "eligible_for_review": bool(enough_oos and test_metrics["expectancy_net_r"] > 0
                                        and test_metrics["profit_factor"] is not None
                                        and test_metrics["profit_factor"] > 1.0),
        })
    return pd.DataFrame(results).sort_values(
        ["eligible_for_review", "out_sample_expectancy_net_r", "out_sample_trades"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description="Chronological India ORB strategy-variant comparison")
    parser.add_argument("--input", required=True, help="5-minute candle CSV")
    parser.add_argument("--output", default="data/india_orb_matrix.csv")
    parser.add_argument("--summary", default="data/india_orb_matrix.json")
    parser.add_argument("--train-fraction", type=float, default=0.70)
    parser.add_argument("--cost-bps-per-side", type=float, default=10.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=2.0)
    parser.add_argument("--min-oos-trades", type=int, default=20)
    args = parser.parse_args()

    matrix = run_matrix(
        pd.read_csv(args.input),
        cost_bps_per_side=args.cost_bps_per_side,
        slippage_bps_per_side=args.slippage_bps_per_side,
        train_fraction=args.train_fraction,
        min_oos_trades=args.min_oos_trades,
    )
    output = Path(args.output)
    summary_path = Path(args.summary)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(output, index=False)
    payload = {
        "variants_tested": int(len(matrix)),
        "eligible_variants": int(matrix["eligible_for_review"].sum()) if not matrix.empty else 0,
        "train_fraction": args.train_fraction,
        "cost_bps_per_side": args.cost_bps_per_side,
        "slippage_bps_per_side": args.slippage_bps_per_side,
        "minimum_oos_trades_for_review": args.min_oos_trades,
        "warning": "Exploratory research only. Review out-of-sample results, sample size, drawdown and execution assumptions; do not select by in-sample profit.",
        "top_variants": matrix.head(10).to_dict(orient="records"),
    }
    summary_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    print(f"Matrix saved: {output}")
    print(f"Summary saved: {summary_path}")


if __name__ == "__main__":
    main()
