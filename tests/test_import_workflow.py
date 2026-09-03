from sqlalchemy import func, select

from finance.db.bootstrap import DEFAULT_CATEGORIES_PATH, seed_categories
from finance.importers.preview import build_import_preview
from finance.models import Account, AccountType, FinancialRole, RawTransaction, Transaction
from finance.repositories.imports import ImportConfirmationError, confirm_import
from tests.helpers import canonical_csv, make_ofx, tx_xml


def add_account(db_session, name="Conta fictícia"):
    account = Account(
        name=name,
        account_type=AccountType.CHECKING,
        financial_role=FinancialRole.OPERATIONAL,
    )
    db_session.add(account)
    db_session.commit()
    return account


def test_reimporting_same_file_does_not_duplicate_transactions(db_session, tmp_path):
    seed_categories(db_session, DEFAULT_CATEGORIES_PATH)
    account = add_account(db_session)
    content = canonical_csv(
        "2026-01-05,Conta fictícia,RECEITA FICTICIA,100.00,150.00,income,"
        "Receitas,Salário,false,false,origem.pdf,2,0.9"
    )
    preview = build_import_preview(content, "lote.csv", db_session, account.id)

    first = confirm_import(preview, db_session, account_id=account.id, archive_root=tmp_path)
    second_preview = build_import_preview(content, "renomeado.csv", db_session, account.id)
    second = confirm_import(
        second_preview, db_session, account_id=account.id, archive_root=tmp_path
    )

    assert first.imported_transactions == 1
    assert second.already_imported is True
    assert second.imported_transactions == 0
    assert db_session.scalar(select(func.count()).select_from(Transaction)) == 1
    assert db_session.scalar(select(func.count()).select_from(RawTransaction)) == 1


def test_possible_duplicate_rows_are_not_silently_removed(db_session, tmp_path):
    account = add_account(db_session)
    content = canonical_csv(
        "2026-01-05,Conta fictícia,MESMO ITEM,-10.00,,expense,,,false,false,a.pdf,2,",
        "2026-01-05,Conta fictícia,MESMO ITEM,-10.00,,expense,,,false,false,a.pdf,3,",
    )
    preview = build_import_preview(content, "ambiguo.csv", db_session, account.id)
    assert preview.internal_duplicate_rows == ("2", "3")

    try:
        confirm_import(preview, db_session, account_id=account.id, archive_root=tmp_path)
    except ImportConfirmationError as exc:
        assert "possíveis duplicatas" in str(exc)
    else:
        raise AssertionError("ambiguous rows were imported silently")


def test_reconciliation_detects_inconsistent_reported_balance(db_session):
    account = add_account(db_session)
    content = canonical_csv(
        "2026-01-05,Conta fictícia,ENTRADA,100.00,150.00,income,,,false,false,a.pdf,2,",
        "2026-01-06,Conta fictícia,SAIDA,-20.00,140.00,expense,,,false,false,a.pdf,3,",
    )
    preview = build_import_preview(content, "divergente.csv", db_session, account.id)

    assert preview.opening_balance_cents == 5000
    assert preview.reconciliation_difference_cents == -1000
    assert preview.balance_sequence_error_rows == ("3",)


def test_ofx_source_cannot_be_mixed_into_account_bound_to_another_bank(db_session, tmp_path):
    account = add_account(db_session)
    bb = make_ofx(tx_xml("20260105120000", "10.00", "bb-1", "BB fictício"))
    bb_preview = build_import_preview(bb, "bb.ofx", db_session, account.id)
    confirm_import(bb_preview, db_session, account_id=account.id, archive_root=tmp_path)

    itau = make_ofx(
        tx_xml("20260106120000", "20.00", "itau-1", "Itaú fictício"),
        bank="0341",
        account="9999",
    )
    itau_preview = build_import_preview(itau, "itau.ofx", db_session, account.id)
    try:
        confirm_import(itau_preview, db_session, account_id=account.id, archive_root=tmp_path)
    except ImportConfirmationError as exc:
        assert "não serão misturados" in str(exc)
    else:
        raise AssertionError("different OFX accounts were mixed")
