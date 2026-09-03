"""Transport objects shared by statement parsers and the import service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from finance.models import TransactionNature


@dataclass(frozen=True)
class ParsedTransaction:
    source_row: str
    original_transaction_date: str
    transaction_date: date
    original_amount: str
    amount_cents: int
    original_description: str
    balance_after_cents: int | None = None
    nature: TransactionNature = TransactionNature.UNCLASSIFIED
    category: str | None = None
    subcategory: str | None = None
    is_internal_transfer: bool = False
    is_extraordinary: bool = False
    confidence_basis_points: int | None = None
    source_identifier: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InvalidTransaction:
    source_row: str
    errors: tuple[str, ...]
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class ParsedStatement:
    source_format: str
    source_file: str
    account_label: str | None
    institution_code: str | None
    institution_label: str | None
    source_account_fingerprint: str | None
    currency: str
    transactions: tuple[ParsedTransaction, ...]
    invalid_transactions: tuple[InvalidTransaction, ...]
    closing_balance_cents: int | None = None


class StatementParseError(ValueError):
    """Raised when a file is not a supported or structurally usable statement."""
