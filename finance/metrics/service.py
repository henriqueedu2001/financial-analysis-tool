"""Deterministic financial metrics over normalized local data."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from finance.models import Account, BalanceSnapshot, Transaction, TransactionNature


@dataclass(frozen=True)
class AccountBalance:
    account_id: int
    account_name: str
    as_of: date
    balance_cents: int | None
    is_reserve: bool
    financial_role: str
    included_in_tracked_wealth: bool


@dataclass(frozen=True)
class PeriodMetrics:
    date_from: date
    date_to: date
    external_income_cents: int
    external_expenses_cents: int
    living_cost_cents: int
    extraordinary_expenses_cents: int
    savings_cents: int
    savings_rate: Decimal | None
    net_reserve_contribution_cents: int
    tracked_wealth_cents: int | None
    operational_balance_cents: int | None
    reserve_balance_cents: int | None


@dataclass(frozen=True)
class MonthlyMetrics:
    month: date
    external_income_cents: int
    external_expenses_cents: int
    living_cost_cents: int
    extraordinary_expenses_cents: int
    savings_cents: int
    savings_rate: Decimal | None
    net_reserve_contribution_cents: int
    tracked_wealth_cents: int | None


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _month_end(value: date) -> date:
    return value.replace(day=calendar.monthrange(value.year, value.month)[1])


def _next_month(value: date) -> date:
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)


def _months_between(start: date, end: date) -> list[date]:
    current = _month_start(start)
    months: list[date] = []
    while current <= _month_start(end):
        months.append(current)
        current = _next_month(current)
    return months


def _effective_living_cost(transaction: Transaction) -> bool:
    if transaction.is_living_cost_override is not None:
        return transaction.is_living_cost_override
    return bool(transaction.category and transaction.category.is_living_cost)


def _is_external(transaction: Transaction) -> bool:
    return not transaction.is_internal_transfer and transaction.nature not in {
        TransactionNature.TRANSFER,
        TransactionNature.ADJUSTMENT,
    }


def _transactions_in_period(session: Session, start: date, end: date) -> list[Transaction]:
    return session.scalars(
        select(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.account))
        .where(Transaction.transaction_date >= start, Transaction.transaction_date <= end)
        .order_by(Transaction.transaction_date, Transaction.id)
    ).all()


def account_balances_as_of(session: Session, as_of: date) -> list[AccountBalance]:
    accounts = session.scalars(select(Account).where(Account.is_active.is_(True))).all()
    balances: list[AccountBalance] = []
    for account in accounts:
        snapshot = session.scalar(
            select(BalanceSnapshot)
            .where(
                BalanceSnapshot.account_id == account.id,
                BalanceSnapshot.snapshot_date <= as_of,
            )
            .order_by(BalanceSnapshot.snapshot_date.desc(), BalanceSnapshot.id.desc())
            .limit(1)
        )
        balance: int | None = None
        if snapshot is not None:
            movement_total = session.scalar(
                select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
                    Transaction.account_id == account.id,
                    Transaction.transaction_date > snapshot.snapshot_date,
                    Transaction.transaction_date <= as_of,
                )
            )
            balance = snapshot.balance_cents + int(movement_total or 0)
        balances.append(
            AccountBalance(
                account_id=account.id,
                account_name=account.name,
                as_of=as_of,
                balance_cents=balance,
                is_reserve=account.is_reserve,
                financial_role=account.financial_role.value,
                included_in_tracked_wealth=account.include_in_tracked_wealth,
            )
        )
    return balances


def period_metrics(session: Session, start: date, end: date) -> PeriodMetrics:
    transactions = _transactions_in_period(session, start, end)
    external = [transaction for transaction in transactions if _is_external(transaction)]
    income = sum(
        transaction.amount_cents for transaction in external if transaction.amount_cents > 0
    )
    expenses = sum(
        abs(transaction.amount_cents) for transaction in external if transaction.amount_cents < 0
    )
    living_cost = sum(
        abs(transaction.amount_cents)
        for transaction in external
        if transaction.amount_cents < 0 and _effective_living_cost(transaction)
    )
    extraordinary = sum(
        abs(transaction.amount_cents)
        for transaction in external
        if transaction.amount_cents < 0 and transaction.is_extraordinary
    )
    savings = income - expenses
    savings_rate = Decimal(savings) / Decimal(income) if income else None
    reserve_contribution = sum(
        transaction.amount_cents
        for transaction in transactions
        if transaction.is_internal_transfer and transaction.account.is_reserve
    )
    balances = account_balances_as_of(session, end)
    tracked_values = [
        balance.balance_cents for balance in balances if balance.included_in_tracked_wealth
    ]
    tracked_wealth = (
        sum(value for value in tracked_values if value is not None)
        if tracked_values and all(value is not None for value in tracked_values)
        else None
    )
    operational_values = [
        balance.balance_cents for balance in balances if balance.financial_role == "operational"
    ]
    reserve_values = [balance.balance_cents for balance in balances if balance.is_reserve]
    return PeriodMetrics(
        date_from=start,
        date_to=end,
        external_income_cents=income,
        external_expenses_cents=expenses,
        living_cost_cents=living_cost,
        extraordinary_expenses_cents=extraordinary,
        savings_cents=savings,
        savings_rate=savings_rate,
        net_reserve_contribution_cents=reserve_contribution,
        tracked_wealth_cents=tracked_wealth,
        operational_balance_cents=(
            sum(value for value in operational_values if value is not None)
            if operational_values and all(value is not None for value in operational_values)
            else None
        ),
        reserve_balance_cents=(
            sum(value for value in reserve_values if value is not None)
            if reserve_values and all(value is not None for value in reserve_values)
            else None
        ),
    )


def monthly_metrics(session: Session, start: date, end: date) -> list[MonthlyMetrics]:
    results: list[MonthlyMetrics] = []
    for month in _months_between(start, end):
        metrics = period_metrics(session, max(start, month), min(end, _month_end(month)))
        results.append(
            MonthlyMetrics(
                month=month,
                external_income_cents=metrics.external_income_cents,
                external_expenses_cents=metrics.external_expenses_cents,
                living_cost_cents=metrics.living_cost_cents,
                extraordinary_expenses_cents=metrics.extraordinary_expenses_cents,
                savings_cents=metrics.savings_cents,
                savings_rate=metrics.savings_rate,
                net_reserve_contribution_cents=metrics.net_reserve_contribution_cents,
                tracked_wealth_cents=metrics.tracked_wealth_cents,
            )
        )
    return results


def burn_rate_normalized(
    session: Session,
    *,
    as_of: date,
    window_months: int,
    include_extraordinary: bool,
) -> int | None:
    if window_months not in {3, 6, 12}:
        raise ValueError("janela do burn rate deve ser 3, 6 ou 12 meses")
    end_month = _month_start(as_of)
    months = [end_month]
    while len(months) < window_months:
        previous_end = months[0] - date.resolution
        months.insert(0, _month_start(previous_end))
    earliest_transaction = session.scalar(select(func.min(Transaction.transaction_date)))
    if earliest_transaction is None or _month_start(earliest_transaction) > months[0]:
        return None
    transactions = _transactions_in_period(session, months[0], _month_end(months[-1]))
    totals = {month: 0 for month in months}
    for transaction in transactions:
        if (
            transaction.amount_cents < 0
            and _is_external(transaction)
            and _effective_living_cost(transaction)
            and (include_extraordinary or not transaction.is_extraordinary)
        ):
            totals[_month_start(transaction.transaction_date)] += abs(transaction.amount_cents)
    average = Decimal(sum(totals.values())) / Decimal(window_months)
    return int(average.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def reserve_coverage_months(
    session: Session,
    *,
    as_of: date,
    window_months: int,
    include_extraordinary: bool,
) -> Decimal | None:
    burn_rate = burn_rate_normalized(
        session,
        as_of=as_of,
        window_months=window_months,
        include_extraordinary=include_extraordinary,
    )
    if not burn_rate:
        return None
    reserve_balances = [
        balance.balance_cents
        for balance in account_balances_as_of(session, as_of)
        if balance.is_reserve and balance.included_in_tracked_wealth
    ]
    if not reserve_balances or any(balance is None for balance in reserve_balances):
        return None
    reserve_total = sum(balance for balance in reserve_balances if balance is not None)
    return Decimal(reserve_total) / Decimal(burn_rate)


def category_spending(session: Session, start: date, end: date) -> list[tuple[str, int]]:
    transactions = _transactions_in_period(session, start, end)
    totals: dict[str, int] = {}
    for transaction in transactions:
        if transaction.amount_cents >= 0 or not _is_external(transaction):
            continue
        category = transaction.category
        label = category.name if category else "A revisar"
        totals[label] = totals.get(label, 0) + abs(transaction.amount_cents)
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))


def account_balance_series(
    session: Session, start: date, end: date
) -> list[tuple[date, AccountBalance]]:
    return [
        (month, balance)
        for month in _months_between(start, end)
        for balance in account_balances_as_of(session, min(end, _month_end(month)))
    ]
