# =============================================================================
# lib/inputs.py: the inputs of a run, from the form to run_pipeline
# =============================================================================
# The "Run it yourself" form gathers the source files, the entity and period,
# the unit cash is stated in, the materiality thresholds and the commentary
# choice. This module checks only what the web layer alone knows (an
# upload's size and length, and that the form is complete), stages the
# uploaded bytes in the session's own temporary folder, and hands everything
# to run_pipeline. Every finance check (columns, rows, names, thresholds) is
# the engine's, so the CLI and the web refuse the same inputs in the same
# words.
#
# Uploaded bytes go to <session folder>/inputs/ under fixed names (never the
# uploaded file name), are read once by the pipeline, and are deleted as soon
# as the run ends, whether it succeeded or not. The pack keeps their SHA-256
# hashes in the audit, so the exact files stay identifiable without being
# kept.
# =============================================================================

import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from config import KPIS_PATH, PNL_PATH
from src.pipeline import (
    CASH_UNITS, PipelineError, PipelineResult, default_threshold_inputs, parse_materiality,
    run_pipeline,
)

MAX_MB = 1
MAX_BYTES = MAX_MB * 1024 * 1024
MAX_PNL_LINES = 500

SAMPLE, OWN = "Use the sample", "Use my own files"
TEMPLATE, MODEL = "Template", "Model"
CASH_CHOICES = {"thousands": "Thousands (as in the sample)", "pounds": "Pounds"}
DEFAULT_ABS, DEFAULT_PCT = default_threshold_inputs()


class UploadError(PipelineError):
    """An upload or a form the person can fix, stated plainly."""


@dataclass(frozen=True)
class Upload:
    name: str
    data: bytes


@dataclass(frozen=True)
class RunInputs:
    """Everything a draft is built from. Two equal RunInputs build the same draft."""
    source: str = SAMPLE
    pnl: Optional[Upload] = None
    kpis: Optional[Upload] = None
    entity: str = ""
    period: str = ""
    cash_unit: str = "thousands"
    materiality_abs: str = DEFAULT_ABS
    materiality_pct: str = DEFAULT_PCT
    commentary: str = TEMPLATE

    def effective(self) -> "RunInputs":
        """The inputs that matter: with the sample, the own-file fields are ignored."""
        if self.source == OWN:
            return self
        return replace(self, pnl=None, kpis=None, entity="", period="", cash_unit="thousands")


def _kb(n_bytes: int) -> str:
    return f"{(n_bytes + 1023) // 1024:,} KB"


def _data_lines(data: bytes) -> int:
    """Lines with content after the header row."""
    return max(sum(1 for line in data.splitlines() if line.strip()) - 1, 0)


def check_upload(label: str, upload: Upload, max_lines: Optional[int] = None) -> None:
    """Refuse a file over 1 MB, or with more data lines than max_lines."""
    if len(upload.data) > MAX_BYTES:
        raise UploadError(f"The {label} file is {_kb(len(upload.data))}; the limit is "
                          f"{MAX_MB} MB. Upload a smaller file.")
    lines = _data_lines(upload.data)
    if max_lines is not None and lines > max_lines:
        raise UploadError(f"The {label} file has {lines:,} lines; the limit is "
                          f"{max_lines:,}. A monthly P&L is usually far shorter.")


def check_form(inputs: RunInputs) -> None:
    """With own files: a P&L file, an entity and a period are required. One message for all gaps."""
    if inputs.source != OWN:
        return
    missing = []
    if inputs.pnl is None:
        missing.append("upload a P&L CSV file (the KPI file is optional)")
    if not inputs.entity.strip():
        missing.append("type the entity name")
    if not inputs.period.strip():
        missing.append("type the period, such as September 2026")
    if missing:
        text = "; ".join(missing)
        raise UploadError(f"To build from your own files, {text}.")
    check_upload("P&L", inputs.pnl, MAX_PNL_LINES)
    if inputs.kpis is not None:
        check_upload("KPI", inputs.kpis)


def stage(inputs: RunInputs, folder: Path) -> tuple[Path, Optional[Path]]:
    """
    The paths run_pipeline reads: the sample's own files, or the uploads
    written to <folder>/inputs/ under fixed names. Checks first, so nothing
    is written for a form that is refused.
    """
    check_form(inputs)
    if inputs.source != OWN:
        return PNL_PATH, KPIS_PATH
    staged = Path(folder) / "inputs"
    staged.mkdir(parents=True, exist_ok=True)
    pnl_path = staged / "pnl.csv"
    pnl_path.write_bytes(inputs.pnl.data)
    kpis_path = None
    if inputs.kpis is not None:
        kpis_path = staged / "kpis.csv"
        kpis_path.write_bytes(inputs.kpis.data)
    return pnl_path, kpis_path


def build_draft(inputs: RunInputs, folder: Path, client=None) -> PipelineResult:
    """
    Build the DRAFT from the form: thresholds parsed by the engine, uploads
    staged, run_pipeline run as a draft, staged uploads deleted. client is
    the session's model client, or None for the template. Raises
    PipelineError (UploadError included) with a plain message; nothing of a
    refused run is left behind.
    """
    materiality_abs, materiality_pct = parse_materiality(inputs.materiality_abs,
                                                         inputs.materiality_pct)
    own = inputs.source == OWN
    try:
        pnl_path, kpis_path = stage(inputs, folder)
        return run_pipeline(
            pnl_path, kpis_path, folder, draft_only=True, client=client,
            materiality_abs=materiality_abs, materiality_pct=materiality_pct,
            entity=inputs.entity if own else None,
            period=inputs.period if own else None,
            cash_scale=CASH_UNITS[inputs.cash_unit] if own else None,
        )
    finally:
        shutil.rmtree(Path(folder) / "inputs", ignore_errors=True)
