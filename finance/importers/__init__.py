from pathlib import Path

from finance.importers.canonical_csv import parse_canonical_csv
from finance.importers.ofx import parse_ofx
from finance.importers.types import ParsedStatement, StatementParseError


def parse_statement(content: bytes, source_file: str) -> ParsedStatement:
    suffix = Path(source_file).suffix.lower()
    if suffix == ".ofx":
        return parse_ofx(content, source_file)
    if suffix == ".csv":
        return parse_canonical_csv(content, source_file)
    raise StatementParseError("formato não suportado; use .ofx ou .csv")


__all__ = ["ParsedStatement", "StatementParseError", "parse_statement"]
