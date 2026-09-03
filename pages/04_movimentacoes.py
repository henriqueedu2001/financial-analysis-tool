import pandas as pd
import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from finance.db import create_session_factory, initialize_database
from finance.models import (
    Account,
    Category,
    RuleMatchType,
    Transaction,
    TransactionNature,
)
from finance.money import InvalidMoney, cents_to_decimal, decimal_to_cents
from finance.repositories.rules import ClassificationRuleError, create_classification_rule
from finance.repositories.transactions import (
    TransactionFilters,
    TransactionUpdateError,
    list_transactions,
    update_transaction_manual,
)


def format_brl(cents: int) -> str:
    conventional = f"{cents_to_decimal(cents):,.2f}"
    return "R$ " + conventional.replace(",", "_").replace(".", ",").replace("_", ".")


def category_label(category: Category) -> str:
    if category.parent_id:
        return f"{category_by_id[category.parent_id].name} / {category.name}"
    return category.name


def override_value(label: str) -> bool | None:
    return {"Herdar da categoria": None, "Sim": True, "Não": False}[label]


st.set_page_config(page_title="Movimentações", page_icon="🧾", layout="wide")
st.title("Movimentações")

engine = initialize_database()
session_factory = create_session_factory(engine)
with session_factory() as session:
    accounts = session.scalars(select(Account).order_by(Account.name)).all()
    categories = session.scalars(select(Category).order_by(Category.name)).all()
    date_bounds = session.execute(
        select(func.min(Transaction.transaction_date), func.max(Transaction.transaction_date))
    ).one()

if not date_bounds[0] or not date_bounds[1]:
    st.info("Ainda não há movimentações importadas.")
    st.stop()

account_by_id = {account.id: account for account in accounts}
category_by_id = {category.id: category for category in categories}

with st.expander("Filtros", expanded=True):
    period_columns = st.columns(2)
    date_from = period_columns[0].date_input("Data inicial", value=date_bounds[0])
    date_to = period_columns[1].date_input("Data final", value=date_bounds[1])
    selected_accounts = st.multiselect(
        "Contas",
        options=list(account_by_id),
        default=list(account_by_id),
        format_func=lambda value: account_by_id[value].name,
    )
    selected_categories = st.multiselect(
        "Categorias",
        options=list(category_by_id),
        format_func=lambda value: category_label(category_by_id[value]),
    )
    selected_natures = st.multiselect(
        "Naturezas",
        options=list(TransactionNature),
        format_func=lambda value: value.value,
    )
    text_filter = st.text_input("Descrição contém")
    amount_columns = st.columns(2)
    minimum_amount = amount_columns[0].text_input("Valor mínimo", placeholder="-1000.00")
    maximum_amount = amount_columns[1].text_input("Valor máximo", placeholder="1000.00")

try:
    min_cents = decimal_to_cents(minimum_amount) if minimum_amount.strip() else None
    max_cents = decimal_to_cents(maximum_amount) if maximum_amount.strip() else None
except InvalidMoney as exc:
    st.error(f"Filtro monetário inválido: {exc}")
    st.stop()

filters = TransactionFilters(
    date_from=date_from,
    date_to=date_to,
    account_ids=tuple(selected_accounts),
    category_ids=tuple(selected_categories),
    natures=tuple(selected_natures),
    min_amount_cents=min_cents,
    max_amount_cents=max_cents,
    description_contains=text_filter or None,
)
with session_factory() as session:
    transactions = list_transactions(session, filters)

st.caption(f"{len(transactions)} resultado(s); limite de exibição: 2.000.")
if not transactions:
    st.info("Nenhuma movimentação corresponde aos filtros.")
    st.stop()

