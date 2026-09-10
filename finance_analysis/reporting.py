from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from finance_analysis.classification import read_csv

MONTHS_PT = (
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
)

EXPECTED_CHARTS = (
    "01_saldos_diarios",
    "02_receitas_gastos_diarios",
    "03_resultado_mensal",
    "04_custo_de_vida_mensal",
    "05_cofrinho",
    "06_indice_sobrevivencia",
    "07_gastos_por_categoria",
    "08_picos_de_gasto",
)

QUALITY_LABELS = {
    "category_expense_reconciliation": "Categorias e despesas",
    "living_cost_partition": "Partição do custo de vida",
    "savings_identity": "Identidade da poupança",
    "anchor_balance": "Âncora do cofrinho",
    "daily_roll_forward": "Reconstrução diária",
    "recorded_events": "Eventos do cofrinho",
    "cdi_rates": "Cobertura do CDI",
    "unrecorded_post_anchor_contributions": "Aportes ausentes",
}


@dataclass(frozen=True)
class ReportData:
    transactions: list[dict[str, str]]
    monthly_metrics: list[dict[str, str]]
    monthly_categories: list[dict[str, str]]
    metrics_summary: list[dict[str, str]]
    peak_candidates: list[dict[str, str]]
    peaks_summary: list[dict[str, str]]
    metrics_quality: list[dict[str, str]]
    reserve_monthly: list[dict[str, str]]
    reserve_quality: list[dict[str, str]]


@dataclass(frozen=True)
class ReportSummary:
    first_month: str
    last_month: str
    last_complete_month: str
    comparable_months: int
    average_living_cost_cents: int
    median_living_cost_cents: int
    standard_deviation_living_cost_cents: int
    minimum_living_cost_cents: int
    minimum_living_cost_month: str
    maximum_living_cost_cents: int
    maximum_living_cost_month: str
    living_cost_cv: Decimal
    latest_living_cost_cents: int
    latest_reserve_cents: int
    latest_survival_months: Decimal
    median_survival_months: Decimal
    conservative_survival_months: Decimal
    total_income_cents: int
    total_gross_expense_cents: int
    total_net_expense_cents: int
    total_savings_cents: int
    positive_savings_months: int
    worst_savings_month: str
    worst_savings_cents: int
    worst_month_gross_expense_cents: int
    worst_month_atypical_expense_cents: int
    savings_without_worst_month_cents: int
    reserve_opening_cents: int
    reserve_closing_cents: int
    reserve_interest_cents: int
    reserve_contribution_cents: int
    deportes_cents: int
    net_reserve_contribution_cents: int
    unknown_transactions: int
    transaction_count: int
    unknown_outflows: int
    outflow_count: int
    comparable_unknown_outflow_count: int
    comparable_outflow_count: int
    comparable_unknown_outflow_cents: int
    comparable_observed_outflow_cents: int
    peak_count: int
    comparable_peak_count: int
    peak_total_cents: int
    average_peak_cents: int
    median_peak_cents: int
    largest_peak_cents: int
    smallest_peak_cents: int
    unknown_peak_count: int
    top_categories: tuple[tuple[str, int], ...]
    top_peaks: tuple[tuple[str, str, str, int], ...]


