from datetime import date
from decimal import Decimal

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import func, select

from finance.db import create_session_factory, initialize_database
from finance.metrics import (
    account_balance_series,
    burn_rate_normalized,
    category_spending,
    monthly_metrics,
    period_metrics,
    reserve_coverage_months,
)
from finance.models import Transaction
from finance.money import cents_to_decimal


def format_brl(cents: int | None) -> str:
    if cents is None:
        return "Indisponível"
    conventional = f"{cents_to_decimal(cents):,.2f}"
    return "R$ " + conventional.replace(",", "_").replace(".", ",").replace("_", ".")


def format_rate(rate: Decimal | None) -> str:
    return "Indisponível" if rate is None else f"{rate * 100:.1f}%"


def reais(cents: int | None) -> float | None:
    # Float is used only by Plotly for display, never for persistence or calculation.
    return float(cents_to_decimal(cents)) if cents is not None else None


st.set_page_config(page_title="Visão geral", page_icon="📈", layout="wide")
st.title("Visão geral")

engine = initialize_database()
session_factory = create_session_factory(engine)
with session_factory() as session:
    minimum_date, maximum_date = session.execute(
        select(func.min(Transaction.transaction_date), func.max(Transaction.transaction_date))
    ).one()

if minimum_date is None or maximum_date is None:
    st.info("Importe movimentações para visualizar métricas e gráficos.")
    st.stop()

default_start = date(max(minimum_date.year, maximum_date.year - 1), minimum_date.month, 1)
if default_start < minimum_date:
    default_start = minimum_date

filter_columns = st.columns(4)
date_from = filter_columns[0].date_input("Início", value=default_start)
date_to = filter_columns[1].date_input("Fim", value=maximum_date)
window = filter_columns[2].selectbox("Janela do burn rate", [3, 6, 12], index=0)
include_extraordinary = filter_columns[3].checkbox(
    "Incluir extraordinárias no burn rate", value=False
)
if date_from > date_to:
    st.error("A data inicial deve ser anterior à data final.")
    st.stop()

with session_factory() as session:
    metrics = period_metrics(session, date_from, date_to)
    months = monthly_metrics(session, date_from, date_to)
    current_burn = burn_rate_normalized(
        session,
        as_of=date_to,
        window_months=window,
        include_extraordinary=include_extraordinary,
    )
    coverage = reserve_coverage_months(
        session,
        as_of=date_to,
        window_months=window,
        include_extraordinary=include_extraordinary,
    )
    spending = category_spending(session, date_from, date_to)
    balance_series = account_balance_series(session, date_from, date_to)
    burn_series = [
        (
            month.month,
            burn_rate_normalized(
                session,
                as_of=month.month,
                window_months=window,
                include_extraordinary=include_extraordinary,
            ),
        )
        for month in months
    ]

first_row = st.columns(5)
first_row[0].metric("Patrimônio monitorado", format_brl(metrics.tracked_wealth_cents))
first_row[1].metric("Conta operacional", format_brl(metrics.operational_balance_cents))
first_row[2].metric("Reserva", format_brl(metrics.reserve_balance_cents))
first_row[3].metric("Receita externa", format_brl(metrics.external_income_cents))
first_row[4].metric("Despesa externa", format_brl(metrics.external_expenses_cents))

second_row = st.columns(5)
second_row[0].metric("Custo de vida", format_brl(metrics.living_cost_cents))
second_row[1].metric("Poupança gerada", format_brl(metrics.savings_cents))
second_row[2].metric("Taxa de poupança", format_rate(metrics.savings_rate))
second_row[3].metric("Aporte líquido", format_brl(metrics.net_reserve_contribution_cents))
second_row[4].metric(
    "Cobertura da reserva",
    "Indisponível" if coverage is None else f"{coverage:.1f} meses",
    help=f"Burn rate atual: {format_brl(current_burn)}",
)

monthly_frame = pd.DataFrame(
    [
        {
            "Mês": item.month,
            "Receitas": reais(item.external_income_cents),
            "Despesas": reais(item.external_expenses_cents),
            "Poupança": reais(item.savings_cents),
            "Custo de vida": reais(item.living_cost_cents),
            "Patrimônio": reais(item.tracked_wealth_cents),
        }
        for item in months
    ]
)

chart_columns = st.columns(2)
with chart_columns[0]:
    st.plotly_chart(
        px.line(
            monthly_frame,
            x="Mês",
            y="Patrimônio",
            markers=True,
            title="Evolução do patrimônio monitorado",
            labels={"value": "R$"},
        ),
        width="stretch",
    )
with chart_columns[1]:
    flow_frame = monthly_frame.melt(
        id_vars="Mês",
        value_vars=["Receitas", "Despesas", "Poupança"],
        var_name="Métrica",
        value_name="R$",
    )
    st.plotly_chart(
        px.bar(
            flow_frame,
            x="Mês",
            y="R$",
            color="Métrica",
            barmode="group",
            title="Receitas, despesas e poupança",
        ),
        width="stretch",
    )

balance_frame = pd.DataFrame(
    [
        {
            "Mês": month,
            "Conta": balance.account_name,
            "Saldo": reais(balance.balance_cents),
        }
        for month, balance in balance_series
    ]
)
chart_columns = st.columns(2)
with chart_columns[0]:
    st.plotly_chart(
        px.line(
            balance_frame,
            x="Mês",
            y="Saldo",
            color="Conta",
            markers=True,
            title="Saldo por conta",
        ),
        width="stretch",
    )
with chart_columns[1]:
    spending_frame = pd.DataFrame(
        [{"Categoria": name, "Gasto": reais(value)} for name, value in spending]
    )
    if spending_frame.empty:
        st.info("Sem despesas no período para o gráfico por categoria.")
    else:
        st.plotly_chart(
            px.bar(
                spending_frame,
                x="Gasto",
                y="Categoria",
                orientation="h",
                title="Gastos por categoria",
            ),
            width="stretch",
        )

chart_columns = st.columns(2)
with chart_columns[0]:
    st.plotly_chart(
        px.line(
            monthly_frame,
            x="Mês",
            y="Custo de vida",
            markers=True,
            title="Evolução do custo de vida",
        ),
        width="stretch",
    )
with chart_columns[1]:
    burn_frame = pd.DataFrame(
        [{"Mês": month, "Burn rate": reais(value)} for month, value in burn_series]
    )
    st.plotly_chart(
        px.line(
            burn_frame,
            x="Mês",
            y="Burn rate",
            markers=True,
            title=f"Burn rate normalizado — {window} meses",
        ),
        width="stretch",
    )

st.caption(
    "Indisponível significa que falta saldo conhecido, receita ou histórico "
    "suficiente; o sistema não substitui o valor por zero."
)
