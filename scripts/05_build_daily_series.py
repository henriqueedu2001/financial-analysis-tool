#!/usr/bin/env python3
from argparse import ArgumentParser
from pathlib import Path

from finance_analysis.classification import read_csv
from finance_analysis.daily import build_daily_balances, build_daily_flows, build_data_quality
from finance_analysis.dates import add_operation_dates
from finance_analysis.ingestion import fieldnames, write_csv_atomic


def main() -> None:
    parser = ArgumentParser(description="Constrói datas efetivas, fluxos e saldos diários.")
    parser.add_argument(
        "--canonical",
        type=Path,
        default=Path("data/derived/transactions_canonical.csv"),
    )
    parser.add_argument(
        "--classified",
        type=Path,
        default=Path("data/derived/transactions_classified.csv"),
    )
    parser.add_argument(
        "--snapshots",
        type=Path,
        default=Path("data/derived/statement_snapshots.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived"))
    args = parser.parse_args()

    canonical = read_csv(args.canonical)
    classified = read_csv(args.classified)
    snapshots = read_csv(args.snapshots)
    dated = add_operation_dates(classified)
    channel_by_transaction = {
        row["parent_transaction_id"]: row["channel"] for row in classified
    }
    canonical_with_channels = [
        {
            **row,
            "channel": channel_by_transaction[row["transaction_id"]],
        }
        for row in canonical
    ]
    balances = build_daily_balances(canonical_with_channels, snapshots)
    flows = build_daily_flows(dated)
    quality = build_data_quality(dated, balances)

    outputs = (
        ("transactions_dated.csv", dated),
        ("daily_balances.csv", balances),
        ("daily_flows.csv", flows),
        ("data_quality.csv", quality),
    )
    for filename, rows in outputs:
        path = args.output_dir / filename
        write_csv_atomic(path, rows, fieldnames(rows))
        print(f"{len(rows)} linhas: {path}")


if __name__ == "__main__":
    main()
