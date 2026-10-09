# =============================================================================
# build_worked_example.py: the signed sample pack the Board pack page shows
# =============================================================================
"""
Build the worked example: the sample files, drafted by the template,
reviewed by a fixed reviewer who adds one reason of their own, and signed
at a fixed time. Every step runs through the engine (run_pipeline with a
scripted ask and confirm), so the files are what a real review produces.

Writes generated/worked_example/:
    the FINAL PDF          the file the reviewer signed
    audit.jsonl            its two audit lines: the review and the rendered
                           event, linked by run id, with the PDF's SHA-256
    page_1.png, ...        each page of that PDF as an image, for the page to
                           show without running anything
    pages.json             the images' names and the SHA-256 of the PDF they
                           were drawn from, which must equal the hash in the
                           rendered audit line

The images are drawn with pypdfium2, a build-time dependency listed in
requirements-dev.txt only: the deployed app shows the images and never
rasterises anything.

Rebuild at each release, from a clean working tree: the PDF prints the
code version, so new code means new bytes, and a test checks that a fresh
build still says what the committed PDF says.

    python scripts/build_worked_example.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import KPIS_PATH, PNL_PATH  # noqa: E402
from src.pipeline import (  # noqa: E402
    SECTION_TITLES, SectionType, audit_text, file_sha256, run_pipeline,
)

OUT = ROOT / "generated" / "worked_example"
AUDIT_NAME = "audit.jsonl"
PAGES_NAME = "pages.json"
SCALE = 1.6                 # 1.6 times A4 at 72 points per inch: 953 by 1348 pixels

REVIEWER = "A. Controller"
REASON = (" The Retail shortfall followed a fortnight's closure of the Leeds site, "
          "which cost £20k in lost sales.")
SIGNED_AT = "2026-07-08T09:00:00+00:00"


def ask(title: str, text: str, warnings: list[str]) -> str:
    """The reviewer's one edit: a reason only they know, added to the executive summary."""
    return text + REASON if title == SECTION_TITLES[SectionType.EXEC_SUMMARY.value] else text


def confirm(summary: list[str]) -> bool:
    """The reviewer reads what is outstanding (their own £20k, flagged) and types SIGN."""
    return True


def draw_pages(pdf: Path, out: Path) -> list[str]:
    """Each page of the PDF as a PNG beside it; returns the file names in page order."""
    import pypdfium2 as pdfium      # build time only: requirements-dev.txt
    document = pdfium.PdfDocument(str(pdf))
    names = []
    try:
        for i in range(len(document)):
            name = f"page_{i + 1}.png"
            document[i].render(scale=SCALE).to_pil().save(out / name, optimize=True)
            names.append(name)
    finally:
        document.close()
    return names


def build(out: Path = OUT, images: bool = True) -> dict[str, Path]:
    """
    Run the review, then write the PDF, its audit lines and (unless images
    is False, as in the test that checks a fresh build) its page images.
    """
    out = Path(out)
    with tempfile.TemporaryDirectory(prefix="worked_example_") as tmp:
        result = run_pipeline(PNL_PATH, KPIS_PATH, Path(tmp), ask=ask, confirm=confirm,
                              reviewer=REVIEWER, now=SIGNED_AT)
        out.mkdir(parents=True, exist_ok=True)
        stale = [*out.glob("*.pdf"), *out.glob("page_*.png"), out / AUDIT_NAME,
                 out / PAGES_NAME, out / "screen.json"]
        for path in stale:
            path.unlink(missing_ok=True)
        pdf = out / result.pdf_path.name
        shutil.copyfile(result.pdf_path, pdf)
        audit = out / AUDIT_NAME
        audit.write_text(audit_text(Path(tmp), result.pack.run_id), encoding="utf-8",
                         newline="\n")
    files = {"pdf": pdf, "audit": audit}
    if images:
        pages = out / PAGES_NAME
        manifest = {"pdf_name": pdf.name, "pdf_sha256": file_sha256(pdf),
                    "pages": draw_pages(pdf, out), "scale": SCALE}
        pages.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
        files["pages"] = pages
    return files


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for kind, path in build().items():
        print(f"{kind}: {path.relative_to(ROOT)}")
