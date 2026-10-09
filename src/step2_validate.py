# =============================================================================
# step2_validate.py: Layer 3: structural sanity checks, warn and carry on
# =============================================================================
"""
Sanity-check the loaded P&L lines and KPIs before any computation.

Finance reasoning: validation here does not ask whether the numbers are
right (that is the preparer's job). It asks whether a pack built from them
would mislead. A P&L with no revenue leaves the revenue subtotal at nil and
gross margin uncomputable. A P&L with no costs makes gross profit and EBIT
simply equal revenue. A KPI with no actual cannot be set against its
target. A blank line item cannot be named in the commentary. A controller
wants to be warned, not stopped, so each check appends a human-readable
warning to the flowing problems list and the records go on to step3
untouched. Nothing raises, nothing is dropped (the P5 validate pattern:
warn and carry on).

Works on the lists step1 returned and the problems list it started. No
Pack exists yet; step4 attaches the combined list to Pack.warnings.

Each check is small and named so a test can target it. Each returns the
warnings it raises, so an empty list means the check passed.
"""

from __future__ import annotations

from src.state import SUBTOTALS, Category, Kpi, PnlLine

_COST_CATEGORIES = (Category.COGS, Category.OPEX)


# -- P&L line checks ----------------------------------------------------------

def categories_recognised(pnl_lines: list[PnlLine]) -> list[str]:
    """
    Warn on any line whose category is not a Category member.

    step1 already rejects unknown categories at load, so on the CSV path
    this never fires. It is defence in depth for records built another way
    (a test, the future web layer), because a line outside the enum falls
    out of every subtotal without anyone noticing.
    """
    return [
        f"pnl ({line.line_item or 'unnamed line'}): unrecognised category "
        f"{line.category!r}, kept but it rolls into no subtotal"
        for line in pnl_lines
        if not isinstance(line.category, Category)
    ]


def line_items_present(pnl_lines: list[PnlLine]) -> list[str]:
    """
    Warn on any line whose source line_item was blank.

    On the CSV path step1 has already labelled such a line and set
    line_item_blank, so the flag is checked as well as the text. The line
    is kept: its amounts still belong in the subtotals, it just has no real
    name for the commentary. The warning names it by the same unnamed label
    the pack shows, plus its actuals so the preparer can find it.
    """
    warnings = []
    for line in pnl_lines:
        if line.line_item_blank or not (line.line_item or "").strip():
            if (line.line_item or "").strip():
                label = line.line_item          # the loader's (numbered) label
            elif isinstance(line.category, Category):
                label = line.category.unnamed_label
            else:
                label = f"Unnamed {line.category} line"
            warnings.append(
                f"pnl ({label}, actuals {line.actuals}): blank line_item, kept"
            )
    return warnings


def _name_key(name: str) -> str:
    return " ".join(name.split()).casefold()


def line_names_unique(pnl_lines: list[PnlLine]) -> list[str]:
    """
    Warn once per name that more than one line shares.

    The code keeps the lines distinct (items are keyed by position, not by
    name), but a director reading two identical labels in the table would
    not know which is which. Comparison ignores case and extra spaces.
    Blank names are line_items_present's job and are skipped here.
    """
    counts: dict[str, list[str]] = {}
    for line in pnl_lines:
        if (line.line_item or "").strip():
            counts.setdefault(_name_key(line.line_item), []).append(line.line_item)
    return [
        f"pnl ({names[0]}): {len(names)} lines share this name, kept as "
        f"separate lines"
        for names in counts.values() if len(names) > 1
    ]


def line_names_not_subtotals(pnl_lines: list[PnlLine]) -> list[str]:
    """
    Warn on a line named like a subtotal (Revenue, COGS, Gross profit, Opex,
    EBIT). A single revenue line called "Revenue" is realistic for a small
    company; the code keeps it apart from the Revenue subtotal, but the
    table would show two rows labelled Revenue.
    """
    subtotal_names = {_name_key(name): name for _, name in SUBTOTALS}
    return [
        f"pnl ({line.line_item}): same name as the "
        f"{subtotal_names[_name_key(line.line_item)]} subtotal, kept as a "
        f"separate line"
        for line in pnl_lines
        if (line.line_item or "").strip()
        and _name_key(line.line_item) in subtotal_names
    ]


def has_revenue(pnl_lines: list[PnlLine]) -> list[str]:
    """
    Warn if the P&L has no revenue line.

    Without revenue the pack would report a nil top line and a gross margin
    with nothing to divide by. Nonsensical, but the controller decides
    whether to proceed, so this warns rather than blocks.
    """
    if any(line.category is Category.REVENUE for line in pnl_lines):
        return []
    return [
        "pnl: no revenue line, so the revenue subtotal is nil "
        "and gross margin cannot be computed"
    ]


def has_costs(pnl_lines: list[PnlLine]) -> list[str]:
    """
    Warn if the P&L has no cost line (neither cogs nor opex).

    Without costs, gross profit and EBIT both collapse to revenue, which
    would present a full month's sales as profit.
    """
    if any(line.category in _COST_CATEGORIES for line in pnl_lines):
        return []
    return [
        "pnl: no cost line (cogs or opex), so gross profit "
        "and EBIT will simply equal revenue"
    ]


# -- KPI checks ---------------------------------------------------------------

def kpis_have_actuals(kpis: list[Kpi]) -> list[str]:
    """
    Warn on any KPI whose actual is missing.

    step1 skips a KPI row with a blank actual, so on the CSV path this is
    defence in depth for records built another way. The KPI is kept so the
    table still shows the metric and its target; step3 must treat its
    deltas as not computable.
    """
    return [
        f"kpi ({kpi.metric or 'unnamed metric'}): missing actual, kept"
        for kpi in kpis
        if kpi.actual is None
    ]


# -- Orchestrator -------------------------------------------------------------

def validate(
    pnl_lines: list[PnlLine],
    kpis: list[Kpi],
    problems: list[str],
) -> list[str]:
    """
    Run every check, append its warnings to problems, and return it.

    The same list object comes back with step1's notes first and step2's
    warnings after, so it reads in the order the pipeline ran. The records
    are inspected only: no value is changed, no record is removed, and
    nothing raises.
    """
    problems.extend(categories_recognised(pnl_lines))
    problems.extend(line_items_present(pnl_lines))
    problems.extend(line_names_unique(pnl_lines))
    problems.extend(line_names_not_subtotals(pnl_lines))
    problems.extend(has_revenue(pnl_lines))
    problems.extend(has_costs(pnl_lines))
    problems.extend(kpis_have_actuals(kpis))
    return problems
