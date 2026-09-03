import streamlit as st
from sqlalchemy import select

from finance.db import create_session_factory, initialize_database
from finance.models import Account, ImportBatch, ImportStatus, ReviewState, Transaction

st.set_page_config(page_title="Revisão", page_icon="🔎", layout="wide")
st.title("Revisão")

engine = initialize_database()
session_factory = create_session_factory(engine)
with session_factory() as session:
    batch_rows = session.execute(
        select(ImportBatch, Account)
        .join(Account, ImportBatch.account_id == Account.id)
        .where(ImportBatch.status == ImportStatus.IMPORTED_WITH_WARNING)
        .order_by(ImportBatch.imported_at.desc())
    ).all()
    transaction_rows = session.execute(
        select(Transaction, Account)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            (Transaction.review_state != ReviewState.REVIEWED)
            | (Transaction.category_id.is_(None))
            | (Transaction.confidence_basis_points < 6000)
        )
        .order_by(Transaction.transaction_date.desc())
        .limit(500)
    ).all()

st.subheader("Movimentações para revisar")
if not transaction_rows:
    st.success("Nenhuma movimentação sem categoria ou com baixa confiança.")
else:
    st.warning(f"{len(transaction_rows)} movimentação(ões) aguardam revisão.")
    st.dataframe(
        [
            {
                "ID": transaction.id,
                "Data": transaction.transaction_date,
                "Conta": account.name,
                "Descrição": transaction.original_description,
                "Sem categoria": transaction.category_id is None,
                "Confiança": (
                    transaction.confidence_basis_points / 10000
                    if transaction.confidence_basis_points is not None
                    else None
                ),
            }
            for transaction, account in transaction_rows
        ],
        width="stretch",
        hide_index=True,
    )

st.subheader("Lotes com pendências")
if not batch_rows:
    st.success("Nenhum lote importado com pendências.")
else:
    st.warning(f"{len(batch_rows)} lote(s) possuem avisos registrados.")
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
            for batch, account in batch_rows
        ],
        width="stretch",
        hide_index=True,
    )

st.info(
    "Use a página Movimentações para corrigir categorias, natureza e propriedades. "
    "A correção manual ficará protegida contra regras automáticas."
)
