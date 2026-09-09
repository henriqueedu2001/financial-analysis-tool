from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta

BB_ACCOUNT = "banco_do_brasil_conta_corrente"
CONSOLIDATED_ACCOUNT = "contas_correntes_consolidadas"

EXTERNAL_INCOME_NATURES = {"income", "family_support"}
EXTERNAL_EXPENSE_NATURES = {"expense", "business_expense", "fee"}
REFUND_NATURES = {"refund", "tax_refund", "deposit_refund"}
INTERNAL_TRANSFER_NATURES = {"self_transfer_unresolved", "reversed_transfer"}


def date_range(first: date, last: date) -> Iterable[date]:
    current = first
    while current <= last:
        yield current
        current += timedelta(days=1)


def _account_metadata(rows: list[dict[str, str]]) -> dict[str, str]:
    return {
        account_id: next(row["institution"] for row in rows if row["account_id"] == account_id)
        for account_id in sorted({row["account_id"] for row in rows})
    }


def reconstruct_ledger_balances(
    transactions: list[dict[str, str]],
    snapshots: list[dict[str, str]],
    account_id: str,
) -> list[dict[str, str | int]]:
    account_transactions = [row for row in transactions if row["account_id"] == account_id]
    account_snapshots = [row for row in snapshots if row["account_id"] == account_id]
    if not account_transactions:
        return []
    if not account_snapshots:
        raise ValueError(f"Conta sem saldo-âncora: {account_id}")

    anchor = max(account_snapshots, key=lambda row: row["balance_date"])
    anchor_date = date.fromisoformat(anchor["balance_date"])
    latest_transaction = max(
        date.fromisoformat(row["transaction_date"]) for row in account_transactions
    )
    if latest_transaction > anchor_date:
        raise ValueError(f"Há transações posteriores ao saldo-âncora de {account_id}")

    daily_movements: dict[date, int] = defaultdict(int)
    daily_rende_facil: dict[date, int] = defaultdict(int)
    for row in account_transactions:
        posting_date = date.fromisoformat(row["transaction_date"])
        amount = int(row["amount_cents"])
        daily_movements[posting_date] += amount
        if row.get("channel") == "bb_rende_facil" or row.get("name_raw") == "BB Rende Fácil":
            daily_rende_facil[posting_date] += amount

    first_date = min(daily_movements)
    closing_by_date: dict[date, int] = {}
    closing_balance = int(anchor["balance_cents"])
    for current in reversed(list(date_range(first_date, anchor_date))):
        closing_by_date[current] = closing_balance
        closing_balance -= daily_movements[current]

    adjustment = 0
    result: list[dict[str, str | int]] = []
    snapshot_by_date = {
        date.fromisoformat(row["balance_date"]): int(row["balance_cents"])
        for row in account_snapshots
    }
    institution = account_transactions[0]["institution"]
    for current in date_range(first_date, anchor_date):
        adjustment -= daily_rende_facil[current]
        ledger = closing_by_date[current]
        analysis = ledger + adjustment
        snapshot = snapshot_by_date.get(current)
        result.append(
            {
                "date": current.isoformat(),
                "account_id": account_id,
                "institution": institution,
                "balance_basis": (
                    "ledger_plus_bb_rende_facil_principal_proxy"
                    if account_id == BB_ACCOUNT
                    else "ledger_balance"
                ),
                "ledger_balance_cents": ledger,
                "liquidity_adjustment_cents": adjustment,
                "analysis_balance_cents": analysis,
                "snapshot_balance_cents": "" if snapshot is None else snapshot,
                "snapshot_difference_cents": "" if snapshot is None else snapshot - ledger,
                "coverage_complete": "true",
            }
        )
    return result


