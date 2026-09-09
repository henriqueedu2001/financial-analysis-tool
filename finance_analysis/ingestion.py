from __future__ import annotations

import csv
import hashlib
import tempfile
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from finance_analysis.config import account_for_path
from finance_analysis.models import AccountDefinition, ParsedStatement, ParsedTransaction
from finance_analysis.ofx import parse_statement, sha256_bytes

SUPPORTED_SUFFIXES = {".ofx"}
BALANCE_MARKER_DESCRIPTIONS = {"saldo anterior", "saldo do dia"}


def discover_sources(source_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    )


def is_balance_marker(transaction: ParsedTransaction) -> bool:
    return (
        not transaction.bank_transaction_id
        and transaction.description_raw.strip().casefold() in BALANCE_MARKER_DESCRIPTIONS
    )


def movement_transactions(statement: ParsedStatement) -> tuple[ParsedTransaction, ...]:
    return tuple(item for item in statement.transactions if not is_balance_marker(item))


def stable_transaction_id(
    account_fingerprint: str,
    transaction: ParsedTransaction,
    occurrence: int,
) -> str:
    if transaction.bank_transaction_id:
        identity = "\0".join(
            (
                "bank-id",
                account_fingerprint,
                transaction.bank_transaction_id,
                transaction.transaction_date.isoformat(),
                str(transaction.amount_cents),
                transaction.description_raw,
            )
        )
    else:
        identity = "\0".join(
            (
                "fallback",
                account_fingerprint,
                transaction.transaction_date.isoformat(),
                str(transaction.amount_cents),
                transaction.description_raw,
                str(occurrence),
            )
        )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _iso(value: date | None) -> str:
    return value.isoformat() if value else ""


def _statement_for_source(path: Path) -> ParsedStatement:
    return parse_statement(path.read_bytes())


def build_inventory(
    source_dir: Path,
    accounts: tuple[AccountDefinition, ...],
) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    first_by_hash: dict[str, str] = {}
    fingerprints: dict[str, str] = {}

    for path in discover_sources(source_dir):
        relative = path.relative_to(source_dir)
        account = account_for_path(relative, accounts)
        content = path.read_bytes()
        digest = sha256_bytes(content)
        duplicate_of = first_by_hash.setdefault(digest, relative.as_posix())
        duplicate_of = "" if duplicate_of == relative.as_posix() else duplicate_of
        base: dict[str, str | int] = {
            "source_file": relative.as_posix(),
            "source_sha256": digest,
            "file_size_bytes": len(content),
            "institution": account.institution,
            "account_id": account.account_id,
            "format": path.suffix.lower().lstrip("."),
            "supported": str(path.suffix.lower() in SUPPORTED_SUFFIXES).lower(),
            "duplicate_of": duplicate_of,
            "status": "not_parsed",
            "account_fingerprint": "",
            "coverage_start": "",
            "coverage_end": "",
            "balance_date": "",
            "balance_cents": "",
            "ofx_rows": "",
            "ignored_balance_markers": "",
            "transaction_rows": "",
        }
        if path.suffix.lower() in SUPPORTED_SUFFIXES:
            statement = _statement_for_source(path)
            if statement.bank_id != account.expected_bank_id:
                raise ValueError(
                    f"BANKID inesperado em {relative}: {statement.bank_id!r}"
                )
            existing = fingerprints.setdefault(account.account_id, statement.account_fingerprint)
            if existing != statement.account_fingerprint:
                raise ValueError(f"Mais de uma conta bancária encontrada em {account.account_id}")
            movements = movement_transactions(statement)
            base.update(
                {
                    "status": "parsed",
                    "account_fingerprint": statement.account_fingerprint,
                    "coverage_start": _iso(
                        min((item.transaction_date for item in movements), default=None)
                    ),
                    "coverage_end": _iso(
                        max((item.transaction_date for item in movements), default=None)
                    ),
                    "balance_date": _iso(statement.balance_date),
                    "balance_cents": (
                        statement.balance_cents if statement.balance_cents is not None else ""
                    ),
                    "ofx_rows": len(statement.transactions),
                    "ignored_balance_markers": len(statement.transactions) - len(movements),
                    "transaction_rows": len(movements),
                }
            )
        rows.append(base)
    return rows


