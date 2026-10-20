# =============================================================================
# pipeline.py: Shared Orchestrator: one headless run from CSV files to a pack
# =============================================================================
"""
run_pipeline() is the whole governance story as one flow: the code loads,
checks and computes every figure, the rule selects what is material, the
commentary is drafted inside those figures, the reviewer reads and signs,
and the pack is rendered with its audit trail.

Finance reasoning: a headless run must never produce a signed pack, because
signing without a person reading is exactly what the tool exists to
prevent. So signing only happens through the injected ask and confirm; the
draft-only path writes a DRAFT with its review notes and audit line, and
there is deliberately no option that signs without them.

All the logic lives here so the CLI (main.py) and the web layer call the
same engine with their own ask and confirm. Nothing here reads input or
prints. A problem the user can fix (a missing file, a P&L with nothing
loadable) raises PipelineError with a plain message.

The inputs of a run are explicit: the files (the KPI file is optional),
the entity and period that head the pack, the currency its amounts are in,
the unit the KPI file states cash in, and the materiality thresholds. Left out, each comes from config,
which describes the sample. Nothing downstream reads config for them: it
reads the Pack.

This module is also the ONE public surface of src/ for the web layer:
streamlit_app/ imports nothing else from src/. Besides run_pipeline it
offers the review stage as thin wrappers over the step code
(review_and_save, signoff_summary, check_text, audit_text), the input
checks a form needs (parse_materiality, CASH_UNITS, CURRENCIES), and re-exports the
display rows, palette and types a page needs. __all__ lists it all.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Optional

from src.explain import (
    FavAdvExample, MaterialItem, SoftCheckExample, default_threshold_inputs,
    fav_adv_examples, headline, material_items, model_prompt, placement_example,
    soft_check_example, thresholds, walkthrough,
)
from config import CURRENCY, MATERIALITY_ABS
from src.formatting import CURRENCIES, Currency, table_value, when_text
from src.notes import (
    MAX_NAME_LENGTH, MODEL_FAILURE_MESSAGES, UNKNOWN_ERROR, count_words, failure_code,
    failure_message, row_handling,
)
from src.state import (
    DRAFT_TEXT, GLYPH, NUMERIC, REVIEWER_TEXT, SECTION_TITLES, Category, Flag, Pack,
    PackStatus, SectionType,
)
from src.step1_load import KPI_COLUMNS, PNL_COLUMNS, MissingColumns, NotText, file_sha256, load
from src.step2_validate import validate
from src.step3_compute import compute
from src.step4_assemble import CASH_REVENUE_MULTIPLE, assemble
from src.step5_narrate import narrate
from src.step6_review import (
    AUDIT_FILE, NAME_WARNING, SIGN_OFF_WARNINGS, SIGN_WARNING, SIGN_WORD, Ask,
    Confirm, _utc_now, answers_ask, audit_text, check_text, confirm_by_word,
    excluded_rows_note, is_sign_word, preview_signoff, record_draft, review,
)
from src.step7_render import ScreenChart, save_pack, screen_charts
from src.story import headline_sentence, pnl_message, summary_line
from src.tables import (
    DRAFT_HEX, DRIVERS_NOTE, DRIVERS_TITLE, FINAL_HEX, KPI_HEADER, KPI_NOTE,
    MATERIAL_HEX, RULE_HEX, DriverRow, PnlRow, Tile, cash_cells, cash_header, cash_note,
    commentary_source, drivers_header, drivers_rows, headline_tiles, kpi_rows, pnl_header,
    pnl_notes, pnl_rows,
)

__all__ = [
    # the run
    "run_pipeline", "PipelineError", "PipelineResult",
    # the inputs of a run
    "parse_materiality", "CASH_UNITS", "CURRENCIES", "Currency", "build_pack",
    "default_threshold_inputs",
    "PNL_COLUMNS", "KPI_COLUMNS", "OPTIONAL_KPI_COLUMNS", "CATEGORIES", "MAX_NAME_LENGTH",
    # what the explanation pages quote from a pack
    "headline", "thresholds", "material_items", "MaterialItem", "placement_example",
    "fav_adv_examples", "FavAdvExample", "soft_check_example", "SoftCheckExample",
    "model_prompt", "walkthrough", "file_sha256", "count_words",
    "CASH_REVENUE_MULTIPLE",
    # the review stage
    "review_and_save", "signoff_summary", "check_text", "audit_text",
    "is_sign_word", "SIGN_WORD", "NAME_WARNING", "SIGN_WARNING",
    # a failed model call, in plain words and a short code
    "failure_code", "failure_message", "MODEL_FAILURE_MESSAGES", "UNKNOWN_ERROR",
    # what a page displays: the PDF's own text, rows and charts
    "headline_sentence", "summary_line", "pnl_message", "headline_tiles", "Tile",
    "excluded_rows_note", "screen_charts", "ScreenChart",
    "pnl_rows", "drivers_rows", "PnlRow", "DriverRow", "pnl_header", "drivers_header",
    "DRIVERS_TITLE", "kpi_rows", "KPI_HEADER", "KPI_NOTE", "cash_cells", "cash_header", "cash_note",
    "pnl_notes", "DRIVERS_NOTE", "when_text", "SECTION_TITLES", "commentary_source",
    "row_handling",
    "DRAFT_HEX", "FINAL_HEX", "MATERIAL_HEX", "RULE_HEX",
    # types and constants
    "Pack", "PackStatus", "SectionType", "Flag", "NUMERIC", "GLYPH",
    "DRAFT_TEXT", "REVIEWER_TEXT",
]


class PipelineError(Exception):
    """A problem with the inputs that a person can fix, stated plainly."""


CASH_UNITS = {"thousands": 1000, "units": 1}
"""What one unit of the cash KPI is worth in whole units of the currency, by the unit the KPI file states it in."""

CATEGORIES = tuple(c.value for c in Category)
OPTIONAL_KPI_COLUMNS = ("prior_year",)


@dataclass
class PipelineResult:
    """
    notices holds the engine's sign-off warnings from a review attempt
    (a blank name, a word other than SIGN), for a screen to show. saved_at
    is the UTC time the PDF was saved.

    From run_pipeline only: data_notes is every load and validation note
    about the input files (skipped rows, unnamed lines, long names, a missing
    KPI file or cash balance, rows the totals exclude), and narrate_notices
    any note from drafting the commentary, such as a model call that failed
    and left the template in its place.
    """
    pack: Pack
    pdf_path: Path
    audit_path: Path
    notices: list[str] = field(default_factory=list)
    saved_at: str = ""
    data_notes: list[str] = field(default_factory=list)
    narrate_notices: list[str] = field(default_factory=list)


_PLAIN_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
_PREFIXES = tuple(sorted({c.sign for c in CURRENCIES.values()} | set(CURRENCIES), key=len,
                           reverse=True))


def _abs_rule(currency: str) -> str:
    return f"The absolute threshold must be a positive amount in {CURRENCIES[currency].name}, such as 50,000."


def _abs_required(currency: str) -> str:
    return (f"Give the absolute threshold in {CURRENCIES[currency].name}. The default, "
            f"{table_value(MATERIALITY_ABS)}, is set for the sample in pounds and does not carry "
            f"over to another currency.")
_PCT_RULE = "The percentage threshold must be above 0 and at most 100, such as 10."


def parse_materiality(abs_text: str, pct_text: str, *, currency: str) -> tuple[Decimal, Decimal]:
    """
    The two thresholds as a person types them ("50,000", "£50,000", "CHF
    50,000"; "10" or "10%"), as Decimals. The amount must be positive and the
    percentage above 0 and at most 100; otherwise PipelineError says what to
    type. In a currency other than the sample's, a blank amount is asked for
    by name: the sample's default does not carry over.
    """
    amount = abs_text.strip()
    for prefix in _PREFIXES:
        amount = amount.removeprefix(prefix)
    amount = amount.replace(",", "").strip()
    percent = pct_text.strip().removesuffix("%").strip()
    problems = []
    if not amount and currency != CURRENCY:
        problems.append(_abs_required(currency))
    elif not _PLAIN_NUMBER.match(amount) or Decimal(amount) <= 0:
        problems.append(_abs_rule(currency))
    if not _PLAIN_NUMBER.match(percent) or not 0 < Decimal(percent) <= 100:
        problems.append(_PCT_RULE)
    if problems:
        raise PipelineError(" ".join(problems))
    return Decimal(amount), Decimal(percent)


def _check_inputs(materiality_abs, materiality_pct, entity, period, cash_scale,
                  currency) -> None:
    """The run's own inputs, checked before any file is read."""
    if currency is not None and currency not in CURRENCIES:
        raise PipelineError(f"The currency must be one of {', '.join(CURRENCIES)}; "
                            f"{currency!r} is not.")
    code = CURRENCY if currency is None else currency
    if materiality_abs is None and code != CURRENCY:
        raise PipelineError(_abs_required(code))
    if materiality_abs is not None and not Decimal(str(materiality_abs)) > 0:
        raise PipelineError(_abs_rule(code))
    if materiality_pct is not None and not 0 < Decimal(str(materiality_pct)) <= 100:
        raise PipelineError(_PCT_RULE)
    for label, value in (("entity name", entity), ("period", period)):
        if value is not None and not value.strip():
            raise PipelineError(f"The {label} is blank. Type the {label} the pack is for.")
    if cash_scale is not None and cash_scale not in CASH_UNITS.values():
        raise PipelineError("Cash in the KPI file must be stated in thousands or in whole units.")


def run_pipeline(
    pnl_path: Path,
    kpis_path: Optional[Path],
    output_dir: Path,
    *,
    ask: Optional[Ask] = None,
    confirm: Optional[Confirm] = None,
    reviewer: str = "",
    client=None,
    materiality_abs: Optional[Decimal] = None,
    materiality_pct: Optional[Decimal] = None,
    entity: Optional[str] = None,
    period: Optional[str] = None,
    cash_scale: Optional[int] = None,
    currency: Optional[str] = None,
    draft_only: bool = False,
    now: Optional[str] = None,
) -> PipelineResult:
    """
    Load, validate, compute, assemble, narrate, review (or record a draft),
    then render and save the pack. Returns the pack, the PDF path, the
    audit path, and the notes on the data and the drafting.

    An interactive run needs ask and confirm; draft_only=True needs neither
    and never signs. kpis_path=None runs without a KPI file: the KPI section
    then holds only the gross margin derived from the P&L, and the cash
    section says no cash balance was supplied. entity, period, cash_scale
    (CASH_UNITS: 1000 when the KPI file states cash in thousands, 1 in whole
    units), currency (a code in CURRENCIES, a label only; nothing is converted)
    and the thresholds left as None come from config, the sample.
    A currency other than the sample's needs its own absolute threshold.
    client=None drafts with the template.

    A problem the person can fix raises PipelineError before anything is
    written: a missing file, a missing column, a P&L with no loadable
    lines, a blank entity or period, a threshold out of range.

    now fixes the run's clock (an ISO UTC time) for the review, the sign-off
    and the rendered event: for a reproducible build such as the worked
    example. A live run leaves it None.
    """
    if not draft_only and (ask is None or confirm is None):
        raise ValueError("A review needs ask and confirm; use draft_only=True to skip review.")
    pack, data_notes, narrate_notices = _build(
        pnl_path, kpis_path, client=client, materiality_abs=materiality_abs,
        materiality_pct=materiality_pct, entity=entity, period=period, cash_scale=cash_scale,
        currency=currency)

    output_dir = Path(output_dir)
    if draft_only:
        record_draft(pack, output_dir=output_dir)
    else:
        review(pack, ask=ask, confirm=confirm, reviewer=reviewer, output_dir=output_dir,
               now=now)

    saved_at = now or _utc_now()
    pdf_path = save_pack(pack, output_dir, now=now)
    return PipelineResult(pack=pack, pdf_path=pdf_path, audit_path=output_dir / AUDIT_FILE,
                          saved_at=saved_at, data_notes=data_notes,
                          narrate_notices=narrate_notices)


def build_pack(
    pnl_path: Path,
    kpis_path: Optional[Path],
    *,
    client=None,
    materiality_abs: Optional[Decimal] = None,
    materiality_pct: Optional[Decimal] = None,
    entity: Optional[str] = None,
    period: Optional[str] = None,
    cash_scale: Optional[int] = None,
    currency: Optional[str] = None,
) -> Pack:
    """
    The narrated DRAFT pack from the files, with nothing reviewed, rendered
    or written: for pages that explain the method on the sample. The same
    load, checks, computation, selection and commentary as run_pipeline.
    """
    return _build(pnl_path, kpis_path, client=client, materiality_abs=materiality_abs,
                  materiality_pct=materiality_pct, entity=entity, period=period,
                  cash_scale=cash_scale, currency=currency)[0]


def _build(pnl_path, kpis_path, *, client, materiality_abs, materiality_pct, entity, period,
           cash_scale, currency) -> tuple[Pack, list[str], list[str]]:
    """(the narrated pack, its data notes, its narrate notices). Writes nothing."""
    _check_inputs(materiality_abs, materiality_pct, entity, period, cash_scale, currency)
    for path in (pnl_path, kpis_path):
        if path is not None and not Path(path).is_file():
            raise PipelineError(f"Input file not found: {path}")

    try:
        loaded = load(Path(pnl_path), None if kpis_path is None else Path(kpis_path))
    except (MissingColumns, NotText) as e:
        raise PipelineError(str(e)) from e
    except (UnicodeDecodeError, csv.Error) as e:
        raise PipelineError(f"An input file could not be read as CSV text: {e}") from e
    if not loaded.pnl_lines:
        detail = "; ".join(loaded.problems[:3]) or "the file has no data rows"
        raise PipelineError(
            f"The P&L file has no lines that could be loaded, so there is nothing "
            f"to compute ({detail}).")

    problems = validate(loaded.pnl_lines, loaded.kpis, loaded.problems)
    computed = compute(loaded.pnl_lines, loaded.kpis, problems)
    thresholds = {
        name: value for name, value in (("materiality_abs", materiality_abs),
                                        ("materiality_pct", materiality_pct))
        if value is not None
    }
    pack = assemble(
        computed.pnl_lines, computed.kpis, computed.subtotals, computed.problems,
        loaded.excluded_pnl_rows, excluded_rows=loaded.excluded_rows,
        pnl_sha256=loaded.pnl_sha256,
        kpis_sha256=loaded.kpis_sha256, **thresholds,
        entity=None if entity is None else entity.strip(),
        period=None if period is None else period.strip(),
        cash_scale=cash_scale, currency=currency, kpis_supplied=kpis_path is not None,
    )
    data_notes = list(pack.warnings)
    if pack.excluded_pnl_rows:
        data_notes.append(excluded_rows_note(pack))
    before = len(pack.warnings)
    narrate(pack, client=client)
    return pack, data_notes, pack.warnings[before:]


# -- The review stage, for a screen with edit boxes ---------------------------------

def signoff_summary(pack: Pack, edits: dict[str, str]) -> list[str]:
    """
    What the reviewer must see before signing, if the texts on screen were
    submitted now: the same lines the CLI prints before SIGN, built by the
    same code review() uses, on a copy of the pack. edits maps each section
    key ("exec_summary", "pnl", "kpis", "cash") to its text.
    """
    return preview_signoff(pack, edits)


def review_and_save(
    pack: Pack,
    output_dir: Path,
    *,
    edits: dict[str, str],
    reviewer: str = "",
    sign_word: Optional[str] = None,
) -> PipelineResult:
    """
    Review the pack with the texts already edited on screen, then render
    and save it: one review line and one rendered line in the audit.

    sign_word=None is "Save as draft": the edits are kept and the pack stays
    DRAFT. Otherwise the engine decides: the pack is signed only with a
    reviewer name and sign_word exactly SIGN; a blank name or any other
    word leaves it DRAFT with the engine's warning in notices. A FINAL pack
    raises AlreadySignedOff: a signed pack is changed by a new run.
    """
    output_dir = Path(output_dir)
    review(pack, ask=answers_ask(pack, edits), confirm=confirm_by_word(pack, sign_word),
           reviewer=reviewer, output_dir=output_dir, sign=sign_word is not None)
    saved_at = _utc_now()
    pdf_path = save_pack(pack, output_dir)
    notices = [w for w in pack.warnings if w in SIGN_OFF_WARNINGS]
    return PipelineResult(pack=pack, pdf_path=pdf_path, audit_path=output_dir / AUDIT_FILE,
                          notices=notices, saved_at=saved_at)
