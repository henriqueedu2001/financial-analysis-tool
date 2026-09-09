from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from finance_analysis.daily import CONSOLIDATED_ACCOUNT

EXTERNAL_INCOME_NATURES = {"income", "family_support"}
EXTERNAL_EXPENSE_NATURES = {"expense", "business_expense", "fee"}
REFUND_NATURES = {"refund", "tax_refund", "deposit_refund"}
UNCLASSIFIED_NATURES = {"inflow_unclassified", "outflow_unclassified"}


def month_sequence(first: str, last: str) -> list[str]:
    current = date.fromisoformat(f"{first}-01")
    end = date.fromisoformat(f"{last}-01")
    result: list[str] = []
    while current <= end:
        result.append(current.strftime("%Y-%m"))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return result


def decimal_ratio(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return ""
    value = Decimal(numerator) / Decimal(denominator)
    return format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")


def _month_end(month: str) -> date:
    year, month_number = map(int, month.split("-"))
    return date(year, month_number, calendar.monthrange(year, month_number)[1])


def _last_balance_by_month(
    rows: list[dict[str, str]], field: str, account_id: str | None = None
) -> dict[str, int]:
    selected = [
        row
        for row in rows
        if account_id is None or row.get("account_id") == account_id
    ]
    by_month: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in selected:
        by_month[row["date"][:7]].append(row)
    return {
        month: int(max(items, key=lambda item: item["date"])[field])
        for month, items in by_month.items()
    }


def build_monthly_metrics(
    transactions: list[dict[str, str]],
    daily_balances: list[dict[str, str]],
    reserve_monthly: list[dict[str, str]],
) -> list[dict[str, str | int]]:
    first_month = min(row["operation_date"][:7] for row in transactions)
    last_month = max(row["operation_date"][:7] for row in transactions)
    months = month_sequence(first_month, last_month)
    last_observed_date = max(date.fromisoformat(row["operation_date"]) for row in transactions)

    transactions_by_month: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in transactions:
        transactions_by_month[row["operation_date"][:7]].append(row)
    current_balances = _last_balance_by_month(
        daily_balances,
        "analysis_balance_cents",
        CONSOLIDATED_ACCOUNT,
    )
    reserve_by_month = {row["month"]: row for row in reserve_monthly}
    account_starts = {
        account_id: min(
            date.fromisoformat(row["operation_date"])
            for row in transactions
            if row["account_id"] == account_id
        )
        for account_id in {row["account_id"] for row in transactions}
    }
    full_coverage_start = max(account_starts.values())

    result: list[dict[str, str | int]] = []
    for month in months:
        rows = transactions_by_month[month]
        external_income = sum(
            int(row["amount_cents"])
            for row in rows
            if row["nature"] in EXTERNAL_INCOME_NATURES and int(row["amount_cents"]) > 0
        )
        gross_expense = sum(
            abs(int(row["amount_cents"]))
            for row in rows
            if row["nature"] in EXTERNAL_EXPENSE_NATURES and int(row["amount_cents"]) < 0
        )
        refunds = sum(
            int(row["amount_cents"])
            for row in rows
            if row["nature"] in REFUND_NATURES
        )
        net_expense = gross_expense - refunds
        recurring_cost = sum(
            abs(int(row["amount_cents"]))
            for row in rows
            if row["nature"] in EXTERNAL_EXPENSE_NATURES
            and int(row["amount_cents"]) < 0
            and row["cost_treatment"] == "recurring"
        )
        expanded_cost = sum(
            abs(int(row["amount_cents"]))
            for row in rows
            if row["nature"] in EXTERNAL_EXPENSE_NATURES
            and int(row["amount_cents"]) < 0
            and row["cost_treatment"] == "expanded"
        )
        outside_cost = sum(
            abs(int(row["amount_cents"]))
            for row in rows
            if row["nature"] in EXTERNAL_EXPENSE_NATURES
            and int(row["amount_cents"]) < 0
            and row["cost_treatment"] == "outside"
        )
        unclassified_outflow = sum(
            abs(int(row["amount_cents"]))
            for row in rows
            if row["nature"] == "outflow_unclassified" and int(row["amount_cents"]) < 0
        )
        unclassified_inflow = sum(
            int(row["amount_cents"])
            for row in rows
            if row["nature"] == "inflow_unclassified" and int(row["amount_cents"]) > 0
        )
        investment_return = sum(
            int(row["amount_cents"])
            for row in rows
            if row["nature"] == "investment_return"
        )
        contributions = sum(
            abs(int(row["amount_cents"]))
            for row in rows
            if row["nature"] == "reserve_contribution"
        )
        deportes = sum(
            abs(int(row["amount_cents"]))
            for row in rows
            if row["nature"] == "deporte"
        )
        savings = external_income - net_expense
        reserve = reserve_by_month.get(month)
        reserve_balance = int(reserve["closing_balance_cents"]) if reserve else None
        current_balance = current_balances.get(month)
        tracked_assets = (
            current_balance + reserve_balance
            if current_balance is not None and reserve_balance is not None
            else None
        )
        complete_month = _month_end(month) <= last_observed_date
        result.append(
            {
                "month": month,
                "is_complete_month": str(complete_month).lower(),
                "account_coverage": (
                    "all_available_accounts"
                    if _month_end(month) >= full_coverage_start
                    else "partial_accounts"
                ),
                "external_income_cents": external_income,
                "gross_external_expense_cents": gross_expense,
                "refund_cents": refunds,
                "net_external_expense_cents": net_expense,
                "savings_cents": savings,
                "savings_rate": decimal_ratio(savings, external_income),
                "recurring_living_cost_cents": recurring_cost,
                "expanded_living_cost_cents": recurring_cost + expanded_cost,
                "atypical_expense_cents": expanded_cost,
                "outside_living_cost_cents": outside_cost,
                "unclassified_outflow_cents": unclassified_outflow,
                "unclassified_inflow_cents": unclassified_inflow,
                "investment_return_cents": investment_return,
                "reserve_contribution_cents": contributions,
                "deporte_cents": deportes,
                "net_reserve_contribution_cents": contributions - deportes,
                "current_accounts_balance_cents": (
                    "" if current_balance is None else current_balance
                ),
                "reserve_balance_cents": "" if reserve_balance is None else reserve_balance,
                "tracked_financial_assets_cents": "" if tracked_assets is None else tracked_assets,
                "survival_index_months": (
                    ""
                    if reserve_balance is None or not complete_month
                    else decimal_ratio(reserve_balance, recurring_cost)
                ),
            }
        )
    return result


def build_monthly_category_spending(
    transactions: list[dict[str, str]],
) -> list[dict[str, str | int]]:
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in transactions:
        if int(row["amount_cents"]) >= 0:
            continue
        if row["nature"] not in EXTERNAL_EXPENSE_NATURES | {"outflow_unclassified"}:
            continue
        groups[(row["operation_date"][:7], row["category"], row["subcategory"])].append(row)

    result: list[dict[str, str | int]] = []
    for (month, category, subcategory), rows in sorted(groups.items()):
        known = [row for row in rows if row["nature"] in EXTERNAL_EXPENSE_NATURES]
        unknown = [row for row in rows if row["nature"] == "outflow_unclassified"]
        known_cents = sum(abs(int(row["amount_cents"])) for row in known)
        unknown_cents = sum(abs(int(row["amount_cents"])) for row in unknown)
        result.append(
            {
                "month": month,
                "category": category,
                "subcategory": subcategory,
                "transaction_count": len(rows),
                "known_expense_cents": known_cents,
                "unclassified_outflow_cents": unknown_cents,
                "total_observed_outflow_cents": known_cents + unknown_cents,
                "recurring_cost_cents": sum(
                    abs(int(row["amount_cents"]))
                    for row in known
                    if row["cost_treatment"] == "recurring"
                ),
                "atypical_expense_cents": sum(
                    abs(int(row["amount_cents"]))
                    for row in known
                    if row["cost_treatment"] == "expanded"
                ),
                "outside_living_cost_cents": sum(
                    abs(int(row["amount_cents"]))
                    for row in known
                    if row["cost_treatment"] == "outside"
                ),
            }
        )
    return result


def _decimal_median(values: list[int]) -> Decimal:
    return Decimal(str(median(values)))


def build_metrics_summary(monthly: list[dict[str, str | int]]) -> list[dict[str, str | int]]:
    complete = [row for row in monthly if row["is_complete_month"] == "true"]
    comparable = [
        row for row in complete if row["account_coverage"] == "all_available_accounts"
    ]
    costs = [int(row["recurring_living_cost_cents"]) for row in comparable]
    mean = _round_decimal(sum(Decimal(value) for value in costs) / Decimal(len(costs)))
    median_cost = _round_decimal(_decimal_median(costs))
    variance = sum((Decimal(value) - Decimal(mean)) ** 2 for value in costs) / Decimal(
        len(costs)
    )
    standard_deviation = _round_decimal(variance.sqrt())
    last_complete = max(complete, key=lambda row: str(row["month"]))
    return [
        {
            "analysis_start_month": monthly[0]["month"],
            "analysis_end_month": monthly[-1]["month"],
            "last_complete_month": last_complete["month"],
            "comparable_complete_months": len(comparable),
            "average_recurring_living_cost_cents": mean,
            "median_recurring_living_cost_cents": median_cost,
            "standard_deviation_living_cost_cents": standard_deviation,
            "coefficient_of_variation": decimal_ratio(standard_deviation, mean),
            "last_complete_recurring_living_cost_cents": last_complete[
                "recurring_living_cost_cents"
            ],
            "last_complete_reserve_balance_cents": last_complete["reserve_balance_cents"],
            "last_complete_survival_index_months": last_complete["survival_index_months"],
        }
    ]


def _round_decimal(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_metrics_quality(
    monthly: list[dict[str, str | int]],
    categories: list[dict[str, str | int]],
) -> list[dict[str, str | int]]:
    category_by_month: dict[str, int] = defaultdict(int)
    for row in categories:
        category_by_month[str(row["month"])] += int(row["known_expense_cents"])
    expense_mismatches = [
        row
        for row in monthly
        if category_by_month[str(row["month"])] != int(row["gross_external_expense_cents"])
    ]
    cost_mismatches = [
        row
        for row in monthly
        if int(row["recurring_living_cost_cents"])
        + int(row["atypical_expense_cents"])
        != int(row["expanded_living_cost_cents"])
    ]
    savings_mismatches = [
        row
        for row in monthly
        if int(row["external_income_cents"])
        - int(row["net_external_expense_cents"])
        != int(row["savings_cents"])
    ]
    return [
        {
            "check_type": "category_expense_reconciliation",
            "status": "balanced" if not expense_mismatches else "mismatch",
            "observed_value": len(expense_mismatches),
            "expected_value": 0,
            "details": f"{len(monthly)} meses verificados",
        },
        {
            "check_type": "living_cost_partition",
            "status": "balanced" if not cost_mismatches else "mismatch",
            "observed_value": len(cost_mismatches),
            "expected_value": 0,
            "details": "Custo ampliado = recorrente + atípico",
        },
        {
            "check_type": "savings_identity",
            "status": "balanced" if not savings_mismatches else "mismatch",
            "observed_value": len(savings_mismatches),
            "expected_value": 0,
            "details": "Poupança = receita externa - despesa externa líquida",
        },
    ]
