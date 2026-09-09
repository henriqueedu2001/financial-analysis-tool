from __future__ import annotations

import hashlib
import html
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from finance_analysis.models import ParsedStatement, ParsedTransaction

_FIELD_TEMPLATE = r"<(?:\w+:)?{name}>\s*([^<\r\n]*)"
_TRANSACTION_BLOCK = re.compile(
    r"<(?:\w+:)?STMTTRN(?:\s[^>]*)?>(.*?)(?:</(?:\w+:)?STMTTRN>|(?=<(?:\w+:)?STMTTRN(?:\s|>))|(?=</(?:\w+:)?BANKTRANLIST>))",
    re.IGNORECASE | re.DOTALL,
)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def decode_ofx(content: bytes) -> str:
    header = content[:2048].decode("ascii", errors="ignore").upper()
    encoding_match = re.search(r"(?:ENCODING|CHARSET):\s*([^\r\n]+)", header)
    declared = encoding_match.group(1).strip() if encoding_match else ""
    encodings = ["utf-8", "cp1252"] if "UTF-8" in declared else ["cp1252", "utf-8"]
    for encoding in encodings:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("OFX não pôde ser decodificado como UTF-8 ou Windows-1252")


def field(text: str, name: str) -> str:
    match = re.search(_FIELD_TEMPLATE.format(name=re.escape(name)), text, re.IGNORECASE)
    if not match:
        return ""
    return html.unescape(match.group(1).strip())


def parse_ofx_date(value: str) -> date:
    digits = re.match(r"\s*(\d{8})", value)
    if not digits:
        raise ValueError(f"Data OFX inválida: {value!r}")
    compact = digits.group(1)
    return date(int(compact[:4]), int(compact[4:6]), int(compact[6:8]))


def money_to_cents(value: str) -> int:
    try:
        amount = Decimal(value.strip().replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"Valor OFX inválido: {value!r}") from exc
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"Valor monetário possui fração de centavo: {value!r}")
    return int(cents)


def account_fingerprint(bank_id: str, account_id: str) -> str:
    if not account_id:
        raise ValueError("OFX sem ACCTID")
    material = f"{bank_id}\0{account_id}".encode()
    return hashlib.sha256(material).hexdigest()


def parse_statement(content: bytes) -> ParsedStatement:
    text = decode_ofx(content)
    bank_id = field(text, "BANKID")
    account_id = field(text, "ACCTID")
    transactions: list[ParsedTransaction] = []

    for index, match in enumerate(_TRANSACTION_BLOCK.finditer(text), start=1):
        block = match.group(1)
        posted_raw = field(block, "DTPOSTED")
        amount_raw = field(block, "TRNAMT")
        if not posted_raw or not amount_raw:
            raise ValueError(f"STMTTRN {index} sem DTPOSTED ou TRNAMT")
        name_raw = field(block, "NAME")
        memo_raw = field(block, "MEMO")
        parts = [part for part in (name_raw, memo_raw) if part]
        if len(parts) == 2 and parts[0].casefold() == parts[1].casefold():
            parts.pop()
        transactions.append(
            ParsedTransaction(
                transaction_date=parse_ofx_date(posted_raw),
                amount_cents=money_to_cents(amount_raw),
                transaction_type=field(block, "TRNTYPE").upper(),
                bank_transaction_id=field(block, "FITID"),
                name_raw=name_raw,
                memo_raw=memo_raw,
                description_raw=" | ".join(parts),
            )
        )

    if not transactions:
        raise ValueError("OFX sem movimentações STMTTRN")

    balance_raw = field(text, "BALAMT")
    balance_date_raw = field(text, "DTASOF")
    return ParsedStatement(
        bank_id=bank_id,
        account_fingerprint=account_fingerprint(bank_id, account_id),
        ofx_start_raw=field(text, "DTSTART"),
        ofx_end_raw=field(text, "DTEND"),
        balance_date=parse_ofx_date(balance_date_raw) if balance_date_raw else None,
        balance_cents=money_to_cents(balance_raw) if balance_raw else None,
        transactions=tuple(transactions),
    )
