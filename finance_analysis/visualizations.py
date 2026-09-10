from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from finance_analysis.daily import CONSOLIDATED_ACCOUNT

COLORS = {
    "primary": "#2166AC",
    "secondary": "#B2182B",
    "positive": "#1B7837",
    "negative": "#B2182B",
    "neutral": "#5B6573",
    "accent": "#7B3294",
    "warning": "#D97706",
    "light": "#C7D5E0",
}

ACCOUNT_LABELS = {
    CONSOLIDATED_ACCOUNT: "Contas correntes",
    "banco_do_brasil_conta_corrente": "Banco do Brasil",
    "itau_conta_corrente": "Itaú",
}

TEMPORAL_CHARTS = {
    "01_saldos_diarios",
    "02_receitas_gastos_diarios",
    "03_resultado_mensal",
    "04_custo_de_vida_mensal",
    "05_cofrinho",
    "06_indice_sobrevivencia",
    "08_picos_de_gasto",
}


@dataclass(frozen=True)
class ChartArtifact:
    slug: str
    title: str
    description: str
    period: str
    sources: tuple[str, ...]
    figure: go.Figure

    @property
    def filename(self) -> str:
        return f"{self.slug}.png"


@dataclass(frozen=True)
class VisualizationInputs:
    daily_balances: list[dict[str, str]]
    daily_flows: list[dict[str, str]]
    reserve_daily: list[dict[str, str]]
    reserve_monthly: list[dict[str, str]]
    monthly_metrics: list[dict[str, str]]
    monthly_categories: list[dict[str, str]]
    peak_candidates: list[dict[str, str]]
    peaks_monthly: list[dict[str, str]]


def _require_fields(name: str, rows: list[dict[str, str]], fields: set[str]) -> None:
    if not rows:
        raise ValueError(f"{name} não contém linhas")
    missing = fields - set(rows[0])
    if missing:
        fields_text = ", ".join(sorted(missing))
        raise ValueError(f"{name} não contém as colunas: {fields_text}")


def _money(cents: str | int) -> float:
    return float(Decimal(str(cents)) / Decimal("100"))


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _month_date(value: str) -> date:
    return date.fromisoformat(f"{value}-01")


def _period(values: list[str]) -> str:
    return f"{min(values)} a {max(values)}"


def _line(
    *,
    x: list[date],
    y: list[float | int],
    name: str,
    color: str,
    symbol: str | list[str] = "circle",
    dash: str = "solid",
    customdata: list[Any] | None = None,
    hovertemplate: str | None = None,
) -> go.Scatter:
    return go.Scatter(
        x=x,
        y=y,
        name=name,
        mode="lines+markers",
        line={"color": color, "width": 2, "dash": dash},
        marker={"color": color, "size": 5, "symbol": symbol},
        customdata=customdata,
        hovertemplate=hovertemplate,
    )


def _style(
    figure: go.Figure,
    title: str,
    *,
    height: int = 760,
    legend: bool = True,
) -> go.Figure:
    figure.update_layout(
        title={"text": title, "x": 0.02, "xanchor": "left"},
        template="plotly_white",
        width=1500,
        height=height,
        margin={"l": 95, "r": 45, "t": 105, "b": 75},
        font={"family": "DejaVu Sans", "size": 15, "color": "#25313C"},
        hovermode="x unified",
        showlegend=legend,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "x": 0.01},
        paper_bgcolor="white",
        plot_bgcolor="white",
    )
    figure.update_xaxes(
        showgrid=False,
        zeroline=False,
        linecolor="#768692",
        ticks="outside",
    )
    figure.update_yaxes(
        showgrid=True,
        gridcolor="#E2E8ED",
        zeroline=True,
        zerolinecolor="#AAB6BF",
        separatethousands=True,
        ticks="outside",
    )
    return figure


def _money_axis(figure: go.Figure, *, row: int | None = None) -> None:
    options: dict[str, Any] = {
        "tickprefix": "R$ ",
        "tickformat": ",.0f",
        "separatethousands": True,
    }
    if row is None:
        figure.update_yaxes(**options)
    else:
        figure.update_yaxes(row=row, col=1, **options)


