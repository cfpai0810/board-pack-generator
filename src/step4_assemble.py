# =============================================================================
# step4_assemble.py: Layer 5: materiality by rule, de-dup, drivers, the Pack
# =============================================================================
"""
Build the Pack: select what is material by rule, place each material item
once, record the lines that drove each material subtotal, and lay out the
four sections with their figures and empty narratives.

Finance reasoning: a board pack is editorial judgement, made safe here by
turning the judgement into a rule. What counts as material is a threshold
on the computed variance against budget, not the model's opinion; the
model later explains the items this phase selected and never chooses
them. Both arms of the rule are inclusive and the percentage is compared
at full precision, so 9.96% (shown as 10.0%) is not material. Prior year
does not drive materiality.

De-dup: a material line under a material subtotal would feature the same
money twice. The board reads the headline subtotal in the exec summary and
the line detail goes to the P&L commentary. A material line whose parent
is not material is news in its own right, so it joins the exec summary
after the subtotals.

Drivers: a line can drive a material subtotal without being material
itself (Ingredients, +4.1% vs budget, is the main cost behind the fall in
gross profit). Drivers are context for the narrative, not featured items,
so the narrative can name them without a new figure: the impact is the
line's own budget variance, sign flipped for costs so that it reads as the
effect on profit.

Keys: every list and the drivers map hold item keys ("subtotal:revenue",
"line:3"), assigned here from P&L position, never display names. A line
called "Revenue" therefore cannot collide with the Revenue subtotal.

No model runs here, and no number is computed beyond that sign flip; every
figure is read from step3's output. Absolute values and negation use
copy_abs() and copy_negate(), which are exact whatever the caller's Decimal
context, so the comparison really is at full precision.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from config import (
    CASH_KPI_METRIC, ENTITY_NAME, MATERIALITY_ABS, MATERIALITY_PCT, PERIOD,
)
from src.formatting import sign_change
from src.state import (
    SUBTOTALS, Category, Kpi, MaterialFlags, Pack, PackStatus, PnlLine,
    Section, SectionType, Subtotals, line_key, subtotal_key,
)

# Which lines can drive each subtotal, by subtotal key.
_DRIVER_SCOPE = {
    subtotal_key("revenue"): {Category.REVENUE},
    subtotal_key("cogs"): {Category.COGS},
    subtotal_key("gross_profit"): {Category.REVENUE, Category.COGS},
    subtotal_key("opex"): {Category.OPEX},
    subtotal_key("ebit"): {Category.REVENUE, Category.COGS, Category.OPEX},
}

TOP_DRIVERS = 3

NO_CASH_NOTE = "No cash balance was supplied."


# -- Materiality --------------------------------------------------------------

def is_material(
    var_abs: Decimal,
    var_pct: Optional[Decimal],
    materiality_abs: Decimal,
    materiality_pct: Decimal,
) -> bool:
    """
    The rule: |var_abs| >= materiality_abs OR |var_pct| >= materiality_pct.

    Both arms inclusive; the percentage is compared at full precision; a
    None percentage (zero budget) leaves the absolute arm alone.
    """
    if var_abs.copy_abs() >= materiality_abs:
        return True
    return var_pct is not None and var_pct.copy_abs() >= materiality_pct


def flag_materiality(
    pnl_lines: list[PnlLine],
    subtotals: Subtotals,
    materiality_abs: Decimal,
    materiality_pct: Decimal,
) -> list[str]:
    """
    Set is_material on every line (True or False, so a re-run with other
    thresholds is clean) and return the material subtotal keys in P&L order.

    Across a change of sign (actual and budget of opposite signs) the
    percentage is meaningless, so only the absolute test applies: a small
    profit turning into a small loss cannot become material on -200%.
    """
    def meaningful_pct(var_pct, actual, budget):
        return None if sign_change(actual, budget) else var_pct

    for line in pnl_lines:
        line.is_material = is_material(
            line.var_budget_abs,
            meaningful_pct(line.var_budget_pct, line.actuals, line.budget),
            materiality_abs, materiality_pct,
        )
    return [
        subtotal_key(prefix) for prefix, _ in SUBTOTALS
        if is_material(
            getattr(subtotals, f"{prefix}_var_budget_abs"),
            meaningful_pct(getattr(subtotals, f"{prefix}_var_budget_pct"),
                           getattr(subtotals, f"{prefix}_actual"),
                           getattr(subtotals, f"{prefix}_budget")),
            materiality_abs, materiality_pct,
        )
    ]


# -- De-dup and placement -----------------------------------------------------

def _by_size(lines: list[PnlLine]) -> list[PnlLine]:
    """Descending |var_budget_abs|; the sort is stable, so ties keep P&L order."""
    return sorted(lines, key=lambda l: l.var_budget_abs.copy_abs(), reverse=True)


def place_lines(
    pnl_lines: list[PnlLine], material_subtotals: list[str],
) -> tuple[list[PnlLine], list[PnlLine]]:
    """
    Split the material lines into (exec summary lines, P&L commentary lines).

    A material line whose parent subtotal is material goes to the
    commentary; one whose parent is not material goes to the exec summary.
    Each list is ordered by descending |var_budget_abs|.
    """
    exec_lines: list[PnlLine] = []
    commentary_lines: list[PnlLine] = []
    for line in _by_size([l for l in pnl_lines if l.is_material]):
        parent = line.category.parent_key if isinstance(line.category, Category) else None
        if parent in material_subtotals:
            commentary_lines.append(line)
        else:
            exec_lines.append(line)
    return exec_lines, commentary_lines


# -- Drivers ------------------------------------------------------------------

def profit_impact(line: PnlLine) -> Decimal:
    """
    The line's budget variance as its effect on profit: as is for revenue,
    sign flipped for costs (a cost overspend lowers gross profit and EBIT).
    """
    if line.category is Category.REVENUE:
        return line.var_budget_abs
    return line.var_budget_abs.copy_negate()


def find_drivers(
    pnl_lines: list[PnlLine], material_subtotals: list[str],
) -> dict[str, list[PnlLine]]:
    """
    For each material subtotal, its top TOP_DRIVERS lines by absolute
    impact, ties broken by P&L order. A line that did not move (zero
    variance) is not a driver.
    """
    drivers: dict[str, list[PnlLine]] = {}
    for key in material_subtotals:
        scope = [
            l for l in pnl_lines
            if l.category in _DRIVER_SCOPE[key] and l.var_budget_abs != 0
        ]
        drivers[key] = _by_size(scope)[:TOP_DRIVERS]
    return drivers


# -- Section figures ----------------------------------------------------------

def _line_figures(line: PnlLine) -> dict:
    category = line.category
    return {
        "kind": "line",
        "key": line.key,
        "name": line.line_item,
        "category": category.value if isinstance(category, Category) else str(category),
        "actual": line.actuals,
        "budget": line.budget,
        "prior_year": line.prior_year,
        "var_budget_abs": line.var_budget_abs,
        "var_budget_pct": line.var_budget_pct,
        "var_py_abs": line.var_py_abs,
        "var_py_pct": line.var_py_pct,
        "is_material": line.is_material,
        "unnamed": line.line_item_blank,
    }


def _subtotal_figures(
    s: Subtotals, prefix: str, name: str, material_subtotals: list[str],
) -> dict:
    key = subtotal_key(prefix)
    return {
        "kind": "subtotal",
        "key": key,
        "name": name,
        "actual": getattr(s, f"{prefix}_actual"),
        "budget": getattr(s, f"{prefix}_budget"),
        "prior_year": getattr(s, f"{prefix}_py"),
        "var_budget_abs": getattr(s, f"{prefix}_var_budget_abs"),
        "var_budget_pct": getattr(s, f"{prefix}_var_budget_pct"),
        "var_py_abs": getattr(s, f"{prefix}_var_py_abs"),
        "var_py_pct": getattr(s, f"{prefix}_var_py_pct"),
        "is_material": key in material_subtotals,
    }


def _margin_figures(s: Subtotals) -> dict:
    return {
        "actual": s.gross_margin_actual,
        "budget": s.gross_margin_budget,
        "prior_year": s.gross_margin_py,
        "var_budget_pts": s.gross_margin_var_budget_pts,
        "var_py_pts": s.gross_margin_var_py_pts,
    }


def _kpi_figures(kpi: Kpi) -> dict:
    return {
        "metric": kpi.metric,
        "actual": kpi.actual,
        "target": kpi.target,
        "prior_year": kpi.prior_year,
        "delta_target": kpi.delta_target,
        "delta_py": kpi.delta_py,
        "derived": kpi.derived,
    }


# -- Sections -----------------------------------------------------------------

def _exec_summary_section(
    s: Subtotals,
    material_subtotals: list[str],
    exec_lines: list[PnlLine],
    drivers: dict[str, list[PnlLine]],
) -> Section:
    items = [
        _subtotal_figures(s, prefix, name, material_subtotals)
        for prefix, name in SUBTOTALS
        if subtotal_key(prefix) in material_subtotals
    ] + [_line_figures(line) for line in exec_lines]
    return Section(
        section_type=SectionType.EXEC_SUMMARY,
        title="Executive summary",
        figures={
            "items": items,
            "drivers": {
                key: [
                    {**_line_figures(line), "impact": profit_impact(line)}
                    for line in lines
                ]
                for key, lines in drivers.items()
            },
            "gross_margin": _margin_figures(s),
        },
    )


def _pnl_section(
    pnl_lines: list[PnlLine],
    s: Subtotals,
    material_subtotals: list[str],
    commentary_lines: list[PnlLine],
) -> Section:
    return Section(
        section_type=SectionType.PNL,
        title="Profit and loss",
        figures={
            "lines": [_line_figures(line) for line in pnl_lines],
            "subtotals": [
                _subtotal_figures(s, prefix, name, material_subtotals)
                for prefix, name in SUBTOTALS
            ],
            "gross_margin": _margin_figures(s),
            "commentary_items": [_line_figures(line) for line in commentary_lines],
        },
    )


def _kpis_section(kpis: list[Kpi]) -> Section:
    """
    Every KPI except the cash balance, which has its own section: the same
    figure shown in two places is the same money featured twice.
    """
    return Section(
        section_type=SectionType.KPIS,
        title="Key performance indicators",
        figures={"kpis": [_kpi_figures(k) for k in kpis
                          if not k.is_metric(CASH_KPI_METRIC)]},
    )


def _cash_section(kpis: list[Kpi], problems: list[str]) -> Section:
    """
    The cash BALANCE from the cash KPI, in the unit its name states. Not a
    cash flow statement: the inputs hold no opening, closing or movement,
    so none is shown. If no cash KPI was supplied, the section says so and
    a warning joins the problems list.
    """
    cash = next((k for k in kpis if k.is_metric(CASH_KPI_METRIC)), None)
    if cash is None:
        problems.append(
            f"kpi ({CASH_KPI_METRIC}): not supplied, so the cash section "
            f"shows no balance"
        )
        figures = {"supplied": False, "metric": CASH_KPI_METRIC, "note": NO_CASH_NOTE}
    else:
        figures = {"supplied": True, **_kpi_figures(cash)}
    return Section(
        section_type=SectionType.CASH,
        title="Cash balance",
        figures=figures,
    )


# -- Orchestrator -------------------------------------------------------------

def assemble(
    pnl_lines: list[PnlLine],
    kpis: list[Kpi],
    subtotals: Subtotals,
    problems: list[str],
    excluded_pnl_rows: int,
    *,
    materiality_abs: Decimal = MATERIALITY_ABS,
    materiality_pct: Decimal = MATERIALITY_PCT,
    pnl_sha256: str = "",
    kpis_sha256: str = "",
) -> Pack:
    """
    Flag materiality, de-dup, find drivers, and build the DRAFT Pack.

    The thresholds default to config and are keyword parameters so tests
    and the web layer can change them without touching config. They cross
    the Decimal boundary here via Decimal(str(x)), so an int from a UI
    control is safe. The problems list becomes Pack.warnings (the same
    list, with any cash warning appended). The input file hashes from
    step1 are carried onto the Pack for the audit.
    """
    materiality_abs = Decimal(str(materiality_abs))
    materiality_pct = Decimal(str(materiality_pct))

    for position, line in enumerate(pnl_lines, start=1):
        line.key = line_key(position)

    material_subtotals = flag_materiality(
        pnl_lines, subtotals, materiality_abs, materiality_pct,
    )
    exec_lines, commentary_lines = place_lines(pnl_lines, material_subtotals)
    drivers = find_drivers(pnl_lines, material_subtotals)

    flags = MaterialFlags(
        exec_summary_items=material_subtotals + [l.key for l in exec_lines],
        pnl_commentary_items=[l.key for l in commentary_lines],
        all_material=material_subtotals + [l.key for l in pnl_lines if l.is_material],
        material_subtotals=list(material_subtotals),
        drivers={key: [l.key for l in lines] for key, lines in drivers.items()},
        materiality_abs=materiality_abs,
        materiality_pct=materiality_pct,
    )

    sections = [
        _exec_summary_section(subtotals, material_subtotals, exec_lines, drivers),
        _pnl_section(pnl_lines, subtotals, material_subtotals, commentary_lines),
        _kpis_section(kpis),
        _cash_section(kpis, problems),
    ]

    return Pack(
        entity=ENTITY_NAME,
        period=PERIOD,
        sections=sections,
        status=PackStatus.DRAFT,
        pnl_lines=pnl_lines,
        kpis=kpis,
        subtotals=subtotals,
        material_flags=flags,
        warnings=problems,
        excluded_pnl_rows=excluded_pnl_rows,
        numeric_warnings=[],
        pnl_sha256=pnl_sha256,
        kpis_sha256=kpis_sha256,
    )
