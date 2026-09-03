import streamlit as st
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from finance.db import create_session_factory, initialize_database
from finance.models import Category, ClassificationRule, RuleMatchType, TransactionNature
from finance.repositories.categories import CategoryError, create_category, update_category
from finance.repositories.rules import (
    ClassificationRuleError,
    create_classification_rule,
    update_classification_rule,
)


def category_label(category: Category) -> str:
    parent = category_by_id.get(category.parent_id)
    return f"{parent.name} / {category.name}" if parent else category.name


def extraordinary_action(value: str) -> bool | None:
    return {"Não alterar": None, "Marcar como sim": True, "Marcar como não": False}[value]


st.set_page_config(page_title="Categorias e regras", page_icon="🏷️", layout="wide")
st.title("Categorias e regras")
st.caption("Menor número de prioridade vence. Apenas a primeira regra compatível é aplicada.")

engine = initialize_database()
session_factory = create_session_factory(engine)
with session_factory() as session:
    categories = session.scalars(select(Category).order_by(Category.name)).all()
    rules = session.scalars(
        select(ClassificationRule).order_by(ClassificationRule.priority, ClassificationRule.id)
    ).all()

category_by_id = {category.id: category for category in categories}
active_categories = [category for category in categories if category.is_active]
category_options = [None, *(category.id for category in active_categories)]
all_category_options = [None, *(category.id for category in categories)]

category_tab, rule_tab = st.tabs(["Categorias", "Regras"])

with category_tab:
    st.dataframe(
        [
            {
                "ID": category.id,
                "Categoria": category_label(category),
                "Custo de vida": category.is_living_cost,
                "Essencial": category.is_essential,
                "Recorrente": category.is_recurring,
                "Extraordinária por padrão": category.is_extraordinary_default,
                "Ativa": category.is_active,
            }
            for category in categories
        ],
        width="stretch",
        hide_index=True,
    )

    st.subheader("Nova categoria")
    with st.form("create-category", clear_on_submit=True):
        new_name = st.text_input("Nome")
        new_parent = st.selectbox(
            "Categoria pai",
            options=category_options,
            format_func=lambda value: (
                "Nenhuma — categoria principal"
                if value is None
                else category_label(category_by_id[value])
            ),
        )
        new_living = st.checkbox("Integra o custo de vida")
        new_essential = st.checkbox("É essencial")
        new_recurring = st.checkbox("É recorrente")
        new_extraordinary = st.checkbox("É extraordinária por padrão")
        create_category_submitted = st.form_submit_button("Criar categoria")

    if create_category_submitted:
        try:
            with session_factory() as session:
                create_category(
                    session,
                    name=new_name,
                    parent_id=new_parent,
                    is_living_cost=new_living,
                    is_essential=new_essential,
                    is_recurring=new_recurring,
                    is_extraordinary_default=new_extraordinary,
                )
            st.rerun()
        except (CategoryError, IntegrityError) as exc:
            st.error(f"Não foi possível criar: {exc}")

    st.subheader("Editar ou desativar")
    edited_id = st.selectbox(
        "Categoria",
        options=list(category_by_id),
        format_func=lambda value: category_label(category_by_id[value]),
        key="edit-category-id",
    )
    edited = category_by_id[edited_id]
    with st.form("edit-category"):
        edited_name = st.text_input("Nome", value=edited.name)
        edited_living = st.checkbox("Integra o custo de vida", value=edited.is_living_cost)
        edited_essential = st.checkbox("É essencial", value=edited.is_essential)
        edited_recurring = st.checkbox("É recorrente", value=edited.is_recurring)
        edited_extraordinary = st.checkbox(
            "É extraordinária por padrão", value=edited.is_extraordinary_default
        )
        edited_active = st.checkbox("Ativa", value=edited.is_active)
        update_category_submitted = st.form_submit_button("Salvar categoria")
    if update_category_submitted:
        try:
            with session_factory() as session:
                update_category(
                    session,
                    edited_id,
                    name=edited_name,
                    is_living_cost=edited_living,
                    is_essential=edited_essential,
                    is_recurring=edited_recurring,
                    is_extraordinary_default=edited_extraordinary,
                    is_active=edited_active,
                )
            st.rerun()
        except CategoryError as exc:
            st.error(str(exc))

