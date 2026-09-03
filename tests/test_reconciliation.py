from datetime import date

from sqlalchemy import select

from finance.importers.preview import build_import_preview
from finance.models import (
    Account,
    AccountType,
    BalanceSnapshot,
    FinancialRole,
)
from finance.reconciliation import reconcile_account, record_balance_snapshot
from finance.repositories.imports import confirm_import
from tests.helpers import canonical_csv


def setup_account(db_session):
    account = Account(
        name="Conta fictícia",
        account_type=AccountType.CHECKING,
        financial_role=FinancialRole.OPERATIONAL,
    )
    db_session.add(account)
    db_session.commit()
    return account


def test_reconciliation_between_snapshots_detects_difference(db_session, tmp_path):
    account = setup_account(db_session)
    record_balance_snapshot(
        db_session,
        account_id=account.id,
        snapshot_date=date(2026, 1, 1),
        balance_cents=10000,
    )
    content = canonical_csv(
        "2026-01-15,Conta fictícia,DESPESA FICTICIA,-20.00,,expense,,,false,false,a.pdf,2,"
    )
    preview = build_import_preview(content, "movimento.csv", db_session, account.id)
    confirm_import(preview, db_session, account_id=account.id, archive_root=tmp_path)
    record_balance_snapshot(
        db_session,
        account_id=account.id,
        snapshot_date=date(2026, 1, 31),
        balance_cents=7000,
    )

    result = reconcile_account(db_session, account.id)[0]
    assert result.opening_balance_cents == 10000
    assert result.movement_total_cents == -2000
    assert result.calculated_closing_balance_cents == 8000
    assert result.reported_closing_balance_cents == 7000
    assert result.difference_cents == 1000


def test_confirmed_import_creates_known_closing_balance_snapshot(db_session, tmp_path):
    account = setup_account(db_session)
    content = canonical_csv(
        "2026-02-01,Conta fictícia,ENTRADA FICTICIA,100.00,150.00,income,,,false,false,a.pdf,2,"
    )
    preview = build_import_preview(content, "saldo.csv", db_session, account.id)
    result = confirm_import(preview, db_session, account_id=account.id, archive_root=tmp_path)

    snapshot = db_session.scalar(select(BalanceSnapshot))
    assert snapshot is not None
    assert snapshot.snapshot_date == date(2026, 2, 1)
    assert snapshot.balance_cents == 15000
    assert snapshot.source_batch_id == result.batch_id
