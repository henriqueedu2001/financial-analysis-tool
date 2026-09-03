import pandas as pd
import streamlit as st
from sqlalchemy import select

from finance.db import create_session_factory, initialize_database
from finance.db.session import PROJECT_ROOT
from finance.importers import StatementParseError
from finance.importers.preview import ImportPreview, build_import_preview
from finance.models import Account
from finance.money import cents_to_decimal
from finance.repositories.imports import ImportConfirmationError, confirm_import


def format_brl(cents: int) -> str:
    conventional = f"{cents_to_decimal(cents):,.2f}"
    return "R$ " + conventional.replace(",", "_").replace(".", ",").replace("_", ".")


st.set_page_config(page_title="Importação", page_icon="📥", layout="wide")
st.title("Importação")
st.caption("Pré-visualize primeiro. Nada é gravado no histórico antes da confirmação.")

engine = initialize_database()
session_factory = create_session_factory(engine)
with session_factory() as session:
    accounts = session.scalars(select(Account).order_by(Account.name)).all()

if not accounts:
    st.warning("Cadastre ao menos uma conta na página Contas antes de importar.")
    st.stop()

account_by_id = {account.id: account for account in accounts}
account_id = st.selectbox(
    "Conta local de destino",
    options=list(account_by_id),
    format_func=lambda value: (
        f"{account_by_id[value].name} — {account_by_id[value].institution or 'sem instituição'}"
    ),
)

source_mode = st.radio(
    "Origem",
    ["Arquivo já organizado em data/inbox", "Enviar arquivo"],
    horizontal=True,
)
content: bytes | None = None
source_file: str | None = None

if source_mode == "Arquivo já organizado em data/inbox":
    inbox = PROJECT_ROOT / "data" / "inbox"
    files = sorted(
        path
        for path in inbox.rglob("*")
        if path.is_file() and path.suffix.lower() in {".ofx", ".csv"}
    )
    if files:
        chosen = st.selectbox(
            "Arquivo",
            files,
            format_func=lambda value: str(value.relative_to(inbox)),
        )
        content = chosen.read_bytes()
        source_file = chosen.name
    else:
        st.info("Nenhum OFX ou CSV foi encontrado em data/inbox.")
else:
    uploaded = st.file_uploader("OFX ou CSV canônico", type=["ofx", "csv"])
    if uploaded is not None:
        content = uploaded.getvalue()
        source_file = uploaded.name

preview: ImportPreview | None = None
if content is not None and source_file is not None:
    try:
        with session_factory() as session:
            preview = build_import_preview(content, source_file, session, account_id)
    except StatementParseError as exc:
        st.error(f"Arquivo não reconhecido: {exc}")

if preview is None:
    st.stop()

statement = preview.statement
st.subheader("Prévia")
if statement.institution_label:
    st.write(f"Instituição detectada: **{statement.institution_label}**")
if statement.account_label:
    st.write(f"Conta declarada no CSV: **{statement.account_label}**")

metric_columns = st.columns(4)
metric_columns[0].metric("Movimentações válidas", len(statement.transactions))
metric_columns[1].metric("Linhas inválidas", len(statement.invalid_transactions))
metric_columns[2].metric("Entradas", format_brl(preview.inflow_cents))
metric_columns[3].metric("Saídas", format_brl(abs(preview.outflow_cents)))

period = (
    f"{preview.period_start.isoformat()} a {preview.period_end.isoformat()}"
    if preview.period_start and preview.period_end
    else "indisponível"
)
st.write(f"Período válido detectado: **{period}**")

if preview.same_file_already_imported:
    st.error("Este mesmo conteúdo já foi importado para a conta selecionada.")
if preview.has_possible_duplicates:
    st.warning(
        f"Há {len(preview.internal_duplicate_rows)} linha(s) semelhante(s) dentro do arquivo "
        f"e {len(preview.existing_duplicate_rows)} possível(is) duplicata(s) no histórico. "
        "Nenhuma será removida automaticamente."
    )

if preview.opening_balance_cents is not None:
    rec_columns = st.columns(3)
    rec_columns[0].metric("Saldo inicial calculado", format_brl(preview.opening_balance_cents))
    rec_columns[1].metric("Saldo final informado", format_brl(preview.closing_balance_cents or 0))
    rec_columns[2].metric(
        "Diferença de reconciliação",
        format_brl(preview.reconciliation_difference_cents or 0),
    )
elif preview.closing_balance_cents is not None:
    st.write(
        "Saldo final informado no OFX: "
        f"**{format_brl(preview.closing_balance_cents)}**. "
        "O arquivo não fornece saldo inicial verificável."
    )

if statement.transactions:
    preview_frame = pd.DataFrame(
        [
            {
                "Linha": row.source_row,
                "Data": row.transaction_date,
                "Descrição original": row.original_description,
                "Valor": str(cents_to_decimal(row.amount_cents)),
                "Natureza inicial": row.nature.value,
            }
            for row in statement.transactions
        ]
    )
    st.dataframe(preview_frame, width="stretch", hide_index=True)

if statement.invalid_transactions:
    with st.expander("Linhas inválidas", expanded=True):
        st.dataframe(
            [
                {"Linha": row.source_row, "Problemas": "; ".join(row.errors)}
                for row in statement.invalid_transactions
            ],
            width="stretch",
            hide_index=True,
        )

st.subheader("Confirmação")
allow_invalid = st.checkbox(
    "Importar somente as linhas válidas e registrar as inválidas como pendência",
    disabled=not statement.invalid_transactions,
)
allow_duplicates = st.checkbox(
    "Reconheço as possíveis duplicatas e quero preservá-las para revisão",
    disabled=not preview.has_possible_duplicates,
)

blocked = bool(
    preview.same_file_already_imported
    or preview.reconciliation_difference_cents not in (None, 0)
    or preview.balance_sequence_error_rows
)
if st.button("Confirmar importação", type="primary", disabled=blocked):
    try:
        with session_factory() as session:
            result = confirm_import(
                preview,
                session,
                account_id=account_id,
                allow_invalid_rows=allow_invalid,
                allow_possible_duplicates=allow_duplicates,
            )
        if result.already_imported:
            st.info("Arquivo já importado; nenhuma movimentação foi criada.")
        else:
            st.success(
                f"Lote {result.batch_id} confirmado: {result.imported_transactions} "
                f"movimentações e {result.rejected_rows} pendência(s)."
            )
    except ImportConfirmationError as exc:
        st.error(str(exc))