st.dataframe(
    pd.DataFrame(
        [
            {
                "ID": transaction.id,
                "Data": transaction.transaction_date,
                "Conta": transaction.account.name,
                "Descrição": transaction.original_description,
                "Valor": format_brl(transaction.amount_cents),
                "Natureza": transaction.nature.value,
                "Categoria": (
                    category_label(transaction.category) if transaction.category else "A revisar"
                ),
                "Extraordinária": transaction.is_extraordinary,
                "Origem classificação": transaction.classification_source.value,
            }
            for transaction in transactions
        ]
    ),
    width="stretch",
    hide_index=True,
)

st.subheader("Revisar uma movimentação")
transaction_by_id = {transaction.id: transaction for transaction in transactions}
selected_id = st.selectbox(
    "Movimentação",
    options=list(transaction_by_id),
    format_func=lambda value: (
        f"#{value} — {transaction_by_id[value].transaction_date} — "
        f"{transaction_by_id[value].original_description[:70]}"
    ),
)
selected = transaction_by_id[selected_id]
active_categories = [category for category in categories if category.is_active]
category_options = [None, *(category.id for category in active_categories)]
current_category = selected.category_id if selected.category_id in category_options else None

with st.expander("Rastreabilidade da origem"):
    st.write(f"Arquivo: `{selected.batch.source_file}`")
    st.write(
        f"Lote: `{selected.batch_id}` · linha de origem: `{selected.raw_transaction.source_row}`"
    )
    st.write(f"Data importada: `{selected.raw_transaction.original_transaction_date}`")
    st.write(f"Valor importado: `{selected.raw_transaction.original_amount}`")
    st.write("Descrição bancária original:")
    st.code(selected.raw_transaction.original_description)

with st.form("manual-correction"):
    category_id = st.selectbox(
        "Categoria / subcategoria",
        options=category_options,
        index=category_options.index(current_category),
        format_func=lambda value: (
            "Sem categoria" if value is None else category_label(category_by_id[value])
        ),
    )
    nature = st.selectbox(
        "Natureza",
        options=list(TransactionNature),
        index=list(TransactionNature).index(selected.nature),
        format_func=lambda value: value.value,
    )
    extraordinary = st.checkbox("Despesa extraordinária", value=selected.is_extraordinary)
    override_labels = ["Herdar da categoria", "Sim", "Não"]
    essential = st.selectbox(
        "Essencial",
        override_labels,
        index={None: 0, True: 1, False: 2}[selected.is_essential_override],
    )
    living_cost = st.selectbox(
        "Integra o custo de vida",
        override_labels,
        index={None: 0, True: 1, False: 2}[selected.is_living_cost_override],
    )
    reason = st.text_input("Motivo da correção (opcional)")

    create_future_rule = st.checkbox("Criar também uma regra para ocorrências futuras")
    rule_columns = st.columns(2)
    rule_name = rule_columns[0].text_input("Nome da nova regra")
    rule_pattern = rule_columns[1].text_input(
        "Descrição contém", value=selected.original_description if create_future_rule else ""
    )
    rule_priority = st.number_input("Prioridade da regra", min_value=0, value=100)
    submitted = st.form_submit_button("Salvar correção", type="primary")

if submitted:
    try:
        with session_factory() as session:
            update_transaction_manual(
                session,
                selected_id,
                category_id=category_id,
                nature=nature,
                is_extraordinary=extraordinary,
                is_essential_override=override_value(essential),
                is_living_cost_override=override_value(living_cost),
                reason=reason,
                commit=False,
            )
            if create_future_rule:
                create_classification_rule(
                    session,
                    name=rule_name,
                    match_type=RuleMatchType.DESCRIPTION_CONTAINS,
                    pattern=rule_pattern,
                    category_id=category_id,
                    nature=nature,
                    mark_extraordinary=extraordinary,
                    priority=int(rule_priority),
                    commit=False,
                )
            session.commit()
        st.success("Correção salva e protegida contra regras automáticas futuras.")
        st.rerun()
    except (TransactionUpdateError, ClassificationRuleError, IntegrityError) as exc:
        st.error(f"Não foi possível salvar: {exc}")
