import streamlit as st
from sqlalchemy import select

from finance.db import create_session_factory, initialize_database
from finance.models import Account, ImportBatch, ImportStatus

st.set_page_config(page_title="Revisão", page_icon="🔎", layout="wide")
st.title("Revisão")

engine = initialize_database()
session_factory = create_session_factory(engine)
with session_factory() as session:
    rows = session.execute(
        select(ImportBatch, Account)
        .join(Account, ImportBatch.account_id == Account.id)
        .where(ImportBatch.status == ImportStatus.IMPORTED_WITH_WARNING)
        .order_by(ImportBatch.imported_at.desc())
    ).all()

if not rows:
    st.success("Nenhum lote importado com pendências.")
else:
    st.warning(f"{len(rows)} lote(s) possuem avisos registrados.")
    st.dataframe(
        [
            {
                "Lote": batch.id,
                "Conta": account.name,
                "Arquivo": batch.source_file,
                "Linhas inválidas": len(batch.validation_result.get("invalid_rows", [])),
                "Duplicatas internas": len(
                    batch.validation_result.get("internal_duplicate_rows", [])
                ),
                "Duplicatas no histórico": len(
                    batch.validation_result.get("existing_duplicate_rows", [])
                ),
            }
            for batch, account in rows
        ],
        width="stretch",
        hide_index=True,
    )

st.info(
    "Revisão e correção transacional serão ampliadas na Fase 3; esta página já "
    "expõe pendências preservadas durante a importação."
)
