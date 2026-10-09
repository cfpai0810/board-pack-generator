# =============================================================================
# explain.py: Shared Helpers: what the explanation pages quote from a pack
# =============================================================================
"""
The web app's content pages explain the method on the sample pack, and
every figure they quote must be the engine's: typed into a page, a figure
would drift the first time the sample or a rule changed. So each quotable
fact is built here from a Pack, as a finished string through
src/formatting.py and src/tables.py, and the pages only place it.

Finance reasoning: the reader decides whether to trust the tool on these
explanations. An explanation that quotes "EBIT, a loss of £46k" has to be
the same number the pack prints, or the explanation itself becomes the
thing that cannot be trusted.

Nothing here computes a new figure: it selects from what step3 and step4
computed and formats it. walkthrough() retells a review from its audit
line, for the worked example that is shown without a run.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from config import MATERIALITY_ABS, MATERIALITY_PCT
from src.formatting import pct, profit_phrase, prose_money, table_value, when_text
from src.notes import and_join, count_words
from src.state import REVIEWER_TEXT, SECTION_TITLES, Category, Pack, subtotal_key
from src.step5_narrate import SYSTEM_PROMPT, build_prompt, narrative_facts, unmatched_tokens
from src.tables import LINE, pnl_rows

_PARENT = {Category.REVENUE: "revenue", Category.COGS: "cogs", Category.OPEX: "opex"}
_CATEGORY_WORDS = {Category.REVENUE: "Revenue", Category.COGS: "Cost (COGS)",
                   Category.OPEX: "Cost (opex)"}


# -- The headline and the thresholds ----------------------------------------------

def headline(pack: Pack) -> dict[str, str]:
    """
    The sample's top line for the "Figures" explanation: the revenue lines
    that sum to revenue (as a phrase with its verb, so one line reads "the
    one revenue line sums"), the revenue, and EBIT against budget, each as
    the pack's prose prints it.
    """
    s = pack.subtotals
    n = sum(1 for line in pack.pnl_lines if line.category is Category.REVENUE)
    return {
        "revenue_lines": (f"the {count_words(n)} revenue line sums" if n == 1
                          else f"the {count_words(n)} revenue lines sum"),
        "revenue": prose_money(s.revenue_actual),
        "ebit": profit_phrase(s.ebit_actual),
        "ebit_budget": profit_phrase(s.ebit_budget, "budgeted "),
    }


def thresholds(pack: Pack) -> tuple[str, str]:
    """The run's materiality thresholds as the pack prints them: ('£50,000', '10.0%')."""
    flags = pack.material_flags
    return f"£{table_value(flags.materiality_abs)}", pct(flags.materiality_pct)


def default_threshold_inputs() -> tuple[str, str]:
    """
    The configured thresholds as a form shows them before anyone types:
    ('50,000', '10'). The form's defaults come from config, never from the page.
    """
    return table_value(MATERIALITY_ABS), f"{MATERIALITY_PCT.normalize():f}"


# -- Materiality --------------------------------------------------------------------

@dataclass(frozen=True)
class MaterialItem:
    name: str
    kind: str              # "Subtotal" or "Line"
    variance: str          # Fav/(Adv) against budget, £
    variance_pct: str      # Fav/(Adv) against budget, %
    placement: str         # where the commentary discusses it


def material_items(pack: Pack) -> list[MaterialItem]:
    """Every material item, in the order of the P&L table, with where it is discussed."""
    flags = pack.material_flags
    exec_items = set(flags.exec_summary_items)
    names = {pack.item(k)["name"]: k for k in flags.all_material}
    items = []
    for row in pnl_rows(pack):
        name = row.label.removesuffix(" *")
        if not row.material or name not in names:
            continue
        key = names[name]
        items.append(MaterialItem(
            name=name,
            kind="Line" if row.kind == LINE else "Subtotal",
            variance=row.cells[3],
            variance_pct=row.cells[4],
            placement=("Executive summary" if key in exec_items
                       else "P&L commentary"),
        ))
    return items


def placement_example(pack: Pack) -> Optional[str]:
    """
    The de-duplication rule seen on this pack, in one sentence: which
    material lines sit under a material subtotal (so go to the P&L
    commentary) and which do not (so go to the executive summary).
    """
    flags = pack.material_flags
    material_subtotals = set(flags.material_subtotals)
    under, alone = {}, {}
    for line in pack.pnl_lines:
        if not line.is_material:
            continue
        parent = subtotal_key(_PARENT[line.category])
        parent_name = pack.item(parent)["name"]
        (under if parent in material_subtotals else alone).setdefault(
            parent_name, []).append(line.line_item)
    parts = []
    for parent, lines in under.items():
        verb = "sits" if len(lines) == 1 else "sit"
        parts.append(f"{and_join(lines)} {verb} under {parent}, which is material, so "
                     f"{'it is' if len(lines) == 1 else 'they are'} discussed in the P&L "
                     f"commentary")
    for parent, lines in alone.items():
        verb = "sits" if len(lines) == 1 else "sit"
        parts.append(f"{and_join(lines)} {verb} under {parent}, which is not, so "
                     f"{'it is' if len(lines) == 1 else 'they are'} in the executive summary")
    return f"In this pack, {'; '.join(parts)}." if parts else None


# -- Fav/(Adv) ----------------------------------------------------------------------

@dataclass(frozen=True)
class FavAdvExample:
    name: str
    kind: str              # "Revenue", "Cost (COGS)" or "Cost (opex)"
    actual: str
    budget: str
    shown: str             # the Fav/(Adv) cell against budget
    reading: str


def fav_adv_examples(pack: Pack) -> list[FavAdvExample]:
    """
    One revenue line and one cost line, as the P&L table shows them: the
    revenue line with the largest budget variance, and the cost line with
    the largest overspend (or, if none overspent, the largest variance).
    """
    rows = {row.label.removesuffix(" *"): row for row in pnl_rows(pack) if row.kind == LINE}
    revenue = [l for l in pack.pnl_lines if l.category is Category.REVENUE]
    costs = [l for l in pack.pnl_lines if l.category in (Category.COGS, Category.OPEX)]
    chosen = []
    if revenue:
        chosen.append(max(revenue, key=lambda l: l.var_budget_abs.copy_abs()))
    if costs:
        over = [l for l in costs if l.var_budget_abs > 0]
        chosen.append(max(over or costs, key=lambda l: l.var_budget_abs.copy_abs()))
    examples = []
    for line in chosen:
        row = rows[line.line_item]
        cost = line.category is not Category.REVENUE
        above = line.var_budget_abs > 0
        if line.var_budget_abs == 0:
            reading = "On budget."
        elif cost:
            reading = ("Above budget, an overspend: adverse." if above
                       else "Below budget, an underspend: favourable.")
        else:
            reading = "Above budget: favourable." if above else "Below budget: adverse."
        examples.append(FavAdvExample(
            name=line.line_item, kind=_CATEGORY_WORDS[line.category],
            actual=row.cells[0], budget=row.cells[1], shown=row.cells[3], reading=reading))
    return examples


# -- The limits of the soft checks ------------------------------------------------------

@dataclass(frozen=True)
class SoftCheckExample:
    budget: str            # the revenue budget as the pack's prose prints it: '£2.59m'
    coarse: str            # the same figure written loosely: '£3m'
    flagged: bool          # whether the numeric check flags the loose figure


def soft_check_example(pack: Pack) -> SoftCheckExample:
    """
    The revenue budget written to the nearest whole unit of its own scale
    ("£2.59m" loosely as "£3m"), and whether the numeric check flags it. It
    rounds a figure to the precision it is written in, so a loose figure
    passes: the page states the limitation from what the engine does.
    """
    budget = pack.subtotals.revenue_budget
    precise = prose_money(budget)
    unit = precise[-2:] if precise.endswith("bn") else precise[-1]
    exponent = {"bn": 9, "m": 6, "k": 3}.get(unit, 0)
    whole = budget.copy_abs().scaleb(-exponent).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    coarse = f"£{whole}{unit if exponent else ''}"
    return SoftCheckExample(budget=precise, coarse=coarse,
                            flagged=bool(unmatched_tokens(f"The budget was {coarse}.", pack)))


# -- What the model sees ----------------------------------------------------------------

def model_prompt(pack: Pack) -> tuple[str, str]:
    """(system prompt, user message): exactly what the model would receive for this pack."""
    system, user = build_prompt(narrative_facts(pack), pack.entity, pack.period)
    return system, user


# -- The review, told from its audit line ---------------------------------------------------

def walkthrough(review: dict) -> list[str]:
    """
    What happened at review, in three lines, read from a review audit line:
    who drafted the commentary, what the reviewer added, and what was flagged
    and acknowledged at sign-off. Nothing is retold that the audit does not hold.
    """
    sections = review["sections"]
    drafted = {s["drafted_by"] for s in sections}
    by = {"template": "The template", "model": "The model"}.get(
        next(iter(drafted)) if len(drafted) == 1 else "", "The model and the template")
    lines = [f"{by} drafted the commentary for {review['entity']}, {review['period']}, from "
             f"figures the code had computed and items a rule had selected."]
    name = review["sign_off_by"] or review["reviewer"] or "The reviewer"
    for s in sections:
        if not s["edited"]:
            continue
        added = (s["final"][len(s["draft"]):].strip() if s["final"].startswith(s["draft"])
                 else s["final"])
        lines.append(f"The reviewer, {name}, added a reason to the "
                     f"{SECTION_TITLES[s['section']].lower()}: \"{added}\"")
    theirs = [f for f in review["numeric_warnings"] if f["raised_on"] == REVIEWER_TEXT]
    if theirs and review["sign_off_at"]:
        figures = and_join([f"'{f['text']}'" for f in theirs])
        lines.append(f"Their figure, {figures}, matches no figure in the pack, so it was "
                     f"flagged; {name} acknowledged the flag and signed off on "
                     f"{when_text(review['sign_off_at'])}.")
    elif review["sign_off_at"]:
        lines.append(f"{name} signed off on {when_text(review['sign_off_at'])}.")
    return lines


__all__ = [
    "walkthrough",
    "headline", "thresholds", "default_threshold_inputs", "MaterialItem", "material_items",
    "placement_example", "FavAdvExample", "fav_adv_examples", "SoftCheckExample",
    "soft_check_example", "model_prompt", "SYSTEM_PROMPT",
]