def build_canonical(
    source_dir: Path,
    accounts: tuple[AccountDefinition, ...],
) -> tuple[list[dict[str, str | int]], list[dict[str, str | int]]]:
    transactions_by_id: dict[str, dict[str, str | int]] = {}
    snapshots_by_key: dict[tuple[str, str], dict[str, str | int]] = {}
    fingerprints: dict[str, str] = {}
    seen_source_hashes: set[str] = set()

    for path in discover_sources(source_dir):
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        relative = path.relative_to(source_dir)
        account = account_for_path(relative, accounts)
        content = path.read_bytes()
        source_hash = sha256_bytes(content)
        if source_hash in seen_source_hashes:
            continue
        seen_source_hashes.add(source_hash)
        statement = parse_statement(content)
        if statement.bank_id != account.expected_bank_id:
            raise ValueError(f"BANKID inesperado em {relative}: {statement.bank_id!r}")
        existing_fingerprint = fingerprints.setdefault(
            account.account_id, statement.account_fingerprint
        )
        if existing_fingerprint != statement.account_fingerprint:
            raise ValueError(f"Mais de uma conta bancária encontrada em {account.account_id}")

        occurrence_by_fallback: dict[tuple[date, int, str], int] = {}
        for position, transaction in enumerate(statement.transactions, start=1):
            if is_balance_marker(transaction):
                continue
            fallback_key = (
                transaction.transaction_date,
                transaction.amount_cents,
                transaction.description_raw,
            )
            occurrence_by_fallback[fallback_key] = occurrence_by_fallback.get(fallback_key, 0) + 1
            transaction_id = stable_transaction_id(
                statement.account_fingerprint,
                transaction,
                occurrence_by_fallback[fallback_key],
            )
            row: dict[str, str | int] = {
                "transaction_id": transaction_id,
                "account_id": account.account_id,
                "institution": account.institution,
                "account_fingerprint": statement.account_fingerprint,
                "transaction_date": transaction.transaction_date.isoformat(),
                "amount_cents": transaction.amount_cents,
                "transaction_type": transaction.transaction_type,
                "bank_transaction_id": transaction.bank_transaction_id,
                "description_raw": transaction.description_raw,
                "name_raw": transaction.name_raw,
                "memo_raw": transaction.memo_raw,
                "source_file": relative.as_posix(),
                "source_sha256": source_hash,
                "source_position": position,
            }
            previous = transactions_by_id.get(transaction_id)
            if previous is not None:
                comparable = (
                    "account_id",
                    "transaction_date",
                    "amount_cents",
                    "description_raw",
                    "bank_transaction_id",
                )
                if any(previous[key] != row[key] for key in comparable):
                    raise ValueError(
                        f"Identificador bancário conflitante: {transaction.bank_transaction_id!r}"
                    )
                continue
            transactions_by_id[transaction_id] = row

        if statement.balance_date is not None and statement.balance_cents is not None:
            key = (account.account_id, statement.balance_date.isoformat())
            snapshot: dict[str, str | int] = {
                "account_id": account.account_id,
                "institution": account.institution,
                "balance_date": statement.balance_date.isoformat(),
                "balance_cents": statement.balance_cents,
                "source_file": relative.as_posix(),
                "source_sha256": source_hash,
            }
            previous_snapshot = snapshots_by_key.get(key)
            if (
                previous_snapshot
                and previous_snapshot["balance_cents"] != snapshot["balance_cents"]
            ):
                raise ValueError(f"Saldos conflitantes para {account.account_id} em {key[1]}")
            snapshots_by_key[key] = snapshot

    transactions = sorted(
        transactions_by_id.values(),
        key=lambda row: (
            str(row["transaction_date"]),
            str(row["account_id"]),
            str(row["transaction_id"]),
        ),
    )
    snapshots = sorted(
        snapshots_by_key.values(),
        key=lambda row: (str(row["balance_date"]), str(row["account_id"])),
    )
    return transactions, snapshots


def _month_sequence(first: date, last: date) -> list[str]:
    year, month = first.year, first.month
    result: list[str] = []
    while (year, month) <= (last.year, last.month):
        result.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return result


def build_coverage_summary(
    transactions: list[dict[str, str | int]],
    snapshots: list[dict[str, str | int]],
) -> list[dict[str, str | int]]:
    result: list[dict[str, str | int]] = []
    account_ids = sorted({str(row["account_id"]) for row in transactions})
    for account_id in account_ids:
        account_rows = [row for row in transactions if row["account_id"] == account_id]
        dates = [date.fromisoformat(str(row["transaction_date"])) for row in account_rows]
        observed_months = {item.strftime("%Y-%m") for item in dates}
        expected_months = _month_sequence(min(dates), max(dates))
        account_snapshots = [row for row in snapshots if row["account_id"] == account_id]
        result.append(
            {
                "account_id": account_id,
                "institution": str(account_rows[0]["institution"]),
                "coverage_start": min(dates).isoformat(),
                "coverage_end": max(dates).isoformat(),
                "transaction_count": len(account_rows),
                "source_file_count": len({str(row["source_file"]) for row in account_rows}),
                "snapshot_count": len(account_snapshots),
                "months_without_transactions": ";".join(
                    month for month in expected_months if month not in observed_months
                ),
            }
        )
    return result


def build_reconciliation(
    transactions: list[dict[str, str | int]],
    snapshots: list[dict[str, str | int]],
) -> list[dict[str, str | int]]:
    result: list[dict[str, str | int]] = []
    account_ids = sorted({str(row["account_id"]) for row in snapshots})
    for account_id in account_ids:
        account_snapshots = sorted(
            (row for row in snapshots if row["account_id"] == account_id),
            key=lambda row: str(row["balance_date"]),
        )
        account_transactions = [
            row for row in transactions if row["account_id"] == account_id
        ]
        for opening, closing in zip(account_snapshots, account_snapshots[1:], strict=False):
            opening_date = date.fromisoformat(str(opening["balance_date"]))
            closing_date = date.fromisoformat(str(closing["balance_date"]))
            movement_cents = sum(
                int(row["amount_cents"])
                for row in account_transactions
                if opening_date
                < date.fromisoformat(str(row["transaction_date"]))
                <= closing_date
            )
            expected_cents = int(opening["balance_cents"]) + movement_cents
            difference_cents = int(closing["balance_cents"]) - expected_cents
            result.append(
                {
                    "account_id": account_id,
                    "opening_date": opening_date.isoformat(),
                    "opening_balance_cents": int(opening["balance_cents"]),
                    "closing_date": closing_date.isoformat(),
                    "closing_balance_cents": int(closing["balance_cents"]),
                    "movement_cents": movement_cents,
                    "difference_cents": difference_cents,
                    "status": "balanced" if difference_cents == 0 else "mismatch",
                }
            )
    return result


def write_csv_atomic(path: Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    materialized = list(rows)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(materialized)
        temporary_path = Path(stream.name)
    temporary_path.replace(path)


def fieldnames(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        raise ValueError("Não é possível escrever CSV vazio")
    return list(rows[0])
