"""SQLAlchemy models for auditable local financial data."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finance.db.base import Base
from finance.models.enums import (
    AccountType,
    ClassificationSource,
    FinancialRole,
    ImportStatus,
    ReviewState,
    RuleMatchType,
    TransactionNature,
    TransferMatchState,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def enum_column(enum_type: type, default=None):
    kwargs = {
        "native_enum": False,
        "values_callable": lambda values: [item.value for item in values],
    }
    return mapped_column(SqlEnum(enum_type, **kwargs), default=default)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("length(currency) = 3", name="ck_accounts_currency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    institution: Mapped[str | None] = mapped_column(String(120))
    source_institution_code: Mapped[str | None] = mapped_column(String(40))
    source_account_fingerprint: Mapped[str | None] = mapped_column(String(64), unique=True)
    account_type: Mapped[AccountType] = enum_column(AccountType)
    financial_role: Mapped[FinancialRole] = enum_column(FinancialRole)
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    include_in_tracked_wealth: Mapped[bool] = mapped_column(Boolean, default=True)
    is_reserve: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    import_batches: Mapped[list[ImportBatch]] = relationship(back_populates="account")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="account")


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint("row_count >= 0", name="ck_import_batches_row_count"),
        Index("ix_import_batches_file_hash", "file_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_format: Mapped[str] = mapped_column(String(20), nullable=False, default="csv")
    archived_source_path: Mapped[str | None] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[ImportStatus] = enum_column(ImportStatus, ImportStatus.PREVIEW)
    inflow_cents: Mapped[int] = mapped_column(Integer, default=0)
    outflow_cents: Mapped[int] = mapped_column(Integer, default=0)
    opening_balance_cents: Mapped[int | None] = mapped_column(Integer)
    closing_balance_cents: Mapped[int | None] = mapped_column(Integer)
    reconciliation_difference_cents: Mapped[int | None] = mapped_column(Integer)
    validation_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reconciliation_override_reason: Mapped[str | None] = mapped_column(Text)

    account: Mapped[Account] = relationship(back_populates="import_batches")
    raw_transactions: Mapped[list[RawTransaction]] = relationship(back_populates="batch")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="batch")


class RawTransaction(Base):
    """Append-only representation of one source row.

    Immutability is an application invariant: later corrections belong in Transaction.
    """

    __tablename__ = "raw_transactions"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_row", name="uq_raw_batch_source_row"),
        Index("ix_raw_transactions_line_hash", "line_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    source_row: Mapped[str] = mapped_column(String(120), nullable=False)
    source_identifier: Mapped[str | None] = mapped_column(String(255))
    line_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_transaction_date: Mapped[str] = mapped_column(String(40), nullable=False)
    original_amount: Mapped[str] = mapped_column(String(80), nullable=False)
    original_description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    batch: Mapped[ImportBatch] = relationship(back_populates="raw_transactions")
    transaction: Mapped[Transaction | None] = relationship(back_populates="raw_transaction")


class RawTransactionImmutable(RuntimeError):
    """Raised when application code attempts to mutate imported raw evidence."""


@event.listens_for(RawTransaction, "before_update")
@event.listens_for(RawTransaction, "before_delete")
def _prevent_raw_transaction_changes(*_args) -> None:
    raise RawTransactionImmutable(
        "raw transactions are append-only; apply corrections to transactions"
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    is_living_cost: Mapped[bool] = mapped_column(Boolean, default=False)
    is_essential: Mapped[bool] = mapped_column(Boolean, default=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    is_extraordinary_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    parent: Mapped[Category | None] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list[Category]] = relationship(back_populates="parent")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("raw_transaction_id", name="uq_transactions_raw_transaction"),
        CheckConstraint(
            "confidence_basis_points IS NULL OR "
            "(confidence_basis_points >= 0 AND confidence_basis_points <= 10000)",
            name="ck_transactions_confidence",
        ),
        Index("ix_transactions_date_account", "transaction_date", "account_id"),
        Index("ix_transactions_stable_signature", "stable_signature"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    original_description: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_description: Mapped[str | None] = mapped_column(Text)
    counterparty: Mapped[str | None] = mapped_column(String(255))
    nature: Mapped[TransactionNature] = enum_column(
        TransactionNature, TransactionNature.UNCLASSIFIED
    )
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    subcategory_text: Mapped[str | None] = mapped_column(String(120))
    is_internal_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    is_extraordinary: Mapped[bool] = mapped_column(Boolean, default=False)
    review_state: Mapped[ReviewState] = enum_column(ReviewState, ReviewState.PENDING)
    confidence_basis_points: Mapped[int | None] = mapped_column(Integer)
    classification_source: Mapped[ClassificationSource] = enum_column(
        ClassificationSource, ClassificationSource.NONE
    )
    manual_classification_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    stable_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    bank_transaction_id: Mapped[str | None] = mapped_column(String(255))
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    raw_transaction_id: Mapped[int] = mapped_column(
        ForeignKey("raw_transactions.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    account: Mapped[Account] = relationship(back_populates="transactions")
    batch: Mapped[ImportBatch] = relationship(back_populates="transactions")
    raw_transaction: Mapped[RawTransaction] = relationship(back_populates="transaction")
    category: Mapped[Category | None] = relationship()


class ClassificationRule(Base):
    __tablename__ = "classification_rules"
    __table_args__ = (
        CheckConstraint("priority >= 0", name="ck_rules_priority"),
        UniqueConstraint("name", name="uq_classification_rules_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    match_type: Mapped[RuleMatchType] = enum_column(RuleMatchType)
    pattern: Mapped[str] = mapped_column(String(500), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    nature: Mapped[TransactionNature | None] = enum_column(TransactionNature)
    mark_extraordinary: Mapped[bool | None] = mapped_column(Boolean)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    category: Mapped[Category | None] = relationship()


class TransferMatch(Base):
    __tablename__ = "transfer_matches"
    __table_args__ = (
        CheckConstraint(
            "outgoing_transaction_id <> incoming_transaction_id",
            name="ck_transfer_match_distinct_transactions",
        ),
        UniqueConstraint(
            "outgoing_transaction_id",
            "incoming_transaction_id",
            name="uq_transfer_match_pair",
        ),
        CheckConstraint(
            "confidence_basis_points IS NULL OR "
            "(confidence_basis_points >= 0 AND confidence_basis_points <= 10000)",
            name="ck_transfer_matches_confidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    outgoing_transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"), nullable=False
    )
    incoming_transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id"), nullable=False
    )
    confidence_basis_points: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[TransferMatchState] = enum_column(
        TransferMatchState, TransferMatchState.SUGGESTED
    )
    manually_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    outgoing_transaction: Mapped[Transaction] = relationship(foreign_keys=[outgoing_transaction_id])
    incoming_transaction: Mapped[Transaction] = relationship(foreign_keys=[incoming_transaction_id])


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "snapshot_date", name="uq_balance_account_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    source_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"))
    source_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    account: Mapped[Account] = relationship()
    source_batch: Mapped[ImportBatch | None] = relationship()
