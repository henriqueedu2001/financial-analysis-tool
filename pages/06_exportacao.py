import json

import streamlit as st
from sqlalchemy import func, select

from finance.db import create_session_factory, initialize_database
from finance.exports import analytical_summary_json, monthly_summary_csv, transactions_csv
from finance.models import Account, Category, Transaction, TransactionNature
from finance.repositories.transactions import TransactionFilters, list_transactions


def category_label(category: Category) -> str:
    parent = category_by_id.get(category.parent_id)
    return f"{parent.name} / {category.name}" if parent else category.name


st.set_page_config(page_title="Exportação", page_icon="📤", layout="wide")
st.title("Exportação")
st.caption(
    "As exportações são geradas em memória. O resumo analítico não inclui descrições "
    "bancárias nem identificadores de conta."
)

engine = initialize_database()
session_factory = create_session_factory(engine)
with session_factory() as session:
    date_bounds = session.execute(
        select(func.min(Transaction.transaction_date), func.max(Transaction.transaction_date))
    ).one()
    accounts = session.scalars(select(Account).order_by(Account.name)).all()
    categories = session.scalars(select(Category).order_by(Category.name)).all()

if not date_bounds[0] or not date_bounds[1]:
    st.info("Importe movimentações antes de gerar exportações.")
    st.stop()

account_by_id = {account.id: account for account in accounts}
category_by_id = {category.id: category for category in categories}

columns = st.columns(2)
date_from = columns[0].date_input("Início", value=date_bounds[0])
date_to = columns[1].date_input("Fim", value=date_bounds[1])
if date_from > date_to:
    st.error("A data inicial deve ser anterior à data final.")
    st.stop()

selected_accounts = st.multiselect(
    "Contas nas movimentações filtradas",
    list(account_by_id),
    default=list(account_by_id),
    format_func=lambda value: account_by_id[value].name,
)
selected_categories = st.multiselect(
    "Categorias nas movimentações filtradas",
    list(category_by_id),
    format_func=lambda value: category_label(category_by_id[value]),
)
selected_natures = st.multiselect(
    "Naturezas nas movimentações filtradas",
    list(TransactionNature),
    format_func=lambda value: value.value,
)
burn_columns = st.columns(2)
burn_window = burn_columns[0].selectbox("Janela do burn rate", [3, 6, 12])
include_extraordinary = burn_columns[1].checkbox("Incluir extraordinárias no burn rate")

with session_factory() as session:
    filtered = list_transactions(
        session,
        TransactionFilters(
            date_from=date_from,
            date_to=date_to,
            account_ids=tuple(selected_accounts),
            category_ids=tuple(selected_categories),
            natures=tuple(selected_natures),
        ),
        limit=100_000,
    )
    transaction_export = transactions_csv(filtered)
    monthly_export = monthly_summary_csv(session, date_from, date_to)
    json_export = analytical_summary_json(
        session,
        date_from,
        date_to,
        burn_window_months=burn_window,
        include_extraordinary_in_burn=include_extraordinary,
    )

st.metric("Movimentações no CSV filtrado", len(filtered))
file_suffix = f"{date_from.isoformat()}_{date_to.isoformat()}"
download_columns = st.columns(3)
download_columns[0].download_button(
    "Baixar movimentações CSV",
    transaction_export,
    file_name=f"movimentacoes_{file_suffix}.csv",
    mime="text/csv",
    width="stretch",
)
download_columns[1].download_button(
    "Baixar resumo mensal CSV",
    monthly_export,
    file_name=f"resumo_mensal_{file_suffix}.csv",
    mime="text/csv",
    width="stretch",
)
download_columns[2].download_button(
    "Baixar JSON para análise externa",
    json_export,
    file_name=f"resumo_analitico_{file_suffix}.json",
    mime="application/json",
    width="stretch",
)

st.subheader("Prévia do JSON agregado")
st.code(
    json.dumps(json.loads(json_export), ensure_ascii=False, indent=2),
    language="json",
)
st.info(
    "Valores monetários usam strings decimais exatas. Antes de enviar o arquivo "
    "a qualquer serviço externo, revise o conteúdo e sua política de privacidade."
)
