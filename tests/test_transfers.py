from sqlalchemy import select

from finance.importers.preview import build_import_preview
from finance.models import (
    Account,
    AccountType,
    FinancialRole,
    Transaction,
    TransactionNature,
    TransferMatchState,
)
from finance.repositories.imports import confirm_import
from finance.transfers import (
    confirm_transfer_match,
    find_transfer_suggestions,
    mark_transaction_as_transfer,
    reject_transfer_match,
)
from tests.helpers import canonical_csv


def add_account(db_session, name, role):
    account = Account(
        name=name,
        account_type=AccountType.CHECKING,
        financial_role=role,
        is_reserve=role is FinancialRole.RESERVE,
    )
    db_session.add(account)
    db_session.commit()
    return account


def import_rows(db_session, tmp_path, account, filename, *rows):
    content = canonical_csv(*rows)
    preview = build_import_preview(content, filename, db_session, account.id)
    return confirm_import(preview, db_session, account_id=account.id, archive_root=tmp_path)


def test_transfer_across_month_boundary_is_suggested_and_reversible(db_session, tmp_path):
    flow = add_account(db_session, "Fluxo fictícia", FinancialRole.OPERATIONAL)
    reserve = add_account(db_session, "Reserva fictícia", FinancialRole.RESERVE)
    import_rows(
        db_session,
        tmp_path,
        flow,
        "saida.csv",
        "2026-01-31,Fluxo fictícia,TRANSFERENCIA PARA RESERVA,-1000.00,,expense,,,"
        "false,false,a.pdf,2,",
    )
    import_rows(
        db_session,
        tmp_path,
        reserve,
        "entrada.csv",
        "2026-02-01,Reserva fictícia,TRANSFERENCIA RECEBIDA,1000.00,,income,,,false,false,b.pdf,2,",
    )

    suggestions = find_transfer_suggestions(db_session)
    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion.date_distance_days == 1
    assert suggestion.ambiguous is False

    match = confirm_transfer_match(
        db_session,
        suggestion.outgoing_transaction_id,
        suggestion.incoming_transaction_id,
        confidence_basis_points=suggestion.confidence_basis_points,
        rationale=suggestion.rationale,
    )
    assert match.state is TransferMatchState.CONFIRMED
    transactions = db_session.scalars(select(Transaction).order_by(Transaction.amount_cents)).all()
    assert all(transaction.is_internal_transfer for transaction in transactions)
    assert all(transaction.nature is TransactionNature.TRANSFER for transaction in transactions)

    reject_transfer_match(db_session, match.id)
    db_session.refresh(match)
    for transaction in transactions:
        db_session.refresh(transaction)
    assert match.state is TransferMatchState.REJECTED
    assert not any(transaction.is_internal_transfer for transaction in transactions)
    assert {transaction.nature for transaction in transactions} == {
        TransactionNature.EXPENSE,
        TransactionNature.INCOME,
    }


def test_equal_value_candidates_are_ambiguous_and_never_auto_confirmed(db_session, tmp_path):
    flow = add_account(db_session, "Fluxo fictícia", FinancialRole.OPERATIONAL)
    reserve = add_account(db_session, "Reserva fictícia", FinancialRole.RESERVE)
    import_rows(
        db_session,
        tmp_path,
        flow,
        "saida.csv",
        "2026-03-10,Fluxo fictícia,TRANSFERENCIA,-500.00,,expense,,,false,false,a.pdf,2,",
    )
    import_rows(
        db_session,
        tmp_path,
        reserve,
        "entradas.csv",
        "2026-03-10,Reserva fictícia,RECEBIMENTO A,500.00,,income,,,false,false,b.pdf,2,",
        "2026-03-11,Reserva fictícia,RECEBIMENTO B,500.00,,income,,,false,false,b.pdf,3,",
    )

    suggestions = find_transfer_suggestions(db_session)
    assert len(suggestions) == 2
    assert all(suggestion.ambiguous for suggestion in suggestions)
    assert not any(
        transaction.is_internal_transfer for transaction in db_session.scalars(select(Transaction))
    )


def test_single_transfer_point_can_be_marked_manually(db_session, tmp_path):
    flow = add_account(db_session, "Fluxo fictícia", FinancialRole.OPERATIONAL)
    import_rows(
        db_session,
        tmp_path,
        flow,
        "ponta.csv",
        "2026-01-05,Fluxo fictícia,APORTE SEM CONTRAPARTE,-250.00,,expense,,,false,false,a.pdf,2,",
    )
    transaction = db_session.scalar(select(Transaction))
    assert transaction is not None

    mark_transaction_as_transfer(db_session, transaction.id, is_transfer=True)
    assert transaction.is_internal_transfer is True
    assert transaction.nature is TransactionNature.TRANSFER
