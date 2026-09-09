from pathlib import Path

import pytest

from finance_analysis.ingestion import (
    build_canonical,
    build_reconciliation,
    is_balance_marker,
    stable_transaction_id,
)
from finance_analysis.models import AccountDefinition
from finance_analysis.ofx import parse_statement
from tests.test_ofx import OFX

ACCOUNT = AccountDefinition(
    account_id="itau_conta_corrente",
    institution="Itaú",
    path_prefix="itau",
    expected_bank_id="0341",
)


def test_duplicate_file_content_is_processed_once(tmp_path: Path):
    source = tmp_path / "itau"
    source.mkdir()
    (source / "original.ofx").write_bytes(OFX)
    (source / "renamed.ofx").write_bytes(OFX)

    transactions, snapshots = build_canonical(tmp_path, (ACCOUNT,))

    assert len(transactions) == 2
    assert len(snapshots) == 1


def test_transaction_id_is_stable_across_source_names():
    statement = parse_statement(OFX)
    transaction = statement.transactions[0]

    first = stable_transaction_id(statement.account_fingerprint, transaction, 1)
    second = stable_transaction_id(statement.account_fingerprint, transaction, 99)

    assert first == second


def test_unexpected_bank_is_rejected(tmp_path: Path):
    source = tmp_path / "itau"
    source.mkdir()
    (source / "statement.ofx").write_bytes(OFX)
    wrong = AccountDefinition(
        account_id="itau_conta_corrente",
        institution="Itaú",
        path_prefix="itau",
        expected_bank_id="9999",
    )

    with pytest.raises(ValueError, match="BANKID inesperado"):
        build_canonical(tmp_path, (wrong,))


def test_bank_balance_marker_is_not_a_financial_movement():
    marker_ofx = OFX.replace(b"PADARIA EXEMPLO", b"Saldo do dia").replace(
        b"<FITID>abc-1", b"<FITID>"
    )
    marker = parse_statement(marker_ofx).transactions[0]

    assert is_balance_marker(marker)


def test_reconciliation_detects_exact_balance():
    transactions = [
        {
            "account_id": "account",
            "transaction_date": "2026-01-10",
            "amount_cents": -2500,
        }
    ]
    snapshots = [
        {"account_id": "account", "balance_date": "2026-01-01", "balance_cents": 10000},
        {"account_id": "account", "balance_date": "2026-01-31", "balance_cents": 7500},
    ]

    result = build_reconciliation(transactions, snapshots)

    assert result[0]["difference_cents"] == 0
    assert result[0]["status"] == "balanced"
