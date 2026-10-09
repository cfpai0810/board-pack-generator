# =============================================================================
# step6_review.py: Layer 7: human review, sign-off, and the audit record
# =============================================================================
"""
The controller reads every section, edits or accepts it, sees every
outstanding flag, and signs, or does not.

Finance reasoning: the pack is not a pack until a person owns it. The code
computed the numbers and the model or the template drafted the words, but
signing off is a human act of responsibility. This is also where the
reasons go in: the controller knows the factory was closed and the model
does not. So review lets the controller edit every narrative (and only the
narrative: figures, flags and drivers are computed and cannot be changed
here), shows them every outstanding flag before they sign, and records
exactly what was drafted, what they changed and what they accepted
knowingly.

The human seam is injected, as it was designed from the start:
    ask(title, text, warnings) -> str
        once per section in order; returns the final text, and returning
        the text unchanged (or None) accepts it.
    confirm(summary) -> bool
        once, with the sign-off summary as a list of plain sentences.
The CLI passes terminal prompts and the web layer passes UI callbacks; this
module never imports streamlit and never calls input().

An edited section is checked again: a figure that matches nothing in the
pack is flagged as raised on the reviewer's text (a typo such as £1.46m for
£1.64m is caught before signing), and a flag whose text the edit removed is
marked resolved. Cause phrases are not sought in the reviewer's text: the
reasons are theirs to give.

Before the sign-off summary, every section's final text (template, model
or reviewer) is checked for characters the PDF font cannot print: each
becomes a glyph flag, so an approximately-equals sign typed by the reviewer
is fixed before it reaches the board as a question mark.

record_draft() is the draft-only path: no prompts and no sign-off, but the
same glyph check and a review audit line marked DRAFT. There is
deliberately no path that signs without a person.

Sign-off needs a confirm and a reviewer name. A FINAL pack records who and
when (UTC), and everything outstanding at that moment as acknowledged.
Otherwise the pack stays DRAFT and nothing is lost. Every run appends one
line to the audit log, whatever the outcome; earlier lines are never
rewritten. A pack already FINAL cannot be reviewed again: a signed pack is
changed by a new run, not by editing.
"""

from __future__ import annotations

import copy
import json
import subprocess
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

from config import ROOT, VERSION
from src.formatting import unprintable
from src.state import (
    DRAFT_TEXT, GLYPH, NUMERIC, REVIEWER_TEXT, SUBTOTALS, Flag, Pack, PackStatus,
    Section, SectionType,
)
from src.step5_narrate import (
    comparison_set, find_cause_phrases, find_direction_phrases, unmatched_tokens,
)

AUDIT_FILE = "audit.jsonl"

Ask = Callable[[str, str, list[str]], Optional[str]]
Confirm = Callable[[list[str]], bool]


class AlreadySignedOff(ValueError):
    """review() was called on a FINAL pack."""


# -- The sign-off rule, shared by the terminal and the web ------------------------

SIGN_WORD = "SIGN"
NAME_WARNING = "review: sign-off needs a reviewer name, so the pack stays DRAFT"
SIGN_WARNING = "review: sign-off needs the word SIGN typed exactly, so the pack stays DRAFT"
SIGN_OFF_WARNINGS = (NAME_WARNING, SIGN_WARNING)


def is_sign_word(text: Optional[str]) -> bool:
    """The one SIGN rule: the word SIGN exactly (spaces around it ignored). 'sign' is not SIGN."""
    return text is not None and text.strip() == SIGN_WORD


def confirm_by_word(pack: Pack, word: Optional[str]) -> Confirm:
    """
    A confirm for a screen where the reviewer types the word. True only for
    exactly SIGN. Any other word (blank included) means a sign-off was
    attempted and refused, so the engine records SIGN_WARNING in the pack
    and in this run's audit line. None means the reviewer chose to save a
    draft: never True, and no warning.
    """
    def confirm(summary: list[str]) -> bool:
        if word is None:
            return False
        if is_sign_word(word):
            return True
        pack.warnings.append(SIGN_WARNING)
        return False
    return confirm


