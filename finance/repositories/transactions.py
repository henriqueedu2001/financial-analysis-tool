"""Queries and auditable manual corrections for transactions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from finance.models import (
    Category,
    ClassificationSource,
    ReviewState,
    Transaction,
    TransactionEdit,
    TransactionNature,
)


class TransactionUpdateError(ValueError):
    pass


@dataclass(frozen=True)
class TransactionFilters:
    date_from: date | None = None
    date_to: date | None = None
    account_ids: tuple[int, ...] = ()
    category_ids: tuple[int, ...] = ()
    natures: tuple[TransactionNature, ...] = ()
    min_amount_cents: int | None = None
    max_amount_cents: int | None = None
    description_contains: str | None = None
    review_state: ReviewState | None = None


def list_transactions(
    session: Session, filters: TransactionFilters | None = None, *, limit: int = 2000
) -> list[Transaction]:
    filters = filters or TransactionFilters()
    statement: Select = (
        select(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.category),
            joinedload(Transaction.raw_transaction),
            joinedload(Transaction.batch),
        )
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .limit(limit)
    )
    if filters.date_from:
        statement = statement.where(Transaction.transaction_date >= filters.date_from)
    if filters.date_to:
        statement = statement.where(Transaction.transaction_date <= filters.date_to)
    if filters.account_ids:
        statement = statement.where(Transaction.account_id.in_(filters.account_ids))
    if filters.category_ids:
        statement = statement.where(Transaction.category_id.in_(filters.category_ids))
    if filters.natures:
        statement = statement.where(Transaction.nature.in_(filters.natures))
    if filters.min_amount_cents is not None:
        statement = statement.where(Transaction.amount_cents >= filters.min_amount_cents)
    if filters.max_amount_cents is not None:
        statement = statement.where(Transaction.amount_cents <= filters.max_amount_cents)
    if filters.description_contains:
        escaped = (
            filters.description_contains.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        statement = statement.where(
            Transaction.original_description.ilike(f"%{escaped}%", escape="\\")
        )
    if filters.review_state:
        statement = statement.where(Transaction.review_state == filters.review_state)
    return list(session.scalars(statement))


def update_transaction_manual(
    session: Session,
    transaction_id: int,
    *,
    category_id: int | None,
    nature: TransactionNature,
    is_extraordinary: bool,
    is_essential_override: bool | None,
    is_living_cost_override: bool | None,
    reason: str | None = None,
    commit: bool = True,
) -> Transaction:
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise TransactionUpdateError("movimentação não encontrada")
    if category_id is not None:
        category = session.get(Category, category_id)
        if category is None or not category.is_active:
            raise TransactionUpdateError("categoria ativa não encontrada")

    requested = {
        "category_id": category_id,
        "nature": nature,
        "is_extraordinary": is_extraordinary,
        "is_essential_override": is_essential_override,
        "is_living_cost_override": is_living_cost_override,
    }
    changes: dict[str, dict[str, object]] = {}
    for field_name, new_value in requested.items():
        old_value = getattr(transaction, field_name)
        old_serialized = old_value.value if isinstance(old_value, TransactionNature) else old_value
        new_serialized = new_value.value if isinstance(new_value, TransactionNature) else new_value
        if old_serialized != new_serialized:
            changes[field_name] = {"before": old_serialized, "after": new_serialized}
            setattr(transaction, field_name, new_value)

    previous_source = transaction.classification_source
    previous_lock = transaction.manual_classification_locked
    transaction.classification_source = ClassificationSource.MANUAL
    transaction.manual_classification_locked = True
    transaction.review_state = ReviewState.REVIEWED
    if changes or not previous_lock or previous_source is not ClassificationSource.MANUAL:
        changes["classification_source"] = {
            "before": previous_source.value,
            "after": ClassificationSource.MANUAL.value,
        }
        changes["manual_classification_locked"] = {
            "before": previous_lock,
            "after": True,
        }
        session.add(
            TransactionEdit(
                transaction_id=transaction.id,
                changes=changes,
                reason=reason.strip() if reason and reason.strip() else None,
            )
        )
    if commit:
        session.commit()
    else:
        session.flush()
    return transaction