with rule_tab:
    if rules:
        st.dataframe(
            [
                {
                    "ID": rule.id,
                    "Prioridade": rule.priority,
                    "Nome": rule.name,
                    "Condição": rule.match_type.value,
                    "Padrão": rule.pattern,
                    "Categoria": (
                        category_label(category_by_id[rule.category_id])
                        if rule.category_id
                        else "Não alterar"
                    ),
                    "Natureza": rule.nature.value if rule.nature else "Não alterar",
                    "Ativa": rule.is_active,
                }
                for rule in rules
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("Nenhuma regra criada.")

    st.subheader("Nova regra")
    with st.form("create-rule", clear_on_submit=True):
        new_rule_name = st.text_input("Nome da regra")
        new_match_type = st.selectbox(
            "Condição", list(RuleMatchType), format_func=lambda value: value.value
        )
        new_pattern = st.text_input("Padrão")
        new_rule_category = st.selectbox(
            "Categoria resultante",
            category_options,
            format_func=lambda value: (
                "Não alterar" if value is None else category_label(category_by_id[value])
            ),
        )
        nature_options = [None, *list(TransactionNature)]
        new_rule_nature = st.selectbox(
            "Natureza resultante",
            nature_options,
            format_func=lambda value: "Não alterar" if value is None else value.value,
        )
        extraordinary_options = ["Não alterar", "Marcar como sim", "Marcar como não"]
        new_rule_extraordinary = st.selectbox("Extraordinária", extraordinary_options)
        new_rule_priority = st.number_input("Prioridade", min_value=0, value=100)
        create_rule_submitted = st.form_submit_button("Criar regra")
    if create_rule_submitted:
        try:
            with session_factory() as session:
                create_classification_rule(
                    session,
                    name=new_rule_name,
                    match_type=new_match_type,
                    pattern=new_pattern,
                    category_id=new_rule_category,
                    nature=new_rule_nature,
                    mark_extraordinary=extraordinary_action(new_rule_extraordinary),
                    priority=int(new_rule_priority),
                )
            st.rerun()
        except (ClassificationRuleError, IntegrityError) as exc:
            st.error(f"Não foi possível criar: {exc}")

    if rules:
        st.subheader("Editar ou desativar")
        rule_by_id = {rule.id: rule for rule in rules}
        edited_rule_id = st.selectbox(
            "Regra",
            list(rule_by_id),
            format_func=lambda value: rule_by_id[value].name,
        )
        edited_rule = rule_by_id[edited_rule_id]
        current_extraordinary = {
            None: "Não alterar",
            True: "Marcar como sim",
            False: "Marcar como não",
        }[edited_rule.mark_extraordinary]
        with st.form("edit-rule"):
            rule_name = st.text_input("Nome", value=edited_rule.name)
            rule_match_type = st.selectbox(
                "Condição",
                list(RuleMatchType),
                index=list(RuleMatchType).index(edited_rule.match_type),
                format_func=lambda value: value.value,
            )
            rule_pattern = st.text_input("Padrão", value=edited_rule.pattern)
            rule_category = st.selectbox(
                "Categoria resultante",
                all_category_options,
                index=all_category_options.index(edited_rule.category_id),
                format_func=lambda value: (
                    "Não alterar" if value is None else category_label(category_by_id[value])
                ),
            )
            rule_nature = st.selectbox(
                "Natureza resultante",
                nature_options,
                index=nature_options.index(edited_rule.nature),
                format_func=lambda value: "Não alterar" if value is None else value.value,
            )
            rule_extraordinary = st.selectbox(
                "Extraordinária",
                extraordinary_options,
                index=extraordinary_options.index(current_extraordinary),
            )
            rule_priority = st.number_input("Prioridade", min_value=0, value=edited_rule.priority)
            rule_active = st.checkbox("Ativa", value=edited_rule.is_active)
            update_rule_submitted = st.form_submit_button("Salvar regra")
        if update_rule_submitted:
            try:
                with session_factory() as session:
                    update_classification_rule(
                        session,
                        edited_rule_id,
                        name=rule_name,
                        match_type=rule_match_type,
                        pattern=rule_pattern,
                        category_id=rule_category,
                        nature=rule_nature,
                        mark_extraordinary=extraordinary_action(rule_extraordinary),
                        priority=int(rule_priority),
                        is_active=rule_active,
                    )
                st.rerun()
            except (ClassificationRuleError, IntegrityError) as exc:
                st.error(f"Não foi possível salvar: {exc}")
