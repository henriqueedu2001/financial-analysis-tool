import streamlit as st

from finance.ui import load_foundation_status

st.set_page_config(page_title="Categorias e regras", page_icon="🏷️", layout="wide")
st.title("Categorias e regras")

status = load_foundation_status()
st.metric("Categorias carregadas", status.category_count)
st.info(
    "A taxonomia inicial já está no banco. O CRUD e as regras locais serão implementados na Fase 3."
)
