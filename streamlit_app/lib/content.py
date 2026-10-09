# =============================================================================
# lib/content.py: what the explanation pages read, never what they type
# =============================================================================
# Every figure an explanation page quotes comes from one of three sources,
# so none can drift from what the engine produces:
#   - the sample pack, built once per server by src.pipeline.build_pack
#     (nothing is reviewed, rendered or written);
#   - the worked example in generated/worked_example/, built at release by
#     scripts/build_worked_example.py through the engine: the signed PDF, its
#     audit lines, and images of its pages drawn from that PDF;
#   - the test counts in generated/test_counts.json, written by the test run.
# Reading files here is presentation: no figure is computed in this module.
# =============================================================================

import csv
import io
import json
from pathlib import Path

import streamlit as st

from config import KPIS_PATH, PNL_PATH, ROOT
from src.pipeline import build_pack, file_sha256

GENERATED = ROOT / "generated"
WORKED = GENERATED / "worked_example"
COUNTS = GENERATED / "test_counts.json"


@st.cache_resource(show_spinner=False)
def sample_pack():
    """The sample's narrated DRAFT pack, built once and shared. Read it; never change it."""
    return build_pack(PNL_PATH, KPIS_PATH)


@st.cache_data(show_spinner=False)
def worked_example() -> dict:
    """
    The signed sample pack as committed: the PDF's bytes and name, its audit
    lines as written and as records, the images of its pages with the hash of
    the PDF they were drawn from, and the SHA-256 of the PDF file, computed
    now, to set beside the hashes the audit and the images recorded.
    """
    pdf = next(WORKED.glob("*.pdf"))
    audit_text = (WORKED / "audit.jsonl").read_text(encoding="utf-8")
    records = [json.loads(line) for line in audit_text.splitlines()]
    pages = json.loads((WORKED / "pages.json").read_text(encoding="utf-8"))
    return {
        "pdf": pdf.read_bytes(),
        "pdf_name": pdf.name,
        "pdf_sha256": file_sha256(pdf),
        "audit_text": audit_text,
        "review": next(r for r in records if r["event"] == "review"),
        "rendered": next(r for r in records if r["event"] == "rendered"),
        "pages": [WORKED / name for name in pages["pages"]],
        "pages_drawn_from": pages["pdf_sha256"],
    }


def test_counts() -> dict | None:
    """The test counts the last full passing run wrote, or None before any has."""
    if not COUNTS.is_file():
        return None
    return json.loads(COUNTS.read_text(encoding="utf-8"))


def sample_rows(which: str, n: int = 3) -> tuple[list[str], list[list[str]]]:
    """The header and first n rows of a sample file ('pnl' or 'kpis'), exactly as in the file."""
    path = PNL_PATH if which == "pnl" else KPIS_PATH
    rows = list(csv.reader(io.StringIO(Path(path).read_text(encoding="utf-8-sig"))))
    return rows[0], rows[1:1 + n]
