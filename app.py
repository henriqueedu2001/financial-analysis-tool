import streamlit as st

from finance.ui import load_foundation_status

st.set_page_config(
    page_title="Finanças pessoais",
    page_icon="📊",
    layout="wide",
)

status = load_foundation_status()

st.title("Finanças pessoais")
st.caption("Aplicação local, auditável e sem integração bancária ou IA no MVP.")

left, right = st.columns(2)
left.metric("Contas cadastradas", status.account_count)
right.metric("Categorias disponíveis", status.category_count)

st.info(
    "Importação e revisão manual estão disponíveis. Cadastre as contas, importe um "
    "OFX/CSV e use Movimentações para classificar o histórico."
)

st.subheader("Estado da implementação")
st.markdown(
    """
- ✅ Banco SQLite e modelos auditáveis
- ✅ Taxonomia editável carregada do YAML
- ✅ OFX/CSV com prévia, validação, reconciliação e deduplicação
- ✅ Consulta, filtros, correções auditáveis e regras locais
- ✅ Transferências reversíveis, ambiguidades e reconciliação por snapshots
- ✅ Métricas determinísticas, patrimônio, burn rate e dashboard
- ⏳ Exportações estruturadas
"""
)
