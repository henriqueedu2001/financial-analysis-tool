from datetime import date

from sqlalchemy import select

from finance.db.bootstrap import DEFAULT_CATEGORIES_PATH, seed_categories
from finance.importers.preview import build_import_preview
from finance.models import Account, AccountType, Category, FinancialRole, TransactionNature
from finance.repositories.categories import create_category, update_category
from finance.repositories.imports import confirm_import
from finance.repositories.transactions import TransactionFilters, list_transactions
from tests.helpers import canonical_csv


def test_category_can_be_created_edited_and_deactivated(db_session):
    parent = create_category(db_session, name="Categoria Fictícia", is_living_cost=True)
    child = create_category(
        db_session,
        name="Subcategoria Fictícia",
        parent_id=parent.id,
        is_essential=True,
    )
    assert child.slug == "categoria-ficticia-subcategoria-ficticia"

    updated = update_category(
        db_session,
        child.id,
        name="Subcategoria Renomeada",
        is_living_cost=True,
        is_essential=False,
        is_recurring=True,
        is_extraordinary_default=False,
        is_active=False,
    )
    assert updated.name == "Subcategoria Renomeada"
    assert updated.slug == "categoria-ficticia-subcategoria-ficticia"
    assert updated.is_active is False


def test_transaction_filters_combine_period_account_nature_amount_and_text(db_session, tmp_path):
    seed_categories(db_session, DEFAULT_CATEGORIES_PATH)
    account = Account(
        name="Conta fictícia",
        account_type=AccountType.CHECKING,
        financial_role=FinancialRole.OPERATIONAL,
    )
    db_session.add(account)
    db_session.commit()
    content = canonical_csv(
        "2026-01-05,Conta fictícia,SALARIO FICTICIO,100.00,,income,Receitas,"
        "Salário,false,false,a.pdf,2,",
        "2026-01-06,Conta fictícia,MERCADO FICTICIO,-20.00,,expense,Alimentação,"
        "Mercado,false,false,a.pdf,3,",
    )
    preview = build_import_preview(content, "filtros.csv", db_session, account.id)
    confirm_import(preview, db_session, account_id=account.id, archive_root=tmp_path)
    market = db_session.scalar(select(Category).where(Category.slug == "alimentacao-mercado"))
    assert market is not None

    rows = list_transactions(
        db_session,
        TransactionFilters(
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
            account_ids=(account.id,),
            category_ids=(market.id,),
            natures=(TransactionNature.EXPENSE,),
            min_amount_cents=-3000,
            max_amount_cents=-1000,
            description_contains="mercado",
        ),
    )

    assert len(rows) == 1
    assert rows[0].original_description == "MERCADO FICTICIO"
