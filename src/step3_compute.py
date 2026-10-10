# =============================================================================
# step3_compute.py: Layer 4: the deterministic engine, every figure born here
# =============================================================================
"""
Compute every number the pack will show: line variances, the subtotals,
gross margin, and the KPI deltas.

Finance reasoning: a board makes decisions from this document, so every
figure has to be reproducible from the source lines. The subtotals are
COMPUTED from the lines by category, never read from a file, and the same
inputs always give the same numbers. The model never produces a figure;
it only narrates what this phase returns.

Sign convention: every variance is raw actual minus comparator, for every
category. A cost overspend is positive (Marketing vBud +37,640). Whether
that is favourable or adverse is a presentation choice for the commentary
and the render, not something to bake into the numbers. The percentage
denominator is abs(comparator), so a negative comparator (a loss-making
budget, say) does not reverse the sign of the percentage.

Precision: full Decimal precision is held throughout and nothing is
rounded here (gross margin is 34.9696...%, shown as 35.0% only at
display). No float enters this module. compute() pins the Decimal context
so a caller that has changed the global precision cannot change a figure.

Zero comparators: a percentage over a zero budget, last year or revenue
is not meaningful, so it is None and a note naming the line and the
comparator joins the problems list. The absolute variance is still
computed.

Gross margin KPI: derived here from the subtotals, never read from
kpis.csv, so the KPI table and the P&L commentary share one source.

Works on the lists step2 passed on and the flowing problems list, filling
the existing fields on the records. No Pack yet (step4 builds it), and
is_material is left alone: materiality is step4's rule.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import NamedTuple, Optional

from config import GROSS_MARGIN_KPI_METRIC
from src.notes import (
    line_subject, margin_not_shown, margin_row_ignored, subtotal_subject, zero_comparator,
    zero_revenue,
)
from src.state import Category, Kpi, PnlLine, Subtotals

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")

# 28 significant digits is the Decimal default, pinned here so a notebook
# or the web layer lowering the global precision cannot alter a figure.
_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)


# -- Result -------------------------------------------------------------------

class ComputeResult(NamedTuple):
    pnl_lines: list[PnlLine]
    kpis: list[Kpi]
    subtotals: Subtotals
    problems: list[str]


# -- Percentage and variance helpers ------------------------------------------

def safe_pct(numerator: Decimal, denominator: Decimal) -> Optional[Decimal]:
    """
    numerator * 100 / abs(denominator), or None when the denominator is zero.

    The one place the zero guard and the abs() denominator live. Every
    variance percentage and gross margin go through it.
    """
    if denominator == _ZERO:
        return None
    return numerator * _HUNDRED / abs(denominator)


def _variance(
    actual: Decimal,
    comparator: Decimal,
    subject: str,
    against: str,
    notes: list[str],
) -> tuple[Decimal, Optional[Decimal]]:
    """
    Return (actual minus comparator, that as a % of comparator), noting a
    zero comparator. subject names the line or subtotal for the note.
    """
    diff = actual - comparator
    pct = safe_pct(diff, comparator)
    if pct is None:
        notes.append(zero_comparator(subject, against))
    return diff, pct


# -- Line variances -----------------------------------------------------------

def compute_line_variances(pnl_lines: list[PnlLine]) -> list[str]:
    """
    Fill var_budget_abs/pct and var_py_abs/pct on every line.

    These are what step4's materiality rule reads, so they are computed for
    every line, named or unnamed. Returns the notes for any zero comparator.
    """
    notes: list[str] = []
    for line in pnl_lines:
        line.var_budget_abs, line.var_budget_pct = _variance(
            line.actuals, line.budget, line_subject(line.line_item), "budget", notes,
        )
        line.var_py_abs, line.var_py_pct = _variance(
            line.actuals, line.prior_year, line_subject(line.line_item), "last year", notes,
        )
    return notes


# -- Subtotals ----------------------------------------------------------------

def _column_sums(
    pnl_lines: list[PnlLine], category: Category,
) -> tuple[Decimal, Decimal, Decimal]:
    """(actual, budget, last year) totals for one category; Decimal zero if it has no lines."""
    lines = [line for line in pnl_lines if line.category is category]
    return (
        sum((line.actuals for line in lines), _ZERO),
        sum((line.budget for line in lines), _ZERO),
        sum((line.prior_year for line in lines), _ZERO),
    )


def compute_subtotals(pnl_lines: list[PnlLine]) -> tuple[Subtotals, list[str]]:
    """
    Build the Subtotals from the lines, for actual, budget and last year.

    Revenue, COGS and opex are sums by category. Gross profit is revenue
    minus COGS; EBIT is gross profit minus opex; gross margin is gross
    profit as a % of revenue. A line whose category is not a Category
    member rolls into nothing (step2 has warned). Returns the notes for
    zero revenue or a zero subtotal budget.
    """
    notes: list[str] = []

    rev_a, rev_b, rev_p = _column_sums(pnl_lines, Category.REVENUE)
    cogs_a, cogs_b, cogs_p = _column_sums(pnl_lines, Category.COGS)
    opex_a, opex_b, opex_p = _column_sums(pnl_lines, Category.OPEX)
    gp_a, gp_b, gp_p = rev_a - cogs_a, rev_b - cogs_b, rev_p - cogs_p

    s = Subtotals(
        revenue_actual=rev_a, revenue_budget=rev_b, revenue_py=rev_p,
        cogs_actual=cogs_a, cogs_budget=cogs_b, cogs_py=cogs_p,
        gross_profit_actual=gp_a, gross_profit_budget=gp_b, gross_profit_py=gp_p,
        opex_actual=opex_a, opex_budget=opex_b, opex_py=opex_p,
        ebit_actual=gp_a - opex_a, ebit_budget=gp_b - opex_b, ebit_py=gp_p - opex_p,
        gross_margin_actual=safe_pct(gp_a, rev_a),
        gross_margin_budget=safe_pct(gp_b, rev_b),
        gross_margin_py=safe_pct(gp_p, rev_p),
    )

    zero_columns = [
        column for column, revenue
        in (("actual", rev_a), ("budget", rev_b), ("last year", rev_p))
        if revenue == _ZERO
    ]
    if zero_columns:
        notes.append(zero_revenue(zero_columns))

    s.revenue_var_budget_abs, s.revenue_var_budget_pct = _variance(
        s.revenue_actual, s.revenue_budget, subtotal_subject("Revenue"), "budget", notes,
    )
    s.cogs_var_budget_abs, s.cogs_var_budget_pct = _variance(
        s.cogs_actual, s.cogs_budget, subtotal_subject("COGS"), "budget", notes,
    )
    s.gross_profit_var_budget_abs, s.gross_profit_var_budget_pct = _variance(
        s.gross_profit_actual, s.gross_profit_budget, subtotal_subject("Gross profit"), "budget", notes,
    )
    s.opex_var_budget_abs, s.opex_var_budget_pct = _variance(
        s.opex_actual, s.opex_budget, subtotal_subject("Opex"), "budget", notes,
    )
    s.ebit_var_budget_abs, s.ebit_var_budget_pct = _variance(
        s.ebit_actual, s.ebit_budget, subtotal_subject("EBIT"), "budget", notes,
    )

    s.revenue_var_py_abs, s.revenue_var_py_pct = _variance(
        s.revenue_actual, s.revenue_py, subtotal_subject("Revenue"), "last year", notes,
    )
    s.cogs_var_py_abs, s.cogs_var_py_pct = _variance(
        s.cogs_actual, s.cogs_py, subtotal_subject("COGS"), "last year", notes,
    )
    s.gross_profit_var_py_abs, s.gross_profit_var_py_pct = _variance(
        s.gross_profit_actual, s.gross_profit_py, subtotal_subject("Gross profit"), "last year", notes,
    )
    s.opex_var_py_abs, s.opex_var_py_pct = _variance(
        s.opex_actual, s.opex_py, subtotal_subject("Opex"), "last year", notes,
    )
    s.ebit_var_py_abs, s.ebit_var_py_pct = _variance(
        s.ebit_actual, s.ebit_py, subtotal_subject("EBIT"), "last year", notes,
    )

    # Points from the full precision margins, never from rounded ones.
    s.gross_margin_var_budget_pts = _points(s.gross_margin_actual, s.gross_margin_budget)
    s.gross_margin_var_py_pts = _points(s.gross_margin_actual, s.gross_margin_py)

    return s, notes


def _points(margin: Optional[Decimal], comparator: Optional[Decimal]) -> Optional[Decimal]:
    """Margin movement in percentage points; None if either margin is not computable."""
    if margin is None or comparator is None:
        return None
    return margin - comparator


# -- KPI deltas ---------------------------------------------------------------

def compute_kpi_deltas(kpis: list[Kpi]) -> None:
    """
    Fill delta_target and delta_py on every KPI (actual minus comparator).

    delta_py is None when the KPI has no figure for last year. A KPI with no actual
    can only arrive from outside the loader (step2 has warned); it gets no
    deltas rather than stopping the run.
    """
    for kpi in kpis:
        if kpi.actual is None:
            kpi.delta_target = kpi.delta_py = None
            continue
        kpi.delta_target = kpi.actual - kpi.target
        kpi.delta_py = None if kpi.prior_year is None else kpi.actual - kpi.prior_year


def add_gross_margin_kpi(
    kpis: list[Kpi], subtotals: Subtotals,
) -> tuple[list[Kpi], list[str]]:
    """
    Return the KPI list with gross margin derived from the P&L, plus notes.

    Gross margin is computed from the P&L lines, so a separate gross margin
    row in kpis.csv would be a second source for the same number, and two
    sources disagree sooner or later (the old sample row gave -4 against
    last year where the P&L gives -3.7 points). Any input row with that name
    is dropped with a note, and a derived KPI is appended: its actual, target
    and prior_year are the actual, budget and last year's margins, and the
    deltas are the margin points fields. If the actual or budget margin
    cannot be computed (zero revenue, already noted), no KPI is added.
    """
    notes: list[str] = []
    kept: list[Kpi] = []
    for kpi in kpis:
        if kpi.is_metric(GROSS_MARGIN_KPI_METRIC):
            notes.append(margin_row_ignored(kpi.metric))
        else:
            kept.append(kpi)

    s = subtotals
    if s.gross_margin_actual is None or s.gross_margin_budget is None:
        notes.append(margin_not_shown())
        return kept, notes

    kept.append(Kpi(
        metric=GROSS_MARGIN_KPI_METRIC,
        actual=s.gross_margin_actual,
        target=s.gross_margin_budget,
        prior_year=s.gross_margin_py,
        delta_target=s.gross_margin_var_budget_pts,
        delta_py=s.gross_margin_var_py_pts,
        derived=True,
    ))
    return kept, notes


# -- Orchestrator -------------------------------------------------------------

def compute(
    pnl_lines: list[PnlLine],
    kpis: list[Kpi],
    problems: list[str],
) -> ComputeResult:
    """
    Fill every computed field and build the Subtotals.

    The records are populated in place and returned with the Subtotals and
    the same problems list, any notes appended after the step1 and step2
    entries. The returned kpis list is new: the input KPIs without any
    gross margin row, then the gross margin KPI derived from the P&L.

    The Decimal context is set with localcontext(), so the caller's own
    context is untouched once compute() returns.
    """
    with localcontext(_CONTEXT):
        problems.extend(compute_line_variances(pnl_lines))
        subtotals, notes = compute_subtotals(pnl_lines)
        problems.extend(notes)
        kpis, notes = add_gross_margin_kpi(kpis, subtotals)
        compute_kpi_deltas([k for k in kpis if not k.derived])
        problems.extend(notes)
    return ComputeResult(pnl_lines, kpis, subtotals, problems)
