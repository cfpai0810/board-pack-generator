# =============================================================================
# state.py: Shared Type Definitions: dataclasses and enums for the pipeline
# =============================================================================
"""
The typed objects every phase passes and receives. Money fields are Decimal.
Variance and delta fields default to None; step3_compute fills them.

Category is an enum of revenue, COGS and opex. The pack computes to EBIT
(revenue minus COGS minus opex), not net income. A row whose category is
not one of the three is rejected at load time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional


# -- Enums --------------------------------------------------------------------

class Category(Enum):
    """P&L line category. Determines which subtotal the line rolls into."""
    REVENUE = "revenue"
    COGS = "cogs"
    OPEX = "opex"

    @property
    def unnamed_label(self) -> str:
        """Display label for a line loaded with a blank line_item, e.g. 'Unnamed COGS line'."""
        name = "COGS" if self is Category.COGS else self.value
        return f"Unnamed {name} line"

    @property
    def parent_key(self) -> str:
        """Key of the subtotal this category's lines roll into."""
        return subtotal_key(self.value)


# -- Item keys ----------------------------------------------------------------
# Placement lists, drivers and lookups hold stable KEYS, never display names,
# so a line called "Revenue" cannot collide with the revenue subtotal and two
# lines with the same name stay distinct. Display names live in the figures.

# Subtotals in P&L order: (Subtotals field prefix, display name).
SUBTOTALS = (
    ("revenue", "Revenue"),
    ("cogs", "COGS"),
    ("gross_profit", "Gross profit"),
    ("opex", "Opex"),
    ("ebit", "EBIT"),
)


def subtotal_key(prefix: str) -> str:
    """'revenue' -> 'subtotal:revenue'."""
    return f"subtotal:{prefix}"


def line_key(position: int) -> str:
    """1-based position in the P&L -> 'line:3'."""
    return f"line:{position}"


class SectionType(Enum):
    """The four sections of a v1 board pack."""
    EXEC_SUMMARY = "exec_summary"
    PNL = "pnl"
    KPIS = "kpis"
    CASH = "cash"


# The one place a section's display title is written: the PDF headings, the
# web boxes, the CLI prompts and every flag message read it from here.
SECTION_TITLES = {
    SectionType.EXEC_SUMMARY.value: "Executive summary",
    SectionType.PNL.value: "Profit and loss",
    SectionType.KPIS.value: "Key performance indicators",
    SectionType.CASH.value: "Cash balance",
}


class PackStatus(Enum):
    """Pack lifecycle: DRAFT until the reviewer signs off."""
    DRAFT = "draft"
    FINAL = "final"


# -- P&L line -----------------------------------------------------------------

@dataclass
class PnlLine:
    """
    One account line from pnl.csv plus its computed variances.

    The loader populates line_item through prior_year. step3_compute fills
    the variance fields. All money fields are Decimal.

    line_item_blank records that the source row had no name. The loader
    keeps such a row (its money belongs in the subtotals), labels it with
    Category.unnamed_label (numbered when a category has several), and sets
    line_item_blank so step2 can still write its data note.

    key is the line's stable identity ("line:3", its 1-based position in
    the P&L), assigned by step4; it is what the placement lists hold.
    """
    line_item: str
    category: Category
    actuals: Decimal
    budget: Decimal
    prior_year: Decimal

    var_budget_abs: Optional[Decimal] = None
    var_budget_pct: Optional[Decimal] = None
    var_py_abs: Optional[Decimal] = None
    var_py_pct: Optional[Decimal] = None

    is_material: bool = False
    line_item_blank: bool = False
    key: str = ""


# -- Subtotals ----------------------------------------------------------------