def load_report_data(input_dir: Path) -> ReportData:
    return ReportData(
        transactions=read_csv(input_dir / "transactions_dated.csv"),
        monthly_metrics=read_csv(input_dir / "monthly_metrics.csv"),
        monthly_categories=read_csv(input_dir / "monthly_category_spending.csv"),
        metrics_summary=read_csv(input_dir / "metrics_summary.csv"),
        peak_candidates=read_csv(input_dir / "spending_peak_candidates.csv"),
        peaks_summary=read_csv(input_dir / "spending_peaks_summary.csv"),
        metrics_quality=read_csv(input_dir / "metrics_quality.csv"),
        reserve_monthly=read_csv(input_dir / "cofrinho_monthly.csv"),
        reserve_quality=read_csv(input_dir / "cofrinho_quality.csv"),
    )


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def _median_decimal(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def calculate_report_summary(data: ReportData) -> ReportSummary:
    if not data.metrics_summary or not data.peaks_summary:
        raise ValueError("Resumos de métricas e picos são obrigatórios")
    comparable = [
        row
        for row in data.monthly_metrics
        if row["is_complete_month"] == "true"
        and row["account_coverage"] == "all_available_accounts"
    ]
    if not comparable:
        raise ValueError("Não há meses completos com cobertura de todas as contas")
    comparable_month_keys = {row["month"] for row in comparable}
    metric_summary = data.metrics_summary[0]
    peak_summary = data.peaks_summary[0]
    worst_month = min(comparable, key=lambda row: int(row["savings_cents"]))

    living_cost_rows = [
        (row["month"], int(row["recurring_living_cost_cents"])) for row in comparable
    ]
    minimum_living_cost_month, minimum_living_cost = min(
        living_cost_rows, key=lambda item: item[1]
    )
    maximum_living_cost_month, maximum_living_cost = max(
        living_cost_rows, key=lambda item: item[1]
    )

    unknown_transactions = [
        row
        for row in data.transactions
        if row["nature"] in {"inflow_unclassified", "outflow_unclassified"}
    ]
    outflows = [row for row in data.transactions if int(row["amount_cents"]) < 0]
    unknown_outflows = [
        row for row in outflows if row["nature"] == "outflow_unclassified"
    ]
    comparable_outflows = [
        row for row in outflows if row["operation_date"][:7] in comparable_month_keys
    ]
    comparable_unknown_outflows = [
        row for row in comparable_outflows if row["nature"] == "outflow_unclassified"
    ]

    category_totals: dict[str, int] = {}
    comparable_observed = 0
    comparable_unknown = 0
    for row in data.monthly_categories:
        if row["month"] not in comparable_month_keys:
            continue
        amount = int(row["total_observed_outflow_cents"])
        category_totals[row["category"]] = category_totals.get(row["category"], 0) + amount
        comparable_observed += amount
        comparable_unknown += int(row["unclassified_outflow_cents"])

    peaks = [row for row in data.peak_candidates if row["is_peak"] == "true"]
    comparable_peaks = [row for row in peaks if row["start_date"][:7] in comparable_month_keys]
    top_peaks = tuple(
        (
            row["start_date"],
            row["label"],
            row["category"],
            int(row["amount_cents"]),
        )
        for row in sorted(peaks, key=lambda row: -int(row["amount_cents"]))[:5]
    )

    reserve_comparable = [
        row
        for row in data.reserve_monthly
        if row["month"] in comparable_month_keys and row["is_complete_month"] == "true"
    ]
    reserve_comparable.sort(key=lambda row: row["month"])
    if not reserve_comparable:
        raise ValueError("Não há meses completos do cofrinho no período comparável")
    survivals = [
        Decimal(row["survival_index_months"])
        for row in comparable
        if row["survival_index_months"]
    ]
    latest_reserve = int(metric_summary["last_complete_reserve_balance_cents"])
    return ReportSummary(
        first_month=metric_summary["analysis_start_month"],
        last_month=metric_summary["analysis_end_month"],
        last_complete_month=metric_summary["last_complete_month"],
        comparable_months=len(comparable),
        average_living_cost_cents=int(metric_summary["average_recurring_living_cost_cents"]),
        median_living_cost_cents=int(metric_summary["median_recurring_living_cost_cents"]),
        standard_deviation_living_cost_cents=int(
            metric_summary["standard_deviation_living_cost_cents"]
        ),
        minimum_living_cost_cents=minimum_living_cost,
        minimum_living_cost_month=minimum_living_cost_month,
        maximum_living_cost_cents=maximum_living_cost,
        maximum_living_cost_month=maximum_living_cost_month,
        living_cost_cv=Decimal(metric_summary["coefficient_of_variation"]),
        latest_living_cost_cents=int(metric_summary["last_complete_recurring_living_cost_cents"]),
        latest_reserve_cents=latest_reserve,
        latest_survival_months=Decimal(metric_summary["last_complete_survival_index_months"]),
        median_survival_months=_median_decimal(survivals),
        conservative_survival_months=_ratio(latest_reserve, maximum_living_cost),
        total_income_cents=sum(int(row["external_income_cents"]) for row in comparable),
        total_gross_expense_cents=sum(
            int(row["gross_external_expense_cents"]) for row in comparable
        ),
        total_net_expense_cents=sum(
            int(row["net_external_expense_cents"]) for row in comparable
        ),
        total_savings_cents=sum(int(row["savings_cents"]) for row in comparable),
        positive_savings_months=sum(int(row["savings_cents"]) > 0 for row in comparable),
        worst_savings_month=worst_month["month"],
        worst_savings_cents=int(worst_month["savings_cents"]),
        worst_month_gross_expense_cents=int(worst_month["gross_external_expense_cents"]),
        worst_month_atypical_expense_cents=int(worst_month["atypical_expense_cents"]),
        savings_without_worst_month_cents=sum(
            int(row["savings_cents"])
            for row in comparable
            if row["month"] != worst_month["month"]
        ),
        reserve_opening_cents=int(reserve_comparable[0]["opening_balance_cents"]),
        reserve_closing_cents=int(reserve_comparable[-1]["closing_balance_cents"]),
        reserve_interest_cents=sum(
            int(row["estimated_interest_cents"]) for row in reserve_comparable
        ),
        reserve_contribution_cents=sum(
            int(row["reserve_contribution_cents"]) for row in comparable
        ),
        deportes_cents=sum(int(row["deporte_cents"]) for row in comparable),
        net_reserve_contribution_cents=sum(
            int(row["net_reserve_contribution_cents"]) for row in comparable
        ),
        unknown_transactions=len(unknown_transactions),
        transaction_count=len(data.transactions),
        unknown_outflows=len(unknown_outflows),
        outflow_count=len(outflows),
        comparable_unknown_outflow_count=len(comparable_unknown_outflows),
        comparable_outflow_count=len(comparable_outflows),
        comparable_unknown_outflow_cents=comparable_unknown,
        comparable_observed_outflow_cents=comparable_observed,
        peak_count=int(peak_summary["peak_count"]),
        comparable_peak_count=len(comparable_peaks),
        peak_total_cents=int(peak_summary["peak_total_cents"]),
        average_peak_cents=int(peak_summary["average_peak_cents"]),
        median_peak_cents=int(peak_summary["median_peak_cents"]),
        largest_peak_cents=int(peak_summary["largest_peak_cents"]),
        smallest_peak_cents=int(peak_summary["smallest_peak_cents"]),
        unknown_peak_count=int(peak_summary["unknown_peak_count"]),
        top_categories=tuple(sorted(category_totals.items(), key=lambda item: -item[1])[:6]),
        top_peaks=top_peaks,
    )


def format_brl(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    value = abs(Decimal(cents) / Decimal("100"))
    text = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{sign}R$ {text}"


def format_percent(value: Decimal) -> str:
    return f"{value * Decimal('100'):.1f}%".replace(".", ",")


def format_decimal(value: Decimal, places: int = 2) -> str:
    return f"{value:.{places}f}".replace(".", ",")


def format_month(month: str) -> str:
    year, month_number = map(int, month.split("-"))
    return f"{MONTHS_PT[month_number - 1]}/{year}"


def latex_escape(value: str) -> str:
    translations = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(translations.get(character, character) for character in value)


def _quality_rows(data: ReportData) -> str:
    rows: list[str] = []
    for row in data.metrics_quality + data.reserve_quality:
        rows.append(
            "{} & {} & {} \\\\".format(
                latex_escape(QUALITY_LABELS.get(row["check_type"], row["check_type"])),
                latex_escape(row["status"]),
                latex_escape(row["details"]),
            )
        )
    return "\n".join(rows)


def _category_rows(summary: ReportSummary) -> str:
    return "\n".join(
        f"{position} & {latex_escape(category)} & {latex_escape(format_brl(amount))} \\\\"
        for position, (category, amount) in enumerate(summary.top_categories, start=1)
    )


def _peak_rows(summary: ReportSummary) -> str:
    return "\n".join(
        "{} & {} & {} & {} \\\\".format(
            latex_escape(peak_date[8:10] + "/" + peak_date[5:7] + "/" + peak_date[:4]),
            latex_escape(label),
            latex_escape(category),
            latex_escape(format_brl(amount)),
        )
        for peak_date, label, category, amount in summary.top_peaks
    )


def load_chart_manifest(figures_dir: Path) -> dict[str, dict[str, object]]:
    manifest_path = figures_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifesto de gráficos ausente: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    charts = {str(item["id"]): item for item in manifest}
    if tuple(charts) != EXPECTED_CHARTS:
        raise ValueError("O manifesto não contém os oito gráficos esperados, na ordem correta")
    for chart in charts.values():
        path = figures_dir / str(chart["file"])
        if not path.is_file():
            raise FileNotFoundError(f"Gráfico ausente: {path}")
    return charts


def _chart_path(chart: dict[str, object], figures_dir: Path) -> str:
    return latex_escape(str((figures_dir / str(chart["file"])).resolve()))


def _replace_placeholders(template: str, replacements: dict[str, str]) -> str:
    result = template
    for key, value in replacements.items():
        result = result.replace(f"@@{key}@@", value)
    unresolved = sorted(set(re.findall(r"@@[A-Z0-9_]+@@", result)))
    if unresolved:
        raise ValueError(f"Placeholders LaTeX sem valor: {', '.join(unresolved)}")
    return result


def render_latex(
    data: ReportData,
    figures_dir: Path,
    template_path: Path,
) -> tuple[str, ReportSummary]:
    summary = calculate_report_summary(data)
    charts = load_chart_manifest(figures_dir)
    top_two = sum(amount for _, amount in summary.top_categories[:2])
    replacements = {
        "PERIOD": latex_escape(
            f"{format_month(summary.first_month)} a {format_month(summary.last_month)}"
        ),
        "LAST_COMPLETE_MONTH": latex_escape(format_month(summary.last_complete_month)),
        "COMPARABLE_MONTHS": str(summary.comparable_months),
        "LATEST_RESERVE": latex_escape(format_brl(summary.latest_reserve_cents)),
        "LATEST_SURVIVAL": format_decimal(summary.latest_survival_months),
        "LATEST_LIVING_COST": latex_escape(format_brl(summary.latest_living_cost_cents)),
        "AVERAGE_LIVING_COST": latex_escape(format_brl(summary.average_living_cost_cents)),
        "MEDIAN_LIVING_COST": latex_escape(format_brl(summary.median_living_cost_cents)),
        "STD_LIVING_COST": latex_escape(
            format_brl(summary.standard_deviation_living_cost_cents)
        ),
        "CV_LIVING_COST": latex_escape(format_percent(summary.living_cost_cv)),
        "MIN_LIVING_COST": latex_escape(format_brl(summary.minimum_living_cost_cents)),
        "MIN_LIVING_COST_MONTH": latex_escape(format_month(summary.minimum_living_cost_month)),
        "MAX_LIVING_COST": latex_escape(format_brl(summary.maximum_living_cost_cents)),
        "MAX_LIVING_COST_MONTH": latex_escape(format_month(summary.maximum_living_cost_month)),
        "CONSERVATIVE_SURVIVAL": format_decimal(summary.conservative_survival_months),
        "MEDIAN_SURVIVAL": format_decimal(summary.median_survival_months),
        "TOTAL_INCOME": latex_escape(format_brl(summary.total_income_cents)),
        "TOTAL_GROSS_EXPENSE": latex_escape(format_brl(summary.total_gross_expense_cents)),
        "TOTAL_NET_EXPENSE": latex_escape(format_brl(summary.total_net_expense_cents)),
        "TOTAL_SAVINGS": latex_escape(format_brl(summary.total_savings_cents)),
        "POSITIVE_SAVINGS_MONTHS": str(summary.positive_savings_months),
        "WORST_SAVINGS_MONTH": latex_escape(format_month(summary.worst_savings_month)),
        "WORST_SAVINGS": latex_escape(format_brl(summary.worst_savings_cents)),
        "WORST_MONTH_GROSS_EXPENSE": latex_escape(
            format_brl(summary.worst_month_gross_expense_cents)
        ),
        "WORST_MONTH_ATYPICAL_EXPENSE": latex_escape(
            format_brl(summary.worst_month_atypical_expense_cents)
        ),
        "SAVINGS_WITHOUT_WORST_MONTH": latex_escape(
            format_brl(summary.savings_without_worst_month_cents)
        ),
        "RESERVE_OPENING": latex_escape(format_brl(summary.reserve_opening_cents)),
        "RESERVE_CLOSING": latex_escape(format_brl(summary.reserve_closing_cents)),
        "RESERVE_INTEREST": latex_escape(format_brl(summary.reserve_interest_cents)),
        "RESERVE_CONTRIBUTION": latex_escape(format_brl(summary.reserve_contribution_cents)),
        "DEPORTES": latex_escape(format_brl(summary.deportes_cents)),
        "NET_RESERVE_CONTRIBUTION": latex_escape(
            format_brl(summary.net_reserve_contribution_cents)
        ),
        "UNKNOWN_TRANSACTIONS": str(summary.unknown_transactions),
        "TRANSACTION_COUNT": str(summary.transaction_count),
        "UNKNOWN_TRANSACTION_PERCENT": latex_escape(
            format_percent(_ratio(summary.unknown_transactions, summary.transaction_count))
        ),
        "UNKNOWN_OUTFLOWS": str(summary.unknown_outflows),
        "OUTFLOW_COUNT": str(summary.outflow_count),
        "UNKNOWN_OUTFLOW_PERCENT": latex_escape(
            format_percent(_ratio(summary.unknown_outflows, summary.outflow_count))
        ),
        "COMPARABLE_UNKNOWN_OUTFLOW_COUNT": str(summary.comparable_unknown_outflow_count),
        "COMPARABLE_OUTFLOW_COUNT": str(summary.comparable_outflow_count),
        "COMPARABLE_UNKNOWN_OUTFLOW_COUNT_PERCENT": latex_escape(
            format_percent(
                _ratio(summary.comparable_unknown_outflow_count, summary.comparable_outflow_count)
            )
        ),
        "COMPARABLE_UNKNOWN_OUTFLOW": latex_escape(
            format_brl(summary.comparable_unknown_outflow_cents)
        ),
        "COMPARABLE_UNKNOWN_OUTFLOW_PERCENT": latex_escape(
            format_percent(
                _ratio(
                    summary.comparable_unknown_outflow_cents,
                    summary.comparable_observed_outflow_cents,
                )
            )
        ),
        "PEAK_COUNT": str(summary.peak_count),
        "COMPARABLE_PEAK_COUNT": str(summary.comparable_peak_count),
        "PEAK_TOTAL": latex_escape(format_brl(summary.peak_total_cents)),
        "AVERAGE_PEAK": latex_escape(format_brl(summary.average_peak_cents)),
        "MEDIAN_PEAK": latex_escape(format_brl(summary.median_peak_cents)),
        "LARGEST_PEAK": latex_escape(format_brl(summary.largest_peak_cents)),
        "SMALLEST_PEAK": latex_escape(format_brl(summary.smallest_peak_cents)),
        "UNKNOWN_PEAK_COUNT": str(summary.unknown_peak_count),
        "TOP_TWO_CATEGORIES": latex_escape(format_brl(top_two)),
        "TOP_TWO_CATEGORIES_PERCENT": latex_escape(
            format_percent(_ratio(top_two, summary.comparable_observed_outflow_cents))
        ),
        "QUALITY_ROWS": _quality_rows(data),
        "CATEGORY_ROWS": _category_rows(summary),
        "PEAK_ROWS": _peak_rows(summary),
    }
    for chart_id, chart in charts.items():
        key = chart_id.upper()
        replacements[f"CHART_{key}"] = _chart_path(chart, figures_dir)
        replacements[f"CHART_{key}_PERIOD"] = latex_escape(str(chart["period"]))
        replacements[f"CHART_{key}_DESCRIPTION"] = latex_escape(str(chart["description"]))

    template = template_path.read_text(encoding="utf-8")
    return _replace_placeholders(template, replacements), summary


def write_latex(source: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=output_path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(source)
    try:
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)


def resolve_tectonic(explicit_path: Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit_path is not None:
        candidates.append(explicit_path)
    configured = os.environ.get("TECTONIC_BIN")
    if configured:
        candidates.append(Path(configured))
    in_path = shutil.which("tectonic")
    if in_path:
        candidates.append(Path(in_path))
    candidates.append(Path.home() / "Projects/flike-tcc/.tools/tectonic-0.17.0/tectonic")
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise FileNotFoundError(
        "Tectonic não encontrado. Use --tectonic ou defina TECTONIC_BIN."
    )


def compile_latex(
    tex_path: Path,
    output_pdf: Path,
    *,
    tectonic_path: Path | None = None,
    cache_dir: Path | None = None,
    only_cached: bool = False,
) -> Path:
    engine = resolve_tectonic(tectonic_path)
    tex_path = tex_path.resolve()
    output_pdf = output_pdf.resolve()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    build_dir = (tex_path.parent / "build").resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    generated = build_dir / f"{tex_path.stem}.pdf"
    generated.unlink(missing_ok=True)
    command = [
        str(engine),
        "-X",
        "compile",
        tex_path.name,
        "--outdir",
        str(build_dir),
        "--keep-logs",
        "--keep-intermediates",
        "--untrusted",
    ]
    if only_cached:
        command.append("--only-cached")
    environment = os.environ.copy()
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        environment["TECTONIC_CACHE_DIR"] = str(cache_dir.resolve())
    process = subprocess.run(
        command,
        cwd=tex_path.parent,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    (build_dir / "tectonic-output.log").write_text(process.stdout, encoding="utf-8")
    if process.returncode:
        raise RuntimeError(
            f"Compilação LaTeX falhou (código {process.returncode}). "
            f"Consulte {build_dir / 'tectonic-output.log'}."
        )
    if not generated.is_file() or not generated.read_bytes().startswith(b"%PDF-"):
        raise RuntimeError("O Tectonic não produziu um PDF válido")
    latex_log = build_dir / f"{tex_path.stem}.log"
    if latex_log.exists():
        contents = latex_log.read_text(encoding="utf-8", errors="replace")
        fatal_patterns = (
            "Missing character:",
            "There were undefined references",
            "LaTeX Error:",
        )
        if any(pattern in contents for pattern in fatal_patterns):
            raise RuntimeError(f"Problema de composição registrado em {latex_log}")
    with tempfile.NamedTemporaryFile(dir=output_pdf.parent, delete=False) as stream:
        staged = Path(stream.name)
        with generated.open("rb") as source:
            shutil.copyfileobj(source, stream)
    try:
        staged.replace(output_pdf)
    finally:
        staged.unlink(missing_ok=True)
    return output_pdf
