# =============================================================================
# story.py: Shared Helpers: the pack's storyline, computed from its figures
# =============================================================================
"""
A board reads a pack as a story: what happened to profit, where it came
from, which lines moved it, then the detail. This module computes the
pieces of that story from the figures step3 and step4 produced:

    headline_sentence   EBIT against budget and last year, in one sentence
    summary_line        the EBIT variance by revenue, COGS and opex, then last year
    ebit_walk           the steps of the budget-to-actual bridge
    line_effects        each line's effect on profit against budget, largest first
    pnl_message         the P&L page's message: revenue against budget, how many
                        revenue lines were below it, and costs against budget

Finance reasoning: the storyline is arithmetic, so it belongs to the code,
like the drivers table. Every sentence here says what moved and by how much,
never why: causes stay the reviewer's, added at review. Nothing is drafted
and nothing is editable; the commentary (template or model, then the
reviewer) sits beside it.

Every amount is a Decimal and every sentence is built through
src/formatting.py, so the story and the tables cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.formatting import pct, profit_phrase, prose_money, pts, sign_change
from src.notes import count_words
from src.state import Category, Pack

_ZERO = Decimal("0")


def signed_money(value: Decimal) -> str:
    """A profit effect or a result in the prose scale, brackets for a negative: '(£112k)', '£3k'."""
    return f"({prose_money(value)})" if value < 0 else prose_money(value)


_LEVEL = {"budget": "on budget", "last year": "level with last year"}


def against(variance: Decimal, comparator: str, percent: Optional[Decimal] = None) -> str:
    """
    A variance in the words the commentary uses: '£112k (4.3%) below budget',
    '£128k (5.5%) above last year', 'on budget'. percent is left out when it
    is None (a zero comparator, or a change of sign, where it means nothing).
    """
    if variance == 0:
        return _LEVEL[comparator]
    share = f" ({pct(percent)})" if percent is not None else ""
    return f"{prose_money(variance)}{share} {'below' if variance < 0 else 'above'} {comparator}"


def points_against(points: Optional[Decimal], comparator: str) -> str:
    """Margin points in words: '4.1 pts below budget', 'level with last year', or n/m."""
    if points is None:
        return f"n/m against {comparator}"
    if pts(points) == "0.0 pts":
        return _LEVEL[comparator]
    return f"{pts(points)} {'below' if points < 0 else 'above'} {comparator}"


def meaningful(percent: Optional[Decimal], actual: Decimal, comparator: Decimal):
    """The percentage, or None across a change of sign, as the tables show n/m."""
    return None if percent is None or sign_change(actual, comparator) else percent


def _against(value: Decimal) -> str:
    return "on budget" if value == 0 else ("below budget" if value < 0 else "above budget")


# -- The headline and the summary_line ---------------------------------------------------

def headline_sentence(pack: Pack) -> str:
    """
    The bottom line against both comparators: 'EBIT was a loss of £46k: £193k
    below budget and £147k below last year.'
    """
    s = pack.subtotals
    return (f"EBIT was {profit_phrase(s.ebit_actual)}: "
            f"{against(s.ebit_var_budget_abs, 'budget')} and "
            f"{against(s.ebit_var_py_abs, 'last year')}.")


def summary_line(pack: Pack) -> str:
    """
    Where the EBIT variance came from, and how the month compares with last
    year: 'Against budget, revenue was £112k lower, COGS £34k higher and opex
    £47k higher; the gross margin was 4.1 pts lower. Against last year,
    revenue grew by £128k (5.5%), but the gross margin fell 3.7 pts to
    35.0%.' A cost above budget lowers profit. "But" joins a rise and a fall;
    it states a contrast, never a cause.
    """
    s = pack.subtotals

    def moved(name: str, variance: Decimal, verb: str = "") -> str:
        if not variance:
            return f"{name} {verb}on budget"
        return f"{name} {verb}{prose_money(variance)} {'lower' if variance < 0 else 'higher'}"

    parts = [moved("revenue", s.revenue_var_budget_abs, "was "),
             moved("COGS", s.cogs_var_budget_abs), moved("opex", s.opex_var_budget_abs)]
    margin_budget = s.gross_margin_var_budget_pts
    text = f"Against budget, {parts[0]}, {parts[1]} and {parts[2]}"
    if margin_budget is not None and pts(margin_budget) != "0.0 pts":
        text += (f"; the gross margin was {pts(margin_budget)} "
                 f"{'lower' if margin_budget < 0 else 'higher'}")
    text += "."

    revenue = s.revenue_var_py_abs
    share = meaningful(s.revenue_var_py_pct, s.revenue_actual, s.revenue_py)
    if revenue:
        grew = (f"revenue {'grew' if revenue > 0 else 'fell'} by {prose_money(revenue)}"
                + (f" ({pct(share)})" if share is not None else ""))
    else:
        grew = "revenue was level"
    margin = s.gross_margin_var_py_pts
    if margin is None or s.gross_margin_actual is None:
        return f"{text} Against last year, {grew}."
    if pts(margin) == "0.0 pts":
        held, contrast = f"the gross margin held at {pct(s.gross_margin_actual)}", False
    else:
        held = (f"the gross margin {'rose' if margin > 0 else 'fell'} {pts(margin)} to "
                f"{pct(s.gross_margin_actual)}")
        contrast = (revenue > 0) != (margin > 0) and revenue != 0
    return f"{text} Against last year, {grew}{', but' if contrast else ', and'} {held}."


# -- The budget-to-actual bridge: from budget EBIT to actual EBIT ------------------------

@dataclass(frozen=True)
class WalkStep:
    label: str
    value: Decimal          # the bar itself: a level for the ends, a profit effect between
    kind: str               # "total" for budget and actual EBIT, "step" for an effect


def ebit_walk(pack: Pack) -> list[WalkStep]:
    """
    Budget EBIT, then the profit effect of revenue, COGS and opex against
    budget, then actual EBIT. The steps sum exactly: budget plus the three
    effects is actual (costs above budget are negative effects on profit).
    """
    s = pack.subtotals
    return [
        WalkStep("Budget EBIT", s.ebit_budget, "total"),
        WalkStep("Revenue", s.revenue_var_budget_abs, "step"),
        WalkStep("COGS", -s.cogs_var_budget_abs, "step"),
        WalkStep("Opex", -s.opex_var_budget_abs, "step"),
        WalkStep("Actual EBIT", s.ebit_actual, "total"),
    ]


# -- Each line's effect on profit ---------------------------------------------------------

_PART = {Category.REVENUE: "Revenue", Category.COGS: "COGS", Category.OPEX: "Opex"}


@dataclass(frozen=True)
class LineEffect:
    name: str
    effect: Decimal         # on profit, against budget: below zero lowered profit
    material: bool
    part: str = ""          # Revenue, COGS or Opex: the step of the bridge it belongs to


def line_effects(pack: Pack, limit: int = 12) -> list[LineEffect]:
    """
    Every line's budget variance as its effect on profit (a revenue
    shortfall or a cost overspend lowers it), largest first. Beyond limit
    lines, the rest are one bar, "Other lines (n)", so a long P&L still
    reads at a glance.
    """
    effects = []
    for line in pack.pnl_lines:
        if not isinstance(line.category, Category):
            continue
        effect = line.var_budget_abs if line.category is Category.REVENUE else -line.var_budget_abs
        effects.append(LineEffect(line.line_item, effect, line.is_material,
                                  _PART[line.category]))
    effects.sort(key=lambda e: (-e.effect.copy_abs(), e.name))
    if len(effects) <= limit:
        return effects
    shown, rest = effects[:limit - 1], effects[limit - 1:]
    total = sum((e.effect for e in rest), _ZERO)
    return shown + [LineEffect(f"Other lines ({len(rest)})", total, False)]


# -- The P&L page's message -----------------------------------------------------------------

def pnl_message(pack: Pack) -> str:
    """
    'Revenue was £112k (4.3%) below budget, with all three revenue lines
    below budget; COGS was £34k above budget and opex £47k above.'
    """
    s = pack.subtotals
    revenue = [l for l in pack.pnl_lines if l.category is Category.REVENUE]
    below = sum(1 for l in revenue if l.var_budget_abs < 0)
    rev = s.revenue_var_budget_abs
    if rev and s.revenue_var_budget_pct is not None:
        text = f"Revenue was {prose_money(rev)} ({pct(s.revenue_var_budget_pct)}) {_against(rev)}"
    else:
        text = f"Revenue was {'on budget' if not rev else prose_money(rev) + ' ' + _against(rev)}"
    if revenue and rev < 0:
        if below == len(revenue):
            which = "the revenue line" if below == 1 else f"all {count_words(below)} revenue lines"
        else:
            which = f"{count_words(below)} of the {count_words(len(revenue))} revenue lines"
        text += f", with {which} below budget" if below else ""
    cogs, opex = s.cogs_var_budget_abs, s.opex_var_budget_abs
    costs = (f"COGS was {prose_money(cogs)} {_against(cogs)}" if cogs else "COGS was on budget")
    costs += (f" and opex {prose_money(opex)} {_against(opex).removesuffix(' budget')}"
              if opex else " and opex on budget")
    return f"{text}; {costs}."