def answers_ask(pack: Pack, answers: dict[str, str]) -> Ask:
    """
    An ask that returns the text already edited on a screen for each section
    (keyed by section: "exec_summary", "pnl", "kpis", "cash"), or the current
    text for a section with no answer.
    """
    keys = {section.title: section.section_type.value for section in pack.sections}
    return lambda title, text, warnings: answers.get(keys[title], text)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def code_version() -> str:
    """
    The short git commit of the project, with "+uncommitted" when the
    working tree differs from it, or config.VERSION when git is not
    available. The input hashes reproduce the figures only with the same
    code: a later fix could change a figure from the same inputs, so a
    signed pack must name the exact code, and must not claim a commit it
    was not built from.
    """
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=5)
    try:
        head = git("rev-parse", "--short", "HEAD")
        commit = head.stdout.strip()
        if head.returncode != 0 or not commit:
            return VERSION
        status = git("status", "--porcelain")
    except (OSError, subprocess.SubprocessError):
        return VERSION
    clean = status.returncode == 0 and not status.stdout.strip()
    return commit if clean else f"{commit}+uncommitted"


# -- Flags during review ------------------------------------------------------

def outstanding_flags(pack: Pack, section: Optional[str] = None) -> list[Flag]:
    """Unresolved numeric, cause, direction then glyph flags, for one section or all."""
    flags = (pack.numeric_warnings + pack.cause_warnings + pack.direction_warnings
             + pack.glyph_warnings)
    return [f for f in flags
            if not f.resolved and (section is None or f.section == section)]


def check_glyphs(pack: Pack) -> None:
    """
    Flag every character in each section's final text that the PDF font
    cannot print, resolving earlier glyph flags whose character has gone.
    A character the reviewer typed is marked as raised on their text.
    """
    for section in pack.sections:
        key = section.section_type.value
        found = unprintable(section.narrative)
        open_flags = [f for f in pack.glyph_warnings if f.section == key and not f.resolved]
        for flag in open_flags:
            if flag.text not in found:
                flag.resolved = True
        flagged = {f.text for f in open_flags if f.text in found}
        for ch in found:
            if ch not in flagged:
                from_reviewer = section.edited and ch not in section.draft
                pack.glyph_warnings.append(Flag(
                    section=key, kind=GLYPH, text=ch,
                    raised_on=REVIEWER_TEXT if from_reviewer else DRAFT_TEXT))


def recheck_section(pack: Pack, section: Section, figures: dict) -> None:
    """
    After an edit: a flag whose text is no longer in the section is
    resolved; a numeric token new in the reviewer's text is flagged as
    raised on it. Cause and direction phrases are only ever sought in model
    prose, so an edit can resolve those flags but never raise one.
    """
    key = section.section_type.value
    tokens = unmatched_tokens(section.narrative, pack, figures)
    phrases = set(find_cause_phrases(section.narrative))
    offsets = set(find_direction_phrases(section.narrative))

    still_flagged = set()
    for flag in pack.numeric_warnings:
        if flag.section == key and not flag.resolved:
            if flag.text in tokens:
                still_flagged.add(flag.text)
            else:
                flag.resolved = True
    for flag in pack.cause_warnings:
        if flag.section == key and not flag.resolved and flag.text not in phrases:
            flag.resolved = True
    for flag in pack.direction_warnings:
        if flag.section == key and not flag.resolved and flag.text not in offsets:
            flag.resolved = True

    pack.numeric_warnings.extend(
        Flag(section=key, kind=NUMERIC, text=token, raised_on=REVIEWER_TEXT)
        for token in tokens if token not in still_flagged
    )


def check_text(pack: Pack, section: str, text: str) -> list[Flag]:
    """
    The numeric and glyph checks on a piece of text for one section, as
    flags, without changing the pack. This is what a reviewer's screen calls
    to show flags live while they edit: the same unmatched_tokens and
    unprintable checks review() applies, so no display layer ever
    re-implements one.

    section is the section's key ("exec_summary", "pnl", "kpis", "cash").
    A flag whose token or character is already in that section's draft
    (what the model or template wrote) is marked as raised on the draft;
    anything new is raised on the reviewer's text. Cause and direction
    phrases are not sought: they are checked only in model prose.
    """
    target = next(s for s in pack.sections if s.section_type.value == section)
    draft = target.draft or target.narrative
    origin = lambda found_in_draft: DRAFT_TEXT if found_in_draft else REVIEWER_TEXT
    flags = [
        Flag(section=section, kind=NUMERIC, text=token,
             raised_on=origin(token in unmatched_tokens(draft, pack)))
        for token in unmatched_tokens(text, pack)
    ]
    flags += [
        Flag(section=section, kind=GLYPH, text=ch, raised_on=origin(ch in draft))
        for ch in unprintable(text)
    ]
    return flags


