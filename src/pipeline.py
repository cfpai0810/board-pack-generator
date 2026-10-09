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

All the logic lives here so the CLI (main.py) and the future web layer call
the same engine with their own ask and confirm. Nothing here reads input or
prints. A problem the user can fix (a missing file, a P&L with nothing
loadable) raises PipelineError with a plain message.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

from src.state import Pack
from src.step1_load import load
from src.step2_validate import validate
from src.step3_compute import compute
from src.step4_assemble import assemble
from src.step5_narrate import narrate
from src.step6_review import AUDIT_FILE, Ask, Confirm, record_draft, review
from src.step7_render import save_pack


class PipelineError(Exception):
    """A problem with the inputs that a person can fix, stated plainly."""


@dataclass
class PipelineResult:
    pack: Pack
    pdf_path: Path
    audit_path: Path


def run_pipeline(
    pnl_path: Path,
    kpis_path: Path,
    output_dir: Path,
    *,
    ask: Optional[Ask] = None,
    confirm: Optional[Confirm] = None,
    reviewer: str = "",
    client=None,
    materiality_abs: Optional[Decimal] = None,
    materiality_pct: Optional[Decimal] = None,
    draft_only: bool = False,
) -> PipelineResult:
    """
    Load, validate, compute, assemble, narrate, review (or record a draft),
    then render and save the pack. Returns the pack, the PDF path and the
    audit path.

    An interactive run needs ask and confirm; draft_only=True needs neither
    and never signs. Thresholds left as None use config. client=None drafts
    with the template.
    """
    if not draft_only and (ask is None or confirm is None):
        raise ValueError("A review needs ask and confirm; use draft_only=True to skip review.")
    for path in (pnl_path, kpis_path):
        if not Path(path).is_file():
            raise PipelineError(f"Input file not found: {path}")

    try:
        loaded = load(Path(pnl_path), Path(kpis_path))
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
        loaded.excluded_pnl_rows, pnl_sha256=loaded.pnl_sha256,
        kpis_sha256=loaded.kpis_sha256, **thresholds,
    )
    narrate(pack, client=client)

    output_dir = Path(output_dir)
    if draft_only:
        record_draft(pack, output_dir=output_dir)
    else:
        review(pack, ask=ask, confirm=confirm, reviewer=reviewer, output_dir=output_dir)

    pdf_path = save_pack(pack, output_dir)
    return PipelineResult(pack=pack, pdf_path=pdf_path, audit_path=output_dir / AUDIT_FILE)
