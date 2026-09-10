#!/usr/bin/env python3
from argparse import ArgumentParser
from pathlib import Path

from finance_analysis.reporting import (
    compile_latex,
    load_report_data,
    render_latex,
    write_latex,
)


def main() -> None:
    parser = ArgumentParser(description="Gera e compila o relatório financeiro em LaTeX.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/derived"))
    parser.add_argument("--figures-dir", type=Path, default=Path("data/reports/figures"))
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("config/report_template.tex"),
    )
    parser.add_argument(
        "--tex-output",
        type=Path,
        default=Path("output/latex/analise_financeira_pessoal.tex"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/pdf/analise_financeira_pessoal.pdf"),
    )
    parser.add_argument("--tectonic", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--only-cached", action="store_true")
    args = parser.parse_args()

    source, summary = render_latex(
        load_report_data(args.input_dir),
        args.figures_dir,
        args.template,
    )
    write_latex(source, args.tex_output)
    compile_latex(
        args.tex_output,
        args.output,
        tectonic_path=args.tectonic,
        cache_dir=args.cache_dir,
        only_cached=args.only_cached,
    )
    print(args.tex_output)
    print(args.output)
    print(
        f"Último mês completo: {summary.last_complete_month}; "
        f"{summary.comparable_months} meses comparáveis."
    )


if __name__ == "__main__":
    main()