def build_daily_balances(
    transactions: list[dict[str, str]], snapshots: list[dict[str, str]]
) -> list[dict[str, str | int]]:
    account_ids = sorted({row["account_id"] for row in transactions})
    per_account = [
        row
        for account_id in account_ids
        for row in reconstruct_ledger_balances(transactions, snapshots, account_id)
    ]
    rows_by_account_date = {
        (str(row["account_id"]), str(row["date"])): row for row in per_account
    }
    starts = {
        account_id: min(
            date.fromisoformat(str(row["date"]))
            for row in per_account
            if row["account_id"] == account_id
        )
        for account_id in account_ids
    }
    first = min(starts.values())
    last = max(date.fromisoformat(str(row["date"])) for row in per_account)
    consolidated: list[dict[str, str | int]] = []
    for current in date_range(first, last):
        available = [
            rows_by_account_date[(account_id, current.isoformat())]
            for account_id in account_ids
            if (account_id, current.isoformat()) in rows_by_account_date
        ]
        if not available:
            continue
        complete = all(current >= starts[account_id] for account_id in account_ids)
        consolidated.append(
            {
                "date": current.isoformat(),
                "account_id": CONSOLIDATED_ACCOUNT,
                "institution": "Banco do Brasil + Itaú",
                "balance_basis": "sum_available_analysis_balances",
                "ledger_balance_cents": sum(int(row["ledger_balance_cents"]) for row in available),
                "liquidity_adjustment_cents": sum(
                    int(row["liquidity_adjustment_cents"]) for row in available
                ),
                "analysis_balance_cents": sum(
                    int(row["analysis_balance_cents"]) for row in available
                ),
                "snapshot_balance_cents": "",
                "snapshot_difference_cents": "",
                "coverage_complete": str(complete).lower(),
            }
        )
    return sorted(
        [*per_account, *consolidated],
        key=lambda row: (str(row["date"]), str(row["account_id"])),
    )


def _blank_flow(
    date_value: date,
    account_id: str,
    institution: str,
    coverage_complete: bool = True,
) -> dict[str, str | int]:
    return {
        "date": date_value.isoformat(),
        "account_id": account_id,
        "institution": institution,
        "coverage_complete": str(coverage_complete).lower(),
        "transaction_count": 0,
        "bank_inflows_cents": 0,
        "bank_outflows_cents": 0,
        "net_bank_flow_cents": 0,
        "external_income_cents": 0,
        "external_expense_cents": 0,
        "refund_cents": 0,
        "investment_return_cents": 0,
        "reserve_contribution_cents": 0,
        "deporte_cents": 0,
        "internal_transfer_net_cents": 0,
        "unclassified_inflow_cents": 0,
        "unclassified_outflow_cents": 0,
    }


