import json

import pytest

from finance_analysis.daily import CONSOLIDATED_ACCOUNT
from finance_analysis.visualizations import (
    TEMPORAL_CHARTS,
    VisualizationInputs,
    build_charts,
    build_daily_balances_chart,
    build_daily_flows_chart,
    build_monthly_result_chart,
    export_charts,
)


def inputs() -> VisualizationInputs:
    daily_balances = []
    for day, total, bb, itau in (
        ("2026-01-01", "300000", "100000", "200000"),
        ("2026-01-02", "320000", "110000", "210000"),
    ):
        for account_id, balance, institution in (
            (CONSOLIDATED_ACCOUNT, total, "Consolidado"),
            ("banco_do_brasil_conta_corrente", bb, "Banco do Brasil"),
            ("itau_conta_corrente", itau, "Itaú"),
        ):
            daily_balances.append(
                {
                    "date": day,
                    "account_id": account_id,
                    "institution": institution,
                    "analysis_balance_cents": balance,
                }
            )
    daily_flows = [
        {
            "date": "2026-01-01",
            "account_id": CONSOLIDATED_ACCOUNT,
            "external_income_cents": "600000",
            "external_expense_cents": "350000",
        },
        {
            "date": "2026-01-02",
            "account_id": CONSOLIDATED_ACCOUNT,
            "external_income_cents": "0",
            "external_expense_cents": "10000",
        },
    ]
    reserve_daily = [
        {
            "date": "2026-01-01",
            "closing_balance_cents": "1000000",
            "is_anchor_date": "true",
        },
        {
            "date": "2026-01-02",
            "closing_balance_cents": "1001000",
            "is_anchor_date": "false",
        },
    ]
    reserve_monthly = [
        {
            "month": "2026-01",
            "contribution_cents": "200000",
            "deporte_cents": "50000",
            "net_contribution_cents": "150000",
        },
        {
            "month": "2026-02",
            "contribution_cents": "0",
            "deporte_cents": "10000",
            "net_contribution_cents": "-10000",
        },
    ]
    monthly_metrics = [
        {
            "month": "2026-01",
            "is_complete_month": "true",
            "account_coverage": "all_available_accounts",
            "external_income_cents": "600000",
            "net_external_expense_cents": "350000",
            "gross_external_expense_cents": "350000",
            "savings_cents": "250000",
            "recurring_living_cost_cents": "300000",
            "expanded_living_cost_cents": "350000",
            "survival_index_months": "3.3333",
        },
        {
            "month": "2026-02",
            "is_complete_month": "false",
            "account_coverage": "all_available_accounts",
            "external_income_cents": "100000",
            "net_external_expense_cents": "80000",
            "gross_external_expense_cents": "80000",
            "savings_cents": "20000",
            "recurring_living_cost_cents": "70000",
            "expanded_living_cost_cents": "80000",
            "survival_index_months": "",
        },
    ]
    monthly_categories = [
        {
            "month": "2026-01",
            "category": "Moradia",
            "recurring_cost_cents": "200000",
            "atypical_expense_cents": "50000",
            "outside_living_cost_cents": "0",
            "unclassified_outflow_cents": "0",
        },
        {
            "month": "2026-01",
            "category": "A revisar",
            "recurring_cost_cents": "0",
            "atypical_expense_cents": "0",
            "outside_living_cost_cents": "0",
            "unclassified_outflow_cents": "10000",
        },
    ]
    peak_candidates = [
        {
            "start_date": "2026-01-15",
            "amount_cents": "100000",
            "label": "Caução",
            "classification_status": "known",
            "is_peak": "true",
        },
        {
            "start_date": "2026-01-20",
            "amount_cents": "1000",
            "label": "Pequeno",
            "classification_status": "known",
            "is_peak": "false",
        },
    ]
    peaks_monthly = [
        {
            "month": "2026-01",
            "peak_count": "1",
            "peak_total_cents": "100000",
            "average_peak_cents": "100000",
        },
        {
            "month": "2026-02",
            "peak_count": "0",
            "peak_total_cents": "0",
            "average_peak_cents": "0",
        },
    ]
    return VisualizationInputs(
        daily_balances=daily_balances,
        daily_flows=daily_flows,
        reserve_daily=reserve_daily,
        reserve_monthly=reserve_monthly,
        monthly_metrics=monthly_metrics,
        monthly_categories=monthly_categories,
        peak_candidates=peak_candidates,
        peaks_monthly=peaks_monthly,
    )


