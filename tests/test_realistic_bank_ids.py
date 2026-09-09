from finance_analysis.ingestion import stable_transaction_id
from finance_analysis.ofx import parse_statement
from tests.test_ofx import OFX


def test_reused_bank_id_does_not_merge_distinct_transactions():
    first_statement = parse_statement(OFX)
    changed = OFX.replace(b"20260105120000", b"20260205120000").replace(
        b"-12.34", b"-99.00"
    )
    second_statement = parse_statement(changed)

    first = stable_transaction_id(
        first_statement.account_fingerprint,
        first_statement.transactions[0],
        1,
    )
    second = stable_transaction_id(
        second_statement.account_fingerprint,
        second_statement.transactions[0],
        1,
    )

    assert first != second
