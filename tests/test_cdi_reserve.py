from datetime import date
from decimal import Decimal

import pytest

from finance_analysis.cdi import build_bcb_url, load_cdi_rates, parse_bcb_payload
from finance_analysis.reserve import (
    ReserveAssumptions,
    build_reserve_daily,
    build_reserve_monthly,
    extract_reserve_events,
)


def assumptions(**changes: object) -> ReserveAssumptions:
    base = ReserveAssumptions(
        anchor_date=date(2026, 1, 31),
        anchor_balance_cents=1_000_000,
        yield_benchmark="CDI",
        yield_percentage=Decimal("100"),
        exclude_unrecorded_later_contributions=True,
        withdrawal_name="deporte",
    )
    return ReserveAssumptions(**{**base.__dict__, **changes})


def event(**changes: str) -> dict[str, str]:
    base = {
        "channel": "cofrinho_application",
        "amount_cents": "-100000",
        "operation_date": "2026-01-02",
        "analytical_transaction_id": "tx-1",
        "parent_transaction_id": "tx-1",
        "account_id": "itau_conta_corrente",
        "description_raw": "APLICACAO COFRINHOS",
        "source_file": "itau/example.ofx",
        "source_position": "1",
    }
    return {**base, **changes}


def test_bcb_payload_preserves_daily_decimal_rate():
    payload = b'[{"data":"02/01/2026","valor":"0.055131"}]'

    rows = parse_bcb_payload(payload)

    assert rows == [
        {
            "date": "2026-01-02",
            "daily_rate_percent": "0.055131",
            "source_series": "12",
        }
    ]


def test_bcb_url_uses_explicit_period():
    url = build_bcb_url(date(2026, 1, 1), date(2026, 1, 31))

    assert "bcdata.sgs.12" in url
    assert "dataInicial=01%2F01%2F2026" in url
    assert "dataFinal=31%2F01%2F2026" in url


def test_duplicate_cdi_date_is_rejected():
    rows = [
        {"date": "2026-01-02", "daily_rate_percent": "0.05"},
        {"date": "2026-01-02", "daily_rate_percent": "0.06"},
    ]

    with pytest.raises(ValueError, match="duplicada"):
        load_cdi_rates(rows)


def test_reserve_event_sign_is_inverted_from_current_account():
    rows = [
        event(),
        event(
            channel="cofrinho_redemption",
            amount_cents="40000",
            operation_date="2026-01-10",
            analytical_transaction_id="tx-2",
            parent_transaction_id="tx-2",
        ),
    ]

    result = extract_reserve_events(rows)

    assert [row["event_type"] for row in result] == ["contribution", "deporte"]
    assert [row["reserve_cashflow_cents"] for row in result] == [100000, -40000]


def test_reserve_reconstruction_hits_anchor_and_reconciles_every_day():
    events = extract_reserve_events([event()])
    rates = {date(2026, 1, day): Decimal("0.05") for day in range(1, 32)}

    result = build_reserve_daily(events, rates, assumptions())

    anchor = result[-1]
    assert anchor["closing_balance_cents"] == 1_000_000
    assert all(
        int(row["opening_balance_cents"])
        + int(row["estimated_interest_cents"])
        + int(row["net_cashflow_cents"])
        == int(row["closing_balance_cents"])
        for row in result
    )


def test_post_anchor_deporte_reduces_reserve():
    events = extract_reserve_events(
        [
            event(),
            event(
                channel="cofrinho_redemption",
                amount_cents="40000",
                operation_date="2026-02-01",
                analytical_transaction_id="tx-2",
                parent_transaction_id="tx-2",
            ),
        ]
    )
    rates = {date(2026, 1, day): Decimal("0") for day in range(1, 32)}

    result = build_reserve_daily(events, rates, assumptions())

    assert result[-1]["date"] == "2026-02-01"
    assert result[-1]["closing_balance_cents"] == 960000


def test_monthly_totals_reconcile_without_float():
    events = extract_reserve_events([event()])
    rates = {date(2026, 1, day): Decimal("0.05") for day in range(1, 32)}
    daily = build_reserve_daily(events, rates, assumptions())

    monthly = build_reserve_monthly(daily, assumptions())[0]

    assert monthly["opening_balance_cents"] + monthly["estimated_interest_cents"] + monthly[
        "net_contribution_cents"
    ] == monthly["closing_balance_cents"]
    assert isinstance(monthly["closing_balance_cents"], int)