def signoff_summary(pack: Pack) -> list[str]:
    """
    Everything the reviewer should see before signing: outstanding numeric,
    cause, direction and glyph flags, load, validation and narrate warnings, and a plain
    statement when the totals exclude rows that could not be loaded.
    """
    summary = [f.message for f in outstanding_flags(pack)]
    summary += list(pack.warnings)
    n = pack.excluded_pnl_rows
    if n:
        rows = "row" if n == 1 else "rows"
        summary.append(
            f"The totals exclude {n} P&L {rows} that could not be loaded, "
            f"so they do not tie to the source file."
        )
    return summary


# -- The audit record ---------------------------------------------------------

def _flag_record(flag: Flag) -> dict:
    return {
        "section": flag.section,
        "kind": flag.kind,
        "text": flag.text,
        "raised_on": flag.raised_on,
        "resolved": flag.resolved,
        "message": flag.message,
    }


def headline_figures(pack: Pack) -> dict:
    """
    The five subtotals and the gross margin, actual, budget and prior year,
    as exact strings: what the board saw, readable in the JSONL without
    rerunning anything.
    """
    s = pack.subtotals
    as_text = lambda v: None if v is None else str(v)
    headline = {
        prefix: {
            "actual": as_text(getattr(s, f"{prefix}_actual")),
            "budget": as_text(getattr(s, f"{prefix}_budget")),
            "prior_year": as_text(getattr(s, f"{prefix}_py")),
        }
        for prefix, _ in SUBTOTALS
    }
    headline["gross_margin"] = {
        "actual": as_text(s.gross_margin_actual),
        "budget": as_text(s.gross_margin_budget),
        "prior_year": as_text(s.gross_margin_py),
    }
    return headline


def _drivers_record(pack: Pack) -> dict:
    """The computed drivers of each material subtotal, with their impact on profit."""
    drivers = pack.section(SectionType.EXEC_SUMMARY).figures["drivers"]
    return {
        key: [{"key": d["key"], "name": d["name"], "impact": d["impact"]} for d in lines]
        for key, lines in drivers.items()
    }


