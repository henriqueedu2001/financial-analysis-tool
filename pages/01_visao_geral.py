import streamlit as st

from finance.ui import load_foundation_status

st.set_page_config(page_title="Visão geral", page_icon="📈", layout="wide")
st.title("Visão geral")

status = load_foundation_status()
st.caption(f"Fundação ativa: {status.account_count} conta(s) e {status.category_count} categorias.")
st.info(
    "Os cartões financeiros e gráficos serão implementados na Fase 5, "
    "após as regras centrais estarem testadas."
)
