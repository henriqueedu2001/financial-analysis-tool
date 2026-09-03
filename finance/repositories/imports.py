"""Transactional persistence of a previously inspected import preview."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from finance.db.session import PROJECT_ROOT
from finance.importers.hashing import raw_line_hash, transaction_signature
from finance.importers.preview import ImportPreview
from finance.importers.types import InvalidTransaction, ParsedTransaction
from finance.models import (
    Account,
    Category,
    ClassificationSource,
    ImportBatch,
    ImportStatus,
    RawTransaction,
    ReviewState,
    Transaction,
)


class ImportConfirmationError(ValueError):
    pass


@dataclass(frozen=True)
class ImportResult:
    batch_id: int
    imported_transactions: int
    rejected_rows: int
    already_imported: bool = False


def confirm_import(
    preview: ImportPreview,
    session: Session,
    *,
    account_id: int,
    allow_invalid_rows: bool = False,
    allow_possible_duplicates: bool = False,
    archive_root: Path | None = None,
) -> ImportResult:
    if preview.account_id != account_id:
        raise ImportConfirmationError("a prévia deve ser refeita para a conta selecionada")
    if not preview.statement.transactions:
        raise ImportConfirmationError("não há movimentações válidas para importar")

    existing_batch = session.scalar(
        select(ImportBatch).where(
            ImportBatch.account_id == account_id,
            ImportBatch.file_hash == preview.file_hash,
            ImportBatch.status.in_((ImportStatus.IMPORTED, ImportStatus.IMPORTED_WITH_WARNING)),
        )
    )
    if existing_batch is not None:
        return ImportResult(existing_batch.id, 0, 0, already_imported=True)

    invalid = preview.statement.invalid_transactions
    if invalid and not allow_invalid_rows:
        raise ImportConfirmationError(
            "existem linhas inválidas; confirme explicitamente a importação parcial"
        )
    if preview.has_possible_duplicates and not allow_possible_duplicates:
        raise ImportConfirmationError(
            "existem possíveis duplicatas; confirme explicitamente para continuar"
        )
    if preview.reconciliation_difference_cents not in (None, 0):
        raise ImportConfirmationError("a divergência de reconciliação bloqueia a importação")
    if preview.balance_sequence_error_rows:
        raise ImportConfirmationError("a sequência de saldos contém divergências")

    account = session.get(Account, account_id)
    if account is None:
        raise ImportConfirmationError("conta selecionada não existe")
    if (
        preview.statement.account_label
        and preview.statement.account_label.casefold() != account.name.casefold()
    ):
        raise ImportConfirmationError(
            "o nome da conta no CSV não corresponde à conta local selecionada"
        )
    _bind_or_validate_source(session, account, preview)

    archived_path = _archive_source(preview, account_id, archive_root)
    status = (
        ImportStatus.IMPORTED_WITH_WARNING
        if invalid or preview.has_possible_duplicates
        else ImportStatus.IMPORTED
    )
    batch = ImportBatch(
        source_file=Path(preview.statement.source_file).name,
        source_format=preview.statement.source_format,
        archived_source_path=str(archived_path),
        file_hash=preview.file_hash,
        account_id=account_id,
        period_start=preview.period_start,
        period_end=preview.period_end,
        row_count=len(preview.statement.transactions) + len(invalid),
        status=status,
        inflow_cents=preview.inflow_cents,
        outflow_cents=preview.outflow_cents,
        opening_balance_cents=preview.opening_balance_cents,
        closing_balance_cents=preview.closing_balance_cents,
        reconciliation_difference_cents=preview.reconciliation_difference_cents,
        validation_result={
            "invalid_rows": [row.source_row for row in invalid],
            "internal_duplicate_rows": list(preview.internal_duplicate_rows),
            "existing_duplicate_rows": list(preview.existing_duplicate_rows),
            "balance_sequence_error_rows": list(preview.balance_sequence_error_rows),
        },
    )
    session.add(batch)
    session.flush()

    category_lookup = _category_lookup(session)
    for row in preview.statement.transactions:
        raw = _create_raw(batch.id, row)
        session.add(raw)
        session.flush()
        category_id = _resolve_category(row, category_lookup)
        transaction = Transaction(
            account_id=account_id,
            transaction_date=row.transaction_date,
            amount_cents=row.amount_cents,
            original_description=row.original_description,
            nature=row.nature,
            category_id=category_id,
            subcategory_text=row.subcategory,
            is_internal_transfer=row.is_internal_transfer,
            is_extraordinary=row.is_extraordinary,
            review_state=(
                ReviewState.PENDING
                if category_id is None or (row.category or "").casefold() == "a revisar"
                else ReviewState.REVIEWED
            ),
            confidence_basis_points=row.confidence_basis_points,
            classification_source=(
                ClassificationSource.IMPORTED if row.category else ClassificationSource.NONE
            ),
            stable_signature=transaction_signature(
                account_id,
                row.transaction_date,
                row.amount_cents,
                row.original_description,
            ),
            bank_transaction_id=row.source_identifier,
            batch_id=batch.id,
            raw_transaction_id=raw.id,
        )
        session.add(transaction)

    for row in invalid:
        session.add(_create_invalid_raw(batch.id, row))

    session.commit()
    return ImportResult(batch.id, len(preview.statement.transactions), len(invalid))


def _bind_or_validate_source(session: Session, account: Account, preview: ImportPreview) -> None:
    fingerprint = preview.statement.source_account_fingerprint
    institution_code = preview.statement.institution_code
    if not fingerprint:
        return
    account_already_bound = session.scalar(
        select(Account).where(
            Account.source_account_fingerprint == fingerprint,
            Account.id != account.id,
        )
    )
    if account_already_bound is not None:
        raise ImportConfirmationError("esta origem OFX já está vinculada a outra conta local")
    if account.source_account_fingerprint and account.source_account_fingerprint != fingerprint:
        raise ImportConfirmationError(
            "a origem OFX não corresponde à conta local; bancos/contas não serão misturados"
        )
    if (
        account.source_institution_code
        and institution_code
        and account.source_institution_code != institution_code
    ):
        raise ImportConfirmationError("a instituição OFX não corresponde à conta local")
    account.source_account_fingerprint = fingerprint
    account.source_institution_code = institution_code


def _archive_source(preview: ImportPreview, account_id: int, archive_root: Path | None) -> Path:
    root = archive_root or PROJECT_ROOT / "data" / "raw"
    institution = _safe_segment(preview.statement.institution_label or "csv")
    year = str(preview.period_start.year) if preview.period_start else "sem_periodo"
    directory = root / institution / f"account_{account_id}" / year
    directory.mkdir(parents=True, exist_ok=True)
    original_name = _safe_filename(preview.statement.source_file)
    destination = directory / f"{preview.file_hash[:12]}__{original_name}"
    if not destination.exists():
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(preview.content)
        temporary.replace(destination)
    return destination


def _safe_segment(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", errors="ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.casefold()).strip("_") or "unknown"


def _safe_filename(value: str) -> str:
    name = Path(value).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "statement"


def _category_lookup(session: Session) -> dict[tuple[str, str | None], int]:
    categories = session.scalars(select(Category)).all()
    by_id = {category.id: category for category in categories}
    lookup: dict[tuple[str, str | None], int] = {}
    for category in categories:
        parent = by_id.get(category.parent_id) if category.parent_id else None
        lookup[(category.name.casefold(), parent.name.casefold() if parent else None)] = category.id
    return lookup


def _resolve_category(
    row: ParsedTransaction, lookup: dict[tuple[str, str | None], int]
) -> int | None:
    if row.subcategory and row.category:
        match = lookup.get((row.subcategory.casefold(), row.category.casefold()))
        if match is not None:
            return match
    if row.category:
        return lookup.get((row.category.casefold(), None))
    return None


def _create_raw(batch_id: int, row: ParsedTransaction) -> RawTransaction:
    return RawTransaction(
        batch_id=batch_id,
        source_row=row.source_row,
        source_identifier=row.source_identifier,
        line_hash=raw_line_hash(row.raw_payload),
        original_transaction_date=row.original_transaction_date,
        original_amount=row.original_amount,
        original_description=row.original_description,
        raw_payload=row.raw_payload,
    )


def _create_invalid_raw(batch_id: int, row: InvalidTransaction) -> RawTransaction:
    payload = dict(row.raw_payload)
    payload["_validation_errors"] = list(row.errors)
    return RawTransaction(
        batch_id=batch_id,
        source_row=row.source_row,
        source_identifier=payload.get("FITID") or None,
        line_hash=raw_line_hash(payload),
        original_transaction_date=str(
            payload.get("DTPOSTED") or payload.get("transaction_date") or ""
        ),
        original_amount=str(payload.get("TRNAMT") or payload.get("amount") or ""),
        original_description=str(
            payload.get("MEMO") or payload.get("NAME") or payload.get("description") or ""
        ),
        raw_payload=payload,
    )
