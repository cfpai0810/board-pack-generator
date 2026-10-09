# =============================================================================
# step7_render.py: Layer 8: the board pack as a PDF, and the rendered event
# =============================================================================
"""
Turn the Pack into the document that lands in front of the board.

Finance reasoning: the PDF has to read like a real management pack. The
reader knows at once whether they hold a draft or the signed version (a
filled status banner, and on a draft a diagonal watermark on every page, so
a loose page cannot pass as final). The numbers follow the conventions a
finance reader expects: whole pounds, negatives in brackets, and variance
columns headed Fav/(Adv), where a cost overspend is adverse. The live model
run showed that "£37k above budget" on a cost can be misread as good news;
the Fav/(Adv) convention settles that in the tables. Material rows are bold,
lightly filled and marked with an asterisk, so the highlight survives black
and white printing. Colour is used only for status and materiality, never
for body numbers (the P5 restraint).

render(pack, format) is pure: it returns bytes and writes nothing. The PDF
is built in reportlab's invariant mode, and a FINAL pack is dated by its
sign-off, so re-rendering a signed pack reproduces the exact file whose
hash is in the audit. save_pack() writes the file and appends a "rendered"
event to the audit log, linked to the review run by run_id.

The Pack is format-agnostic, so PPTX is a second renderer over the same
object: a documented v1.1 stub here that raises rather than producing a
broken file.
"""

from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

from src.formatting import (
    cash_pounds, margin_cell, pct, pts_cell, table_number, table_value, when_text,
)
from src.state import Pack, PackStatus, SectionType
from src.step5_narrate import TEMPLATE, clean_dashes
from src.step6_review import _utc_now, excluded_rows_note, signoff_summary, write_audit
from src.tables import (
    DRAFT_HEX, DRIVERS_HEADER, DRIVERS_NOTE, FINAL_HEX, KPI_NOTE, LINE, cash_note,
    MATERIAL_HEX, PNL_HEADER, RULE_HEX, SUBTOTAL, drivers_rows, pnl_notes, pnl_rows,
)

# -- Look: colour only for status and materiality -----------------------------

DRAFT_FILL = colors.HexColor(DRAFT_HEX)
FINAL_FILL = colors.HexColor(FINAL_HEX)
MATERIAL_FILL = colors.HexColor(MATERIAL_HEX)
WATERMARK = colors.Color(0.87, 0.87, 0.87)
RULE = colors.HexColor(RULE_HEX)

MARGIN = 1.8 * cm
PAGE_W, PAGE_H = A4
BODY_W = PAGE_W - 2 * MARGIN

_BASE = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13)
_SMALL = ParagraphStyle("small", parent=_BASE, fontSize=7.5, leading=10)
_H1 = ParagraphStyle("h1", parent=_BASE, fontName="Helvetica-Bold", fontSize=16, leading=20)
_H2 = ParagraphStyle("h2", parent=_BASE, fontName="Helvetica-Bold", fontSize=11.5,
                     leading=15, spaceBefore=10, spaceAfter=4)
_H3 = ParagraphStyle("h3", parent=_BASE, fontName="Helvetica-Bold", fontSize=9.5,
                     leading=13, spaceBefore=8, spaceAfter=3)
_BANNER = ParagraphStyle("banner", parent=_BASE, fontName="Helvetica-Bold", fontSize=11,
                         textColor=colors.white, alignment=TA_CENTER)

_LEGAL_SUFFIXES = {"ltd", "limited", "plc", "llp", "inc", "llc"}


# -- Text helpers -------------------------------------------------------------

def _safe(text: str) -> str:
    """
    Text the standard PDF fonts can draw. Dashes become what step5 makes of
    them, and any character outside the fonts' set becomes '?' rather than
    a missing glyph box. Display only: the audit keeps the exact text.
    """
    return clean_dashes(text).encode("cp1252", errors="replace").decode("cp1252")


def _para(text: str, style: ParagraphStyle = _BASE) -> Paragraph:
    return Paragraph(escape(_safe(text)).replace("\n", "<br/>"), style)


def _short(sha: str) -> str:
    return sha[:12] if sha else "not recorded"


_CELL = ParagraphStyle("cell", parent=_BASE, fontSize=8, leading=9.5)
_CELL_BOLD = ParagraphStyle("cell_bold", parent=_CELL, fontName="Helvetica-Bold")


