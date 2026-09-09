from __future__ import annotations

import calendar
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from finance_analysis.daily import date_range

CONTRIBUTION_CHANNEL = "cofrinho_application"
DEPORT_CHANNEL = "cofrinho_redemption"


@dataclass(frozen=True)
class ReserveAssumptions:
    anchor_date: date
    anchor_balance_cents: int
    yield_benchmark: str
    yield_percentage: Decimal
    exclude_unrecorded_later_contributions: bool
    withdrawal_name: str


def load_reserve_assumptions(path: Path) -> ReserveAssumptions:
    with path.open("rb") as stream:
        values = tomllib.load(stream)["cofrinho"]
    anchor_date = values["anchor_date"]
    if not isinstance(anchor_date, date):
        anchor_date = date.fromisoformat(str(anchor_date))
    assumptions = ReserveAssumptions(
        anchor_date=anchor_date,
        anchor_balance_cents=int(values["anchor_balance_cents"]),
        yield_benchmark=str(values["yield_benchmark"]),
        yield_percentage=Decimal(str(values["yield_percentage"])),
        exclude_unrecorded_later_contributions=bool(
            values["exclude_unrecorded_later_contributions"]
        ),
        withdrawal_name=str(values["withdrawal_name"]),
    )
    if assumptions.anchor_balance_cents < 0:
        raise ValueError("O saldo-âncora do cofrinho não pode ser negativo")
    if assumptions.yield_benchmark != "CDI":
        raise ValueError("Apenas o benchmark CDI é suportado nesta fase")
    if assumptions.yield_percentage < 0:
        raise ValueError("O percentual do CDI não pode ser negativo")
    return assumptions


def extract_reserve_events(rows: list[dict[str, str]]) -> list[dict[str, str | int]]:
    result: list[dict[str, str | int]] = []
    for row in rows:
        channel = row["channel"]
        if channel not in {CONTRIBUTION_CHANNEL, DEPORT_CHANNEL}:
            continue
        amount = int(row["amount_cents"])
        if channel == CONTRIBUTION_CHANNEL and amount >= 0:
            raise ValueError("Aplicação no cofrinho deveria sair da conta corrente")
        if channel == DEPORT_CHANNEL and amount <= 0:
            raise ValueError("Deporte deveria entrar na conta corrente")
        event_type = "contribution" if channel == CONTRIBUTION_CHANNEL else "deporte"
        magnitude = abs(amount)
        result.append(
            {
                "date": row["operation_date"],
                "analytical_transaction_id": row["analytical_transaction_id"],
                "parent_transaction_id": row["parent_transaction_id"],
                "event_type": event_type,
                "amount_cents": magnitude,
                "reserve_cashflow_cents": magnitude if event_type == "contribution" else -magnitude,
                "account_id": row["account_id"],
                "description_raw": row["description_raw"],
                "source_file": row["source_file"],
                "source_position": row["source_position"],
            }
        )
    return sorted(
        result,
        key=lambda row: (
            str(row["date"]),
            str(row["analytical_transaction_id"]),
        ),
    )


def _round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _effective_rate(rate: Decimal, percentage: Decimal) -> Decimal:
    return rate * percentage / Decimal("100")


def _daily_interest(opening_cents: int, daily_rate_percent: Decimal) -> int:
    return _round_cents(Decimal(opening_cents) * daily_rate_percent / Decimal("100"))


def build_reserve_daily(
    events: list[dict[str, str | int]],
    cdi_rates: dict[date, Decimal],
    assumptions: ReserveAssumptions,
) -> list[dict[str, str | int]]:
    if not events:
        raise ValueError("Não há aportes ou deportes do cofrinho")
    event_dates = [date.fromisoformat(str(row["date"])) for row in events]
    first_event = min(event_dates)
    last_event = max(event_dates)
    start = first_event.replace(day=1)
    end = max(assumptions.anchor_date, last_event)
    if assumptions.anchor_date < start:
        raise ValueError("O saldo-âncora antecede os movimentos do cofrinho")

    cashflow_by_date: dict[date, int] = defaultdict(int)
    contribution_by_date: dict[date, int] = defaultdict(int)
    deporte_by_date: dict[date, int] = defaultdict(int)
    for event in events:
        event_date = date.fromisoformat(str(event["date"]))
        cashflow = int(event["reserve_cashflow_cents"])
        cashflow_by_date[event_date] += cashflow
        if event["event_type"] == "contribution":
            contribution_by_date[event_date] += int(event["amount_cents"])
        else:
            deporte_by_date[event_date] += int(event["amount_cents"])

    effective_rates = {
        rate_date: _effective_rate(rate, assumptions.yield_percentage)
        for rate_date, rate in cdi_rates.items()
    }
    missing_rate_days = [
        current
        for current in date_range(start, end)
        if current.weekday() < 5 and current not in effective_rates
    ]
    if len(missing_rate_days) > 25:
        raise ValueError("Cobertura CDI insuficiente para reconstruir o cofrinho")

    backward: dict[date, dict[str, str | int]] = {}
    closing = assumptions.anchor_balance_cents
    for current in reversed(list(date_range(start, assumptions.anchor_date))):
        cashflow = cashflow_by_date[current]
        rate = effective_rates.get(current, Decimal("0"))
        factor = Decimal("1") + rate / Decimal("100")
        opening = _round_cents(Decimal(closing - cashflow) / factor)
        interest = closing - opening - cashflow
        backward[current] = _daily_row(
            current,
            opening,
            rate,
            interest,
            contribution_by_date[current],
            deporte_by_date[current],
            closing,
            assumptions,
        )
        closing = opening

    result = [backward[current] for current in date_range(start, assumptions.anchor_date)]
    closing = assumptions.anchor_balance_cents
    for current in date_range(assumptions.anchor_date + timedelta(days=1), end):
        opening = closing
        rate = effective_rates.get(current, Decimal("0"))
        interest = _daily_interest(opening, rate)
        closing = opening + interest + cashflow_by_date[current]
        result.append(
            _daily_row(
                current,
                opening,
                rate,
                interest,
                contribution_by_date[current],
                deporte_by_date[current],
                closing,
                assumptions,
            )
        )
    return result


