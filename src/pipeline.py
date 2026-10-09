# =============================================================================
# pipeline.py: Shared Orchestrator: one headless run from CSV files to a pack
# =============================================================================
"""
run_pipeline() is the whole governance story as one flow: the code loads,
checks and computes every figure, the rule selects what is material, the
narrative is drafted inside those figures, a named person reviews and
signs, and the pack is rendered with its audit trail.

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
the entity and period that head the pack, the unit the KPI file states
cash in, and the materiality thresholds. Left out, each comes from config,
which describes the sample. Nothing downstream reads config for them: it
reads the Pack.

This module is also the ONE public surface of src/ for the web layer:
streamlit_app/ imports nothing else from src/. Besides run_pipeline it
offers the review stage as thin wrappers over the step code
(review_and_save, signoff_summary, check_text, audit_text), the input
checks a form needs (parse_materiality, CASH_UNITS), and re-exports the
display rows, palette and types a page needs. __all__ lists it all.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Optional

from src.formatting import when_text
from src.notes import row_handling
from src.state import (
    DRAFT_TEXT, GLYPH, NUMERIC, REVIEWER_TEXT, SECTION_TITLES, Flag, Pack, PackStatus,
    SectionType,
)
from src.step1_load import MissingColumns, load
from src.step2_validate import validate
from src.step3_compute import compute
from src.step4_assemble import assemble
from src.step5_narrate import narrate
from src.step6_review import (
    AUDIT_FILE, NAME_WARNING, SIGN_OFF_WARNINGS, SIGN_WARNING, SIGN_WORD, Ask,
    Confirm, _utc_now, answers_ask, audit_text, check_text, confirm_by_word,
    excluded_rows_note, is_sign_word, preview_signoff, record_draft, review,
)
from src.step7_render import save_pack
from src.tables import (
    DRAFT_HEX, DRIVERS_HEADER, DRIVERS_NOTE, FINAL_HEX, MATERIAL_HEX, PNL_HEADER,
    RULE_HEX, DriverRow, PnlRow, commentary_source, drivers_rows, pnl_notes, pnl_rows,
)

__all__ = [
    # the run
    "run_pipeline", "PipelineError", "PipelineResult",
    # the inputs of a run
    "parse_materiality", "CASH_UNITS",
    # the review stage
    "review_and_save", "signoff_summary", "check_text", "audit_text",
    "is_sign_word", "SIGN_WORD", "NAME_WARNING", "SIGN_WARNING",
    # what a page displays
    "pnl_rows", "drivers_rows", "PnlRow", "DriverRow", "PNL_HEADER", "DRIVERS_HEADER",
    "pnl_notes", "DRIVERS_NOTE", "when_text", "SECTION_TITLES", "commentary_source",
    "row_handling",
    "DRAFT_HEX", "FINAL_HEX", "MATERIAL_HEX", "RULE_HEX",
    # types and constants
    "Pack", "PackStatus", "SectionType", "Flag", "NUMERIC", "GLYPH",
    "DRAFT_TEXT", "REVIEWER_TEXT",
]


class PipelineError(Exception):
    """A problem with the inputs that a person can fix, stated plainly."""


CASH_UNITS = {"thousands": 1000, "pounds": 1}
"""What one unit of the cash KPI is worth in pounds, by the unit the KPI file states it in."""


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
_ABS_RULE = "The absolute threshold must be a positive amount in pounds, such as 50,000."
_PCT_RULE = "The percentage threshold must be above 0 and at most 100, such as 10."


def parse_materiality(abs_text: str, pct_text: str) -> tuple[Decimal, Decimal]:
    """
    The two thresholds as a person types them ("50,000" or "£50,000"; "10" or
    "10%"), as Decimals. The amount must be positive and the percentage above
    0 and at most 100; otherwise PipelineError says what to type.
    """
    amount = abs_text.strip().removeprefix("£").replace(",", "").strip()
    percent = pct_text.strip().removesuffix("%").strip()
    problems = []
    if not _PLAIN_NUMBER.match(amount) or Decimal(amount) <= 0:
        problems.append(_ABS_RULE)
    if not _PLAIN_NUMBER.match(percent) or not 0 < Decimal(percent) <= 100:
        problems.append(_PCT_RULE)
    if problems:
        raise PipelineError(" ".join(problems))
    return Decimal(amount), Decimal(percent)


def _check_inputs(materiality_abs, materiality_pct, entity, period, cash_scale) -> None:
    """The run's own inputs, checked before any file is read."""
    if materiality_abs is not None and not Decimal(str(materiality_abs)) > 0:
        raise PipelineError(_ABS_RULE)
    if materiality_pct is not None and not 0 < Decimal(str(materiality_pct)) <= 100:
        raise PipelineError(_PCT_RULE)
    for label, value in (("entity name", entity), ("period", period)):
        if value is not None and not value.strip():
            raise PipelineError(f"The {label} is blank. Type the {label} the pack is for.")
    if cash_scale is not None and cash_scale not in CASH_UNITS.values():
        raise PipelineError("Cash in the KPI file must be stated in thousands or in pounds.")


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
    draft_only: bool = False,
) -> PipelineResult:
    """
    Load, validate, compute, assemble, narrate, review (or record a draft),
    then render and save the pack. Returns the pack, the PDF path, the
    audit path, and the notes on the data and the drafting.

    An interactive run needs ask and confirm; draft_only=True needs neither
    and never signs. kpis_path=None runs without a KPI file: the KPI section
    then holds only the gross margin derived from the P&L, and the cash
    section says no cash balance was supplied. entity, period, cash_scale
    (CASH_UNITS: 1000 when the KPI file states cash in thousands, 1 in
    pounds) and the thresholds left as None come from config, the sample.
    client=None drafts with the template.

    A problem the person can fix raises PipelineError before anything is
    written: a missing file, a missing column, a P&L with no loadable
    lines, a blank entity or period, a threshold out of range.
    """
    if not draft_only and (ask is None or confirm is None):
        raise ValueError("A review needs ask and confirm; use draft_only=True to skip review.")
    _check_inputs(materiality_abs, materiality_pct, entity, period, cash_scale)
    for path in (pnl_path, kpis_path):
        if path is not None and not Path(path).is_file():
            raise PipelineError(f"Input file not found: {path}")

    try:
        loaded = load(Path(pnl_path), None if kpis_path is None else Path(kpis_path))
    except MissingColumns as e:
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
        cash_scale=cash_scale, kpis_supplied=kpis_path is not None,
    )
    data_notes = list(pack.warnings)
    if pack.excluded_pnl_rows:
        data_notes.append(excluded_rows_note(pack))
    before = len(pack.warnings)
    narrate(pack, client=client)
    narrate_notices = pack.warnings[before:]

    output_dir = Path(output_dir)
    if draft_only:
        record_draft(pack, output_dir=output_dir)
    else:
        review(pack, ask=ask, confirm=confirm, reviewer=reviewer, output_dir=output_dir)

    saved_at = _utc_now()
    pdf_path = save_pack(pack, output_dir)
    return PipelineResult(pack=pack, pdf_path=pdf_path, audit_path=output_dir / AUDIT_FILE,
                          saved_at=saved_at, data_notes=data_notes,
                          narrate_notices=narrate_notices)


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