@dataclass
class Subtotals:
    """
    Computed subtotals from the P&L lines. Every number here is born in
    step3_compute and is tested against the tie-out gate.

    Gross margin is a percentage held at full Decimal precision; round only
    for display. The margin points fields are the difference of the full
    precision margins, never of two rounded ones, so the table and the
    commentary cannot disagree. Variances are raw actual minus comparator
    for every subtotal, so a cost overspend is positive. A percentage is
    None when its denominator is zero.
    """
    revenue_actual: Decimal = Decimal("0")
    revenue_budget: Decimal = Decimal("0")
    revenue_py: Decimal = Decimal("0")

    cogs_actual: Decimal = Decimal("0")
    cogs_budget: Decimal = Decimal("0")
    cogs_py: Decimal = Decimal("0")

    gross_profit_actual: Decimal = Decimal("0")
    gross_profit_budget: Decimal = Decimal("0")
    gross_profit_py: Decimal = Decimal("0")

    opex_actual: Decimal = Decimal("0")
    opex_budget: Decimal = Decimal("0")
    opex_py: Decimal = Decimal("0")

    ebit_actual: Decimal = Decimal("0")
    ebit_budget: Decimal = Decimal("0")
    ebit_py: Decimal = Decimal("0")

    gross_margin_actual: Optional[Decimal] = None
    gross_margin_budget: Optional[Decimal] = None
    gross_margin_py: Optional[Decimal] = None
    gross_margin_var_budget_pts: Optional[Decimal] = None
    gross_margin_var_py_pts: Optional[Decimal] = None

    revenue_var_budget_abs: Optional[Decimal] = None
    revenue_var_budget_pct: Optional[Decimal] = None
    cogs_var_budget_abs: Optional[Decimal] = None
    cogs_var_budget_pct: Optional[Decimal] = None
    gross_profit_var_budget_abs: Optional[Decimal] = None
    gross_profit_var_budget_pct: Optional[Decimal] = None
    opex_var_budget_abs: Optional[Decimal] = None
    opex_var_budget_pct: Optional[Decimal] = None
    ebit_var_budget_abs: Optional[Decimal] = None
    ebit_var_budget_pct: Optional[Decimal] = None

    revenue_var_py_abs: Optional[Decimal] = None
    revenue_var_py_pct: Optional[Decimal] = None
    cogs_var_py_abs: Optional[Decimal] = None
    cogs_var_py_pct: Optional[Decimal] = None
    gross_profit_var_py_abs: Optional[Decimal] = None
    gross_profit_var_py_pct: Optional[Decimal] = None
    opex_var_py_abs: Optional[Decimal] = None
    opex_var_py_pct: Optional[Decimal] = None
    ebit_var_py_abs: Optional[Decimal] = None
    ebit_var_py_pct: Optional[Decimal] = None


# -- KPI ----------------------------------------------------------------------

def _metric_key(name: str, *, ignore_unit: bool = False) -> str:
    """
    A metric name reduced to lower-case letters and digits, for matching.
    ignore_unit drops a trailing "(unit)" first, so "Cash balance (GBP 000s)",
    "Cash balance (GBP)" and "Cash balance" are the same metric.
    """
    if ignore_unit:
        name = re.sub(r"\s*\([^)]*\)\s*$", "", name)
    return "".join(ch for ch in name.casefold() if ch.isalnum())


@dataclass
class Kpi:
    """
    One operational or cash metric from kpis.csv plus its computed deltas.

    The loader populates metric through prior_year. step3_compute fills the
    delta fields. prior_year is optional in the input.

    derived marks a KPI built from the P&L rather than read from kpis.csv
    (gross margin), so the render can label it "from the P&L".
    """
    metric: str
    actual: Decimal
    target: Decimal
    prior_year: Optional[Decimal] = None

    delta_target: Optional[Decimal] = None
    delta_py: Optional[Decimal] = None

    derived: bool = False

    def is_metric(self, name: str, *, ignore_unit: bool = False) -> bool:
        """
        True when this KPI is the metric called name, ignoring case, spaces
        and punctuation ("Gross margin %" matches "Gross margin (%)"), and
        with ignore_unit any trailing "(unit)" too.
        """
        return (_metric_key(self.metric, ignore_unit=ignore_unit)
                == _metric_key(name, ignore_unit=ignore_unit))


# -- Section ------------------------------------------------------------------

@dataclass
class Section:
    """
    One section of the board pack (executive summary, P&L, KPIs, or cash).

    step4_assemble builds the section with its computed figures and no
    commentary. step5_narrate drafts the commentary and records who drafted it
    in drafted_by ("template" or "model"). The section is format-agnostic;
    step7_render reads it.
    """
    section_type: SectionType
    title: str
    figures: dict = field(default_factory=dict)
    narrative: str = ""
    drafted_by: str = ""
    draft: str = ""

    @property
    def edited(self) -> bool:
        """True once step6 has stored a draft and the final text differs from it."""
        return bool(self.draft) and self.narrative != self.draft


# -- Review flags -------------------------------------------------------------

NUMERIC = "numeric"
CAUSE = "cause"
DIRECTION = "direction"
GLYPH = "glyph"
DRAFT_TEXT = "draft"
REVIEWER_TEXT = "reviewer"


@dataclass
class Flag:
    """
    One hit from a soft check, for the reviewer: a figure in the prose that
    matches nothing in the pack (numeric), a phrase in model prose that may
    state a cause (cause), offset language in model prose, which no longer
    attributes (direction), or a character the PDF font cannot print
    (glyph). A flag is never a block.

    raised_on says whose text it was found in (the draft or the reviewer's
    edit). resolved means a reviewer's edit removed it; it is kept, not
    deleted, so the audit shows what the review fixed.
    """
    section: str
    kind: str
    text: str
    raised_on: str = DRAFT_TEXT
    resolved: bool = False

    @property
    def detail(self) -> str:
        """What the flag says, without its section or where it was raised."""
        if self.kind == NUMERIC:
            return f"'{self.text}' matches no figure in the pack"
        if self.kind == GLYPH:
            return (f"'{self.text}' (U+{ord(self.text[0]):04X}) cannot be printed in the "
                    f"PDF font and would appear as '?'")
        if self.kind == DIRECTION:
            return (f"'{self.text}' describes an offset; attribution belongs to the "
                    f"computed drivers table, not the commentary")
        return f"'{self.text}' may state a cause"

    @property
    def message(self) -> str:
        """
        The one display form of a flag, used everywhere a person reads it: the
        boxes on screen, the sign-off summary, the CLI and the PDF review
        notes. It names the section by its title, never its internal key.
        """
        origin = " (in the reviewer's text)" if self.raised_on == REVIEWER_TEXT else ""
        return f"{SECTION_TITLES.get(self.section, self.section)}: {self.detail}{origin}"


