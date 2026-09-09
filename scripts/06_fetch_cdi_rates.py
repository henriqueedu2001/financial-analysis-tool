#!/usr/bin/env python3
from argparse import ArgumentParser
from datetime import date
from pathlib import Path

from finance_analysis.cdi import fetch_cdi_rates
from finance_analysis.ingestion import fieldnames, write_csv_atomic


def main() -> None:
    parser = ArgumentParser(description="Baixa a taxa CDI diária oficial do SGS/BCB.")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("config/reference/cdi_daily.csv"),
    )
    args = parser.parse_args()

    rows = fetch_cdi_rates(args.start, args.end)
    write_csv_atomic(args.output, rows, fieldnames(rows))
    print(f"{len(rows)} taxas CDI oficiais: {args.output}")


if __name__ == "__main__":
    main()