def test_build_charts_creates_the_eight_planned_visualizations():
    charts = build_charts(inputs())

    assert [chart.slug for chart in charts] == [
        "01_saldos_diarios",
        "02_receitas_gastos_diarios",
        "03_resultado_mensal",
        "04_custo_de_vida_mensal",
        "05_cofrinho",
        "06_indice_sobrevivencia",
        "07_gastos_por_categoria",
        "08_picos_de_gasto",
    ]


def test_temporal_charts_use_only_connected_lines_with_markers():
    charts = build_charts(inputs())

    for chart in charts:
        if chart.slug not in TEMPORAL_CHARTS:
            continue
        assert all(trace.type == "scatter" for trace in chart.figure.data)
        assert all(trace.mode == "lines+markers" for trace in chart.figure.data)


def test_every_temporal_axis_has_monthly_ticks():
    charts = build_charts(inputs())

    for chart in charts:
        if chart.slug not in TEMPORAL_CHARTS:
            continue
        assert all(axis.dtick == "M1" for axis in chart.figure.select_xaxes())


def test_no_chart_uses_pie_or_doughnut():
    charts = build_charts(inputs())

    assert all(
        trace.type not in {"pie", "sunburst"}
        for chart in charts
        for trace in chart.figure.data
    )


def test_every_axis_has_an_explicit_title():
    charts = build_charts(inputs())

    for chart in charts:
        assert all(axis.title.text for axis in chart.figure.select_xaxes())
        assert all(axis.title.text for axis in chart.figure.select_yaxes())


def test_category_ranking_uses_horizontal_bars_only():
    chart = next(chart for chart in build_charts(inputs()) if chart.slug.startswith("07_"))

    assert all(trace.type == "bar" for trace in chart.figure.data)
    assert all(trace.orientation == "h" for trace in chart.figure.data)


def test_monthly_chart_values_match_source_cents_in_reais():
    chart = build_monthly_result_chart(inputs().monthly_metrics)

    assert list(chart.figure.data[0].y) == [6000.0, 1000.0]
    assert list(chart.figure.data[1].y) == [3500.0, 800.0]
    assert list(chart.figure.data[2].y) == [2500.0, 200.0]


def test_daily_expenses_are_reflected_and_net_series_is_named_precisely():
    chart = build_daily_flows_chart(inputs().daily_flows)

    assert list(chart.figure.data[1].y) == [-3500.0, -100.0]
    assert chart.figure.data[2].name == "Fluxo líquido externo"
    assert list(chart.figure.data[2].y) == [2500.0, -100.0]
    assert chart.figure.layout.yaxis.dtick == 1000


def test_daily_balance_legend_has_space_above_subplot_title():
    data = inputs()
    chart = build_daily_balances_chart(data.daily_balances, data.reserve_daily)
    accounts_title = next(
        annotation
        for annotation in chart.figure.layout.annotations
        if annotation.text == "Contas correntes"
    )

    assert chart.figure.layout.legend.y - accounts_title.y >= 0.05
    assert chart.figure.layout.legend.yanchor == "top"


def test_incomplete_month_uses_open_marker():
    chart = build_monthly_result_chart(inputs().monthly_metrics)

    assert chart.figure.data[0].marker.symbol[-1] == "circle-open"


def test_missing_required_column_fails_explicitly():
    bad_rows = [{"month": "2026-01"}]

    with pytest.raises(ValueError, match="não contém as colunas"):
        build_monthly_result_chart(bad_rows)


def test_static_export_writes_png_and_auditable_manifest(tmp_path):
    chart = build_monthly_result_chart(inputs().monthly_metrics)

    exported = export_charts([chart], tmp_path)

    assert exported == [tmp_path / "03_resultado_mensal.png"]
    assert exported[0].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest[0]["sources"] == ["monthly_metrics.csv"]
    assert manifest[0]["period"] == "2026-01 a 2026-02"
