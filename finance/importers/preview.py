"""Build a non-mutating import preview with reconciliation and duplicate hints."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from finance.importers import parse_statement
from finance.importers.hashing import sha256_bytes, transaction_signature
from finance.importers.types import ParsedStatement
from finance.models import ImportBatch, ImportStatus, Transaction


@dataclass(frozen=True)
class ImportPreview:
    content: bytes
    statement: ParsedStatement
    file_hash: str
    account_id: int | None
    same_file_already_imported: bool
    internal_duplicate_rows: tuple[str, ...]
    existing_duplicate_rows: tuple[str, ...]
    period_start: date | None
    period_end: date | None
    inflow_cents: int
    outflow_cents: int
    opening_balance_cents: int | None
    closing_balance_cents: int | None
    reconciliation_difference_cents: int | None
    balance_sequence_error_rows: tuple[str, ...]

    @property
    def has_possible_duplicates(self) -> bool:
        return bool(self.internal_duplicate_rows or self.existing_duplicate_rows)


def build_import_preview(
    content: bytes,
    source_file: str,
    session: Session,
    account_id: int | None = None,
) -> ImportPreview:
    statement = parse_statement(content, source_file)
    file_hash = sha256_bytes(content)
    rows = statement.transactions
    dates = [row.transaction_date for row in rows]
    inflow = sum(row.amount_cents for row in rows if row.amount_cents > 0)
    outflow = sum(row.amount_cents for row in rows if row.amount_cents < 0)

    same_file = False
    internal_duplicates: tuple[str, ...] = ()
    existing_duplicates: tuple[str, ...] = ()
    if account_id is not None:
        imported_statuses = (ImportStatus.IMPORTED, ImportStatus.IMPORTED_WITH_WARNING)
        same_file = (
            session.scalar(
                select(ImportBatch.id).where(
                    ImportBatch.account_id == account_id,
                    ImportBatch.file_hash == file_hash,
                    ImportBatch.status.in_(imported_statuses),
                )
            )
            is not None
        )

        signatures = [
            transaction_signature(
                account_id, row.transaction_date, row.amount_cents, row.original_description
            )
            for row in rows
        ]
        counts = Counter(signatures)
        internal_duplicates = tuple(
            row.source_row
            for row, signature in zip(rows, signatures, strict=True)
            if counts[signature] > 1
        )
        if signatures:
            existing = set(
                session.scalars(
                    select(Transaction.stable_signature).where(
                        Transaction.account_id == account_id,
                        Transaction.stable_signature.in_(set(signatures)),
                    )
                )
            )
            existing_duplicates = tuple(
                row.source_row
                for row, signature in zip(rows, signatures, strict=True)
                if signature in existing
            )

    opening, closing, difference, sequence_errors = _reconcile(statement)
    return ImportPreview(
        content=content,
        statement=statement,
        file_hash=file_hash,
        account_id=account_id,
        same_file_already_imported=same_file,
        internal_duplicate_rows=internal_duplicates,
        existing_duplicate_rows=existing_duplicates,
        period_start=min(dates) if dates else None,
        period_end=max(dates) if dates else None,
        inflow_cents=inflow,
        outflow_cents=outflow,
        opening_balance_cents=opening,
        closing_balance_cents=closing,
        reconciliation_difference_cents=difference,
        balance_sequence_error_rows=sequence_errors,
    )


def _reconcile(
    statement: ParsedStatement,
) -> tuple[int | None, int | None, int | None, tuple[str, ...]]:
    rows = statement.transactions
    if not rows or not all(row.balance_after_cents is not None for row in rows):
        return None, statement.closing_balance_cents, None, ()

    first_balance = rows[0].balance_after_cents
    assert first_balance is not None
    opening = first_balance - rows[0].amount_cents
    expected = opening
    errors: list[str] = []
    for row in rows:
        expected += row.amount_cents
        if row.balance_after_cents != expected:
            errors.append(row.source_row)
    closing = rows[-1].balance_after_cents
    assert closing is not None
    difference = opening + sum(row.amount_cents for row in rows) - closing
    return opening, closing, difference, tuple(errors)
