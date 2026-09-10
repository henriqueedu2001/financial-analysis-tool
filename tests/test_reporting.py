from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from finance_analysis.reporting import (
    EXPECTED_CHARTS,
    ReportData,
    calculate_report_summary,
    format_brl,
    latex_escape,
    load_chart_manifest,
    render_latex,
    resolve_tectonic,
    write_latex,
)


def report_data() -> ReportData:
    monthly = [
        {
            "month": "2026-01",
            "is_complete_month": "true",
            "account_coverage": "all_available_accounts",
            "external_income_cents": "600000",
            "gross_external_expense_cents": "400000",
            "net_external_expense_cents": "390000",
            "savings_cents": "210000",
            "recurring_living_cost_cents": "300000",
            "reserve_contribution_cents": "200000",
            "deporte_cents": "50000",
            "net_reserve_contribution_cents": "150000",
            "survival_index_months": "8.0000",
            "atypical_expense_cents": "50000",
        },
        {
            "month": "2026-02",
            "is_complete_month": "true",
            "account_coverage": "all_available_accounts",
            "external_income_cents": "500000",
            "gross_external_expense_cents": "550000",
            "net_external_expense_cents": "540000",
            "savings_cents": "-40000",
            "recurring_living_cost_cents": "400000",
            "reserve_contribution_cents": "100000",
            "deporte_cents": "200000",
            "net_reserve_contribution_cents": "-100000",
            "survival_index_months": "6.5000",
            "atypical_expense_cents": "200000",
        },
        {
            "month": "2026-03",
            "is_complete_month": "false",
            "account_coverage": "all_available_accounts",
            "external_income_cents": "999999",
            "gross_external_expense_cents": "999999",
            "net_external_expense_cents": "999999",
            "savings_cents": "0",
            "recurring_living_cost_cents": "999999",
            "reserve_contribution_cents": "0",
            "deporte_cents": "0",
            "net_reserve_contribution_cents": "0",
            "survival_index_months": "",
            "atypical_expense_cents": "0",
        },
    ]
    return ReportData(
        transactions=[
            {"operation_date": "2026-01-02", "nature": "expense", "amount_cents": "-1000"},
            {
                "operation_date": "2026-01-03",
                "nature": "outflow_unclassified",
                "amount_cents": "-2000",
            },
            {"operation_date": "2026-02-04", "nature": "income", "amount_cents": "5000"},
        ],
        monthly_metrics=monthly,
        monthly_categories=[
            {
                "month": "2026-01",
                "category": "Moradia",
                "total_observed_outflow_cents": "200000",
                "unclassified_outflow_cents": "0",
            },
            {
                "month": "2026-02",
                "category": "Não classificado",
                "total_observed_outflow_cents": "50000",
                "unclassified_outflow_cents": "50000",
            },
        ],
        metrics_summary=[
            {
                "analysis_start_month": "2026-01",
                "analysis_end_month": "2026-03",
                "last_complete_month": "2026-02",
                "average_recurring_living_cost_cents": "350000",
                "median_recurring_living_cost_cents": "350000",
                "standard_deviation_living_cost_cents": "50000",
                "coefficient_of_variation": "0.1429",
                "last_complete_recurring_living_cost_cents": "400000",
                "last_complete_reserve_balance_cents": "2600000",
                "last_complete_survival_index_months": "6.5000",
            }
        ],
        peak_candidates=[
            {
                "start_date": "2026-01-10",
                "label": "Evento & teste",
                "category": "Moradia",
                "amount_cents": "100000",
                "is_peak": "true",
            },
            {
                "start_date": "2026-03-10",
                "label": "Mês parcial",
                "category": "Compras",
                "amount_cents": "80000",
                "is_peak": "true",
            },
        ],
        peaks_summary=[
            {
                "peak_count": "2",
                "peak_total_cents": "180000",
                "average_peak_cents": "90000",
                "median_peak_cents": "90000",
                "largest_peak_cents": "100000",
                "smallest_peak_cents": "80000",
                "unknown_peak_count": "0",
            }
        ],
        metrics_quality=[
            {"check_type": "savings_identity", "status": "balanced", "details": "ok"}
        ],
        reserve_monthly=[
            {
                "month": "2026-01",
                "opening_balance_cents": "2500000",
                "closing_balance_cents": "2660000",
                "estimated_interest_cents": "10000",
                "is_complete_month": "true",
            },
            {
                "month": "2026-02",
                "opening_balance_cents": "2660000",
                "closing_balance_cents": "2600000",
                "estimated_interest_cents": "40000",
                "is_complete_month": "true",
            },
        ],
        reserve_quality=[
            {"check_type": "anchor_balance", "status": "balanced", "details": "2026-02-28"}
        ],
    )


