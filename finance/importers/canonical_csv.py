"""Strict parser for version 1 of the canonical CSV contract."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from finance.importers.types import (
    InvalidTransaction,
    ParsedStatement,
    ParsedTransaction,
    StatementParseError,
)
from finance.models import TransactionNature
from finance.money import decimal_to_cents

REQUIRED_COLUMNS = {
    "transaction_date",
    "account",
    "description",
    "amount",
    "balance_after",
    "nature",
    "category",
    "subcategory",
    "is_internal_transfer",
    "is_extraordinary",
    "source_file",
    "source_row",
    "confidence",
}


class CanonicalCsvRow(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=False)

    transaction_date: date
    account: str = Field(min_length=1)
    description: str = Field(min_length=1)
    amount: Decimal
    balance_after: Decimal | None = None
    nature: TransactionNature
    category: str | None = None
    subcategory: str | None = None
    is_internal_transfer: bool
    is_extraordinary: bool
    source_file: str = Field(min_length=1)
    source_row: str = Field(min_length=1)
    confidence: Decimal | None = None

    @field_validator("amount", "balance_after")
    @classmethod
    def validate_money(cls, value: Decimal | None) -> Decimal | None:
        if value is not None:
            decimal_to_cents(value)
        return value

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not Decimal("0") <= value <= Decimal("1"):
            raise ValueError("confidence deve estar entre 0 e 1")
        return value

    @field_validator("is_internal_transfer", "is_extraordinary", mode="before")
    @classmethod
    def validate_boolean(cls, value: object) -> bool:
        if isinstance(value, str) and value.casefold() in {"true", "false"}:
            return value.casefold() == "true"
        raise ValueError("use somente true ou false")


def _blank_to_none(row: dict[str, str]) -> dict[str, str | None]:
    optional = {"balance_after", "category", "subcategory", "confidence"}
    return {key: (None if key in optional and value == "" else value) for key, value in row.items()}


def parse_canonical_csv(content: bytes, source_file: str) -> ParsedStatement:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StatementParseError("CSV deve usar codificação UTF-8") from exc

    reader = csv.DictReader(io.StringIO(text))
    columns = set(reader.fieldnames or [])
    missing = sorted(REQUIRED_COLUMNS - columns)
    if missing:
        raise StatementParseError(f"CSV sem colunas obrigatórias: {', '.join(missing)}")

    valid: list[ParsedTransaction] = []
    invalid: list[InvalidTransaction] = []
    accounts: set[str] = set()
    for line_number, raw in enumerate(reader, start=2):
        payload = {key: value for key, value in raw.items() if key is not None}
        try:
            row = CanonicalCsvRow.model_validate(_blank_to_none(payload))
        except ValidationError as exc:
            errors = tuple(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            )
            invalid.append(InvalidTransaction(str(line_number), errors, payload))
            continue

        accounts.add(row.account)
        valid.append(
            ParsedTransaction(
                source_row=row.source_row,
                original_transaction_date=payload["transaction_date"],
                transaction_date=row.transaction_date,
                original_amount=payload["amount"],
                amount_cents=decimal_to_cents(row.amount),
                original_description=row.description,
                balance_after_cents=(
                    decimal_to_cents(row.balance_after) if row.balance_after is not None else None
                ),
                nature=row.nature,
                category=row.category,
                subcategory=row.subcategory,
                is_internal_transfer=row.is_internal_transfer,
                is_extraordinary=row.is_extraordinary,
                confidence_basis_points=(
                    int(row.confidence * 10_000) if row.confidence is not None else None
                ),
                source_identifier=None,
                raw_payload=payload,
            )
        )

    if len(accounts) > 1:
        raise StatementParseError(
            "um lote CSV deve conter somente uma conta; separe o arquivo por conta"
        )
    if not valid and not invalid:
        raise StatementParseError("CSV não contém linhas de movimentação")

    return ParsedStatement(
        source_format="csv",
        source_file=source_file,
        account_label=next(iter(accounts), None),
        institution_code=None,
        institution_label=None,
        source_account_fingerprint=None,
        currency="BRL",
        transactions=tuple(valid),
        invalid_transactions=tuple(invalid),
        closing_balance_cents=(
            valid[-1].balance_after_cents
            if valid and all(row.balance_after_cents is not None for row in valid)
            else None
        ),
    )
