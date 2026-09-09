from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BCB_SERIES_ID = 12
BCB_ENDPOINT = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{BCB_SERIES_ID}/dados"


def build_bcb_url(start: date, end: date) -> str:
    if end < start:
        raise ValueError("A data final do CDI não pode anteceder a inicial")
    query = urlencode(
        {
            "formato": "json",
            "dataInicial": start.strftime("%d/%m/%Y"),
            "dataFinal": end.strftime("%d/%m/%Y"),
        }
    )
    return f"{BCB_ENDPOINT}?{query}"


def parse_bcb_payload(payload: bytes) -> list[dict[str, str]]:
    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, list):
        raise ValueError("Resposta inesperada da API SGS do Banco Central")

    result: list[dict[str, str]] = []
    seen_dates: set[date] = set()
    for item in decoded:
        try:
            rate_date = datetime.strptime(item["data"], "%d/%m/%Y").date()
            rate = Decimal(str(item["valor"]).replace(",", "."))
        except (KeyError, TypeError, ValueError, InvalidOperation) as error:
            raise ValueError("Taxa CDI inválida na resposta do Banco Central") from error
        if rate_date in seen_dates:
            raise ValueError(f"Taxa CDI duplicada em {rate_date.isoformat()}")
        if rate < 0:
            raise ValueError(f"Taxa CDI negativa em {rate_date.isoformat()}")
        seen_dates.add(rate_date)
        result.append(
            {
                "date": rate_date.isoformat(),
                "daily_rate_percent": format(rate, "f"),
                "source_series": str(BCB_SERIES_ID),
            }
        )
    return sorted(result, key=lambda row: row["date"])


def fetch_cdi_rates(start: date, end: date, timeout_seconds: int = 30) -> list[dict[str, str]]:
    request = Request(
        build_bcb_url(start, end),
        headers={"User-Agent": "financial-analysis-tool/0.1"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        payload = response.read()
    rows = parse_bcb_payload(payload)
    if not rows:
        raise ValueError("A API do Banco Central não retornou taxas CDI")
    return rows


def load_cdi_rates(rows: list[dict[str, str]]) -> dict[date, Decimal]:
    result: dict[date, Decimal] = {}
    for row in rows:
        rate_date = date.fromisoformat(row["date"])
        if rate_date in result:
            raise ValueError(f"Taxa CDI duplicada em {rate_date.isoformat()}")
        rate = Decimal(row["daily_rate_percent"])
        if rate < 0:
            raise ValueError(f"Taxa CDI negativa em {rate_date.isoformat()}")
        result[rate_date] = rate
    if not result:
        raise ValueError("Tabela CDI vazia")
    return result
