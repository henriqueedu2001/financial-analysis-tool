from decimal import Decimal

import pytest

from finance.importers import StatementParseError, parse_statement
from finance.models import TransactionNature
from tests.helpers import canonical_csv, make_ofx, tx_sgml, tx_xml


@pytest.mark.parametrize("xml", [True, False])
def test_ofx_parser_accepts_xml_and_sgml(xml):
    factory = tx_xml if xml else tx_sgml
    content = make_ofx(
        factory("20260105120000[-03:BRT]", "1000.10", "id-1", "Receita fictícia"),
        factory("20260106120000[-03:BRT]", "-0.20", "id-2", "Despesa fictícia"),
        xml=xml,
    )

    statement = parse_statement(content, "ficticio.ofx")

    assert statement.institution_label == "Banco do Brasil"
    assert len(statement.transactions) == 2
    assert statement.transactions[0].amount_cents == 100010
    assert statement.transactions[0].nature is TransactionNature.INCOME
    assert statement.transactions[1].amount_cents == -20
    assert statement.closing_balance_cents == 120000
    assert statement.source_account_fingerprint


def test_ofx_implausible_date_is_explicitly_rejected():
    content = make_ofx(tx_xml("00021130000000", "1.00", "", "Linha inválida"))

    statement = parse_statement(content, "bb-ficticio.ofx")

    assert not statement.transactions
    assert len(statement.invalid_transactions) == 1
    assert "fora do intervalo" in statement.invalid_transactions[0].errors[0]


def test_canonical_csv_preserves_text_and_exact_money():
    content = canonical_csv(
        "2026-01-05,Conta Fictícia,DESCRICAO ORIGINAL,6000.00,7000.00,income,"
        "Receitas,Salário,false,false,origem.pdf,2,0.975"
    )

    statement = parse_statement(content, "canonico.csv")

    row = statement.transactions[0]
    assert row.original_description == "DESCRICAO ORIGINAL"
    assert row.amount_cents == 600000
    assert row.balance_after_cents == 700000
    assert row.confidence_basis_points == 9750
    assert statement.account_label == "Conta Fictícia"


def test_canonical_csv_rejects_non_contract_boolean():
    content = canonical_csv(
        "2026-01-05,Conta Fictícia,DESCRICAO,1.00,,income,,,yes,false,origem.pdf,2,"
    )

    statement = parse_statement(content, "canonico.csv")

    assert not statement.transactions
    assert "true ou false" in " ".join(statement.invalid_transactions[0].errors)


def test_canonical_csv_rejects_mixed_accounts():
    content = canonical_csv(
        "2026-01-05,Conta A,ITEM A,1.00,,income,,,false,false,a.pdf,2,",
        "2026-01-05,Conta B,ITEM B,1.00,,income,,,false,false,b.pdf,2,",
    )
    with pytest.raises(StatementParseError, match="somente uma conta"):
        parse_statement(content, "misto.csv")


def test_parser_does_not_use_binary_float_for_decimal_values():
    content = canonical_csv(
        "2026-01-05,Conta Fictícia,A,0.10,,income,,,false,false,a.pdf,2,",
        "2026-01-06,Conta Fictícia,B,0.20,,income,,,false,false,a.pdf,3,",
    )
    statement = parse_statement(content, "exato.csv")
    total = sum(row.amount_cents for row in statement.transactions)
    assert total == 30
    assert Decimal(total) / 100 == Decimal("0.30")
