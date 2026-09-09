#!/usr/bin/env python3
from argparse import ArgumentParser
from pathlib import Path

from finance_analysis.config import load_accounts
from finance_analysis.ingestion import (
    build_canonical,
    build_coverage_summary,
    build_reconciliation,
    fieldnames,
    write_csv_atomic,
)


def main() -> None:
    parser = ArgumentParser(description="Consolida OFX numa tabela canônica deduplicada.")
    parser.add_argument("--source-dir", type=Path, default=Path("data/sources"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived"))
    parser.add_argument("--accounts", type=Path, default=Path("config/accounts.toml"))
    args = parser.parse_args()

    transactions, snapshots = build_canonical(args.source_dir, load_accounts(args.accounts))
    transaction_path = args.output_dir / "transactions_canonical.csv"
    snapshot_path = args.output_dir / "statement_snapshots.csv"
    coverage_path = args.output_dir / "coverage_summary.csv"
    reconciliation_path = args.output_dir / "reconciliation.csv"
    coverage = build_coverage_summary(transactions, snapshots)
    reconciliation = build_reconciliation(transactions, snapshots)
    write_csv_atomic(transaction_path, transactions, fieldnames(transactions))
    write_csv_atomic(snapshot_path, snapshots, fieldnames(snapshots))
    write_csv_atomic(coverage_path, coverage, fieldnames(coverage))
    write_csv_atomic(reconciliation_path, reconciliation, fieldnames(reconciliation))

    inputs = sum(row["amount_cents"] > 0 for row in transactions)
    outputs = sum(row["amount_cents"] < 0 for row in transactions)
    print(
        f"Tabela canônica: {len(transactions)} movimentações "
        f"({inputs} entradas, {outputs} saídas) e {len(snapshots)} saldos."
    )
    print(transaction_path)
    print(snapshot_path)
    print(coverage_path)
    print(reconciliation_path)


if __name__ == "__main__":
    main()
