import streamlit as st
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from finance.db import create_session_factory, initialize_database
from finance.models import Account, AccountType, FinancialRole
from finance.repositories.accounts import create_account

st.set_page_config(page_title="Contas", page_icon="🏦", layout="wide")
st.title("Contas")
st.caption(
    "Cadastre somente um nome local. Agência e número da conta não são necessários: "
    "o primeiro OFX confirmado cria um vínculo por hash, sem gravar esses números no SQLite."
)

engine = initialize_database()
session_factory = create_session_factory(engine)
with session_factory() as session:
    accounts = session.scalars(select(Account).order_by(Account.name)).all()

if accounts:
    st.dataframe(
        [
            {
                "Nome": account.name,
                "Instituição": account.institution or "—",
                "Tipo": account.account_type.value,
                "Papel": account.financial_role.value,
                "Reserva": account.is_reserve,
                "Consolidado": account.include_in_tracked_wealth,
                "Origem OFX vinculada": bool(account.source_account_fingerprint),
            }
            for account in accounts
        ],
        width="stretch",
        hide_index=True,
    )
else:
    st.info("Nenhuma conta cadastrada.")

st.subheader("Cadastrar conta")
with st.form("create-account", clear_on_submit=True):
    name = st.text_input("Nome local", placeholder="Ex.: Conta de fluxo BB")
    institution = st.selectbox("Instituição", ["Banco do Brasil", "Itaú", "Outra"])
    custom_institution = (
        st.text_input("Nome da instituição") if institution == "Outra" else institution
    )
    account_type = st.selectbox(
        "Tipo técnico",
        list(AccountType),
        format_func=lambda value: value.value,
    )
    financial_role = st.selectbox(
        "Papel financeiro",
        list(FinancialRole),
        format_func=lambda value: value.value,
    )
    include = st.checkbox("Incluir no patrimônio monitorado", value=True)
    reserve = st.checkbox("É conta de reserva", value=False)
    submitted = st.form_submit_button("Cadastrar")

if submitted:
    if not name.strip():
        st.error("Informe um nome para a conta.")
    elif not custom_institution.strip():
        st.error("Informe a instituição.")
    else:
        try:
            with session_factory() as session:
                create_account(
                    session,
                    name=name,
                    institution=custom_institution,
                    account_type=account_type,
                    financial_role=financial_role,
                    include_in_tracked_wealth=include,
                    is_reserve=reserve,
                )
            st.success("Conta cadastrada. Recarregue a página para atualizar a lista.")
        except IntegrityError:
            st.error("Já existe uma conta com esse nome.")
