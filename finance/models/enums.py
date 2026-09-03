"""Stable string enums stored in SQLite."""

from enum import StrEnum


class StringEnum(StrEnum):
    pass


class AccountType(StringEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    INVESTMENT = "investment"
    CASH = "cash"
    CREDIT = "credit"
    OTHER = "other"


class FinancialRole(StringEnum):
    OPERATIONAL = "operational"
    RESERVE = "reserve"
    INVESTMENT = "investment"
    LIABILITY = "liability"


class ImportStatus(StringEnum):
    PREVIEW = "preview"
    VALIDATED = "validated"
    IMPORTED = "imported"
    IMPORTED_WITH_WARNING = "imported_with_warning"
    REJECTED = "rejected"


class TransactionNature(StringEnum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    INVESTMENT_RETURN = "investment_return"
    REFUND = "refund"
    FEE = "fee"
    ADJUSTMENT = "adjustment"
    UNCLASSIFIED = "unclassified"


class ReviewState(StringEnum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    NEEDS_ATTENTION = "needs_attention"


class ClassificationSource(StringEnum):
    IMPORTED = "imported"
    RULE = "rule"
    MANUAL = "manual"
    NONE = "none"


class RuleMatchType(StringEnum):
    DESCRIPTION_CONTAINS = "description_contains"
    DESCRIPTION_REGEX = "description_regex"
    COUNTERPARTY_CONTAINS = "counterparty_contains"


class TransferMatchState(StringEnum):
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
