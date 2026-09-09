#!/usr/bin/env python3
from argparse import ArgumentParser
from pathlib import Path

from finance_analysis.classification import load_events, read_csv
from finance_analysis.ingestion import fieldnames, write_csv_atomic
from finance_analysis.metrics import (
    build_metrics_quality,
    build_metrics_summary,
    build_monthly_category_spending,
    build_monthly_metrics,
)
from finance_analysis.peaks import (
    build_peak_candidates,
    build_peaks_monthly,
    build_peaks_summary,
)


def main() -> None:
    parser = ArgumentParser(description="Calcula métricas mensais e picos de gasto.")
    parser.add_argument(
        "--transactions",
        type=Path,
        default=Path("data/derived/transactions_dated.csv"),
    )
    parser.add_argument(
        "--daily-balances",
        type=Path,
        default=Path("data/derived/daily_balances.csv"),
    )
    parser.add_argument(
        "--reserve-monthly",
        type=Path,
        default=Path("data/derived/cofrinho_monthly.csv"),
    )
    parser.add_argument(
        "--events",
        type=Path,
        default=Path("data/knowledge/transaction_events.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived"))
    args = parser.parse_args()

    transactions = read_csv(args.transactions)
    daily_balances = read_csv(args.daily_balances)
    reserve_monthly = read_csv(args.reserve_monthly)
    events = load_events(args.events)

    monthly = build_monthly_metrics(transactions, daily_balances, reserve_monthly)
    categories = build_monthly_category_spending(transactions)
    summary = build_metrics_summary(monthly)
    candidates = build_peak_candidates(transactions, events)
    peaks_monthly = build_peaks_monthly(candidates, monthly)
    peaks_summary = build_peaks_summary(candidates, peaks_monthly)
    quality = build_metrics_quality(monthly, categories)

    outputs = (
        ("monthly_metrics.csv", monthly),
        ("monthly_category_spending.csv", categories),
        ("metrics_summary.csv", summary),
        ("spending_peak_candidates.csv", candidates),
        ("spending_peaks_monthly.csv", peaks_monthly),
        ("spending_peaks_summary.csv", peaks_summary),
        ("metrics_quality.csv", quality),
    )
    for filename, rows in outputs:
        path = args.output_dir / filename
        write_csv_atomic(path, rows, fieldnames(rows))
        print(f"{len(rows)} linhas: {path}")


if __name__ == "__main__":
    main()
