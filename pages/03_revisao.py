import streamlit as st
from sqlalchemy import select

from finance.db import create_session_factory, initialize_database
from finance.models import (
    Account,
    ImportBatch,
    ImportStatus,
    ReviewState,
    Transaction,
    TransferMatch,
    TransferMatchState,
)
from finance.money import InvalidMoney, cents_to_decimal, decimal_to_cents
from finance.reconciliation import (
    ReconciliationError,
    reconcile_account,
    record_balance_snapshot,
)
from finance.transfers import (
    TransferError,
    confirm_transfer_match,
    find_transfer_suggestions,
    mark_transaction_as_transfer,
    reject_transfer_match,
)


def format_brl(cents: int) -> str:
    conventional = f"{cents_to_decimal(cents):,.2f}"
    return "R$ " + conventional.replace(",", "_").replace(".", ",").replace("_", ".")


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
    all_transaction_rows = session.execute(
        select(Transaction, Account)
        .join(Account, Transaction.account_id == Account.id)
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
    ).all()
    accounts = session.scalars(select(Account).order_by(Account.name)).all()
    suggestions = find_transfer_suggestions(session)
    confirmed_matches = session.scalars(
        select(TransferMatch)
        .where(TransferMatch.state == TransferMatchState.CONFIRMED)
        .order_by(TransferMatch.id.desc())
    ).all()
    reconciliations = [
        result for account in accounts for result in reconcile_account(session, account.id)
    ]

transaction_by_id = {transaction.id: transaction for transaction, _ in all_transaction_rows}
account_by_transaction_id = {
    transaction.id: account for transaction, account in all_transaction_rows
}
account_by_id = {account.id: account for account in accounts}

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

st.divider()
st.subheader("Possíveis transferências internas")
if suggestions:
    st.dataframe(
        [
            {
                "Saída ID": suggestion.outgoing_transaction_id,
                "Conta de saída": account_by_transaction_id[
                    suggestion.outgoing_transaction_id
                ].name,
                "Entrada ID": suggestion.incoming_transaction_id,
                "Conta de entrada": account_by_transaction_id[
                    suggestion.incoming_transaction_id
                ].name,
                "Valor": format_brl(
                    abs(transaction_by_id[suggestion.outgoing_transaction_id].amount_cents)
                ),
                "Distância em dias": suggestion.date_distance_days,
                "Confiança": suggestion.confidence_basis_points / 10000,
                "Ambígua": suggestion.ambiguous,
            }
            for suggestion in suggestions
        ],
        width="stretch",
        hide_index=True,
    )
    suggestion_options = list(range(len(suggestions)))
    selected_suggestion_index = st.selectbox(
        "Sugestão para confirmar",
        suggestion_options,
        format_func=lambda index: (
            f"#{suggestions[index].outgoing_transaction_id} → "
            f"#{suggestions[index].incoming_transaction_id}"
            f"{' — AMBÍGUA' if suggestions[index].ambiguous else ''}"
        ),
    )
    selected_suggestion = suggestions[selected_suggestion_index]
    acknowledge_ambiguity = st.checkbox(
        "Revisei as alternativas e confirmo este par ambíguo",
        disabled=not selected_suggestion.ambiguous,
    )
    if st.button("Confirmar par sugerido"):
        if selected_suggestion.ambiguous and not acknowledge_ambiguity:
            st.error("Uma sugestão ambígua exige confirmação explícita.")
        else:
            try:
                with session_factory() as session:
                    confirm_transfer_match(
                        session,
                        selected_suggestion.outgoing_transaction_id,
                        selected_suggestion.incoming_transaction_id,
                        confidence_basis_points=(selected_suggestion.confidence_basis_points),
                        rationale=selected_suggestion.rationale,
                    )
                st.rerun()
            except TransferError as exc:
                st.error(str(exc))
else:
    st.info("Nenhum par compatível ainda não revisado.")