def _date_axis(
    figure: go.Figure,
    values: list[date],
    *,
    row: int | None = None,
) -> None:
    options: dict[str, Any] = {
        "range": [min(values) - timedelta(days=5), max(values) + timedelta(days=5)],
        "tickformat": "%m/%Y",
        "dtick": "M1",
    }
    if row is None:
        figure.update_xaxes(**options)
    else:
        figure.update_xaxes(row=row, col=1, **options)


def _month_symbols(rows: list[dict[str, str]]) -> list[str]:
    return ["circle" if row["is_complete_month"] == "true" else "circle-open" for row in rows]


def build_daily_balances_chart(
    balances: list[dict[str, str]], reserve_daily: list[dict[str, str]]
) -> ChartArtifact:
    _require_fields(
        "daily_balances.csv",
        balances,
        {"date", "account_id", "analysis_balance_cents"},
    )
    _require_fields(
        "cofrinho_daily.csv",
        reserve_daily,
        {"date", "closing_balance_cents"},
    )
    figure = make_subplots(
        rows=2,
        cols=1,
        vertical_spacing=0.2,
        subplot_titles=("Contas correntes", "Cofrinho e total monitorado"),
    )
    balance_by_account: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in balances:
        balance_by_account[row["account_id"]].append(row)
    account_colors = {
        CONSOLIDATED_ACCOUNT: COLORS["neutral"],
        "banco_do_brasil_conta_corrente": COLORS["primary"],
        "itau_conta_corrente": COLORS["secondary"],
    }
    for account_id in (
        CONSOLIDATED_ACCOUNT,
        "banco_do_brasil_conta_corrente",
        "itau_conta_corrente",
    ):
        rows = sorted(balance_by_account.get(account_id, []), key=lambda row: row["date"])
        if not rows:
            continue
        figure.add_trace(
            _line(
                x=[_date(row["date"]) for row in rows],
                y=[_money(row["analysis_balance_cents"]) for row in rows],
                name=ACCOUNT_LABELS[account_id],
                color=account_colors[account_id],
                dash="dash" if account_id == CONSOLIDATED_ACCOUNT else "solid",
                hovertemplate="%{x|%d/%m/%Y}<br>%{fullData.name}: R$ %{y:,.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    current_by_date = {
        row["date"]: int(row["analysis_balance_cents"])
        for row in balances
        if row["account_id"] == CONSOLIDATED_ACCOUNT
    }
    reserve_rows = sorted(reserve_daily, key=lambda row: row["date"])
    figure.add_trace(
        _line(
            x=[_date(row["date"]) for row in reserve_rows],
            y=[_money(row["closing_balance_cents"]) for row in reserve_rows],
            name="Cofrinho estimado",
            color=COLORS["accent"],
            symbol="diamond-open",
            hovertemplate="%{x|%d/%m/%Y}<br>Cofrinho estimado: R$ %{y:,.2f}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    tracked_rows = [row for row in reserve_rows if row["date"] in current_by_date]
    figure.add_trace(
        _line(
            x=[_date(row["date"]) for row in tracked_rows],
            y=[
                _money(int(row["closing_balance_cents"]) + current_by_date[row["date"]])
                for row in tracked_rows
            ],
            name="Total monitorado",
            color=COLORS["positive"],
            hovertemplate="%{x|%d/%m/%Y}<br>Total monitorado: R$ %{y:,.2f}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    _style(figure, "Saldos diários observados e estimados", height=960)
    figure.update_layout(
        title={"y": 0.99, "yanchor": "top"},
        legend={"y": 1.08, "yanchor": "top"},
        margin={"t": 110},
    )
    figure.layout.yaxis.domain = (0.58, 0.96)
    figure.layout.yaxis2.domain = (0.0, 0.36)
    figure.layout.annotations[0].y = 1.01
    figure.layout.annotations[1].y = 0.39
    for row in (1, 2):
        figure.update_xaxes(title_text="Data", row=row, col=1)
        figure.update_yaxes(title_text="Saldo (R$)", row=row, col=1)
        _money_axis(figure, row=row)
    _date_axis(
        figure,
        [_date(row["date"]) for row in balances],
        row=1,
    )
    _date_axis(
        figure,
        [_date(row["date"]) for row in reserve_rows],
        row=2,
    )
    dates = [row["date"] for row in balances]
    return ChartArtifact(
        slug="01_saldos_diarios",
        title="Saldos diários observados e estimados",
        description=(
            "Saldo analítico das contas correntes, saldo reconstruído do cofrinho e soma "
            "monitorada no período comum."
        ),
        period=_period(dates),
        sources=("daily_balances.csv", "cofrinho_daily.csv"),
        figure=figure,
    )


def build_daily_flows_chart(rows: list[dict[str, str]]) -> ChartArtifact:
    _require_fields(
        "daily_flows.csv",
        rows,
        {"date", "account_id", "external_income_cents", "external_expense_cents"},
    )
    consolidated = sorted(
        (row for row in rows if row["account_id"] == CONSOLIDATED_ACCOUNT),
        key=lambda row: row["date"],
    )
    if not consolidated:
        raise ValueError("daily_flows.csv não contém a série consolidada")
    dates = [_date(row["date"]) for row in consolidated]
    income = [_money(row["external_income_cents"]) for row in consolidated]
    expenses = [-_money(row["external_expense_cents"]) for row in consolidated]
    net_flow = [entry + expense for entry, expense in zip(income, expenses, strict=True)]
    figure = go.Figure()
    figure.add_trace(
        _line(
            x=dates,
            y=income,
            name="Receitas externas",
            color=COLORS["positive"],
            hovertemplate="%{x|%d/%m/%Y}<br>Receitas: R$ %{y:,.2f}<extra></extra>",
        )
    )
    figure.add_trace(
        _line(
            x=dates,
            y=expenses,
            name="Despesas externas",
            color=COLORS["negative"],
            symbol="square-open",
            hovertemplate="%{x|%d/%m/%Y}<br>Despesas: R$ %{y:,.2f}<extra></extra>",
        )
    )
    figure.add_trace(
        _line(
            x=dates,
            y=net_flow,
            name="Fluxo líquido externo",
            color=COLORS["primary"],
            symbol="diamond",
            dash="dot",
            hovertemplate=(
                "%{x|%d/%m/%Y}<br>Fluxo líquido externo: R$ %{y:,.2f}<extra></extra>"
            ),
        )
    )
    _style(figure, "Receitas e gastos externos por dia")
    figure.update_xaxes(title_text="Data")
    figure.update_yaxes(title_text="Valor diário (R$)", dtick=1000)
    _money_axis(figure)
    _date_axis(figure, dates)
    return ChartArtifact(
        slug="02_receitas_gastos_diarios",
        title="Receitas e gastos externos por dia",
        description=(
            "Entradas e saídas externas consolidadas. Transferências próprias não entram "
            "nas séries."
        ),
        period=_period([row["date"] for row in consolidated]),
        sources=("daily_flows.csv",),
        figure=figure,
    )


def build_monthly_result_chart(rows: list[dict[str, str]]) -> ChartArtifact:
    _require_fields(
        "monthly_metrics.csv",
        rows,
        {
            "month",
            "is_complete_month",
            "external_income_cents",
            "net_external_expense_cents",
            "savings_cents",
        },
    )
    ordered = sorted(rows, key=lambda row: row["month"])
    months = [_month_date(row["month"]) for row in ordered]
    symbols = _month_symbols(ordered)
    figure = go.Figure()
    series = (
        ("Receitas externas", "external_income_cents", COLORS["positive"], "circle"),
        ("Despesas externas líquidas", "net_external_expense_cents", COLORS["negative"], "square"),
        ("Poupança gerada", "savings_cents", COLORS["primary"], "diamond"),
    )
    for name, field, color, base_symbol in series:
        marker_symbols = [
            base_symbol if symbol == "circle" else f"{base_symbol}-open" for symbol in symbols
        ]
        figure.add_trace(
            _line(
                x=months,
                y=[_money(row[field]) for row in ordered],
                name=name,
                color=color,
                symbol=marker_symbols,
                hovertemplate="%{x|%m/%Y}<br>%{fullData.name}: R$ %{y:,.2f}<extra></extra>",
            )
        )
    _style(figure, "Receitas, despesas e poupança por mês")
    figure.update_xaxes(title_text="Mês")
    figure.update_yaxes(title_text="Valor mensal (R$)")
    _money_axis(figure)
    _date_axis(figure, months)
    return ChartArtifact(
        slug="03_resultado_mensal",
        title="Receitas, despesas e poupança por mês",
        description="Círculos abertos identificam meses incompletos.",
        period=_period([row["month"] for row in ordered]),
        sources=("monthly_metrics.csv",),
        figure=figure,
    )


def build_living_cost_chart(rows: list[dict[str, str]]) -> ChartArtifact:
    _require_fields(
        "monthly_metrics.csv",
        rows,
        {
            "month",
            "is_complete_month",
            "recurring_living_cost_cents",
            "expanded_living_cost_cents",
            "gross_external_expense_cents",
        },
    )
    ordered = sorted(rows, key=lambda row: row["month"])
    months = [_month_date(row["month"]) for row in ordered]
    symbols = _month_symbols(ordered)
    figure = go.Figure()
    series = (
        ("Custo recorrente", "recurring_living_cost_cents", COLORS["primary"], "circle"),
        ("Custo com atípicos", "expanded_living_cost_cents", COLORS["warning"], "diamond"),
        ("Despesa externa bruta", "gross_external_expense_cents", COLORS["neutral"], "square"),
    )
    for name, field, color, base_symbol in series:
        marker_symbols = [
            base_symbol if symbol == "circle" else f"{base_symbol}-open" for symbol in symbols
        ]
        figure.add_trace(
            _line(
                x=months,
                y=[_money(row[field]) for row in ordered],
                name=name,
                color=color,
                symbol=marker_symbols,
                hovertemplate="%{x|%m/%Y}<br>%{fullData.name}: R$ %{y:,.2f}<extra></extra>",
            )
        )
    _style(figure, "Custo de vida e despesas por mês")
    figure.update_xaxes(title_text="Mês")
    figure.update_yaxes(title_text="Valor mensal (R$)", rangemode="tozero")
    _money_axis(figure)
    _date_axis(figure, months)
    return ChartArtifact(
        slug="04_custo_de_vida_mensal",
        title="Custo de vida e despesas por mês",
        description=(
            "O custo recorrente exclui gastos atípicos. Marcadores abertos indicam meses "
            "incompletos."
        ),
        period=_period([row["month"] for row in ordered]),
        sources=("monthly_metrics.csv",),
        figure=figure,
    )


def build_reserve_chart(
    reserve_daily: list[dict[str, str]], reserve_monthly: list[dict[str, str]]
) -> ChartArtifact:
    _require_fields(
        "cofrinho_daily.csv",
        reserve_daily,
        {"date", "closing_balance_cents", "is_anchor_date"},
    )
    _require_fields(
        "cofrinho_monthly.csv",
        reserve_monthly,
        {"month", "contribution_cents", "deporte_cents", "net_contribution_cents"},
    )
    figure = make_subplots(
        rows=2,
        cols=1,
        vertical_spacing=0.14,
        subplot_titles=("Saldo estimado do cofrinho", "Aportes e deportes mensais"),
    )
    daily = sorted(reserve_daily, key=lambda row: row["date"])
    monthly = sorted(reserve_monthly, key=lambda row: row["month"])
    figure.add_trace(
        _line(
            x=[_date(row["date"]) for row in daily],
            y=[_money(row["closing_balance_cents"]) for row in daily],
            name="Saldo estimado",
            color=COLORS["accent"],
            symbol=["star" if row["is_anchor_date"] == "true" else "circle" for row in daily],
            hovertemplate="%{x|%d/%m/%Y}<br>Saldo estimado: R$ %{y:,.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    months = [_month_date(row["month"]) for row in monthly]
    for name, field, color, symbol in (
        ("Aportes", "contribution_cents", COLORS["positive"], "circle"),
        ("Deportes", "deporte_cents", COLORS["negative"], "square-open"),
        ("Aporte líquido", "net_contribution_cents", COLORS["primary"], "diamond"),
    ):
        figure.add_trace(
            _line(
                x=months,
                y=[_money(row[field]) for row in monthly],
                name=name,
                color=color,
                symbol=symbol,
                hovertemplate="%{x|%m/%Y}<br>%{fullData.name}: R$ %{y:,.2f}<extra></extra>",
            ),
            row=2,
            col=1,
        )
    _style(figure, "Evolução do cofrinho, aportes e deportes", height=940)
    figure.update_xaxes(title_text="Data", row=1, col=1)
    figure.update_xaxes(title_text="Mês", row=2, col=1)
    figure.update_yaxes(title_text="Saldo estimado (R$)", row=1, col=1)
    figure.update_yaxes(title_text="Valor mensal (R$)", row=2, col=1)
    _money_axis(figure, row=1)
    _money_axis(figure, row=2)
    _date_axis(figure, [_date(row["date"]) for row in daily], row=1)
    _date_axis(figure, months, row=2)
    return ChartArtifact(
        slug="05_cofrinho",
        title="Evolução do cofrinho, aportes e deportes",
        description=(
            "Reconstrução a 100% do CDI ancorada no saldo conhecido; a estrela marca a "
            "data da âncora."
        ),
        period=_period([row["date"] for row in daily]),
        sources=("cofrinho_daily.csv", "cofrinho_monthly.csv"),
        figure=figure,
    )


def build_survival_chart(rows: list[dict[str, str]]) -> ChartArtifact:
    _require_fields(
        "monthly_metrics.csv",
        rows,
        {"month", "is_complete_month", "survival_index_months"},
    )
    usable = sorted(
        (
            row
            for row in rows
            if row["is_complete_month"] == "true" and row["survival_index_months"] != ""
        ),
        key=lambda row: row["month"],
    )
    if not usable:
        raise ValueError("monthly_metrics.csv não contém índice de sobrevivência calculável")
    values = [float(Decimal(row["survival_index_months"])) for row in usable]
    figure = go.Figure(
        _line(
            x=[_month_date(row["month"]) for row in usable],
            y=values,
            name="Índice de sobrevivência",
            color=COLORS["accent"],
            hovertemplate="%{x|%m/%Y}<br>Cobertura: %{y:.2f} meses<extra></extra>",
        )
    )
    latest = usable[-1]
    latest_value = values[-1]
    figure.add_annotation(
        x=_month_date(latest["month"]),
        y=latest_value,
        text=f"Último mês completo: {latest_value:.2f} meses",
        showarrow=True,
        arrowhead=2,
        ax=-105,
        ay=-55,
        bgcolor="white",
        bordercolor=COLORS["accent"],
    )
    _style(figure, "Meses de sobrevivência cobertos pelo cofrinho", legend=False)
    survival_months = [_month_date(row["month"]) for row in usable]
    figure.update_xaxes(title_text="Mês")
    figure.update_yaxes(title_text="Cobertura da reserva (meses)", rangemode="tozero")
    _date_axis(figure, survival_months)
    return ChartArtifact(
        slug="06_indice_sobrevivencia",
        title="Meses de sobrevivência cobertos pelo cofrinho",
        description=(
            "Saldo estimado do cofrinho dividido pelo custo de vida recorrente de cada "
            "mês completo."
        ),
        period=_period([row["month"] for row in usable]),
        sources=("monthly_metrics.csv",),
        figure=figure,
    )


def build_category_chart(
    category_rows: list[dict[str, str]], monthly_rows: list[dict[str, str]]
) -> ChartArtifact:
    _require_fields(
        "monthly_category_spending.csv",
        category_rows,
        {
            "month",
            "category",
            "recurring_cost_cents",
            "atypical_expense_cents",
            "outside_living_cost_cents",
            "unclassified_outflow_cents",
        },
    )
    _require_fields(
        "monthly_metrics.csv",
        monthly_rows,
        {"month", "is_complete_month", "account_coverage"},
    )
    comparable_months = {
        row["month"]
        for row in monthly_rows
        if row["is_complete_month"] == "true"
        and row["account_coverage"] == "all_available_accounts"
    }
    if not comparable_months:
        comparable_months = {
            row["month"] for row in monthly_rows if row["is_complete_month"] == "true"
        }
    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    fields = (
        "recurring_cost_cents",
        "atypical_expense_cents",
        "outside_living_cost_cents",
        "unclassified_outflow_cents",
    )
    for row in category_rows:
        if row["month"] not in comparable_months:
            continue
        for field in fields:
            totals[row["category"]][field] += int(row[field])
    ordered_categories = sorted(
        totals,
        key=lambda category: sum(totals[category][field] for field in fields),
    )
    if not ordered_categories:
        raise ValueError("monthly_category_spending.csv não contém meses comparáveis")
    figure = go.Figure()
    for name, field, color, pattern in (
        ("Custo recorrente", "recurring_cost_cents", COLORS["primary"], ""),
        ("Gasto atípico", "atypical_expense_cents", COLORS["warning"], "/"),
        ("Fora do custo de vida", "outside_living_cost_cents", COLORS["neutral"], "."),
        ("Não classificado", "unclassified_outflow_cents", COLORS["secondary"], "x"),
    ):
        figure.add_trace(
            go.Bar(
                x=[_money(totals[category][field]) for category in ordered_categories],
                y=ordered_categories,
                name=name,
                orientation="h",
                marker={"color": color, "pattern": {"shape": pattern}},
                hovertemplate="%{y}<br>%{fullData.name}: R$ %{x:,.2f}<extra></extra>",
            )
        )
    _style(
        figure,
        "Gastos por categoria nos meses completos com todas as contas",
        height=max(760, 38 * len(ordered_categories) + 230),
    )
    figure.update_layout(barmode="stack", hovermode="y unified")
    figure.update_xaxes(title_text="Gasto acumulado no período (R$)", rangemode="tozero")
    figure.update_yaxes(title_text="Categoria", showgrid=False, zeroline=False)
    figure.update_xaxes(tickprefix="R$ ", tickformat=",.0f", separatethousands=True)
    return ChartArtifact(
        slug="07_gastos_por_categoria",
        title="Gastos por categoria nos meses completos com todas as contas",
        description=(
            "Ranking acumulado por categoria, separado pelo tratamento no custo de vida."
        ),
        period=_period(sorted(comparable_months)),
        sources=("monthly_category_spending.csv", "monthly_metrics.csv"),
        figure=figure,
    )


def build_peaks_chart(
    candidates: list[dict[str, str]], monthly_rows: list[dict[str, str]]
) -> ChartArtifact:
    _require_fields(
        "spending_peak_candidates.csv",
        candidates,
        {"start_date", "amount_cents", "label", "is_peak"},
    )
    _require_fields(
        "spending_peaks_monthly.csv",
        monthly_rows,
        {"month", "peak_count", "peak_total_cents", "average_peak_cents"},
    )
    peaks = sorted(
        (row for row in candidates if row["is_peak"] == "true"),
        key=lambda row: row["start_date"],
    )
    if not peaks:
        raise ValueError("spending_peak_candidates.csv não contém picos")
    monthly = sorted(monthly_rows, key=lambda row: row["month"])
    figure = make_subplots(
        rows=3,
        cols=1,
        vertical_spacing=0.16,
        subplot_titles=("Picos individuais", "Frequência mensal", "Magnitude mensal"),
    )
    figure.add_trace(
        _line(
            x=[_date(row["start_date"]) for row in peaks],
            y=[_money(row["amount_cents"]) for row in peaks],
            name="Valor do pico",
            color=COLORS["warning"],
            symbol=[
                "x" if row.get("classification_status") == "unknown" else "diamond"
                for row in peaks
            ],
            customdata=[row["label"] for row in peaks],
            hovertemplate=(
                "%{x|%d/%m/%Y}<br>%{customdata}<br>Valor: R$ %{y:,.2f}<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )
    months = [_month_date(row["month"]) for row in monthly]
    figure.add_trace(
        _line(
            x=months,
            y=[int(row["peak_count"]) for row in monthly],
            name="Quantidade de picos",
            color=COLORS["primary"],
            hovertemplate="%{x|%m/%Y}<br>Picos: %{y}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    for name, field, color, symbol in (
        ("Total em picos", "peak_total_cents", COLORS["negative"], "circle"),
        ("Média por pico", "average_peak_cents", COLORS["accent"], "square-open"),
    ):
        figure.add_trace(
            _line(
                x=months,
                y=[_money(row[field]) for row in monthly],
                name=name,
                color=color,
                symbol=symbol,
                hovertemplate="%{x|%m/%Y}<br>%{fullData.name}: R$ %{y:,.2f}<extra></extra>",
            ),
            row=3,
            col=1,
        )
    _style(figure, "Frequência e magnitude dos picos de gasto", height=1320)
    for row in (1, 2, 3):
        figure.update_xaxes(title_text="Data" if row == 1 else "Mês", row=row, col=1)
    _date_axis(figure, [_date(row["start_date"]) for row in peaks], row=1)
    _date_axis(figure, months, row=2)
    _date_axis(figure, months, row=3)
    figure.update_yaxes(title_text="Valor do pico (R$)", rangemode="tozero", row=1, col=1)
    figure.update_yaxes(
        title_text="Quantidade de picos",
        rangemode="tozero",
        dtick=1,
        row=2,
        col=1,
    )
    figure.update_yaxes(title_text="Valor mensal (R$)", rangemode="tozero", row=3, col=1)
    _money_axis(figure, row=1)
    _money_axis(figure, row=3)
    return ChartArtifact(
        slug="08_picos_de_gasto",
        title="Frequência e magnitude dos picos de gasto",
        description=(
            "Picos pelo escore Z modificado. Um marcador em x identifica pico ainda não "
            "classificado."
        ),
        period=_period([row["start_date"] for row in peaks]),
        sources=("spending_peak_candidates.csv", "spending_peaks_monthly.csv"),
        figure=figure,
    )


def build_charts(inputs: VisualizationInputs) -> list[ChartArtifact]:
    charts = [
        build_daily_balances_chart(inputs.daily_balances, inputs.reserve_daily),
        build_daily_flows_chart(inputs.daily_flows),
        build_monthly_result_chart(inputs.monthly_metrics),
        build_living_cost_chart(inputs.monthly_metrics),
        build_reserve_chart(inputs.reserve_daily, inputs.reserve_monthly),
        build_survival_chart(inputs.monthly_metrics),
        build_category_chart(inputs.monthly_categories, inputs.monthly_metrics),
        build_peaks_chart(inputs.peak_candidates, inputs.peaks_monthly),
    ]
    validate_chart_contract(charts)
    return charts


def validate_chart_contract(charts: list[ChartArtifact]) -> None:
    slugs = [chart.slug for chart in charts]
    if len(slugs) != len(set(slugs)):
        raise ValueError("Há identificadores de gráficos repetidos")
    for chart in charts:
        if not chart.figure.layout.title.text:
            raise ValueError(f"{chart.slug} não possui título")
        for axis_name in chart.figure.select_xaxes():
            if not axis_name.title.text:
                raise ValueError(f"{chart.slug} possui eixo horizontal sem título")
        for axis_name in chart.figure.select_yaxes():
            if not axis_name.title.text:
                raise ValueError(f"{chart.slug} possui eixo vertical sem título")
        if any(trace.type in {"pie", "sunburst"} for trace in chart.figure.data):
            raise ValueError(f"{chart.slug} usa um gráfico circular proibido")
        if chart.slug in TEMPORAL_CHARTS:
            for trace in chart.figure.data:
                if trace.type != "scatter" or trace.mode != "lines+markers":
                    raise ValueError(
                        f"{chart.slug} possui série temporal sem linhas e pontos"
                    )


def export_charts(charts: list[ChartArtifact], output_dir: Path) -> list[Path]:
    validate_chart_contract(charts)
    output_dir.mkdir(parents=True, exist_ok=True)
    exported: list[Path] = []
    manifest: list[dict[str, Any]] = []
    for chart in charts:
        output_path = output_dir / chart.filename
        image = chart.figure.to_image(format="png", width=1500, height=chart.figure.layout.height)
        temporary = output_path.with_suffix(".png.tmp")
        temporary.write_bytes(image)
        temporary.replace(output_path)
        exported.append(output_path)
        manifest.append(
            {
                "id": chart.slug,
                "file": chart.filename,
                "title": chart.title,
                "description": chart.description,
                "period": chart.period,
                "sources": list(chart.sources),
            }
        )
    manifest_path = output_dir / "manifest.json"
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_manifest.replace(manifest_path)
    return exported
