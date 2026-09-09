from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from finance_analysis.metrics import EXTERNAL_EXPENSE_NATURES, REFUND_NATURES

MODIFIED_Z_CONSTANT = Decimal("0.6745")
MODIFIED_Z_THRESHOLD = Decimal("3.5")
PEAK_RECURRENCES = {"non_recurring", "not_applicable"}


def _median(values: list[int | Decimal]) -> Decimal:
    return Decimal(str(median(values)))


def _score(value: int, center: Decimal, mad: Decimal) -> Decimal | None:
    if mad == 0:
        return Decimal("0") if Decimal(value) == center else None
    return MODIFIED_Z_CONSTANT * (Decimal(value) - center) / mad


def _event_members(
    events: list[dict[str, str]],
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    event_by_transaction: dict[str, str] = {}
    metadata: dict[str, dict[str, str]] = {}
    for row in events:
        event_by_transaction[row["transaction_id"]] = row["event_id"]
        metadata.setdefault(row["event_id"], row)
    return event_by_transaction, metadata


def build_peak_candidates(
    transactions: list[dict[str, str]],
    events: list[dict[str, str]],
) -> list[dict[str, str | int]]:
    event_by_transaction, event_metadata = _event_members(events)
    analytical_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in transactions:
        event_id = event_by_transaction.get(row["parent_transaction_id"])
        episode_id = (
            f"event:{event_id}"
            if event_id
            else f"transaction:{row['analytical_transaction_id']}"
        )
        analytical_groups[episode_id].append(row)

    episodes: list[dict[str, str | int]] = []
    for episode_id, rows in analytical_groups.items():
        eligible = [
            row
            for row in rows
            if row["peak_eligible"] == "true"
            and row["recurrence"] in PEAK_RECURRENCES
            and int(row["amount_cents"]) < 0
        ]
        if not eligible:
            continue
        relevant = [
            row
            for row in rows
            if row["nature"] in EXTERNAL_EXPENSE_NATURES | REFUND_NATURES
            or row["nature"] == "outflow_unclassified"
        ]
        net_spending = -sum(int(row["amount_cents"]) for row in relevant)
        if net_spending <= 0:
            continue
        categories = sorted({row["category"] for row in eligible})
        subcategories = sorted({row["subcategory"] for row in eligible})
        event_id = episode_id.removeprefix("event:") if episode_id.startswith("event:") else ""
        metadata = event_metadata.get(event_id, {})
        episodes.append(
            {
                "episode_id": episode_id,
                "start_date": min(row["operation_date"] for row in rows),
                "end_date": max(row["operation_date"] for row in rows),
                "episode_type": "linked_event" if event_id else "single_transaction",
                "label": metadata.get("event_label") or eligible[0]["counterparty_display"],
                "amount_cents": net_spending,
                "category": categories[0] if len(categories) == 1 else "Múltiplas",
                "subcategory": subcategories[0] if len(subcategories) == 1 else "Múltiplas",
                "classification_status": (
                    "unknown"
                    if any(row["nature"] == "outflow_unclassified" for row in eligible)
                    else "known"
                ),
                "transaction_count": len({row["parent_transaction_id"] for row in rows}),
            }
        )

    amounts = [int(row["amount_cents"]) for row in episodes]
    if not amounts:
        return []
    center = _median(amounts)
    mad = _median([abs(Decimal(value) - center) for value in amounts])
    result: list[dict[str, str | int]] = []
    for episode in episodes:
        score = _score(int(episode["amount_cents"]), center, mad)
        result.append(
            {
                **episode,
                "population_median_cents": _round_decimal(center),
                "population_mad_cents": _round_decimal(mad),
                "modified_z_score": (
                    ""
                    if score is None
                    else format(score.quantize(Decimal("0.0001")), "f")
                ),
                "threshold": format(MODIFIED_Z_THRESHOLD, "f"),
                "is_peak": str(score is not None and score > MODIFIED_Z_THRESHOLD).lower(),
            }
        )
    return sorted(
        result,
        key=lambda row: (-int(row["amount_cents"]), str(row["episode_id"])),
    )


def build_peaks_monthly(
    candidates: list[dict[str, str | int]],
    monthly_metrics: list[dict[str, str | int]],
) -> list[dict[str, str | int]]:
    peaks_by_month: dict[str, list[dict[str, str | int]]] = defaultdict(list)
    for row in candidates:
        if row["is_peak"] == "true":
            peaks_by_month[str(row["start_date"])[:7]].append(row)
    result: list[dict[str, str | int]] = []
    for metric in monthly_metrics:
        month = str(metric["month"])
        peaks = peaks_by_month[month]
        amounts = [int(row["amount_cents"]) for row in peaks]
        total = sum(amounts)
        result.append(
            {
                "month": month,
                "is_complete_month": metric["is_complete_month"],
                "account_coverage": metric["account_coverage"],
                "peak_count": len(peaks),
                "peak_total_cents": total,
                "average_peak_cents": _round_decimal(
                    Decimal(total) / Decimal(len(peaks)) if peaks else Decimal("0")
                ),
                "median_peak_cents": _round_decimal(_median(amounts)) if peaks else 0,
                "largest_peak_cents": max(amounts, default=0),
                "peak_share_of_gross_expense": (
                    ""
                    if int(metric["gross_external_expense_cents"]) == 0
                    else format(
                        (
                            Decimal(total)
                            / Decimal(int(metric["gross_external_expense_cents"]))
                        ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                        "f",
                    )
                ),
            }
        )
    return result


def build_peaks_summary(
    candidates: list[dict[str, str | int]],
    monthly: list[dict[str, str | int]],
) -> list[dict[str, str | int]]:
    peaks = [row for row in candidates if row["is_peak"] == "true"]
    amounts = [int(row["amount_cents"]) for row in peaks]
    complete_months = [row for row in monthly if row["is_complete_month"] == "true"]
    full_coverage_months = [
        row
        for row in complete_months
        if row["account_coverage"] == "all_available_accounts"
    ]
    full_coverage_keys = {str(row["month"]) for row in full_coverage_months}
    full_coverage_peaks = [
        row for row in peaks if str(row["start_date"])[:7] in full_coverage_keys
    ]
    total = sum(amounts)
    return [
        {
            "method": "upper_modified_z_score_on_non_recurring_amounts",
            "threshold": format(MODIFIED_Z_THRESHOLD, "f"),
            "candidate_count": len(candidates),
            "peak_count": len(peaks),
            "known_peak_count": sum(row["classification_status"] == "known" for row in peaks),
            "unknown_peak_count": sum(row["classification_status"] == "unknown" for row in peaks),
            "complete_month_count": len(complete_months),
            "peaks_per_complete_month": (
                format(
                    (Decimal(len(peaks)) / Decimal(len(complete_months))).quantize(
                        Decimal("0.0001"), rounding=ROUND_HALF_UP
                    ),
                    "f",
                )
                if complete_months
                else ""
            ),
            "full_coverage_complete_month_count": len(full_coverage_months),
            "full_coverage_peak_count": len(full_coverage_peaks),
            "peaks_per_full_coverage_month": (
                format(
                    (
                        Decimal(len(full_coverage_peaks))
                        / Decimal(len(full_coverage_months))
                    ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                    "f",
                )
                if full_coverage_months
                else ""
            ),
            "peak_total_cents": total,
            "average_peak_cents": _round_decimal(Decimal(total) / Decimal(len(peaks))),
            "median_peak_cents": _round_decimal(_median(amounts)),
            "largest_peak_cents": max(amounts),
            "smallest_peak_cents": min(amounts),
        }
    ]


def _round_decimal(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