with st.expander("Associar manualmente ou marcar uma ponta isolada"):
    outgoing_ids = [
        transaction.id for transaction, _ in all_transaction_rows if transaction.amount_cents < 0
    ]
    incoming_ids = [
        transaction.id for transaction, _ in all_transaction_rows if transaction.amount_cents > 0
    ]
    if outgoing_ids and incoming_ids:
        with st.form("manual-transfer-pair"):
            outgoing_id = st.selectbox(
                "Saída",
                outgoing_ids,
                format_func=lambda value: (
                    f"#{value} · {account_by_transaction_id[value].name} · "
                    f"{format_brl(transaction_by_id[value].amount_cents)} · "
                    f"{transaction_by_id[value].original_description[:50]}"
                ),
            )
            incoming_id = st.selectbox(
                "Entrada",
                incoming_ids,
                format_func=lambda value: (
                    f"#{value} · {account_by_transaction_id[value].name} · "
                    f"{format_brl(transaction_by_id[value].amount_cents)} · "
                    f"{transaction_by_id[value].original_description[:50]}"
                ),
            )
            pair_submitted = st.form_submit_button("Associar par manualmente")
        if pair_submitted:
            try:
                with session_factory() as session:
                    confirm_transfer_match(session, outgoing_id, incoming_id)
                st.rerun()
            except TransferError as exc:
                st.error(str(exc))

    if transaction_by_id:
        with st.form("single-transfer-point"):
            isolated_id = st.selectbox(
                "Movimentação sem contraparte presente",
                list(transaction_by_id),
                format_func=lambda value: (
                    f"#{value} · {account_by_transaction_id[value].name} · "
                    f"{format_brl(transaction_by_id[value].amount_cents)}"
                ),
            )
            isolated_state = st.checkbox(
                "Marcar como transferência interna",
                value=transaction_by_id[isolated_id].is_internal_transfer,
            )
            isolated_submitted = st.form_submit_button("Salvar marcação")
        if isolated_submitted:
            try:
                with session_factory() as session:
                    mark_transaction_as_transfer(session, isolated_id, is_transfer=isolated_state)
                st.rerun()
            except TransferError as exc:
                st.error(str(exc))

st.subheader("Associações confirmadas")
if confirmed_matches:
    st.dataframe(
        [
            {
                "Associação": match.id,
                "Saída": match.outgoing_transaction_id,
                "Entrada": match.incoming_transaction_id,
                "Confirmação manual": match.manually_confirmed,
            }
            for match in confirmed_matches
        ],
        width="stretch",
        hide_index=True,
    )
    match_id = st.selectbox("Associação para desfazer", [match.id for match in confirmed_matches])
    if st.button("Desassociar", type="secondary"):
        try:
            with session_factory() as session:
                reject_transfer_match(session, match_id)
            st.rerun()
        except TransferError as exc:
            st.error(str(exc))
else:
    st.info("Nenhuma transferência associada.")

st.divider()
st.subheader("Reconciliação por saldos conhecidos")
if reconciliations:
    st.dataframe(
        [
            {
                "Conta": account_by_id[result.account_id].name,
                "Início": result.opening_date,
                "Fim": result.closing_date,
                "Saldo inicial": format_brl(result.opening_balance_cents),
                "Movimentações": format_brl(result.movement_total_cents),
                "Saldo calculado": format_brl(result.calculated_closing_balance_cents),
                "Saldo informado": format_brl(result.reported_closing_balance_cents),
                "Diferença": format_brl(result.difference_cents),
            }
            for result in reconciliations
        ],
        width="stretch",
        hide_index=True,
    )
else:
    st.info("São necessários ao menos dois snapshots da mesma conta para reconciliar.")

if accounts:
    with st.form("manual-snapshot"):
        snapshot_account_id = st.selectbox(
            "Conta do saldo",
            list(account_by_id),
            format_func=lambda value: account_by_id[value].name,
        )
        snapshot_date = st.date_input("Data do saldo")
        snapshot_amount = st.text_input("Saldo conhecido", placeholder="1000.00")
        snapshot_note = st.text_input("Observação (opcional)")
        snapshot_submitted = st.form_submit_button("Registrar snapshot")
    if snapshot_submitted:
        try:
            balance_cents = decimal_to_cents(snapshot_amount)
            with session_factory() as session:
                record_balance_snapshot(
                    session,
                    account_id=snapshot_account_id,
                    snapshot_date=snapshot_date,
                    balance_cents=balance_cents,
                    source_note=snapshot_note,
                )
            st.rerun()
        except (InvalidMoney, ReconciliationError) as exc:
            st.error(str(exc))