def build_daily_flows(rows: list[dict[str, str]]) -> list[dict[str, str | int]]:
    if not rows:
        return []
    institutions = _account_metadata(rows)
    dates = [date.fromisoformat(row["operation_date"]) for row in rows]
    first, last = min(dates), max(dates)
    coverage = {
        account_id: (
            min(
                date.fromisoformat(row["operation_date"])
                for row in rows
                if row["account_id"] == account_id
            ),
            max(
                date.fromisoformat(row["operation_date"])
                for row in rows
                if row["account_id"] == account_id
            ),
        )
        for account_id in institutions
    }
    result_by_key: dict[tuple[str, date], dict[str, str | int]] = {}
    for account_id, institution in institutions.items():
        account_first, account_last = coverage[account_id]
        for current in date_range(account_first, account_last):
            result_by_key[(account_id, current)] = _blank_flow(current, account_id, institution)

    for row in rows:
        current = date.fromisoformat(row["operation_date"])
        target = result_by_key[(row["account_id"], current)]
        amount = int(row["amount_cents"])
        nature = row["nature"]
        target["transaction_count"] = int(target["transaction_count"]) + 1
        if amount > 0:
            target["bank_inflows_cents"] = int(target["bank_inflows_cents"]) + amount
        elif amount < 0:
            target["bank_outflows_cents"] = int(target["bank_outflows_cents"]) + abs(amount)
        target["net_bank_flow_cents"] = int(target["net_bank_flow_cents"]) + amount

        if nature in EXTERNAL_INCOME_NATURES and amount > 0:
            target["external_income_cents"] = int(target["external_income_cents"]) + amount
        if nature in EXTERNAL_EXPENSE_NATURES and amount < 0:
            target["external_expense_cents"] = int(target["external_expense_cents"]) + abs(amount)
        if nature in REFUND_NATURES:
            target["refund_cents"] = int(target["refund_cents"]) + amount
        if nature == "investment_return":
            target["investment_return_cents"] = int(target["investment_return_cents"]) + amount
        if nature == "reserve_contribution":
            target["reserve_contribution_cents"] = (
                int(target["reserve_contribution_cents"]) + abs(amount)
            )
        if nature == "deporte":
            target["deporte_cents"] = int(target["deporte_cents"]) + abs(amount)
        if nature in INTERNAL_TRANSFER_NATURES:
            target["internal_transfer_net_cents"] = (
                int(target["internal_transfer_net_cents"]) + amount
            )
        if nature == "inflow_unclassified" and amount > 0:
            target["unclassified_inflow_cents"] = (
                int(target["unclassified_inflow_cents"]) + amount
            )
        if nature == "outflow_unclassified" and amount < 0:
            target["unclassified_outflow_cents"] = (
                int(target["unclassified_outflow_cents"]) + abs(amount)
            )

    per_account = list(result_by_key.values())
    consolidated: list[dict[str, str | int]] = []
    numeric_fields = [
        field
        for field in per_account[0]
        if field not in {"date", "account_id", "institution", "coverage_complete"}
    ]
    for current in date_range(first, last):
        complete = all(start <= current <= end for start, end in coverage.values())
        row = _blank_flow(
            current,
            CONSOLIDATED_ACCOUNT,
            "Banco do Brasil + Itaú",
            coverage_complete=complete,
        )
        for account_id in institutions:
            source = result_by_key.get((account_id, current))
            if source is None:
                continue
            for field in numeric_fields:
                row[field] = int(row[field]) + int(source[field])
        consolidated.append(row)
    return sorted(
        [*per_account, *consolidated],
        key=lambda row: (str(row["date"]), str(row["account_id"])),
    )


def build_data_quality(
    dated_transactions: list[dict[str, str]],
    daily_balances: list[dict[str, str | int]],
) -> list[dict[str, str | int]]:
    result: list[dict[str, str | int]] = []
    for account_id in sorted({row["account_id"] for row in dated_transactions}):
        rows = [row for row in dated_transactions if row["account_id"] == account_id]
        derived = [row for row in rows if row["operation_date_source"] != "posting_date"]
        shifted = [row for row in rows if int(row["operation_posting_lag_days"]) != 0]
        maximum_lag = max(
            (-int(row["operation_posting_lag_days"]) for row in rows), default=0
        )
        result.append(
            {
                "check_type": "operation_dates",
                "account_id": account_id,
                "reference_date": "",
                "status": "ok",
                "observed_value": len(derived),
                "expected_value": len(rows),
                "difference_cents": "",
                "details": (
                    f"{len(shifted)} datas diferem da data contábil; "
                    f"maior atraso: {maximum_lag} dias"
                ),
            }
        )

    for row in daily_balances:
        if row["snapshot_balance_cents"] == "":
            continue
        difference = int(row["snapshot_difference_cents"])
        result.append(
            {
                "check_type": "balance_snapshot",
                "account_id": row["account_id"],
                "reference_date": row["date"],
                "status": "balanced" if difference == 0 else "mismatch",
                "observed_value": row["ledger_balance_cents"],
                "expected_value": row["snapshot_balance_cents"],
                "difference_cents": difference,
                "details": "Saldo diário reconstruído versus saldo informado no OFX",
            }
        )
    return result
