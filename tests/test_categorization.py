from sqlalchemy import func, select

from finance.categorization import apply_first_matching_rule
from finance.db.bootstrap import DEFAULT_CATEGORIES_PATH, seed_categories
from finance.importers.preview import build_import_preview
from finance.models import (
    Account,
    AccountType,
    Category,
    ClassificationSource,
    FinancialRole,
    RuleMatchType,
    Transaction,
    TransactionEdit,
    TransactionNature,
)
from finance.repositories.imports import confirm_import
from finance.repositories.rules import ClassificationRuleError, create_classification_rule
from finance.repositories.transactions import update_transaction_manual
from tests.helpers import canonical_csv


def setup_account_and_categories(db_session):
    seed_categories(db_session, DEFAULT_CATEGORIES_PATH)
    account = Account(
        name="Conta fictícia",
        account_type=AccountType.CHECKING,
        financial_role=FinancialRole.OPERATIONAL,
    )
    db_session.add(account)
    db_session.commit()
    categories = {
        category.slug: category for category in db_session.scalars(select(Category)).all()
    }
    return account, categories


def import_one(db_session, tmp_path, account, description="UBER TESTE"):
    content = canonical_csv(
        f"2026-01-05,{account.name},{description},-20.00,,expense,,,false,false,a.pdf,2,"
    )
    preview = build_import_preview(content, "lote.csv", db_session, account.id)
    confirm_import(preview, db_session, account_id=account.id, archive_root=tmp_path)
    return db_session.scalar(select(Transaction))


def test_rule_is_applied_to_future_import(db_session, tmp_path):
    account, categories = setup_account_and_categories(db_session)
    target = categories["transporte-aplicativo"]
    create_classification_rule(
        db_session,
        name="Aplicativos de transporte",
        match_type=RuleMatchType.DESCRIPTION_CONTAINS,
        pattern="uber",
        category_id=target.id,
        nature=TransactionNature.EXPENSE,
        priority=10,
    )

    transaction = import_one(db_session, tmp_path, account)

    assert transaction.category_id == target.id
    assert transaction.classification_source is ClassificationSource.RULE


def test_manual_correction_prevails_over_automatic_rule(db_session, tmp_path):
    account, categories = setup_account_and_categories(db_session)
    original = categories["transporte-aplicativo"]
    corrected = categories["alimentacao-restaurante"]
    create_classification_rule(
        db_session,
        name="Regra inicial",
        match_type=RuleMatchType.DESCRIPTION_CONTAINS,
        pattern="UBER",
        category_id=original.id,
        priority=10,
    )
    transaction = import_one(db_session, tmp_path, account)

    update_transaction_manual(
        db_session,
        transaction.id,
        category_id=corrected.id,
        nature=TransactionNature.EXPENSE,
        is_extraordinary=True,
        is_essential_override=False,
        is_living_cost_override=True,
        reason="Correção fictícia",
    )
    db_session.refresh(transaction)

    assert apply_first_matching_rule(db_session, transaction) is None
    assert transaction.category_id == corrected.id
    assert transaction.classification_source is ClassificationSource.MANUAL
    assert transaction.manual_classification_locked is True
    assert transaction.is_extraordinary is True
    edit = db_session.scalar(select(TransactionEdit))
    assert edit is not None
    assert edit.changes["category_id"] == {"before": original.id, "after": corrected.id}
    assert edit.reason == "Correção fictícia"


def test_lower_priority_number_wins(db_session, tmp_path):
    account, categories = setup_account_and_categories(db_session)
    lower_precedence = categories["compras-casa"]
    winner = categories["moradia-manutencao"]
    for name, priority, category in (
        ("Regra genérica", 100, lower_precedence),
        ("Regra prioritária", 5, winner),
    ):
        create_classification_rule(
            db_session,
            name=name,
            match_type=RuleMatchType.DESCRIPTION_CONTAINS,
            pattern="LOJA TESTE",
            category_id=category.id,
            priority=priority,
        )

    transaction = import_one(db_session, tmp_path, account, "LOJA TESTE")
    assert transaction.category_id == winner.id


def test_invalid_regex_rule_is_rejected(db_session):
    _, categories = setup_account_and_categories(db_session)
    try:
        create_classification_rule(
            db_session,
            name="Regex inválida",
            match_type=RuleMatchType.DESCRIPTION_REGEX,
            pattern="[",
            category_id=categories["a-revisar"].id,
        )
    except ClassificationRuleError as exc:
        assert "regular inválida" in str(exc)
    else:
        raise AssertionError("invalid regular expression was accepted")
    assert db_session.scalar(select(func.count()).select_from(TransactionEdit)) == 0
