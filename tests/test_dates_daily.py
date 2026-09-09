from finance_analysis.daily import (
    BB_ACCOUNT,
    CONSOLIDATED_ACCOUNT,
    build_daily_balances,
    build_daily_flows,
    reconstruct_ledger_balances,
)
from finance_analysis.dates import add_operation_dates, infer_operation_date


def transaction(**changes: str) -> dict[str, str]:
    base = {
        "transaction_id": "tx-1",
        "parent_transaction_id": "tx-1",
        "account_id": BB_ACCOUNT,
        "institution": "Banco do Brasil",
        "transaction_date": "2026-01-05",
        "amount_cents": "-1000",
        "name_raw": "Compra com Cartão",
        "memo_raw": "03/01 18:30 PADARIA EXEMPLO",
        "channel": "debit_card_purchase",
        "nature": "expense",
    }
    return {**base, **changes}


def test_bb_operation_date_uses_memo_and_preserves_posting_date():
    row = transaction()

    enriched = add_operation_dates([row])[0]

    assert enriched["posting_date"] == "2026-01-05"
    assert enriched["operation_date"] == "2026-01-03"
    assert enriched["operation_date_source"] == "bb_memo_prefix"
    assert enriched["transaction_date"] == "2026-01-05"


def test_operation_date_handles_year_rollover():
    result = infer_operation_date(
        transaction(transaction_date="2026-01-02", memo_raw="31/12 22:00 EXEMPLO")
    )

    assert result.value.isoformat() == "2025-12-31"


def test_itau_operation_date_uses_conservative_suffix():
    result = infer_operation_date(
        transaction(
            account_id="itau_conta_corrente",
            transaction_date="2026-02-02",
            memo_raw="PIX QRS Gowd Instit31 01",
        )
    )

    assert result.value.isoformat() == "2026-01-31"
    assert result.source == "itau_memo_suffix"


def test_suspicious_memo_date_falls_back_to_posting_date():
    result = infer_operation_date(
        transaction(transaction_date="2026-01-20", memo_raw="03/01 18:30 EXEMPLO")
    )

    assert result.value.isoformat() == "2026-01-20"
    assert result.source == "posting_date"


def test_balance_is_reconstructed_backward_from_final_snapshot():
    rows = [
        transaction(transaction_date="2026-01-01", amount_cents="10000"),
        transaction(transaction_date="2026-01-02", amount_cents="-2500"),
    ]
    snapshots = [
        {
            "account_id": BB_ACCOUNT,
            "balance_date": "2026-01-02",
            "balance_cents": "7500",
        }
    ]

    result = reconstruct_ledger_balances(rows, snapshots, BB_ACCOUNT)

    assert [row["ledger_balance_cents"] for row in result] == [10000, 7500]
    assert result[-1]["snapshot_difference_cents"] == 0


def test_rende_facil_is_kept_out_of_operational_liquidity_proxy():
    rows = [
        transaction(transaction_date="2026-01-02", amount_cents="230000", channel="income"),
        transaction(transaction_date="2026-01-02", amount_cents="-145000"),
        transaction(
            transaction_date="2026-01-02",
            amount_cents="-85000",
            name_raw="BB Rende Fácil",
            channel="bb_rende_facil",
        ),
    ]
    snapshots = [
        {
            "account_id": BB_ACCOUNT,
            "balance_date": "2026-01-02",
            "balance_cents": "0",
        }
    ]

    result = reconstruct_ledger_balances(rows, snapshots, BB_ACCOUNT)[0]

    assert result["ledger_balance_cents"] == 0
    assert result["liquidity_adjustment_cents"] == 85000
    assert result["analysis_balance_cents"] == 85000


def test_consolidated_transfer_changes_accounts_but_not_total():
    transactions = [
        transaction(
            transaction_id="out",
            parent_transaction_id="out",
            account_id=BB_ACCOUNT,
            transaction_date="2026-01-02",
            amount_cents="-100000",
        ),
        transaction(
            transaction_id="in",
            parent_transaction_id="in",
            account_id="itau_conta_corrente",
            institution="Itaú",
            transaction_date="2026-01-02",
            amount_cents="100000",
        ),
    ]
    snapshots = [
        {"account_id": BB_ACCOUNT, "balance_date": "2026-01-02", "balance_cents": "0"},
        {
            "account_id": "itau_conta_corrente",
            "balance_date": "2026-01-02",
            "balance_cents": "200000",
        },
    ]

    rows = build_daily_balances(transactions, snapshots)
    consolidated = next(row for row in rows if row["account_id"] == CONSOLIDATED_ACCOUNT)

    assert consolidated["analysis_balance_cents"] == 200000


def test_daily_flows_exclude_transfers_and_unclassified_from_income_and_expense():
    rows = add_operation_dates(
        [
            transaction(amount_cents="600000", nature="income", memo_raw="05/01 08:00 SALARIO"),
            transaction(
                transaction_id="expense",
                parent_transaction_id="expense",
                amount_cents="-350000",
                nature="expense",
                memo_raw="05/01 09:00 DESPESA",
            ),
            transaction(
                transaction_id="transfer",
                parent_transaction_id="transfer",
                amount_cents="-200000",
                nature="reserve_contribution",
                memo_raw="05/01 10:00 APORTE",
            ),
            transaction(
                transaction_id="unknown",
                parent_transaction_id="unknown",
                amount_cents="-1490",
                nature="outflow_unclassified",
                memo_raw="05/01 11:00 DESCONHECIDO",
            ),
        ]
    )

    result = build_daily_flows(rows)
    daily = next(
        row
        for row in result
        if row["account_id"] == BB_ACCOUNT and row["date"] == "2026-01-05"
    )

    assert daily["external_income_cents"] == 600000
    assert daily["external_expense_cents"] == 350000
    assert daily["reserve_contribution_cents"] == 200000
    assert daily["unclassified_outflow_cents"] == 1490
    assert all(isinstance(value, int) for key, value in daily.items() if key.endswith("_cents"))


def test_daily_flows_do_not_invent_zero_history_before_account_coverage():
    rows = add_operation_dates(
        [
            transaction(transaction_date="2025-01-02", memo_raw="02/01 08:00 EXEMPLO"),
            transaction(
                transaction_id="itau",
                parent_transaction_id="itau",
                account_id="itau_conta_corrente",
                institution="Itaú",
                transaction_date="2026-01-02",
                memo_raw="PIX QRS Exemplo02 01",
            ),
        ]
    )

    result = build_daily_flows(rows)

    assert not any(
        row["account_id"] == "itau_conta_corrente" and row["date"] < "2026-01-02"
        for row in result
    )
    partial = next(
        row
        for row in result
        if row["account_id"] == CONSOLIDATED_ACCOUNT and row["date"] == "2025-01-02"
    )
    assert partial["coverage_complete"] == "false"
