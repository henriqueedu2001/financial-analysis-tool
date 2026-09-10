#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineStep:
    number: int
    name: str
    script: str


STEPS = (
    PipelineStep(1, "inventário dos extratos", "scripts/01_inventory_sources.py"),
    PipelineStep(2, "normalização e deduplicação", "scripts/02_build_canonical.py"),
    PipelineStep(3, "preparação da classificação", "scripts/03_prepare_classification.py"),
    PipelineStep(4, "aplicação da classificação", "scripts/04_apply_classification.py"),
    PipelineStep(5, "séries diárias", "scripts/05_build_daily_series.py"),
    PipelineStep(7, "reconstrução do cofrinho", "scripts/07_build_cofrinho.py"),
    PipelineStep(8, "métricas e picos", "scripts/08_build_metrics.py"),
    PipelineStep(9, "gráficos", "scripts/09_build_visualizations.py"),
    PipelineStep(10, "relatório LaTeX", "scripts/10_build_report.py"),
)


def command_for_step(step: PipelineStep) -> list[str]:
    return [sys.executable, step.script]


def run_pipeline(*, refresh_cdi: bool = False) -> None:
    steps = list(STEPS)
    if refresh_cdi:
        steps.insert(5, PipelineStep(6, "atualização do CDI", "scripts/06_fetch_cdi_rates.py"))
    for position, step in enumerate(steps, start=1):
        print(
            f"\n[{position}/{len(steps)}] Fase técnica {step.number}: {step.name}",
            flush=True,
        )
        subprocess.run(command_for_step(step), check=True)
    print("\nPipeline concluído: output/pdf/analise_financeira_pessoal.pdf", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa toda a análise e produz o relatório final."
    )
    parser.add_argument(
        "--refresh-cdi",
        action="store_true",
        help="Atualiza o CDI oficial antes de reconstruir o cofrinho.",
    )
    args = parser.parse_args()
    run_pipeline(refresh_cdi=args.refresh_cdi)


if __name__ == "__main__":
    main()
