from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class AccountDefinition:
    account_id: str
    institution: str
    path_prefix: str
    expected_bank_id: str


@dataclass(frozen=True)
class ParsedTransaction:
    transaction_date: date
    amount_cents: int
    transaction_type: str
    bank_transaction_id: str
    name_raw: str
    memo_raw: str
    description_raw: str


@dataclass(frozen=True)
class ParsedStatement:
    bank_id: str
    account_fingerprint: str
    ofx_start_raw: str
    ofx_end_raw: str
    balance_date: date | None
    balance_cents: int | None
    transactions: tuple[ParsedTransaction, ...]

    @property
    def coverage_start(self) -> date | None:
        return min((item.transaction_date for item in self.transactions), default=None)

    @property
    def coverage_end(self) -> date | None:
        return max((item.transaction_date for item in self.transactions), default=None)
