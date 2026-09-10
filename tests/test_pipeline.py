from __future__ import annotations

import subprocess

from scripts.run_pipeline import STEPS, command_for_step, run_pipeline


def test_pipeline_orders_every_reproducible_stage() -> None:
    assert [step.number for step in STEPS] == [1, 2, 3, 4, 5, 7, 8, 9, 10]
    assert command_for_step(STEPS[-1])[-1] == "scripts/10_build_report.py"


def test_pipeline_refreshes_cdi_only_when_requested(monkeypatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, check: commands.append(command),
    )

    run_pipeline(refresh_cdi=True)

    assert len(commands) == 10
    assert commands[5][-1] == "scripts/06_fetch_cdi_rates.py"
    assert commands[-1][-1] == "scripts/10_build_report.py"
