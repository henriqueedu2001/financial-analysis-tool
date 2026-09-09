#!/usr/bin/env python3
import csv
from argparse import ArgumentParser
from pathlib import Path

from finance_analysis.classification import (
    ALLOCATION_FIELDS,
    EVENT_FIELDS,
    GROUP_FIELDS,
    INVESTIGATION_FIELDS,
    OVERRIDE_FIELDS,
    RULE_FIELDS,
    build_groups,
    load_allocations,
    load_events,
    load_investigations,
    load_overrides,
    load_rules,
    read_csv,
    sort_groups_by_materiality,
    validate_knowledge_references,
)
from finance_analysis.ingestion import write_csv_atomic


def initialize_csv(path: Path, fields: list[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.DictWriter(stream, fieldnames=fields).writeheader()


def main() -> None:
    parser = ArgumentParser(description="Agrupa transações para classificação assistida.")
    parser.add_argument(
        "--transactions",
        type=Path,
        default=Path("data/derived/transactions_canonical.csv"),
    )
    parser.add_argument("--knowledge-dir", type=Path, default=Path("data/knowledge"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/derived"))
    parser.add_argument(
        "--base-rules", type=Path, default=Path("config/base_classification_rules.csv")
    )
    args = parser.parse_args()

    rules_path = args.knowledge_dir / "classification_rules.csv"
    overrides_path = args.knowledge_dir / "transaction_overrides.csv"
    allocations_path = args.knowledge_dir / "transaction_allocations.csv"
    investigations_path = args.knowledge_dir / "investigation_queue.csv"
    events_path = args.knowledge_dir / "transaction_events.csv"
    initialize_csv(rules_path, RULE_FIELDS)
    initialize_csv(overrides_path, OVERRIDE_FIELDS)
    initialize_csv(allocations_path, ALLOCATION_FIELDS)
    initialize_csv(investigations_path, INVESTIGATION_FIELDS)
    initialize_csv(events_path, EVENT_FIELDS)
    investigations = load_investigations(investigations_path)
    events = load_events(events_path)
    decision_log = args.knowledge_dir / "decision_log.md"
    if not decision_log.exists():
        decision_log.write_text("# Decisões de classificação\n", encoding="utf-8")

    rows = read_csv(args.transactions)
    rules = load_rules(args.base_rules, rules_path)
    overrides = load_overrides(overrides_path)
    allocations = load_allocations(allocations_path)
    validate_knowledge_references(
        rows,
        rules,
        overrides,
        allocations,
        investigations,
        events,
    )
    groups = build_groups(
        rows,
        rules,
        overrides,
        allocations,
    )
    unresolved = sort_groups_by_materiality(
        [row for row in groups if row["missing_fields"]]
    )
    write_csv_atomic(args.output_dir / "classification_groups.csv", groups, GROUP_FIELDS)
    write_csv_atomic(args.output_dir / "classification_queue.csv", unresolved, GROUP_FIELDS)
    print(
        f"Classificação: {len(groups)} grupos; "
        f"{len(groups) - len(unresolved)} resolvidos e {len(unresolved)} pendentes."
    )
    print(args.output_dir / "classification_queue.csv")


if __name__ == "__main__":
    main()
