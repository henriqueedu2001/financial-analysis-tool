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
    "A Fundação e a importação auditável estão instaladas. Cadastre as contas e "
    "use a página Importação para revisar um OFX ou CSV antes de confirmar."
)

st.subheader("Estado da implementação")
st.markdown(
    """
- ✅ Banco SQLite e modelos auditáveis
- ✅ Taxonomia editável carregada do YAML
- ✅ OFX/CSV com prévia, validação, reconciliação e deduplicação
- ✅ Arquivo original preservado por instituição e hash
- ⏳ Edição, regras, transferências, métricas e exportações
"""
)
