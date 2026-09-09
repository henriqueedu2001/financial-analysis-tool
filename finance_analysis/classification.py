from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from datetime import date
from pathlib import Path
from statistics import median_low

CLASSIFICATION_FIELDS = (
    "nature",
    "category",
    "subcategory",
    "recurrence",
    "flexibility",
    "cost_treatment",
    "peak_eligible",
)

RULE_FIELDS = [
    "rule_id",
    "priority",
    "match_type",
    "match_value",
    "valid_from",
    "valid_to",
    "min_amount_cents",
    "max_amount_cents",
    *CLASSIFICATION_FIELDS,
    "notes",
    "decision_source",
]

OVERRIDE_FIELDS = [
    "transaction_id",
    *CLASSIFICATION_FIELDS,
    "notes",
    "decision_source",
]

ALLOCATION_FIELDS = [
    "allocation_id",
    "transaction_id",
    "amount_cents",
    *CLASSIFICATION_FIELDS,
    "notes",
    "decision_source",
]

INVESTIGATION_FIELDS = [
    "investigation_id",
    "group_id",
    "status",
    "question",
    "known_evidence",
    "next_evidence",
    "notes",
    "decision_source",
]

EVENT_FIELDS = [
    "event_id",
    "transaction_id",
    "event_type",
    "event_label",
    "notes",
    "decision_source",
]

INVESTIGATION_STATUSES = {"needs_investigation", "deprioritized", "resolved"}

