#!/usr/bin/env python3
from argparse import ArgumentParser
from pathlib import Path

from finance_analysis.classification import read_csv
from finance_analysis.visualizations import (
    VisualizationInputs,
    build_charts,
    export_charts,
)


def main() -> None:
    parser = ArgumentParser(description="Gera os gráficos estáticos da análise financeira.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/derived"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/reports/figures"),
    )
    args = parser.parse_args()

    inputs = VisualizationInputs(
        daily_balances=read_csv(args.input_dir / "daily_balances.csv"),
        daily_flows=read_csv(args.input_dir / "daily_flows.csv"),
        reserve_daily=read_csv(args.input_dir / "cofrinho_daily.csv"),
        reserve_monthly=read_csv(args.input_dir / "cofrinho_monthly.csv"),
        monthly_metrics=read_csv(args.input_dir / "monthly_metrics.csv"),
        monthly_categories=read_csv(args.input_dir / "monthly_category_spending.csv"),
        peak_candidates=read_csv(args.input_dir / "spending_peak_candidates.csv"),
        peaks_monthly=read_csv(args.input_dir / "spending_peaks_monthly.csv"),
    )
    charts = build_charts(inputs)
    exported = export_charts(charts, args.output_dir)
    for path in exported:
        print(path)
    print(args.output_dir / "manifest.json")


if __name__ == "__main__":
    main()
