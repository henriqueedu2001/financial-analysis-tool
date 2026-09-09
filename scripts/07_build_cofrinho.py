#!/usr/bin/env python3
from argparse import ArgumentParser
from pathlib import Path

from finance_analysis.cdi import load_cdi_rates
from finance_analysis.classification import read_csv
from finance_analysis.ingestion import fieldnames, write_csv_atomic
from finance_analysis.reserve import (
    build_reserve_daily,
    build_reserve_monthly,
    build_reserve_quality,
    extract_reserve_events,
    load_reserve_assumptions,
)


def main() -> None:
    parser = ArgumentParser(description="Reconstrói o cofrinho a partir do saldo-âncora.")
    parser.add_argument(
        "--transactions",
        type=Path,
        default=Path("data/derived/transactions_dated.csv"),
    )
    parser.add_argument(
        "--facts",
        type=Path,
        default=Path("data/knowledge/financial_facts.toml"),
    )
    parser.add_argument(
        "--cdi",
        type=Path,
        default=Path("config/reference/cdi_daily.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived"))
    args = parser.parse_args()

    assumptions = load_reserve_assumptions(args.facts)
    transactions = read_csv(args.transactions)
    cdi_rates = load_cdi_rates(read_csv(args.cdi))
    events = extract_reserve_events(transactions)
    daily = build_reserve_daily(events, cdi_rates, assumptions)
    monthly = build_reserve_monthly(daily, assumptions)
    quality = build_reserve_quality(daily, events, cdi_rates, assumptions)

    outputs = (
        ("cofrinho_events.csv", events),
        ("cofrinho_daily.csv", daily),
        ("cofrinho_monthly.csv", monthly),
        ("cofrinho_quality.csv", quality),
    )
    for filename, rows in outputs:
        path = args.output_dir / filename
        write_csv_atomic(path, rows, fieldnames(rows))
        print(f"{len(rows)} linhas: {path}")


if __name__ == "__main__":
    main()
