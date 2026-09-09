#!/usr/bin/env python3
from argparse import ArgumentParser
from pathlib import Path

from finance_analysis.classification import (
    CLASSIFICATION_FIELDS,
    classify_row,
    expand_allocations,
    load_allocations,
    load_overrides,
    load_rules,
    read_csv,
)
from finance_analysis.ingestion import fieldnames, write_csv_atomic


def main() -> None:
    parser = ArgumentParser(description="Aplica regras e exceções à tabela canônica.")
    parser.add_argument(
        "--transactions",
        type=Path,
        default=Path("data/derived/transactions_canonical.csv"),
    )
    parser.add_argument("--knowledge-dir", type=Path, default=Path("data/knowledge"))
    parser.add_argument(
        "--base-rules", type=Path, default=Path("config/base_classification_rules.csv")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/derived/transactions_classified.csv")
    )
    args = parser.parse_args()

    rows = read_csv(args.transactions)
    rules = load_rules(args.base_rules, args.knowledge_dir / "classification_rules.csv")
    overrides = load_overrides(args.knowledge_dir / "transaction_overrides.csv")
    classified = [classify_row(row, rules, overrides) for row in rows]
    classified = expand_allocations(
        classified,
        load_allocations(args.knowledge_dir / "transaction_allocations.csv"),
    )
    unresolved = [
        row
        for row in classified
        if any(not row[field] for field in CLASSIFICATION_FIELDS)
    ]
    if unresolved:
        unresolved_path = args.output.with_name("classification_unresolved.csv")
        write_csv_atomic(unresolved_path, unresolved, fieldnames(unresolved))
        raise SystemExit(
            f"Classificação incompleta: {len(unresolved)} transações pendentes. "
            f"Consulte {unresolved_path}."
        )

    write_csv_atomic(args.output, classified, fieldnames(classified))
    print(f"Classificação completa: {len(classified)} transações.")
    print(args.output)


if __name__ == "__main__":
    main()
