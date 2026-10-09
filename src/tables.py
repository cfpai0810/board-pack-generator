# =============================================================================
# tables.py: Shared Helpers: the pack's tables as rows of formatted strings
# =============================================================================
"""
The P&L table and the drivers table as rows of finished strings, built once
for every display: the PDF (step7) draws them and the web layer shows them.
So the board's PDF and the screen can never disagree on a cell, and no
Decimal ever reaches a display layer: every value here has already passed
through src/formatting.py.

The conventions are the PDF's. Values are whole pounds with negatives in
brackets. Variance columns are Fav/(Adv): costs are sign-flipped for
display only. A percentage across a change of sign or over a zero
comparator is n/m. Margin points sit in the % column of each Fav/(Adv)
group. A material row carries an asterisk in its label.

The palette lives here too, as hex strings, so the web theme uses the same
status and materiality colours as the PDF.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.formatting import (
    fav_adv, fav_adv_pct, margin_cell, pts_cell, table_value,
)
from src.state import SUBTOTALS, Category, Pack, SectionType, subtotal_key

# -- Palette: colour only for status and materiality ---------------------------

DRAFT_HEX = "#B45F06"
FINAL_HEX = "#2E6B3F"
MATERIAL_HEX = "#FFF2CC"
RULE_HEX = "#808080"

# -- The P&L table --------------------------------------------------------------

PNL_HEADER = (
    ("", "Actual", "Budget", "Prior year", "Fav/(Adv) vs budget", "",
     "Fav/(Adv) vs prior year", ""),
    ("", "£", "£", "£", "£", "%", "£", "%"),
)

LINE = "line"
SUBTOTAL = "subtotal"
MARGIN = "margin"

_COST_PREFIXES = {"cogs", "opex"}


@dataclass(frozen=True)
class PnlRow:
    """One body row: its label (asterisked if material), seven cells, and how it is styled."""
    label: str
    cells: tuple[str, ...]
    kind: str
    material: bool


def _row(label, actual, budget, py, var_b, pct_b, var_py, pct_py, *, cost, material, kind):
    return PnlRow(
        label=f"{label} *" if material else label,
        cells=(
            table_value(actual), table_value(budget), table_value(py),
            fav_adv(var_b, cost=cost), fav_adv_pct(pct_b, actual, budget, cost=cost),
            fav_adv(var_py, cost=cost), fav_adv_pct(pct_py, actual, py, cost=cost),
        ),
        kind=kind,
        material=material,
    )


def pnl_rows(pack: Pack) -> list[PnlRow]:
    """
    Every P&L line grouped by category with its subtotal, then Gross profit,
    EBIT and the gross margin row, in the order the board reads them.
    """
    s = pack.subtotals
    material_subtotals = set(pack.material_flags.material_subtotals)
    names = dict(SUBTOTALS)
    rows: list[PnlRow] = []

    def lines(category: Category) -> None:
        for line in pack.pnl_lines:
            if line.category is category:
                rows.append(_row(
                    line.line_item, line.actuals, line.budget, line.prior_year,
                    line.var_budget_abs, line.var_budget_pct,
                    line.var_py_abs, line.var_py_pct,
                    cost=category is not Category.REVENUE,
                    material=line.is_material, kind=LINE))

    def subtotal(prefix: str) -> None:
        rows.append(_row(
            names[prefix], getattr(s, f"{prefix}_actual"), getattr(s, f"{prefix}_budget"),
            getattr(s, f"{prefix}_py"),
            getattr(s, f"{prefix}_var_budget_abs"), getattr(s, f"{prefix}_var_budget_pct"),
            getattr(s, f"{prefix}_var_py_abs"), getattr(s, f"{prefix}_var_py_pct"),
            cost=prefix in _COST_PREFIXES,
            material=subtotal_key(prefix) in material_subtotals, kind=SUBTOTAL))

    lines(Category.REVENUE)
    subtotal("revenue")
    lines(Category.COGS)
    subtotal("cogs")
    subtotal("gross_profit")
    lines(Category.OPEX)
    subtotal("opex")
    subtotal("ebit")
    rows.append(PnlRow(
        label="Gross margin",
        cells=(margin_cell(s.gross_margin_actual), margin_cell(s.gross_margin_budget),
               margin_cell(s.gross_margin_py),
               "", pts_cell(s.gross_margin_var_budget_pts),
               "", pts_cell(s.gross_margin_var_py_pts)),
        kind=MARGIN,
        material=False,
    ))
    return rows


# -- The drivers table ------------------------------------------------------------

DRIVERS_HEADER = (("Subtotal", "Line", "Impact on profit"), ("", "", "Fav/(Adv) £"))

# Subtotals whose drivers are tabulated: the ones that span categories, so
# the table says which side of the P&L moved them.
ATTRIBUTED = (subtotal_key("gross_profit"), subtotal_key("ebit"))


@dataclass(frozen=True)
class DriverRow:
    """subtotal is blank on the second and later rows of a group."""
    subtotal: str
    line: str
    impact: str


def drivers_rows(pack: Pack) -> list[DriverRow]:
    """
    Main drivers of the variance against budget, for Gross profit and EBIT
    when material. The impact is stored in profit terms already, so no flip:
    a line that lowered profit is bracketed, a genuine offset is plain.
    Empty when neither subtotal is material.
    """
    drivers = pack.section(SectionType.EXEC_SUMMARY).figures["drivers"]
    rows: list[DriverRow] = []
    for key in ATTRIBUTED:
        for i, d in enumerate(drivers.get(key, [])):
            rows.append(DriverRow(
                subtotal=pack.item(key)["name"] if i == 0 else "",
                line=d["name"],
                impact=fav_adv(d["impact"], cost=False),
            ))
    return rows