def chart_files(path: Path) -> None:
    manifest = []
    for chart_id in EXPECTED_CHARTS:
        filename = f"{chart_id}.png"
        (path / filename).write_bytes(b"PNG")
        manifest.append(
            {
                "id": chart_id,
                "file": filename,
                "period": "2026-01 a 2026-02",
                "description": "Descrição",
                "sources": ["fixture.csv"],
            }
        )
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_report_summary_uses_only_complete_comparable_months() -> None:
    summary = calculate_report_summary(report_data())

    assert summary.comparable_months == 2
    assert summary.total_income_cents == 1_100_000
    assert summary.total_savings_cents == 170_000
    assert summary.positive_savings_months == 1
    assert summary.worst_savings_month == "2026-02"
    assert summary.savings_without_worst_month_cents == 210_000
    assert summary.minimum_living_cost_month == "2026-01"
    assert summary.maximum_living_cost_month == "2026-02"


def test_report_summary_keeps_savings_and_reserve_flow_distinct() -> None:
    summary = calculate_report_summary(report_data())

    assert summary.total_savings_cents == 170_000
    assert summary.net_reserve_contribution_cents == 50_000
    assert summary.reserve_interest_cents == 50_000


def test_report_summary_calculates_survival_range_without_float() -> None:
    summary = calculate_report_summary(report_data())

    assert summary.latest_survival_months == Decimal("6.5000")
    assert summary.median_survival_months == Decimal("7.2500")
    assert summary.conservative_survival_months == Decimal("6.5000")


def test_money_and_latex_formatting_are_locale_safe() -> None:
    assert format_brl(-135895) == "-R$ 1.358,95"
    assert latex_escape(r"A&B_50%\\") == r"A\&B\_50\%\textbackslash{}\textbackslash{}"


def test_chart_manifest_requires_all_eight_charts_in_order(tmp_path: Path) -> None:
    chart_files(tmp_path)

    charts = load_chart_manifest(tmp_path)

    assert tuple(charts) == EXPECTED_CHARTS


def test_chart_manifest_rejects_missing_chart(tmp_path: Path) -> None:
    chart_files(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())[:-1]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="oito gráficos"):
        load_chart_manifest(tmp_path)


def test_latex_render_fills_financial_and_figure_placeholders(tmp_path: Path) -> None:
    figures = tmp_path / "figures"
    figures.mkdir()
    chart_files(figures)
    template = tmp_path / "template.tex"
    template.write_text(
        "@@TOTAL_INCOME@@|@@CHART_01_SALDOS_DIARIOS@@|@@PEAK_ROWS@@",
        encoding="utf-8",
    )

    source, summary = render_latex(report_data(), figures, template)

    assert "R\\$ 11.000,00" in source
    assert "01\\_saldos\\_diarios.png" in source
    assert "Evento \\& teste" in source
    assert "@@" not in source
    assert summary.last_complete_month == "2026-02"


def test_latex_source_is_written_atomically(tmp_path: Path) -> None:
    output = tmp_path / "private" / "report.tex"

    write_latex("conteúdo", output)

    assert output.read_text(encoding="utf-8") == "conteúdo"


def test_explicit_tectonic_path_has_precedence(tmp_path: Path) -> None:
    engine = tmp_path / "tectonic"
    engine.write_text("binário", encoding="utf-8")
    engine.chmod(0o755)

    assert resolve_tectonic(engine) == engine.resolve()
