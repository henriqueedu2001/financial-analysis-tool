from datetime import date

from sqlalchemy import inspect, select, text

from finance.db.bootstrap import DEFAULT_CATEGORIES_PATH, seed_categories
from finance.models import (
    Account,
    AccountType,
    Category,
    ClassificationSource,
    FinancialRole,
    ImportBatch,
    ImportStatus,
    RawTransaction,
    RawTransactionImmutable,
    Transaction,
    TransactionNature,
)


def test_foundation_creates_all_planned_tables(db_session):
    expected = {
        "accounts",
        "balance_snapshots",
        "categories",
        "classification_rules",
        "import_batches",
        "raw_transactions",
        "transactions",
        "transaction_edits",
        "transfer_matches",
    }
    assert set(inspect(db_session.bind).get_table_names()) == expected


def test_sqlite_foreign_keys_are_enabled(db_session):
    assert db_session.scalar(text("PRAGMA foreign_keys")) == 1


def test_seed_is_idempotent_and_does_not_overwrite_user_edits(db_session):
    created = seed_categories(db_session, DEFAULT_CATEGORIES_PATH)
    assert created > 0

    market = db_session.scalar(select(Category).where(Category.slug == "alimentacao-mercado"))
    assert market is not None
    assert market.is_living_cost is True
    market.name = "Supermercado personalizado"
    db_session.commit()

    assert seed_categories(db_session, DEFAULT_CATEGORIES_PATH) == 0
    db_session.refresh(market)
    assert market.name == "Supermercado personalizado"


def test_account_technical_type_and_financial_role_are_independent(db_session):
    account = Account(
        name="Reserva fictícia",
        institution="Banco Exemplo",
        account_type=AccountType.CHECKING,
        financial_role=FinancialRole.RESERVE,
        currency="BRL",
        is_reserve=True,
    )
    db_session.add(account)
    db_session.commit()

    assert account.account_type is AccountType.CHECKING
    assert account.financial_role is FinancialRole.RESERVE


def test_normalized_transaction_keeps_auditable_raw_source(db_session):
    account = Account(
        name="Fluxo fictícia",
        account_type=AccountType.CHECKING,
        financial_role=FinancialRole.OPERATIONAL,
    )
    db_session.add(account)
    db_session.flush()

    batch = ImportBatch(
        source_file="arquivo-renomeado.csv",
        file_hash="a" * 64,
        account_id=account.id,
        row_count=1,
        status=ImportStatus.IMPORTED,
    )
    db_session.add(batch)
    db_session.flush()

    raw = RawTransaction(
        batch_id=batch.id,
        source_row="17",
        line_hash="b" * 64,
        original_transaction_date="2026-01-05",
        original_amount="6000.00",
        original_description="SALARIO EMPRESA EXEMPLO",
        raw_payload={"extra_column": "preserved"},
    )
    db_session.add(raw)
    db_session.flush()

    transaction = Transaction(
        account_id=account.id,
        transaction_date=date(2026, 1, 5),
        amount_cents=600000,
        original_description=raw.original_description,
        nature=TransactionNature.INCOME,
        classification_source=ClassificationSource.MANUAL,
        manual_classification_locked=True,
        stable_signature="c" * 64,
        batch_id=batch.id,
        raw_transaction_id=raw.id,
    )
    db_session.add(transaction)
    db_session.commit()

    saved = db_session.scalar(select(Transaction))
    assert saved is not None
    assert saved.amount_cents == 600000
    assert saved.raw_transaction.original_amount == "6000.00"
    assert saved.raw_transaction.raw_payload["extra_column"] == "preserved"
    assert saved.manual_classification_locked is True

    saved.raw_transaction.original_amount = "1.00"
    try:
        db_session.commit()
    except RawTransactionImmutable:
        db_session.rollback()
    else:
        raise AssertionError("raw audit evidence was changed")