def _label(text: str, width: float, bold: bool = False):
    """
    A name cell. Plain text when it fits its column; when it would not, a
    Paragraph that wraps inside the column, so a long line or KPI name makes
    the row taller rather than the table wider.
    """
    text = _safe(text)
    if stringWidth(text, "Helvetica-Bold" if bold else "Helvetica", 8) <= width:
        return text
    return Paragraph(escape(text), _CELL_BOLD if bold else _CELL)


# -- The P&L table ------------------------------------------------------------

def _pnl_table(pack: Pack) -> Table:
    """The P&L table, drawn from src.tables.pnl_rows: the same cells the web layer shows."""
    rows = pnl_rows(pack)
    label_w = 4.3 * cm
    data = [list(PNL_HEADER[0]), list(PNL_HEADER[1])]
    # 18 points of padding at most: 12 to indent a line, 6 on the right
    data += [[_label(row.label, label_w - 18, bold=row.kind == SUBTOTAL), *row.cells]
             for row in rows]

    num_w = (BODY_W - label_w) / 7
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("FONT", (0, 0), (-1, 1), "Helvetica-Bold", 8),
        ("SPAN", (4, 0), (5, 0)), ("SPAN", (6, 0), (7, 0)),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (4, 0), (7, 0), "CENTER"),
        ("LINEBELOW", (0, 1), (-1, 1), 0.6, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    # Bold means subtotal, always, with a rule above. Materiality is shown only
    # by the fill and the asterisk, so a material line never looks like a total.
    for i, row in enumerate(rows, start=2):
        if row.kind == LINE:
            style.append(("LEFTPADDING", (0, i), (0, i), 12))
        else:
            style.append(("LINEABOVE", (0, i), (-1, i), 0.4, RULE))
        if row.kind == SUBTOTAL:
            style.append(("FONT", (0, i), (-1, i), "Helvetica-Bold", 8))
        if row.material:
            style.append(("BACKGROUND", (0, i), (-1, i), MATERIAL_FILL))
    style.append(("LINEBELOW", (0, len(data) - 2), (-1, len(data) - 2), 0.8, RULE))
    table = Table(data, colWidths=[label_w] + [num_w] * 7, repeatRows=2)
    table.setStyle(TableStyle(style))
    return table


# -- KPI and cash tables ------------------------------------------------------

def _drivers_block(pack: Pack) -> list:
    """
    "Main drivers of the variance against budget": for Gross profit and
    EBIT when material, each driver line with its impact on profit in
    Fav/(Adv) form. The impact is stored in profit terms already, so no
    flip: a line that lowered profit is bracketed, a genuine offset is
    plain. Computed, not drafted, and not editable at review: attribution
    is arithmetic, which the live model runs could not convey reliably.
    """
    driver_rows = drivers_rows(pack)
    if not driver_rows:
        return []
    rows = [list(DRIVERS_HEADER[0]), list(DRIVERS_HEADER[1])]
    rows += [[r.subtotal, _label(r.line, 4.6 * cm - 12), r.impact] for r in driver_rows]
    table = Table(rows, colWidths=[3.6 * cm, 4.6 * cm, 3.4 * cm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("FONT", (0, 0), (-1, 1), "Helvetica-Bold", 8),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("LINEBELOW", (0, 1), (-1, 1), 0.6, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [KeepTogether([
        _para("Main drivers of the variance against budget", _H3),
        table,
        Spacer(1, 3),
        _para(DRIVERS_NOTE, _SMALL),
    ])]


def _kpi_table(pack: Pack) -> Table:
    rows = [["", "Actual", "Target", "Prior year", "vs target", "vs prior year"]]
    for k in pack.section(SectionType.KPIS).figures["kpis"]:
        if k["derived"]:
            label = re.sub(r"\s*\([^)]*\)\s*$", "", k["metric"]) + ", from the P&L"
            cells = [margin_cell(k["actual"]), margin_cell(k["target"]),
                     margin_cell(k["prior_year"]), pts_cell(k["delta_target"]),
                     pts_cell(k["delta_py"])]
        else:
            label = k["metric"]
            cells = [table_number(k[f]) for f in
                     ("actual", "target", "prior_year", "delta_target", "delta_py")]
        rows.append([_label(label, _LABEL_W - 12)] + cells)
    return _simple_table(rows)


def _cash_table(figures: dict, scale) -> Table:
    pounds = lambda v: "n/a" if v is None else table_value(cash_pounds(v, scale))
    rows = [
        ["", "Actual", "Target", "Prior year", "vs target", "vs prior year"],
        ["", "£", "£", "£", "£", "£"],
        ["Cash balance"] + [pounds(figures[f]) for f in
                            ("actual", "target", "prior_year", "delta_target", "delta_py")],
    ]
    return _simple_table(rows, header_rows=2)


_LABEL_W = 5.0 * cm


def _simple_table(rows, header_rows: int = 1) -> Table:
    num_w = (BODY_W - _LABEL_W) / (len(rows[0]) - 1)
    table = Table(rows, colWidths=[_LABEL_W] + [num_w] * (len(rows[0]) - 1))
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("FONT", (0, 0), (-1, header_rows - 1), "Helvetica-Bold", 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 0.6, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _boxed(text: str) -> Table:
    box = Table([[_para(text, ParagraphStyle("notice", parent=_BASE, fontName="Helvetica-Bold"))]],
                colWidths=[BODY_W])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return box


# -- The document -------------------------------------------------------------

def _banner(pack: Pack) -> Table:
    if pack.status is PackStatus.FINAL:
        text = f"FINAL: signed off by {pack.sign_off_by} on {when_text(pack.sign_off_at)}"
        fill = FINAL_FILL
    else:
        text = "DRAFT: not signed off. Not for circulation as final."
        fill = DRAFT_FILL
    banner = Table([[_para(text, _BANNER)]], colWidths=[BODY_W])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return banner


def _governance(pack: Pack) -> list:
    flags = pack.material_flags
    model_sections = [s.title for s in pack.sections if s.drafted_by != TEMPLATE]
    template_sections = [s.title for s in pack.sections if s.drafted_by == TEMPLATE]
    if not model_sections:
        drafted = "the template (no model was used)"
    elif not template_sections:
        drafted = f"the model {pack.narrative_model}"
    else:
        drafted = (f"the model {pack.narrative_model}; the template for "
                   f"{', '.join(template_sections)}")
    edited = [s.title for s in pack.sections if s.edited]
    if pack.status is PackStatus.FINAL:
        signed = f"Reviewed and signed off by {pack.sign_off_by} on {when_text(pack.sign_off_at)}."
    else:
        signed = "Not signed off."
    lines = [
        f"Entity and period: {pack.entity}, {pack.period}.",
        "Figures computed in tested Python from the source files.",
        f"Input files (SHA-256, first 12 characters): P&L {_short(pack.pnl_sha256)}, "
        + (f"KPIs {_short(pack.kpis_sha256)}." if pack.kpis_supplied
           else "KPIs not supplied (no KPI file)."),
        f"Code version: {pack.code_version or 'not recorded'}.",
        f"Materiality: a variance against budget of £{table_value(flags.materiality_abs)} "
        f"or {pct(flags.materiality_pct)} or more, set by rule, not by the model.",
        f"Commentary drafted by: {drafted}.",
        f"Edited at review: {', '.join(edited) if edited else 'none'}.",
        signed,
    ]
    if pack.run_id:
        lines.append(f"Review run: {pack.run_id}.")
    return [_para(line) for line in lines]


def _story(pack: Pack) -> list:
    pnl = pack.section(SectionType.PNL)
    kpis = pack.section(SectionType.KPIS)
    cash = pack.section(SectionType.CASH)
    flags = pack.material_flags

    story = [
        _para(pack.entity, _H1),
        _para(f"Monthly management pack, {pack.period}"),
        Spacer(1, 8),
        _banner(pack),
        Spacer(1, 6),
        _para("Executive summary", _H2),
        _para(pack.section(SectionType.EXEC_SUMMARY).narrative),
        *_drivers_block(pack),
        _para("Profit and loss", _H2),
    ]
    if pack.excluded_pnl_rows:
        story += [_boxed(excluded_rows_note(pack)), Spacer(1, 6)]
    story += [
        _pnl_table(pack),
        _para("Commentary on material lines", _H3),
        _para(pnl.narrative),
        Spacer(1, 6),
        *[_para(note, _SMALL) for note in pnl_notes(pack)],
        # Each heading stays on the same page as its table: a header row
        # stranded at the foot of a page reads as a table with no data.
        KeepTogether([
            _para("Key performance indicators", _H2),
            _kpi_table(pack),
            Spacer(1, 4),
            _para(KPI_NOTE, _SMALL),
        ]),
        Spacer(1, 6),
        _para(kpis.narrative),
    ]
    if cash.figures["supplied"]:
        story += [
            KeepTogether([
                _para("Cash", _H2),
                _cash_table(cash.figures, pack.cash_scale),
                Spacer(1, 4),
                _para(cash_note(pack), _SMALL),
            ]),
            Spacer(1, 6),
            _para(cash.narrative),
        ]
    else:
        story += [_para("Cash", _H2), _para(cash.figures["note"])]
        if cash.narrative != cash.figures["note"]:
            story.append(_para(cash.narrative))
    story += [KeepTogether([_para("Governance and sign-off", _H2), *_governance(pack)])]

    if pack.status is not PackStatus.FINAL:
        notes = signoff_summary(pack)
        story += [PageBreak(), _para("Review notes", _H2),
                  _para("Outstanding when this draft was rendered. The pack is a draft "
                        "until these are reviewed and it is signed off.")]
        story += ([_para(f"{i}. {note}") for i, note in enumerate(notes, start=1)]
                  or [_para("No outstanding flags or warnings.")])
    return story


def _page_decorator(pack: Pack, generated: str):
    draft = pack.status is not PackStatus.FINAL

    def decorate(canvas, doc):
        canvas.saveState()
        if draft:
            canvas.setFillColor(WATERMARK)
            canvas.setFont("Helvetica-Bold", 110)
            canvas.translate(PAGE_W / 2, PAGE_H / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, -38, "DRAFT")
            canvas.rotate(-45)
            canvas.translate(-PAGE_W / 2, -PAGE_H / 2)
        canvas.setFillColor(colors.black)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(MARGIN, 1.0 * cm,
                          _safe(f"{pack.entity}, {pack.period}. Generated {generated}."))
        canvas.restoreState()

    return decorate


class _NumberedCanvas(Canvas):
    """
    Holds each page until the document is complete, then writes "Page n of
    N" on every page, so a missing page is obvious. Passes invariant mode
    through, so a FINAL still renders to identical bytes.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self.setFont("Helvetica", 7)
            self.drawRightString(PAGE_W - MARGIN, 1.0 * cm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def _render_pdf(pack: Pack) -> bytes:
    final = pack.status is PackStatus.FINAL
    generated = when_text(pack.sign_off_at if final else _utc_now())
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=1.8 * cm,
        title=_safe(f"{pack.entity} management pack, {pack.period}"),
        author="Board pack generator", subject=pack.status.value.upper(),
        invariant=1,
    )
    decorate = _page_decorator(pack, generated)
    doc.build(_story(pack), onFirstPage=decorate, onLaterPages=decorate,
              canvasmaker=_NumberedCanvas)
    return buffer.getvalue()


# -- Public interface -----------------------------------------------------------

def render(pack: Pack, format: str = "pdf") -> bytes:
    """
    The pack as bytes in the requested format. Pure: writes nothing.

    "pdf" is built. "pptx" is the planned v1.1 renderer over the same Pack
    and raises NotImplementedError rather than producing a broken file.
    """
    if format == "pdf":
        return _render_pdf(pack)
    if format == "pptx":
        raise NotImplementedError(
            "PPTX output is planned for v1.1. The Pack is format-agnostic, so it "
            "will be a second renderer over the same object. Use format='pdf'."
        )
    raise ValueError(f"Unknown format {format!r}. Use 'pdf'.")


def pack_file_name(pack: Pack, format: str = "pdf") -> str:
    """e.g. harmwell_foods_2026_06_board_pack_FINAL.pdf"""
    words = re.findall(r"[a-z0-9]+", pack.entity.lower())
    while words and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    try:
        period = datetime.strptime(pack.period.strip(), "%B %Y").strftime("%Y_%m")
    except ValueError:
        period = "_".join(re.findall(r"[a-z0-9]+", pack.period.lower()))
    status = pack.status.value.upper()
    return f"{'_'.join(words) or 'entity'}_{period}_board_pack_{status}.{format}"


def save_pack(pack: Pack, output_dir: Path, format: str = "pdf") -> Path:
    """
    Write the rendered pack to output_dir and append a "rendered" event to
    the audit log, linked to the review run by run_id.
    """
    data = render(pack, format)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / pack_file_name(pack, format)
    path.write_bytes(data)
    write_audit({
        "run_id": pack.run_id or None,
        "event": "rendered",
        "format": format,
        "file_name": path.name,
        "pdf_sha256": hashlib.sha256(data).hexdigest(),
        "timestamp": _utc_now(),
    }, output_dir)
    return path
