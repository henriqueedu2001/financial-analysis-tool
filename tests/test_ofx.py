from datetime import date

import pytest

from finance_analysis.ofx import money_to_cents, parse_statement

OFX = b"""OFXHEADER:100
DATA:OFXSGML
VERSION:102
ENCODING:USASCII
CHARSET:1252

<OFX>
<BANKID>0341
<ACCTID>secret-account
<BANKTRANLIST>
<DTSTART>20260101000000[-03:EST]
<DTEND>20260131235959[-03:EST]
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260105120000[-03:EST]
<TRNAMT>-12.34
<FITID>abc-1
<MEMO>PADARIA EXEMPLO
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20260110120000[-03:EST]
<TRNAMT>100.00
<FITID>abc-2
<NAME>RECEITA FICTICIA
<MEMO>RECEITA FICTICIA
</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL>
<BALAMT>87.66
<DTASOF>20260131235959[-03:EST]
</LEDGERBAL>
</OFX>
"""


def test_parse_sgml_statement_without_closed_leaf_tags():
    statement = parse_statement(OFX)

    assert statement.bank_id == "0341"
    assert len(statement.account_fingerprint) == 64
    assert "secret-account" not in statement.account_fingerprint
    assert statement.coverage_start == date(2026, 1, 5)
    assert statement.coverage_end == date(2026, 1, 10)
    assert statement.balance_date == date(2026, 1, 31)
    assert statement.balance_cents == 8766
    assert statement.transactions[0].amount_cents == -1234
    assert statement.transactions[1].description_raw == "RECEITA FICTICIA"


def test_money_rejects_fractions_of_cent():
    with pytest.raises(ValueError, match="fração de centavo"):
        money_to_cents("1.001")
