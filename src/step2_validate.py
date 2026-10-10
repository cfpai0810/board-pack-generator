# =============================================================================
# step2_validate.py: Layer 3: structural sanity checks, warn and carry on
# =============================================================================
"""
Sanity-check the loaded P&L lines and KPIs before any computation.

Finance reasoning: validation here does not ask whether the numbers are
right (that is for whoever prepared the files). It asks whether a pack built from them
would mislead. A P&L with no revenue leaves the revenue subtotal at nil and
gross margin uncomputable. A P&L with no costs makes gross profit and EBIT
simply equal revenue. A KPI with no actual cannot be set against its
target. A blank line item cannot be named in the commentary. The reviewer
wants to be told, not stopped, so each check appends a data note to the
flowing problems list and the records go on to step3 untouched. Nothing
raises, nothing is dropped (the P5 validate pattern: note and carry on).

Works on the lists step1 returned and the problems list it started. No
Pack exists yet; step4 attaches the combined list to Pack.warnings, which
holds the data notes.

Each check is small and named so a test can target it. Each returns the
data notes it writes, so an empty list means the check passed.
"""

from __future__ import annotations

from src import notes
from src.notes import MAX_NAME_LENGTH
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
        notes.odd_category(line.line_item, line.category)
        for line in pnl_lines
        if not isinstance(line.category, Category)
    ]


def _category_word(category) -> str:
    if category is Category.COGS:
        return "COGS"
    return category.value if isinstance(category, Category) else str(category)


def line_items_present(pnl_lines: list[PnlLine]) -> list[str]:
    """
    Warn once per category on the lines whose source line_item was blank.

    On the CSV path step1 has already labelled such a line and set
    line_item_blank, so that field is checked as well as the text. The line
    is kept: its amounts still belong in the subtotals, it just has no real
    name for the commentary. The note gives the label the pack shows it
    under, so whoever prepared the file can find it in the table.
    """
    labels: dict[str, list[str]] = {}
    for line in pnl_lines:
        if line.line_item_blank or not (line.line_item or "").strip():
            if (line.line_item or "").strip():
                label = line.line_item          # the loader's (numbered) label
            elif isinstance(line.category, Category):
                label = line.category.unnamed_label
            else:
                label = f"Unnamed {line.category} line"
            labels.setdefault(_category_word(line.category), []).append(label)
    return [notes.unnamed_lines(word, names) for word, names in labels.items()]


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
    return [notes.shared_name(names[0], len(names))
            for names in counts.values() if len(names) > 1]


def line_names_not_subtotals(pnl_lines: list[PnlLine]) -> list[str]:
    """
    Note a line named like a subtotal ("Revenue", "COGS", "Gross profit",
    "Opex", "EBIT"). A single revenue line called "Revenue" is realistic for a
    small company; the code keeps it apart from the revenue subtotal, but the
    table would show two rows labelled "Revenue".
    """
    subtotal_names = {_name_key(name): name for _, name in SUBTOTALS}
    return [
        notes.subtotal_name(line.line_item, subtotal_names[_name_key(line.line_item)])
        for line in pnl_lines
        if (line.line_item or "").strip()
        and _name_key(line.line_item) in subtotal_names
    ]


def has_revenue(pnl_lines: list[PnlLine]) -> list[str]:
    """
    Warn if the P&L has no revenue line.

    Without revenue the pack would report a nil top line and a gross margin
    with nothing to divide by. Nonsensical, but the reviewer decides
    whether to proceed, so this warns rather than blocks.
    """
    if any(line.category is Category.REVENUE for line in pnl_lines):
        return []
    return [notes.no_revenue()]


def has_costs(pnl_lines: list[PnlLine]) -> list[str]:
    """
    Warn if the P&L has no cost line (neither cogs nor opex).

    Without costs, gross profit and EBIT both collapse to revenue, which
    would present a full month's sales as profit.
    """
    if any(line.category in _COST_CATEGORIES for line in pnl_lines):
        return []
    return [notes.no_costs()]


def names_not_too_long(pnl_lines: list[PnlLine], kpis: list[Kpi]) -> list[str]:
    """
    Warn on a line or KPI name longer than 60 characters. It is kept, and the
    PDF wraps it inside its column rather than widening the table, but a
    board reads short labels faster, so whoever prepared the file may want to shorten it.
    """
    warnings = [notes.long_name(notes.PNL, line.line_item)
                for line in pnl_lines if len(line.line_item or "") > MAX_NAME_LENGTH]
    warnings += [notes.long_name(notes.KPI_FILE, kpi.metric)
                 for kpi in kpis if len(kpi.metric or "") > MAX_NAME_LENGTH]
    return warnings


# -- KPI checks ---------------------------------------------------------------

def kpis_have_actuals(kpis: list[Kpi]) -> list[str]:
    """
    Warn on any KPI whose actual is missing.

    step1 skips a KPI row with a blank actual, so on the CSV path this is
    defence in depth for records built another way. The KPI is kept so the
    table still shows the metric and its target; step3 must treat its
    deltas as not computable.
    """
    return [notes.kpi_no_actual(kpi.metric) for kpi in kpis if kpi.actual is None]


# -- Orchestrator -------------------------------------------------------------

def validate(
    pnl_lines: list[PnlLine],
    kpis: list[Kpi],
    problems: list[str],
) -> list[str]:
    """
    Run every check, append its data notes to problems, and return it.

    The same list object comes back with step1's notes first and step2's
    after, so it reads in the order the pipeline ran. The records
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
    problems.extend(names_not_too_long(pnl_lines, kpis))
    return problems