# -- Materiality: what the rule selects ----------------------------------------

@dataclass
class MaterialFlags:
    """
    The output of the deterministic materiality selection in step4_assemble.

    Every list holds item KEYS ("subtotal:revenue", "line:3"), never display
    names; Pack.item(key) returns an item's figures, name included.

    exec_summary_items: material subtotals in P&L order, then material
        lines whose parent subtotal is not material (Revenue, Gross profit,
        EBIT, Marketing on the sample).
    pnl_commentary_items: material lines whose parent subtotal is material,
        so the board reads the subtotal and the line goes to the P&L
        commentary (Retail, Export).
    all_material: the full set before de-dup; subtotals in P&L order, then
        lines in P&L order.
    material_subtotals: the material subtotals alone, in P&L order.
    drivers: for each material subtotal key, its top driver line keys by
        absolute impact on profit. Shown as the computed drivers table, not featured.
    materiality_abs, materiality_pct: the thresholds that made this
        selection, recorded so the audit can show which rule selected them.
    """
    exec_summary_items: list[str] = field(default_factory=list)
    pnl_commentary_items: list[str] = field(default_factory=list)
    all_material: list[str] = field(default_factory=list)
    material_subtotals: list[str] = field(default_factory=list)
    drivers: dict[str, list[str]] = field(default_factory=dict)
    materiality_abs: Optional[Decimal] = None
    materiality_pct: Optional[Decimal] = None


# -- Pack ---------------------------------------------------------------------

@dataclass
class Pack:
    """
    The top-level board pack object passed through the pipeline.

    Built by step4_assemble (sections, the material items), filled by
    step5_narrate (commentary), reviewed by step6_review (status, edits),
    rendered by step7_render. Format-agnostic: the renderer reads the Pack
    and emits bytes.

    excluded_pnl_rows is the count of P&L rows that carried data but could
    not be loaded. When it is above zero the totals do not tie to the
    source file, and step7 shows a prominent notice.

    narrative_model, narrative_input_tokens and narrative_output_tokens
    record the model call step5 made (empty and zero on the templated
    path), for the step6 audit.

    pnl_sha256 and kpis_sha256 identify the exact input files. sign_off_at
    is the UTC time of sign-off, and acknowledged holds the sign-off
    summary the reviewer confirmed: every flag and data note outstanding
    when they signed. run_id is the latest review run, so a render can link its
    audit event to it; code_version is the code that computed the figures.
    currency is the ISO code every amount is written in (formatting.CURRENCIES),
    an input of the run, never a conversion. cash_scale is what one unit of the
    cash KPI is worth in whole units (1000 when
    the file states cash in thousands, 1 when in whole units): an input of the
    run, never assumed. kpis_supplied is False when the run had no KPI file,
    so the governance block can say so rather than show an empty hash.
    """
    entity: str = ""
    period: str = ""
    sections: list[Section] = field(default_factory=list)
    status: PackStatus = PackStatus.DRAFT
    pnl_lines: list[PnlLine] = field(default_factory=list)
    kpis: list[Kpi] = field(default_factory=list)
    subtotals: Optional[Subtotals] = None
    material_flags: Optional[MaterialFlags] = None
    warnings: list[str] = field(default_factory=list)
    excluded_pnl_rows: int = 0
    excluded_rows: list = field(default_factory=list)      # SkippedRow(row, name) each
    numeric_warnings: list[Flag] = field(default_factory=list)
    cause_warnings: list[Flag] = field(default_factory=list)
    direction_warnings: list[Flag] = field(default_factory=list)
    glyph_warnings: list[Flag] = field(default_factory=list)
    reviewer_edits: dict = field(default_factory=dict)
    sign_off_by: str = ""
    sign_off_at: str = ""
    acknowledged: list[str] = field(default_factory=list)
    narrative_model: str = ""
    narrative_input_tokens: int = 0
    narrative_output_tokens: int = 0
    pnl_sha256: str = ""
    kpis_sha256: str = ""
    run_id: str = ""
    code_version: str = ""
    cash_scale: int = 1000
    currency: str = "GBP"
    kpis_supplied: bool = True

    def section(self, section_type: SectionType) -> Section:
        """The section of the given type."""
        return next(s for s in self.sections if s.section_type is section_type)

    def item(self, key: str) -> dict:
        """
        The figures for a line or subtotal key, from the P&L section. This
        is how a key in a placement list becomes a display name and numbers.
        """
        figures = self.section(SectionType.PNL).figures
        for entry in figures["lines"] + figures["subtotals"]:
            if entry["key"] == key:
                return entry
        raise KeyError(key)
