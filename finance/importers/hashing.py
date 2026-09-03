"""Stable hashes used for audit and duplicate detection."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import date
from typing import Any


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def account_fingerprint(institution_code: str, branch_id: str, account_id: str) -> str:
    material = f"{institution_code.strip()}|{branch_id.strip()}|{account_id.strip()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def normalized_description(description: str) -> str:
    normalized = unicodedata.normalize("NFKC", description).upper()
    return " ".join(normalized.split())


def transaction_signature(
    account_id: int, transaction_date: date, amount_cents: int, description: str
) -> str:
    material = (
        f"{account_id}|{transaction_date.isoformat()}|{amount_cents}|"
        f"{normalized_description(description)}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def raw_line_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
