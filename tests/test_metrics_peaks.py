from decimal import Decimal

from finance_analysis.metrics import (
    build_metrics_quality,
    build_monthly_category_spending,
    build_monthly_metrics,
    decimal_ratio,
)
from finance_analysis.peaks import build_peak_candidates


def transaction(**changes: str) -> dict[str, str]:
    base = {
        "analytical_transaction_id": "tx-1",
        "parent_transaction_id": "tx-1",
        "account_id": "banco_do_brasil_conta_corrente",
        "operation_date": "2026-01-10",
        "amount_cents": "-10000",
        "nature": "expense",
        "category": "Alimentação",
        "subcategory": "Restaurante",
        "cost_treatment": "recurring",
        "recurrence": "variable_habitual",
        "peak_eligible": "false",
        "counterparty_display": "Exemplo",
    }
    return {**base, **changes}


def balances() -> list[dict[str, str]]:
    return [
        {
            "date": "2026-01-31",
            "account_id": "contas_correntes_consolidadas",
            "analysis_balance_cents": "250000",
        }
    ]


def reserve() -> list[dict[str, str]]:
    return [{"month": "2026-01", "closing_balance_cents": "1000000"}]


def test_zero_income_has_no_invalid_savings_rate():
    rows = [transaction()]

    result = build_monthly_metrics(rows, balances(), reserve())[0]

    assert result["external_income_cents"] == 0
    assert result["savings_rate"] == ""


def test_refund_can_make_net_expense_negative_without_being_clamped():
    rows = [
        transaction(amount_cents="-1000"),
        transaction(
            analytical_transaction_id="refund",
            parent_transaction_id="refund",
            amount_cents="2000",
            nature="refund",
            category="Estornos",
            subcategory="Reembolso",
            cost_treatment="outside",
        ),
    ]

    result = build_monthly_metrics(rows, balances(), reserve())[0]

    assert result["net_external_expense_cents"] == -1000
    assert result["savings_cents"] == 1000


def test_savings_is_different_from_reserve_contribution():
    rows = [
        transaction(
            analytical_transaction_id="income",
            parent_transaction_id="income",
            amount_cents="600000",
            nature="income",
            category="Receitas",
            cost_treatment="outside",
        ),
        transaction(amount_cents="-350000"),
        transaction(
            analytical_transaction_id="contribution",
            parent_transaction_id="contribution",
            amount_cents="-200000",
            nature="reserve_contribution",
            category="Patrimônio",
            cost_treatment="outside",
        ),
    ]

    result = build_monthly_metrics(rows, balances(), reserve())[0]

    assert result["savings_cents"] == 250000
    assert result["net_reserve_contribution_cents"] == 200000


def test_atypical_expense_reduces_savings_but_not_recurring_living_cost():
    rows = [
        transaction(amount_cents="-350000"),
        transaction(
            analytical_transaction_id="peak",
            parent_transaction_id="peak",
            amount_cents="-50000",
            cost_treatment="expanded",
            recurrence="non_recurring",
            peak_eligible="true",
        ),
    ]

    result = build_monthly_metrics(rows, balances(), reserve())[0]

    assert result["gross_external_expense_cents"] == 400000
    assert result["recurring_living_cost_cents"] == 350000
    assert result["atypical_expense_cents"] == 50000


def test_survival_index_uses_same_month_recurring_cost():
    result = build_monthly_metrics(
        [transaction(operation_date="2026-01-31")], balances(), reserve()
    )[0]

    assert result["survival_index_months"] == "100.0000"


def test_survival_index_is_omitted_for_incomplete_month():
    rows = [transaction(operation_date="2026-01-10")]

    result = build_monthly_metrics(rows, balances(), reserve())[0]

    assert result["is_complete_month"] == "false"
    assert result["survival_index_months"] == ""


def test_category_totals_reconcile_to_external_expense():
    rows = [
        transaction(),
        transaction(analytical_transaction_id="tx-2", parent_transaction_id="tx-2"),
    ]
    monthly = build_monthly_metrics(rows, balances(), reserve())
    categories = build_monthly_category_spending(rows)

    quality = build_metrics_quality(monthly, categories)

    assert all(row["status"] == "balanced" for row in quality)


def test_peak_model_excludes_recurring_rent_and_detects_large_non_recurring_cost():
    rows = [
        transaction(
            analytical_transaction_id=f"small-{index}",
            parent_transaction_id=f"small-{index}",
            amount_cents=str(-(1000 + index * 100)),
            recurrence="non_recurring",
            peak_eligible="true",
        )
        for index in range(20)
    ]
    rows.extend(
        [
            transaction(
                analytical_transaction_id="rent",
                parent_transaction_id="rent",
                amount_cents="-500000",
                category="Moradia",
                subcategory="Aluguel",
                recurrence="fixed_contractual",
                peak_eligible="false",
            ),
            transaction(
                analytical_transaction_id="deposit",
                parent_transaction_id="deposit",
                amount_cents="-100000",
                category="Moradia",
                subcategory="Caução",
                cost_treatment="expanded",
                recurrence="non_recurring",
                peak_eligible="true",
            ),
        ]
    )

    result = build_peak_candidates(rows, [])

    assert not any(row["episode_id"] == "transaction:rent" for row in result)
    assert next(row for row in result if row["episode_id"] == "transaction:deposit")[
        "is_peak"
    ] == "true"


def test_linked_refund_neutralizes_peak_candidate():
    rows = [
        transaction(
            analytical_transaction_id="purchase",
            parent_transaction_id="purchase",
            amount_cents="-100000",
            recurrence="non_recurring",
            peak_eligible="true",
        ),
        transaction(
            analytical_transaction_id="refund",
            parent_transaction_id="refund",
            amount_cents="100000",
            nature="refund",
            category="Estornos",
            subcategory="Reembolso",
            cost_treatment="outside",
            recurrence="not_applicable",
            peak_eligible="false",
        ),
    ]
    events = [
        {"event_id": "refunded", "transaction_id": "purchase", "event_label": "Compra estornada"},
        {"event_id": "refunded", "transaction_id": "refund", "event_label": "Compra estornada"},
    ]

    result = build_peak_candidates(rows, events)

    assert result == []


def test_decimal_ratio_is_deterministic():
    assert decimal_ratio(1, 3) == "0.3333"
    assert Decimal(decimal_ratio(1, 3)) * 3 == Decimal("0.9999")
