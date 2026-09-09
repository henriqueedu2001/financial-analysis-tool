from pathlib import Path

import pytest

from finance_analysis.classification import (
    classify_row,
    detect_channel,
    expand_allocations,
    group_identity,
    load_events,
    load_investigations,
    normalize_text,
    sort_groups_by_materiality,
    validate_knowledge_references,
)


def transaction(**changes: str) -> dict[str, str]:
    base = {
        "transaction_id": "tx-1",
        "account_id": "banco_do_brasil_conta_corrente",
        "transaction_date": "2026-01-10",
        "amount_cents": "-18000",
        "name_raw": "Pix - Enviado",
        "memo_raw": "10/01 08:30 Psicologo Exemplo",
        "description_raw": "Pix - Enviado | 10/01 08:30 Psicologo Exemplo",
    }
    return {**base, **changes}


def rule(**changes: str) -> dict[str, str]:
    base = {
        "rule_id": "rule",
        "priority": "100",
        "match_type": "group_id",
        "match_value": group_identity(transaction())[0],
        "valid_from": "",
        "valid_to": "",
        "min_amount_cents": "",
        "max_amount_cents": "",
        "nature": "expense",
        "category": "Saúde",
        "subcategory": "Psicoterapia",
        "recurrence": "variable_habitual",
        "flexibility": "mandatory",
        "cost_treatment": "recurring",
        "peak_eligible": "false",
        "notes": "",
        "decision_source": "test",
    }
    return {**base, **changes}


def test_normalization_ignores_accents_case_and_punctuation():
    assert normalize_text("  Psicólogo: João! ") == "PSICOLOGO JOAO"


def test_bb_pix_group_ignores_transaction_timestamp():
    first = transaction(memo_raw="10/01 08:30 Psicologo Exemplo")
    second = transaction(memo_raw="17/01 12:00 Psicologo Exemplo")

    assert group_identity(first)[0] == group_identity(second)[0]


def test_itau_cofrinho_channels_are_explicit():
    row = transaction(
        account_id="itau_conta_corrente",
        name_raw="",
        memo_raw="RESGATE CDB Cofrinhos",
    )

    assert detect_channel(row) == "cofrinho_redemption"


def test_received_pix_with_same_name_but_distinct_identifiers_is_split():
    first = transaction(
        name_raw="Pix - Recebido",
        memo_raw="10/01 08:30 00012345678901 MESMO NOME",
    )
    second = transaction(
        name_raw="Pix - Recebido",
        memo_raw="10/01 08:30 99912345678901 MESMO NOME",
    )

    assert group_identity(first)[0] != group_identity(second)[0]


def test_transaction_override_prevails_over_rule():
    row = transaction()
    override = {
        "transaction_id": "tx-1",
        "nature": "",
        "category": "Saúde",
        "subcategory": "Psicoterapia",
        "recurrence": "fixed_contractual",
        "flexibility": "",
        "cost_treatment": "",
        "peak_eligible": "",
        "notes": "Correção",
        "decision_source": "henrique",
    }

    result = classify_row(row, [rule(recurrence="variable_habitual")], {"tx-1": override})

    assert result["recurrence"] == "fixed_contractual"


def test_allocation_splits_transaction_without_losing_original_value():
    classified = classify_row(transaction(amount_cents="-147833"), [rule()], {})
    parts = [
        {
            "allocation_id": "rent",
            "transaction_id": "tx-1",
            "amount_cents": "-130500",
            "nature": "expense",
            "category": "Moradia",
            "subcategory": "Aluguel",
            "recurrence": "fixed_contractual",
            "flexibility": "mandatory",
            "cost_treatment": "recurring",
            "peak_eligible": "false",
            "notes": "",
            "decision_source": "test",
        },
        {
            "allocation_id": "fee",
            "transaction_id": "tx-1",
            "amount_cents": "-17333",
            "nature": "expense",
            "category": "Moradia",
            "subcategory": "Taxa imobiliária",
            "recurrence": "non_recurring",
            "flexibility": "mandatory",
            "cost_treatment": "expanded",
            "peak_eligible": "true",
            "notes": "",
            "decision_source": "test",
        },
    ]

    result = expand_allocations([classified], parts)

    assert [row["amount_cents"] for row in result] == ["-130500", "-17333"]
    assert all(row["original_amount_cents"] == "-147833" for row in result)
    assert all(row["parent_transaction_id"] == "tx-1" for row in result)


def test_allocation_must_reconcile_to_original_transaction():
    classified = classify_row(transaction(amount_cents="-10000"), [rule()], {})
    incomplete = [
        {
            "allocation_id": "part",
            "transaction_id": "tx-1",
            "amount_cents": "-9999",
            **{field: "" for field in (
                "nature",
                "category",
                "subcategory",
                "recurrence",
                "flexibility",
                "cost_treatment",
                "peak_eligible",
            )},
            "notes": "",
            "decision_source": "test",
        }
    ]

    try:
        expand_allocations([classified], incomplete)
    except ValueError as error:
        assert "somam -9999" in str(error)
    else:
        raise AssertionError("A soma incorreta deveria falhar")


def test_investigation_status_must_be_explicit(tmp_path: Path):
    path = tmp_path / "investigations.csv"
    path.write_text(
        "investigation_id,group_id,status,question,known_evidence,next_evidence,notes,decision_source\n"
        "case-1,group-1,talvez,Questão,Evidência,Próximo passo,Nota,test\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Status inválido"):
        load_investigations(path)


def test_transaction_cannot_belong_to_multiple_events(tmp_path: Path):
    path = tmp_path / "events.csv"
    path.write_text(
        "event_id,transaction_id,event_type,event_label,notes,decision_source\n"
        "event-1,tx-1,expense,Primeiro,,test\n"
        "event-2,tx-1,expense,Segundo,,test\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mais de um evento"):
        load_events(path)


def test_knowledge_cannot_reference_missing_groups_or_transactions():
    rows = [transaction()]
    missing_group_rule = rule(match_value="grupo-inexistente")
    event = {"transaction_id": "tx-inexistente"}

    with pytest.raises(ValueError, match="Referências de conhecimento inexistentes"):
        validate_knowledge_references(
            rows,
            [missing_group_rule],
            {},
            [],
            [],
            [event],
        )


def test_classification_queue_prioritizes_largest_individual_transaction():
    groups = [
        {
            "counterparty_key": "MUITAS PEQUENAS",
            "maximum_abs_cents": 5_000,
            "total_abs_cents": 100_000,
        },
        {
            "counterparty_key": "UMA GRANDE",
            "maximum_abs_cents": 80_000,
            "total_abs_cents": 80_000,
        },
    ]

    ordered = sort_groups_by_materiality(groups)

    assert [group["counterparty_key"] for group in ordered] == [
        "UMA GRANDE",
        "MUITAS PEQUENAS",
    ]
