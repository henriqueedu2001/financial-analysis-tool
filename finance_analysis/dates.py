from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

BB_MEMO_DATE = re.compile(r"^(\d{2})/(\d{2})\s+\d{2}:\d{2}(?:\s+|$)")
ITAU_MEMO_DATE = re.compile(r"(?<=[A-Za-z])(\d{2})\s+(\d{2})$")


@dataclass(frozen=True)
class OperationDate:
    value: date
    source: str
    days_from_posting: int


def _closest_date(posting_date: date, day: int, month: int) -> date | None:
    candidates: list[date] = []
    for year in (posting_date.year - 1, posting_date.year, posting_date.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: abs((candidate - posting_date).days))


def infer_operation_date(row: dict[str, str], maximum_posting_lag_days: int = 4) -> OperationDate:
    """Deriva a data da operação sem alterar a data contábil informada pelo OFX."""
    posting_date = date.fromisoformat(row["transaction_date"])
    memo = row.get("memo_raw", "").strip()
    match: re.Match[str] | None = None
    source = ""

    if row["account_id"] == "banco_do_brasil_conta_corrente":
        match = BB_MEMO_DATE.search(memo)
        source = "bb_memo_prefix"
    elif row["account_id"] == "itau_conta_corrente":
        match = ITAU_MEMO_DATE.search(memo)
        source = "itau_memo_suffix"

    if match:
        candidate = _closest_date(posting_date, int(match.group(1)), int(match.group(2)))
        if candidate is not None:
            difference = (candidate - posting_date).days
            if -maximum_posting_lag_days <= difference <= 0:
                return OperationDate(candidate, source, difference)

    return OperationDate(posting_date, "posting_date", 0)


def add_operation_dates(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for row in rows:
        operation = infer_operation_date(row)
        result.append(
            {
                **row,
                "posting_date": row["transaction_date"],
                "operation_date": operation.value.isoformat(),
                "operation_date_source": operation.source,
                "operation_posting_lag_days": str(operation.days_from_posting),
            }
        )
    return result
