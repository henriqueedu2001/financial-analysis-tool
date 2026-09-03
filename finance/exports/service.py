"""Deterministic CSV and JSON exports for local or external analysis."""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from finance.metrics import (
    burn_rate_normalized,
    category_spending,
    monthly_metrics,
    period_metrics,
    reserve_coverage_months,
)
from finance.models import Transaction
from finance.money import cents_to_decimal


def _money(cents: int | None) -> str | None:
    return None if cents is None else format(cents_to_decimal(cents), ".2f")


def _rate(value: Decimal | None) -> str | None:
    return None if value is None else format(value.quantize(Decimal("0.0001")), "f")


def transactions_csv(transactions: list[Transaction]) -> bytes:
    output = io.StringIO(newline="")
    fieldnames = [
        "transaction_id",
        "transaction_date",
        "account",
        "description",
        "amount",
        "nature",
        "category",
        "is_internal_transfer",
        "is_extraordinary",
        "is_essential",
        "is_living_cost",
        "review_state",
        "classification_source",
        "source_file",
        "source_row",
        "import_batch_id",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for transaction in transactions:
        category = transaction.category
        essential = (
            transaction.is_essential_override
            if transaction.is_essential_override is not None
            else bool(category and category.is_essential)
        )
        living_cost = (
            transaction.is_living_cost_override
            if transaction.is_living_cost_override is not None
            else bool(category and category.is_living_cost)
        )
        writer.writerow(
            {
                "transaction_id": transaction.id,
                "transaction_date": transaction.transaction_date.isoformat(),
                "account": transaction.account.name,
                "description": transaction.original_description,
                "amount": _money(transaction.amount_cents),
                "nature": transaction.nature.value,
                "category": category.name if category else "A revisar",
                "is_internal_transfer": str(transaction.is_internal_transfer).lower(),
                "is_extraordinary": str(transaction.is_extraordinary).lower(),
                "is_essential": str(essential).lower(),
                "is_living_cost": str(living_cost).lower(),
                "review_state": transaction.review_state.value,
                "classification_source": transaction.classification_source.value,
                "source_file": transaction.batch.source_file,
                "source_row": transaction.raw_transaction.source_row,
                "import_batch_id": transaction.batch_id,
            }
        )
    return output.getvalue().encode("utf-8")


def monthly_summary_csv(session: Session, start: date, end: date) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "month",
            "external_income",
            "external_expenses",
            "living_cost",
            "extraordinary_expenses",
            "savings",
            "savings_rate",
            "net_reserve_contribution",
            "tracked_wealth",
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    for item in monthly_metrics(session, start, end):
        writer.writerow(
            {
                "month": item.month.strftime("%Y-%m"),
                "external_income": _money(item.external_income_cents),
                "external_expenses": _money(item.external_expenses_cents),
                "living_cost": _money(item.living_cost_cents),
                "extraordinary_expenses": _money(item.extraordinary_expenses_cents),
                "savings": _money(item.savings_cents),
                "savings_rate": _rate(item.savings_rate),
                "net_reserve_contribution": _money(item.net_reserve_contribution_cents),
                "tracked_wealth": _money(item.tracked_wealth_cents),
            }
        )
    return output.getvalue().encode("utf-8")


def analytical_summary(
    session: Session,
    start: date,
    end: date,
    *,
    burn_window_months: int = 3,
    include_extraordinary_in_burn: bool = False,
) -> dict:
    metrics = period_metrics(session, start, end)
    burn = burn_rate_normalized(
        session,
        as_of=end,
        window_months=burn_window_months,
        include_extraordinary=include_extraordinary_in_burn,
    )
    coverage = reserve_coverage_months(
        session,
        as_of=end,
        window_months=burn_window_months,
        include_extraordinary=include_extraordinary_in_burn,
    )
    monthly = monthly_metrics(session, start, end)
    return {
        "schema_version": 1,
        "currency": "BRL",
        "money_format": "decimal_string",
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "external_income": _money(metrics.external_income_cents),
        "external_expenses": _money(metrics.external_expenses_cents),
        "living_cost": _money(metrics.living_cost_cents),
        "extraordinary_expenses": _money(metrics.extraordinary_expenses_cents),
        "savings": _money(metrics.savings_cents),
        "savings_rate": _rate(metrics.savings_rate),
        "net_reserve_contribution": _money(metrics.net_reserve_contribution_cents),
        "tracked_wealth": _money(metrics.tracked_wealth_cents),
        "reserve_balance": _money(metrics.reserve_balance_cents),
        "burn_rate": {
            "window_months": burn_window_months,
            "includes_extraordinary": include_extraordinary_in_burn,
            "monthly_amount": _money(burn),
        },
        "reserve_coverage_months": _rate(coverage),
        "monthly": [
            {
                "month": item.month.strftime("%Y-%m"),
                "external_income": _money(item.external_income_cents),
                "external_expenses": _money(item.external_expenses_cents),
                "living_cost": _money(item.living_cost_cents),
                "extraordinary_expenses": _money(item.extraordinary_expenses_cents),
                "savings": _money(item.savings_cents),
                "savings_rate": _rate(item.savings_rate),
                "net_reserve_contribution": _money(item.net_reserve_contribution_cents),
                "tracked_wealth": _money(item.tracked_wealth_cents),
            }
            for item in monthly
        ],
        "spending_by_category": [
            {"category": category, "amount": _money(amount)}
            for category, amount in category_spending(session, start, end)
        ],
        "notes": [
            "Internal transfers are excluded from external income and expenses.",
            "Unavailable metrics are represented by null.",
            "No raw bank descriptions or account identifiers are included in this summary.",
        ],
    }


def analytical_summary_json(
    session: Session,
    start: date,
    end: date,
    *,
    burn_window_months: int = 3,
    include_extraordinary_in_burn: bool = False,
) -> bytes:
    payload = analytical_summary(
        session,
        start,
        end,
        burn_window_months=burn_window_months,
        include_extraordinary_in_burn=include_extraordinary_in_burn,
    )
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
