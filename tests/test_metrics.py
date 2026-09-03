from datetime import date
from decimal import Decimal

from sqlalchemy import select

from finance.db.bootstrap import DEFAULT_CATEGORIES_PATH, seed_categories
from finance.importers.preview import build_import_preview
from finance.metrics import (
    burn_rate_normalized,
    period_metrics,
    reserve_coverage_months,
)
from finance.models import Account, AccountType, FinancialRole, Transaction
from finance.reconciliation import record_balance_snapshot
from finance.repositories.imports import confirm_import
from finance.transfers import confirm_transfer_match, find_transfer_suggestions
from tests.helpers import canonical_csv


def add_account(db_session, name, role, *, reserve=False):
    account = Account(
        name=name,
        account_type=AccountType.CHECKING,
        financial_role=role,
        is_reserve=reserve,
        include_in_tracked_wealth=True,
    )
    db_session.add(account)
    db_session.commit()
    return account


def import_file(db_session, tmp_path, account, filename, *rows):
    content = canonical_csv(*rows)
    preview = build_import_preview(content, filename, db_session, account.id)
    confirm_import(preview, db_session, account_id=account.id, archive_root=tmp_path)


def test_transfer_has_zero_consolidated_effect_and_savings_differs_from_contribution(
    db_session, tmp_path
):
    seed_categories(db_session, DEFAULT_CATEGORIES_PATH)
    flow = add_account(db_session, "Fluxo fictícia", FinancialRole.OPERATIONAL)
    reserve = add_account(db_session, "Reserva fictícia", FinancialRole.RESERVE, reserve=True)
    record_balance_snapshot(
        db_session,
        account_id=flow.id,
        snapshot_date=date(2026, 1, 1),
        balance_cents=0,
    )
    record_balance_snapshot(
        db_session,
        account_id=reserve.id,
        snapshot_date=date(2026, 1, 1),
        balance_cents=1_000_000,
    )
    import_file(
        db_session,
        tmp_path,
        flow,
        "fluxo.csv",
        "2026-01-05,Fluxo fictícia,SALARIO,6000.00,,income,Receitas,Salário,false,false,a.pdf,2,",
        "2026-01-10,Fluxo fictícia,CUSTO DE VIDA,-3500.00,,expense,Alimentação,"
        "Mercado,false,false,a.pdf,3,",
        "2026-01-20,Fluxo fictícia,ENVIO RESERVA,-2000.00,,expense,,,false,false,a.pdf,4,",
    )
    import_file(
        db_session,
        tmp_path,
        reserve,
        "reserva.csv",
        "2026-01-20,Reserva fictícia,RECEBIMENTO FLUXO,2000.00,,income,,,false,false,b.pdf,2,",
    )
    suggestion = find_transfer_suggestions(db_session)[0]
    confirm_transfer_match(
        db_session,
        suggestion.outgoing_transaction_id,
        suggestion.incoming_transaction_id,
    )

    metrics = period_metrics(db_session, date(2026, 1, 1), date(2026, 1, 31))

    assert metrics.external_income_cents == 600_000
    assert metrics.external_expenses_cents == 350_000
    assert metrics.savings_cents == 250_000
    assert metrics.net_reserve_contribution_cents == 200_000
    assert metrics.savings_cents != metrics.net_reserve_contribution_cents
    assert metrics.operational_balance_cents == 50_000
    assert metrics.reserve_balance_cents == 1_200_000
    assert metrics.tracked_wealth_cents == 1_250_000
    assert metrics.savings_rate == Decimal(250_000) / Decimal(600_000)

    transfer_total = sum(
        transaction.amount_cents
        for transaction in db_session.scalars(select(Transaction))
        if transaction.is_internal_transfer
    )
    assert transfer_total == 0


def test_extraordinary_expense_reduces_savings_but_can_be_excluded_from_burn_rate(
    db_session, tmp_path
):
    seed_categories(db_session, DEFAULT_CATEGORIES_PATH)
    flow = add_account(db_session, "Fluxo fictícia", FinancialRole.OPERATIONAL)
    reserve = add_account(db_session, "Reserva fictícia", FinancialRole.RESERVE, reserve=True)
    for account, balance in ((flow, 0), (reserve, 600_000)):
        record_balance_snapshot(
            db_session,
            account_id=account.id,
            snapshot_date=date(2026, 1, 1),
            balance_cents=balance,
        )
    import_file(
        db_session,
        tmp_path,
        flow,
        "custos.csv",
        "2026-01-05,Fluxo fictícia,CUSTO JAN,-1000.00,,expense,Moradia,Aluguel,"
        "false,false,a.pdf,2,",
        "2026-02-05,Fluxo fictícia,CUSTO FEV,-1000.00,,expense,Moradia,Aluguel,"
        "false,false,a.pdf,3,",
        "2026-03-05,Fluxo fictícia,CUSTO MAR,-1000.00,,expense,Moradia,Aluguel,"
        "false,false,a.pdf,4,",
        "2026-03-10,Fluxo fictícia,EXTRAORDINARIA,-600.00,,expense,Moradia,"
        "Manutenção,false,true,a.pdf,5,",
    )

    metrics = period_metrics(db_session, date(2026, 1, 1), date(2026, 3, 31))
    excluded = burn_rate_normalized(
        db_session,
        as_of=date(2026, 3, 31),
        window_months=3,
        include_extraordinary=False,
    )
    included = burn_rate_normalized(
        db_session,
        as_of=date(2026, 3, 31),
        window_months=3,
        include_extraordinary=True,
    )
    coverage = reserve_coverage_months(
        db_session,
        as_of=date(2026, 3, 31),
        window_months=3,
        include_extraordinary=False,
    )

    assert metrics.external_expenses_cents == 360_000
    assert metrics.savings_cents == -360_000
    assert metrics.savings_rate is None
    assert excluded == 100_000
    assert included == 120_000
    assert coverage == Decimal("6")


def test_tracked_wealth_is_unavailable_when_an_included_account_has_no_known_balance(
    db_session,
):
    add_account(db_session, "Sem saldo", FinancialRole.OPERATIONAL)
    metrics = period_metrics(db_session, date(2026, 1, 1), date(2026, 1, 31))
    assert metrics.tracked_wealth_cents is None
    assert metrics.savings_rate is None
