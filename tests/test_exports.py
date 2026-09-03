import csv
import io
import json
from datetime import date

from sqlalchemy import select

from finance.db.bootstrap import DEFAULT_CATEGORIES_PATH, seed_categories
from finance.exports import analytical_summary_json, monthly_summary_csv, transactions_csv
from finance.importers.preview import build_import_preview
from finance.models import Account, AccountType, FinancialRole
from finance.reconciliation import record_balance_snapshot
from finance.repositories.imports import confirm_import
from finance.repositories.transactions import list_transactions
from tests.helpers import canonical_csv


def setup_export_data(db_session, tmp_path):
    seed_categories(db_session, DEFAULT_CATEGORIES_PATH)
    account = Account(
        name="Conta fictícia",
        account_type=AccountType.CHECKING,
        financial_role=FinancialRole.OPERATIONAL,
    )
    db_session.add(account)
    db_session.commit()
    record_balance_snapshot(
        db_session,
        account_id=account.id,
        snapshot_date=date(2026, 1, 1),
        balance_cents=10_000,
    )
    content = canonical_csv(
        "2026-01-05,Conta fictícia,RECEITA SUPER SECRETA,100.10,,income,Receitas,"
        "Salário,false,false,origem.pdf,2,0.9",
        "2026-01-06,Conta fictícia,DESPESA FICTICIA,-20.20,,expense,Alimentação,"
        "Mercado,false,false,origem.pdf,3,0.8",
    )
    preview = build_import_preview(content, "export.csv", db_session, account.id)
    confirm_import(preview, db_session, account_id=account.id, archive_root=tmp_path)
    return account


def test_filtered_transaction_csv_preserves_exact_values_and_audit_source(db_session, tmp_path):
    setup_export_data(db_session, tmp_path)
    rows = list_transactions(db_session)
    exported = transactions_csv(rows).decode()
    parsed = list(csv.DictReader(io.StringIO(exported)))

    assert {row["amount"] for row in parsed} == {"100.10", "-20.20"}
    assert {row["source_file"] for row in parsed} == {"export.csv"}
    assert {row["source_row"] for row in parsed} == {"2", "3"}


def test_monthly_summary_csv_uses_decimal_strings(db_session, tmp_path):
    setup_export_data(db_session, tmp_path)
    exported = monthly_summary_csv(db_session, date(2026, 1, 1), date(2026, 1, 31)).decode()
    row = next(csv.DictReader(io.StringIO(exported)))

    assert row["external_income"] == "100.10"
    assert row["external_expenses"] == "20.20"
    assert row["savings"] == "79.90"


def test_analytical_json_is_aggregated_and_contains_no_bank_description(db_session, tmp_path):
    setup_export_data(db_session, tmp_path)
    exported = analytical_summary_json(db_session, date(2026, 1, 1), date(2026, 1, 31))
    payload = json.loads(exported)

    assert payload["money_format"] == "decimal_string"
    assert payload["external_income"] == "100.10"
    assert payload["external_expenses"] == "20.20"
    assert payload["savings"] == "79.90"
    assert payload["savings_rate"] == "0.7982"
    assert "RECEITA SUPER SECRETA" not in exported.decode()
    assert "origem.pdf" not in exported.decode()
    assert db_session.scalar(select(Account.id)) is not None