GROUP_FIELDS = [
    "group_id",
    "channel",
    "counterparty_key",
    "counterparty_display",
    "transaction_count",
    "inflow_count",
    "outflow_count",
    "first_date",
    "last_date",
    "active_months",
    "minimum_abs_cents",
    "median_abs_cents",
    "maximum_abs_cents",
    "total_abs_cents",
    "sample_descriptions",
    "missing_fields",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    alphanumeric = re.sub(r"[^A-Za-z0-9]+", " ", ascii_text)
    return " ".join(alphanumeric.upper().split())


def _strip_bb_datetime(value: str) -> str:
    return re.sub(r"^\d{2}/\d{2}\s+\d{2}:\d{2}\s+", "", value).strip()


def _strip_itau_date_suffix(value: str) -> str:
    return re.sub(r"(?<=[A-Za-z])\d{2}\s+\d{2}$", "", value).strip()


def _bb_counterparty(name: str, memo: str) -> tuple[str, str]:
    candidate = _strip_bb_datetime(memo) or name
    identifier_fingerprint = ""
    if name == "Pix - Recebido":
        identified = re.match(r"^(\d{11,14})\s+(.+)$", candidate)
        if identified:
            identifier = identified.group(1).lstrip("0") or "0"
            identifier_fingerprint = hashlib.sha256(identifier.encode()).hexdigest()[:12]
            candidate = identified.group(2)
    if name == "BB Rende Fácil":
        return "BB Rende Fácil", ""
    if name in {
        "Cobrança de I.O.F.",
        "Cobrança de Juros",
        "Movimento do Dia",
        "Pagamento de Impostos",
        "Pagto cartão crédito",
    }:
        return memo or name, ""
    return candidate or name or "Sem contraparte", identifier_fingerprint


def _itau_counterparty(memo: str) -> str:
    value = _strip_itau_date_suffix(memo)
    prefixes = (
        "PIX QRS ",
        "PIX TRANSF ",
        "DEV PIX ",
        "PAG BOLETO ",
    )
    for prefix in prefixes:
        if value.upper().startswith(prefix):
            return value[len(prefix) :].strip()
    if value.upper().startswith("TED "):
        return re.sub(r"^TED\s+\d+\s+\d+\s+", "", value, flags=re.IGNORECASE).strip()
    return value or "Sem contraparte"


def detect_channel(row: dict[str, str]) -> str:
    name = row["name_raw"].strip()
    memo_upper = row["memo_raw"].strip().upper()
    if row["account_id"] == "banco_do_brasil_conta_corrente":
        channels = {
            "Compra com Cartão": "debit_card_purchase",
            "Pix - Enviado": "pix_sent",
            "Pix - Recebido": "pix_received",
            "Pix-Envio devolvido": "pix_sent_refund",
            "Pix-Recebimento devolvido": "pix_received_reversal",
            "BB Rende Fácil": "bb_rende_facil",
            "Pagamento de Boleto": "bill_payment",
            "Movimento do Dia": "scheduled_debit",
            "Cobrança de I.O.F.": "bank_iof",
            "Cobrança de Juros": "bank_interest",
            "Pagto cartão crédito": "credit_card_payment",
            "Compra DBT": "debit_card_adjustment",
            "Pagamento de Impostos": "tax_payment",
        }
        return channels.get(name, "bb_other")

    if memo_upper == "APLICACAO COFRINHOS":
        return "cofrinho_application"
    if memo_upper in {"RESGATE CDB COFRINHOS", "COF RESGATE CDB", "RESGATE COFRINHOS"}:
        return "cofrinho_redemption"
    if memo_upper == "REND PAGO APLIC AUT MAIS":
        return "investment_yield"
    if memo_upper == "SEGURO CARTAO":
        return "card_insurance"
    if memo_upper.startswith("PIX QRS "):
        return "pix_qr_sent"
    if memo_upper.startswith("PIX TRANSF "):
        return "pix_transfer"
    if memo_upper.startswith("DEV PIX "):
        return "pix_refund"
    if memo_upper.startswith("PAG BOLETO "):
        return "bill_payment"
    if memo_upper.startswith("TED "):
        return "ted_transfer"
    if memo_upper.startswith("INT  DARF"):
        return "tax_payment"
    return "itau_other"


def counterparty_for(row: dict[str, str]) -> tuple[str, str]:
    if row["account_id"] == "banco_do_brasil_conta_corrente":
        display, identifier_fingerprint = _bb_counterparty(
            row["name_raw"].strip(), row["memo_raw"].strip()
        )
    else:
        display = _itau_counterparty(row["memo_raw"].strip())
        identifier_fingerprint = ""
    key = (
        f"ID {identifier_fingerprint}"
        if identifier_fingerprint
        else normalize_text(display)
    )
    return key, display


def group_identity(row: dict[str, str]) -> tuple[str, str, str, str]:
    channel = detect_channel(row)
    counterparty_key, display = counterparty_for(row)
    material = f"{channel}\0{counterparty_key}".encode()
    group_id = hashlib.sha256(material).hexdigest()[:20]
    return group_id, channel, counterparty_key, display


def rule_matches(rule: dict[str, str], row: dict[str, str]) -> bool:
    group_id, channel, counterparty_key, _ = group_identity(row)
    values = {
        "group_id": group_id,
        "channel": channel,
        "counterparty_key": counterparty_key,
    }
    if rule["match_type"] not in values:
        raise ValueError(f"match_type inválido: {rule['match_type']!r}")
    if values[rule["match_type"]] != rule["match_value"]:
        return False

    transaction_date = date.fromisoformat(row["transaction_date"])
    amount_cents = int(row["amount_cents"])
    if rule["valid_from"] and transaction_date < date.fromisoformat(rule["valid_from"]):
        return False
    if rule["valid_to"] and transaction_date > date.fromisoformat(rule["valid_to"]):
        return False
    if rule["min_amount_cents"] and amount_cents < int(rule["min_amount_cents"]):
        return False
    return not rule["max_amount_cents"] or amount_cents <= int(rule["max_amount_cents"])


def classify_row(
    row: dict[str, str],
    rules: list[dict[str, str]],
    overrides: dict[str, dict[str, str]],
) -> dict[str, str]:
    result = {field: "" for field in CLASSIFICATION_FIELDS}
    provenance: list[str] = []
    for rule in sorted(rules, key=lambda item: int(item["priority"] or 0)):
        if not rule_matches(rule, row):
            continue
        for field in CLASSIFICATION_FIELDS:
            if rule[field]:
                result[field] = rule[field]
        provenance.append(rule["rule_id"])

    override = overrides.get(row["transaction_id"])
    if override:
        for field in CLASSIFICATION_FIELDS:
            if override[field]:
                result[field] = override[field]
        provenance.append(f"override:{row['transaction_id']}")

    group_id, channel, counterparty_key, display = group_identity(row)
    return {
        **row,
        "group_id": group_id,
        "channel": channel,
        "counterparty_key": counterparty_key,
        "counterparty_display": display,
        **result,
        "classification_provenance": ";".join(provenance),
    }


def build_groups(
    rows: list[dict[str, str]],
    rules: list[dict[str, str]],
    overrides: dict[str, dict[str, str]],
    allocations: list[dict[str, str]] | None = None,
) -> list[dict[str, str | int]]:
    allocations = allocations or []
    allocations_by_transaction: dict[str, list[dict[str, str]]] = {}
    for allocation in allocations:
        allocations_by_transaction.setdefault(allocation["transaction_id"], []).append(
            allocation
        )
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(group_identity(row)[0], []).append(row)

    result: list[dict[str, str | int]] = []
    for group_id, items in grouped.items():
        _, channel, counterparty_key, display = group_identity(items[0])
        amounts = [abs(int(item["amount_cents"])) for item in items]
        classified = [classify_row(item, rules, overrides) for item in items]
        item_ids = {item["transaction_id"] for item in items}
        relevant_allocations = [
            allocation
            for transaction_id in item_ids
            for allocation in allocations_by_transaction.get(transaction_id, [])
        ]
        classified = expand_allocations(classified, relevant_allocations)
        missing = sorted(
            {
                field
                for item in classified
                for field in CLASSIFICATION_FIELDS
                if not item[field]
            }
        )
        samples = list(dict.fromkeys(item["description_raw"] for item in items))[:3]
        result.append(
            {
                "group_id": group_id,
                "channel": channel,
                "counterparty_key": counterparty_key,
                "counterparty_display": display,
                "transaction_count": len(items),
                "inflow_count": sum(int(item["amount_cents"]) > 0 for item in items),
                "outflow_count": sum(int(item["amount_cents"]) < 0 for item in items),
                "first_date": min(item["transaction_date"] for item in items),
                "last_date": max(item["transaction_date"] for item in items),
                "active_months": len({item["transaction_date"][:7] for item in items}),
                "minimum_abs_cents": min(amounts),
                "median_abs_cents": median_low(amounts),
                "maximum_abs_cents": max(amounts),
                "total_abs_cents": sum(amounts),
                "sample_descriptions": " || ".join(samples),
                "missing_fields": ";".join(missing),
            }
        )
    return sorted(
        result,
        key=lambda item: (-int(item["transaction_count"]), str(item["counterparty_key"])),
    )


def sort_groups_by_materiality(
    groups: list[dict[str, str | int]],
) -> list[dict[str, str | int]]:
    """Prioriza o maior lançamento individual e depois o impacto total do grupo."""
    return sorted(
        groups,
        key=lambda item: (
            -int(item["maximum_abs_cents"]),
            -int(item["total_abs_cents"]),
            str(item["counterparty_key"]),
        ),
    )


def validate_rules(rules: list[dict[str, str]]) -> None:
    ids = [rule["rule_id"] for rule in rules]
    if any(not rule_id for rule_id in ids):
        raise ValueError("Toda regra precisa de rule_id")
    if len(ids) != len(set(ids)):
        raise ValueError("rule_id duplicado")
    for rule in rules:
        if set(rule) != set(RULE_FIELDS):
            raise ValueError(f"Colunas inválidas na regra {rule['rule_id']!r}")


def load_rules(base_path: Path, knowledge_path: Path) -> list[dict[str, str]]:
    rules = read_csv(base_path)
    if knowledge_path.exists():
        rules.extend(read_csv(knowledge_path))
    validate_rules(rules)
    return rules


def load_overrides(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows = read_csv(path)
    return {row["transaction_id"]: row for row in rows}


def load_allocations(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows = read_csv(path)
    allocation_ids = [row["allocation_id"] for row in rows]
    if any(not allocation_id for allocation_id in allocation_ids):
        raise ValueError("Toda alocação precisa de allocation_id")
    if len(allocation_ids) != len(set(allocation_ids)):
        raise ValueError("allocation_id duplicado")
    for row in rows:
        if set(row) != set(ALLOCATION_FIELDS):
            raise ValueError(f"Colunas inválidas na alocação {row['allocation_id']!r}")
        if not row["transaction_id"]:
            raise ValueError(f"Alocação sem transaction_id: {row['allocation_id']!r}")
        if not row["amount_cents"]:
            raise ValueError(f"Alocação sem valor: {row['allocation_id']!r}")
    return rows


def load_investigations(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows = read_csv(path)
    ids = [row["investigation_id"] for row in rows]
    if any(not investigation_id for investigation_id in ids):
        raise ValueError("Toda investigação precisa de investigation_id")
    if len(ids) != len(set(ids)):
        raise ValueError("investigation_id duplicado")
    for row in rows:
        if set(row) != set(INVESTIGATION_FIELDS):
            raise ValueError(
                f"Colunas inválidas na investigação {row['investigation_id']!r}"
            )
        if not row["group_id"]:
            raise ValueError(
                f"Investigação sem group_id: {row['investigation_id']!r}"
            )
        if row["status"] not in INVESTIGATION_STATUSES:
            raise ValueError(
                f"Status inválido na investigação {row['investigation_id']!r}: "
                f"{row['status']!r}"
            )
    return rows


def load_events(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows = read_csv(path)
    transaction_ids = [row["transaction_id"] for row in rows]
    if any(not transaction_id for transaction_id in transaction_ids):
        raise ValueError("Toda associação de evento precisa de transaction_id")
    if len(transaction_ids) != len(set(transaction_ids)):
        raise ValueError("Uma transação não pode pertencer a mais de um evento")
    for row in rows:
        if set(row) != set(EVENT_FIELDS):
            raise ValueError(f"Colunas inválidas no evento {row['event_id']!r}")
        if not row["event_id"]:
            raise ValueError("Toda associação de evento precisa de event_id")
    return rows


def validate_knowledge_references(
    transactions: list[dict[str, str]],
    rules: list[dict[str, str]],
    overrides: dict[str, dict[str, str]],
    allocations: list[dict[str, str]],
    investigations: list[dict[str, str]],
    events: list[dict[str, str]],
) -> None:
    """Impede que conhecimento privado aponte silenciosamente para dados ausentes."""
    transaction_ids = {row["transaction_id"] for row in transactions}
    group_ids = {group_identity(row)[0] for row in transactions}

    missing_rule_groups = sorted(
        {
            rule["match_value"]
            for rule in rules
            if rule["match_type"] == "group_id"
            and rule["match_value"] not in group_ids
        }
    )
    missing_investigation_groups = sorted(
        {
            row["group_id"]
            for row in investigations
            if row["group_id"] not in group_ids
        }
    )
    referenced_transactions = {
        *overrides,
        *(row["transaction_id"] for row in allocations),
        *(row["transaction_id"] for row in events),
    }
    missing_transactions = sorted(referenced_transactions - transaction_ids)

    errors = []
    if missing_rule_groups:
        errors.append(f"regras: {', '.join(missing_rule_groups)}")
    if missing_investigation_groups:
        errors.append(f"investigações: {', '.join(missing_investigation_groups)}")
    if missing_transactions:
        errors.append(f"transações: {', '.join(missing_transactions)}")
    if errors:
        raise ValueError("Referências de conhecimento inexistentes: " + "; ".join(errors))


def expand_allocations(
    classified: list[dict[str, str]], allocations: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Substitui uma movimentação composta por parcelas analíticas auditáveis."""
    by_transaction: dict[str, list[dict[str, str]]] = {}
    for allocation in allocations:
        by_transaction.setdefault(allocation["transaction_id"], []).append(allocation)

    transactions = {row["transaction_id"]: row for row in classified}
    unknown = sorted(set(by_transaction) - set(transactions))
    if unknown:
        raise ValueError(f"Alocações referenciam transações inexistentes: {unknown}")

    result: list[dict[str, str]] = []
    for row in classified:
        parts = by_transaction.get(row["transaction_id"])
        if not parts:
            result.append(
                {
                    **row,
                    "analytical_transaction_id": row["transaction_id"],
                    "parent_transaction_id": row["transaction_id"],
                    "original_amount_cents": row["amount_cents"],
                    "is_allocation": "false",
                }
            )
            continue

        allocated_total = sum(int(part["amount_cents"]) for part in parts)
        if allocated_total != int(row["amount_cents"]):
            raise ValueError(
                f"Alocações de {row['transaction_id']} somam {allocated_total} "
                f"mas a transação vale {row['amount_cents']}"
            )
        for part in parts:
            part_classification = {
                field: part[field] or row[field] for field in CLASSIFICATION_FIELDS
            }
            result.append(
                {
                    **row,
                    "amount_cents": part["amount_cents"],
                    **part_classification,
                    "classification_provenance": ";".join(
                        filter(
                            None,
                            (
                                row["classification_provenance"],
                                f"allocation:{part['allocation_id']}",
                            ),
                        )
                    ),
                    "analytical_transaction_id": part["allocation_id"],
                    "parent_transaction_id": row["transaction_id"],
                    "original_amount_cents": row["amount_cents"],
                    "is_allocation": "true",
                }
            )
    return result
