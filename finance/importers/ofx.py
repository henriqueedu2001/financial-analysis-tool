"""Parser for both OFX 2 XML and OFX 1 SGML statement variants."""

from __future__ import annotations

import html
import re
from datetime import date, datetime

from finance.importers.hashing import account_fingerprint
from finance.importers.types import (
    InvalidTransaction,
    ParsedStatement,
    ParsedTransaction,
    StatementParseError,
)
from finance.models import TransactionNature
from finance.money import InvalidMoney, decimal_to_cents

BANK_LABELS = {
    "1": "Banco do Brasil",
    "001": "Banco do Brasil",
    "0341": "Itaú",
    "341": "Itaú",
}


def _decode_ofx(content: bytes) -> str:
    header = content[:1000].decode("ascii", errors="ignore")
    charset_match = re.search(r"(?im)^CHARSET:\s*([^\r\n]+)", header)
    charset = charset_match.group(1).strip().upper() if charset_match else ""
    encodings = ["utf-8"] if "UTF" in charset else []
    encodings.extend(["cp1252", "latin-1"])
    for encoding in encodings:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise StatementParseError("não foi possível decodificar o arquivo OFX")


def _tag(text: str, name: str) -> str:
    match = re.search(rf"<{re.escape(name)}>\s*([^<\r\n]*)", text, re.IGNORECASE)
    return html.unescape(match.group(1).strip()) if match else ""


def _parse_date(raw_value: str) -> date:
    digits = raw_value[:8]
    if len(digits) != 8 or not digits.isdigit():
        raise ValueError("data OFX ausente ou inválida")
    parsed = datetime.strptime(digits, "%Y%m%d").date()
    if not 1990 <= parsed.year <= 2100:
        raise ValueError("data OFX fora do intervalo aceito (1990–2100)")
    return parsed


def parse_ofx(content: bytes, source_file: str) -> ParsedStatement:
    text = _decode_ofx(content)
    if "<OFX>" not in text.upper():
        raise StatementParseError("arquivo não contém uma estrutura OFX")

    bank_id = _tag(text, "BANKID")
    branch_id = _tag(text, "BRANCHID")
    account_id = _tag(text, "ACCTID")
    if not bank_id or not account_id:
        raise StatementParseError("OFX sem identificação bancária ou de conta")

    blocks = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", text, flags=re.IGNORECASE | re.DOTALL)
    if not blocks:
        raise StatementParseError("OFX sem movimentações STMTTRN")

    valid: list[ParsedTransaction] = []
    invalid: list[InvalidTransaction] = []
    for position, block in enumerate(blocks, start=1):
        payload = {
            key.upper(): html.unescape(value.strip())
            for key, value in re.findall(
                r"<([A-Z0-9_.-]+)>\s*([^<\r\n]*)", block, flags=re.IGNORECASE
            )
        }
        errors: list[str] = []
        raw_date = payload.get("DTPOSTED", "")
        raw_amount = payload.get("TRNAMT", "")
        name = payload.get("NAME", "")
        memo = payload.get("MEMO", "")
        description = memo or name

        try:
            parsed_date = _parse_date(raw_date)
        except ValueError as exc:
            errors.append(str(exc))
            parsed_date = None
        try:
            amount_cents = decimal_to_cents(raw_amount)
        except InvalidMoney as exc:
            errors.append(str(exc))
            amount_cents = None
        if not description.strip():
            errors.append("descrição OFX ausente")

        source_row = str(position)
        if errors:
            invalid.append(InvalidTransaction(source_row, tuple(errors), raw_payload=payload))
            continue

        assert parsed_date is not None and amount_cents is not None
        nature = TransactionNature.INCOME if amount_cents > 0 else TransactionNature.EXPENSE
        valid.append(
            ParsedTransaction(
                source_row=source_row,
                original_transaction_date=raw_date,
                transaction_date=parsed_date,
                original_amount=raw_amount,
                amount_cents=amount_cents,
                original_description=description,
                nature=nature,
                source_identifier=payload.get("FITID") or None,
                raw_payload=payload,
            )
        )

    currency = _tag(text, "CURDEF") or "BRL"
    raw_closing_balance = _tag(text, "BALAMT")
    try:
        closing_balance = decimal_to_cents(raw_closing_balance) if raw_closing_balance else None
    except InvalidMoney:
        closing_balance = None

    return ParsedStatement(
        source_format="ofx",
        source_file=source_file,
        account_label=None,
        institution_code=bank_id,
        institution_label=BANK_LABELS.get(bank_id, f"Banco {bank_id}"),
        source_account_fingerprint=account_fingerprint(bank_id, branch_id, account_id),
        currency=currency[:3].upper(),
        transactions=tuple(valid),
        invalid_transactions=tuple(invalid),
        closing_balance_cents=closing_balance,
    )