def _daily_row(
    current: date,
    opening: int,
    rate: Decimal,
    interest: int,
    contribution: int,
    deporte: int,
    closing: int,
    assumptions: ReserveAssumptions,
) -> dict[str, str | int]:
    return {
        "date": current.isoformat(),
        "opening_balance_cents": opening,
        "cdi_daily_rate_percent": format(rate, "f") if rate else "",
        "estimated_interest_cents": interest,
        "contribution_cents": contribution,
        "deporte_cents": deporte,
        "net_cashflow_cents": contribution - deporte,
        "closing_balance_cents": closing,
        "is_anchor_date": str(current == assumptions.anchor_date).lower(),
        "estimation_method": (
            "backward_from_anchor"
            if current <= assumptions.anchor_date
            else "forward_from_anchor"
        ),
    }


def build_reserve_monthly(
    daily_rows: list[dict[str, str | int]],
    assumptions: ReserveAssumptions,
) -> list[dict[str, str | int]]:
    grouped: dict[str, list[dict[str, str | int]]] = defaultdict(list)
    for row in daily_rows:
        grouped[str(row["date"])[:7]].append(row)
    model_end = date.fromisoformat(str(daily_rows[-1]["date"]))
    result: list[dict[str, str | int]] = []
    for month, rows in sorted(grouped.items()):
        year, month_number = map(int, month.split("-"))
        month_end = date(year, month_number, calendar.monthrange(year, month_number)[1])
        result.append(
            {
                "month": month,
                "opening_balance_cents": int(rows[0]["opening_balance_cents"]),
                "contribution_cents": sum(int(row["contribution_cents"]) for row in rows),
                "deporte_cents": sum(int(row["deporte_cents"]) for row in rows),
                "net_contribution_cents": sum(int(row["net_cashflow_cents"]) for row in rows),
                "estimated_interest_cents": sum(
                    int(row["estimated_interest_cents"]) for row in rows
                ),
                "closing_balance_cents": int(rows[-1]["closing_balance_cents"]),
                "is_complete_month": str(month_end <= model_end).lower(),
                "is_anchor_month": str(month == assumptions.anchor_date.strftime("%Y-%m")).lower(),
            }
        )
    return result


def build_reserve_quality(
    daily_rows: list[dict[str, str | int]],
    events: list[dict[str, str | int]],
    cdi_rates: dict[date, Decimal],
    assumptions: ReserveAssumptions,
) -> list[dict[str, str | int]]:
    anchor = next(row for row in daily_rows if row["is_anchor_date"] == "true")
    daily_reconciliation_errors = [
        row
        for row in daily_rows
        if int(row["opening_balance_cents"])
        + int(row["estimated_interest_cents"])
        + int(row["net_cashflow_cents"])
        != int(row["closing_balance_cents"])
    ]
    return [
        {
            "check_type": "anchor_balance",
            "status": (
                "balanced"
                if int(anchor["closing_balance_cents"]) == assumptions.anchor_balance_cents
                else "mismatch"
            ),
            "observed_value": anchor["closing_balance_cents"],
            "expected_value": assumptions.anchor_balance_cents,
            "details": assumptions.anchor_date.isoformat(),
        },
        {
            "check_type": "daily_roll_forward",
            "status": "balanced" if not daily_reconciliation_errors else "mismatch",
            "observed_value": len(daily_reconciliation_errors),
            "expected_value": 0,
            "details": f"{len(daily_rows)} dias reconstruídos",
        },
        {
            "check_type": "recorded_events",
            "status": "ok",
            "observed_value": len(events),
            "expected_value": len(events),
            "details": (
                f"{sum(row['event_type'] == 'contribution' for row in events)} aportes; "
                f"{sum(row['event_type'] == 'deporte' for row in events)} deportes"
            ),
        },
        {
            "check_type": "cdi_rates",
            "status": "ok",
            "observed_value": len(cdi_rates),
            "expected_value": len(cdi_rates),
            "details": (
                f"SGS 12; {min(cdi_rates).isoformat()} a {max(cdi_rates).isoformat()}"
            ),
        },
        {
            "check_type": "unrecorded_post_anchor_contributions",
            "status": (
                "excluded"
                if assumptions.exclude_unrecorded_later_contributions
                else "included"
            ),
            "observed_value": 0,
            "expected_value": 0,
            "details": "Aportes posteriores não presentes nos extratos não foram estimados",
        },
    ]
