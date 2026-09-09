#!/usr/bin/env python3
from argparse import ArgumentParser
from pathlib import Path

from finance_analysis.config import load_accounts
from finance_analysis.ingestion import build_inventory, fieldnames, write_csv_atomic


def main() -> None:
    parser = ArgumentParser(description="Inventaria fontes financeiras sem alterá-las.")
    parser.add_argument("--source-dir", type=Path, default=Path("data/sources"))
    parser.add_argument("--output", type=Path, default=Path("data/derived/source_inventory.csv"))
    parser.add_argument("--accounts", type=Path, default=Path("config/accounts.toml"))
    args = parser.parse_args()

    rows = build_inventory(args.source_dir, load_accounts(args.accounts))
    write_csv_atomic(args.output, rows, fieldnames(rows))
    parsed = sum(row["status"] == "parsed" for row in rows)
    unsupported = sum(row["supported"] == "false" for row in rows)
    duplicates = sum(bool(row["duplicate_of"]) for row in rows)
    print(
        f"Inventário: {len(rows)} arquivos, {parsed} OFX analisados, "
        f"{unsupported} auxiliares e {duplicates} duplicados."
    )
    print(args.output)


if __name__ == "__main__":
    main()