def audit_record(pack: Pack, *, run_id: str, timestamp: str, reviewer: str,
                 mode: str = "interactive") -> dict:
    """One review run as a JSON-ready dict (Decimals are written as exact strings)."""
    flags = pack.material_flags
    placement = {k: "exec_summary" for k in flags.exec_summary_items}
    placement.update({k: "pnl_commentary" for k in flags.pnl_commentary_items})
    used_model = bool(pack.narrative_model)
    signed = pack.status is PackStatus.FINAL
    return {
        "run_id": run_id,
        "event": "review",
        "mode": mode,
        "timestamp": timestamp,
        "code_version": pack.code_version,
        "entity": pack.entity,
        "period": pack.period,
        "status": pack.status.value,
        "inputs": {
            "pnl_sha256": pack.pnl_sha256,
            "kpis_sha256": pack.kpis_sha256,
            "excluded_pnl_rows": pack.excluded_pnl_rows,
        },
        "headline": headline_figures(pack),
        "materiality": {
            "materiality_abs": flags.materiality_abs,
            "materiality_pct": flags.materiality_pct,
            "material": [
                {"key": k, "name": pack.item(k)["name"], "placement": placement[k]}
                for k in flags.all_material
            ],
            "drivers": _drivers_record(pack),
        },
        "sections": [
            {
                "section": s.section_type.value,
                "drafted_by": s.drafted_by,
                "draft": s.draft,
                "final": s.narrative,
                "edited": s.edited,
            }
            for s in pack.sections
        ],
        "model": {
            "id": pack.narrative_model if used_model else None,
            "input_tokens": pack.narrative_input_tokens if used_model else None,
            "output_tokens": pack.narrative_output_tokens if used_model else None,
        },
        "numeric_warnings": [_flag_record(f) for f in pack.numeric_warnings],
        "cause_warnings": [_flag_record(f) for f in pack.cause_warnings],
        "direction_warnings": [_flag_record(f) for f in pack.direction_warnings],
        "glyph_warnings": [_flag_record(f) for f in pack.glyph_warnings],
        "warnings": list(pack.warnings),
        "acknowledged": list(pack.acknowledged),
        "reviewer": reviewer or None,
        "sign_off_by": pack.sign_off_by if signed else None,
        "sign_off_at": pack.sign_off_at if signed else None,
    }


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def write_audit(record: dict, output_dir: Path) -> Path:
    """Append one JSON line to output_dir/audit.jsonl; never rewrite earlier lines."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / AUDIT_FILE
    line = json.dumps(record, default=_json_default, ensure_ascii=False)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")
    return path


# -- Orchestrator -------------------------------------------------------------

def review(
    pack: Pack,
    *,
    ask: Ask,
    confirm: Confirm,
    reviewer: str,
    output_dir: Path,
    sign: bool = True,
) -> Pack:
    """
    Run the review: ask about each section, recheck edits, summarise what
    is outstanding, ask for sign-off, and append the audit line.

    Raises AlreadySignedOff on a FINAL pack. A blank reviewer cannot sign:
    confirm is not asked, a warning is added and the pack stays DRAFT.
    sign=False records the review without attempting sign-off (a screen's
    "Save as draft"): confirm is never asked and no sign-off warning is
    added, because nobody tried to sign.
    """
    run_at = _start_run(pack)
    _clear_sign_off_warnings(pack)
    _apply_answers(pack, ask, comparison_set(pack))

    name = (reviewer or "").strip()
    if not sign:
        pass
    elif not name:
        pack.warnings.append(NAME_WARNING)
    else:
        summary = signoff_summary(pack)
        if confirm(summary):
            pack.status = PackStatus.FINAL
            pack.sign_off_by = name
            pack.sign_off_at = _utc_now()
            pack.acknowledged = summary

    record = audit_record(pack, run_id=pack.run_id, timestamp=run_at, reviewer=name)
    write_audit(record, output_dir)
    return pack


def _apply_answers(pack: Pack, ask: Ask, figures: dict) -> None:
    """
    Ask about each section in order, keep each final text, recheck what was
    edited, record the edits, and check every section for unprintable
    characters. Shared by review() and preview_signoff(), so the summary a
    screen shows is built by the same code that review() uses.
    """
    for section in pack.sections:
        current = section.narrative
        key = section.section_type.value
        answer = ask(section.title, current,
                     [f.message for f in outstanding_flags(pack, key)])
        final = current if answer is None else answer.strip()
        if final != current:
            section.narrative = final
            recheck_section(pack, section, figures)

    pack.reviewer_edits = {
        s.section_type.value: s.narrative for s in pack.sections if s.edited
    }
    check_glyphs(pack)


def _clear_sign_off_warnings(pack: Pack) -> None:
    """
    The two sign-off warnings describe one attempt, so each run starts
    without them; otherwise a refused attempt on a web pack would still be
    listed when the reviewer tries again. The audit line of the refused
    attempt keeps its warning.
    """
    for warning in SIGN_OFF_WARNINGS:
        while warning in pack.warnings:
            pack.warnings.remove(warning)


def preview_signoff(pack: Pack, answers: dict[str, str]) -> list[str]:
    """
    The sign-off summary review() would pass to confirm if these texts were
    submitted now. Runs the same steps on a copy, so the pack itself is
    unchanged and no audit line is written.
    """
    trial = copy.deepcopy(pack)
    _clear_sign_off_warnings(trial)
    for section in trial.sections:
        if not section.draft:
            section.draft = section.narrative
    _apply_answers(trial, answers_ask(trial, answers), comparison_set(trial))
    return signoff_summary(trial)


def audit_text(output_dir: Path, run_id: Optional[str] = None) -> str:
    """
    The audit log's lines as JSONL text, all of them or only those of one
    run (its review and rendered lines). Empty when there is no log yet.
    """
    path = Path(output_dir) / AUDIT_FILE
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    if run_id is not None:
        lines = [line for line in lines if json.loads(line).get("run_id") == run_id]
    return "".join(line + "\n" for line in lines)


def _start_run(pack: Pack) -> str:
    """Refuse a FINAL pack, start a new run, keep the first draft text. Returns the run time."""
    if pack.status is PackStatus.FINAL:
        raise AlreadySignedOff(
            "This pack is already signed off (FINAL). A signed pack is changed "
            "by a new run, not by editing."
        )
    pack.run_id = uuid.uuid4().hex
    pack.code_version = code_version()
    for section in pack.sections:
        if not section.draft:
            section.draft = section.narrative       # what the model or template wrote
    return _utc_now()


def record_draft(pack: Pack, *, output_dir: Path) -> Pack:
    """
    The draft-only path: no prompts, nothing edited, no sign-off. Runs the
    glyph check and appends a review audit line marked DRAFT (mode
    draft_only), so a draft PDF is still tied to a run in the audit.
    """
    run_at = _start_run(pack)
    check_glyphs(pack)
    record = audit_record(pack, run_id=pack.run_id, timestamp=run_at, reviewer="",
                          mode="draft_only")
    write_audit(record, output_dir)
    return pack
