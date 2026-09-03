"""Balance snapshots and deterministic reconciliation between known balances."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finance.models import Account, BalanceSnapshot, Transaction


class ReconciliationError(ValueError):
    pass


@dataclass(frozen=True)
class ReconciliationResult:
    account_id: int
    opening_date: date
    closing_date: date
    opening_balance_cents: int
    movement_total_cents: int
    calculated_closing_balance_cents: int
    reported_closing_balance_cents: int
    difference_cents: int


def record_balance_snapshot(
    session: Session,
    *,
    account_id: int,
    snapshot_date: date,
    balance_cents: int,
    source_batch_id: int | None = None,
    source_note: str | None = None,
    commit: bool = True,
) -> BalanceSnapshot:
    if session.get(Account, account_id) is None:
        raise ReconciliationError("conta não encontrada")
    existing = session.scalar(
        select(BalanceSnapshot).where(
            BalanceSnapshot.account_id == account_id,
            BalanceSnapshot.snapshot_date == snapshot_date,
        )
    )
    if existing is not None:
        if existing.balance_cents != balance_cents:
            raise ReconciliationError("já existe um saldo diferente para esta conta e data")
        return existing
    snapshot = BalanceSnapshot(
        account_id=account_id,
        snapshot_date=snapshot_date,
        balance_cents=balance_cents,
        source_batch_id=source_batch_id,
        source_note=source_note.strip() if source_note and source_note.strip() else None,
    )
    session.add(snapshot)
    if commit:
        session.commit()
    else:
        session.flush()
    return snapshot


def reconcile_account(session: Session, account_id: int) -> list[ReconciliationResult]:
    snapshots = session.scalars(
        select(BalanceSnapshot)
        .where(BalanceSnapshot.account_id == account_id)
        .order_by(BalanceSnapshot.snapshot_date, BalanceSnapshot.id)
    ).all()
    results: list[ReconciliationResult] = []
    for opening, closing in zip(snapshots, snapshots[1:], strict=False):
        movement_total = session.scalar(
            select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
                Transaction.account_id == account_id,
                Transaction.transaction_date > opening.snapshot_date,
                Transaction.transaction_date <= closing.snapshot_date,
            )
        )
        movement_total = int(movement_total or 0)
        calculated = opening.balance_cents + movement_total
        results.append(
            ReconciliationResult(
                account_id=account_id,
                opening_date=opening.snapshot_date,
                closing_date=closing.snapshot_date,
                opening_balance_cents=opening.balance_cents,
                movement_total_cents=movement_total,
                calculated_closing_balance_cents=calculated,
                reported_closing_balance_cents=closing.balance_cents,
                difference_cents=calculated - closing.balance_cents,
            )
        )
    return results
