# =============================================================================
# step7_render.py: Layer 8: the board pack as a PDF, and the rendered event
# =============================================================================
"""
Turn the Pack into the document that lands in front of the board.

Finance reasoning: the PDF has to read like a real board pack. The
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
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.graphics import renderSVG
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

from src.formatting import cash_pounds, pct, table_value, when_text
from src.state import Pack, PackStatus, SectionType
from src.story import (
    ebit_walk, headline_sentence, line_effects, pnl_message, signed_money, summary_line,
)
from src.step5_narrate import TEMPLATE, clean_dashes
from src.step6_review import _utc_now, excluded_rows_note, signoff_summary, write_audit
from src.tables import (
    CASH_HEADER, DRAFT_HEX, DRIVERS_HEADER, DRIVERS_NOTE, DRIVERS_TITLE, FINAL_HEX, KPI_HEADER, KPI_NOTE, LINE,
    MATERIAL_HEX, PNL_HEADER, RULE_HEX, SUBTOTAL, cash_cells, cash_note, drivers_rows,
    headline_tiles, kpi_rows, pnl_notes, pnl_rows,
)

# -- Look: colour only for status and materiality -----------------------------

DRAFT_FILL = colors.HexColor(DRAFT_HEX)
FINAL_FILL = colors.HexColor(FINAL_HEX)
MATERIAL_FILL = colors.HexColor(MATERIAL_HEX)
WATERMARK = colors.Color(0.87, 0.87, 0.87)
RULE = colors.HexColor(RULE_HEX)
INK = colors.HexColor("#1A1F23")          # body text: near black, prints as black
GREY = colors.HexColor("#5A646D")         # secondary text: units, notes, labels
HAIRLINE = colors.HexColor("#C9CED2")     # light rules between rows and around the page
PANEL = colors.HexColor("#F2F3F4")        # the headline tiles and the governance panel

MARGIN = 1.8 * cm
PAGE_W, PAGE_H = A4
BODY_W = PAGE_W - 2 * MARGIN
# The frame indents its contents by 6 points; a table BODY_W wide is centred
# over it, so its fills bleed 6 points either side while its text (6 points
# of cell padding) lines up with the paragraphs. TEXT_W is that text width.
FRAME_PAD = 6
TEXT_W = BODY_W - 2 * FRAME_PAD

_BASE = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13.5,
                       textColor=INK)
_SMALL = ParagraphStyle("small", parent=_BASE, fontSize=7.5, leading=10, textColor=GREY)
_NOTE = ParagraphStyle("note", parent=_SMALL, spaceBefore=2)
_H1 = ParagraphStyle("h1", parent=_BASE, fontName="Helvetica-Bold", fontSize=18, leading=22)
_SUBTITLE = ParagraphStyle("subtitle", parent=_BASE, fontSize=10.5, leading=14, textColor=GREY)
_H2 = ParagraphStyle("h2", parent=_BASE, fontName="Helvetica-Bold", fontSize=12.5,
                     leading=16, spaceBefore=14, spaceAfter=0, keepWithNext=1)
_H3 = ParagraphStyle("h3", parent=_BASE, fontName="Helvetica-Bold", fontSize=9.5,
                     leading=13, spaceBefore=10, spaceAfter=4, keepWithNext=1)
_BANNER = ParagraphStyle("banner", parent=_BASE, fontName="Helvetica-Bold", fontSize=10.5,
                         leading=13, textColor=colors.white, alignment=TA_CENTER)
_TILE_LABEL = ParagraphStyle("tile_label", parent=_BASE, fontSize=7.5, leading=9,
                             textColor=GREY)
_TILE_VALUE = ParagraphStyle("tile_value", parent=_BASE, fontName="Helvetica-Bold",
                             fontSize=15, leading=19)
_TILE_VERSUS = ParagraphStyle("tile_versus", parent=_BASE, fontSize=7.5, leading=9,
                              textColor=GREY)
_PANEL_TEXT = ParagraphStyle("panel", parent=_BASE, fontSize=8.5, leading=12)
_HEADLINE = ParagraphStyle("headline", parent=_BASE, fontName="Helvetica-Bold", fontSize=14,
                           leading=18, spaceAfter=3)
_SUMMARY_LINE = ParagraphStyle("summary_line", parent=_BASE, fontSize=10, leading=14,
                             textColor=GREY, spaceAfter=10)
_MESSAGE = ParagraphStyle("message", parent=_BASE, fontName="Helvetica-Bold", fontSize=10,
                          leading=14, spaceAfter=8)
_CAPTION = ParagraphStyle("caption", parent=_SMALL, spaceBefore=3, spaceAfter=10)
BAR_STEP = colors.HexColor("#8C959C")     # a step in the bridge
BAR_LIGHT = colors.HexColor("#C3C9CE")    # a line that is not material
_LIST = ParagraphStyle("list", parent=_BASE, leftIndent=14, firstLineIndent=-14,
                       spaceAfter=3)

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


def _heading(text: str) -> list:
    """A section heading with a rule beneath it, kept with what follows."""
    rule = HRFlowable(width="100%", thickness=0.7, color=INK, spaceBefore=2, spaceAfter=7)
    rule.keepWithNext = 1
    return [_para(text, _H2), rule]


def _table_style(header_rows: int, units_row: bool) -> list:
    """Bold header, a grey units row if there is one, a rule under the header, even padding."""
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("FONT", (0, 0), (-1, header_rows - 1), "Helvetica-Bold", 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 0.7, INK),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if units_row:
        last = header_rows - 1
        style += [("FONT", (0, last), (-1, last), "Helvetica", 7),
                  ("TEXTCOLOR", (0, last), (-1, last), GREY),
                  ("TOPPADDING", (0, last), (-1, last), 0)]
    return style


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
    style = _table_style(header_rows=2, units_row=True) + [
        ("SPAN", (4, 0), (5, 0)), ("SPAN", (6, 0), (7, 0)),
        ("ALIGN", (4, 0), (7, 0), "CENTER"),
        # each Fav/(Adv) group is underlined, so its two columns read as one
        ("LINEBELOW", (4, 0), (5, 0), 0.4, HAIRLINE),
        ("LINEBELOW", (6, 0), (7, 0), 0.4, HAIRLINE),
    ]
    # Bold means subtotal, always, with a rule above. Materiality is shown only
    # by the fill and the asterisk, so a material line never looks like a total.
    for i, row in enumerate(rows, start=2):
        if row.kind == LINE:
            style.append(("LEFTPADDING", (0, i), (0, i), 12))
        else:
            style.append(("LINEABOVE", (0, i), (-1, i), 0.5, RULE))
        if row.kind == SUBTOTAL:
            style.append(("FONT", (0, i), (-1, i), "Helvetica-Bold", 8))
        if row.material:
            style.append(("BACKGROUND", (0, i), (-1, i), MATERIAL_FILL))
    style.append(("LINEBELOW", (0, len(data) - 2), (-1, len(data) - 2), 1.0, INK))
    style.append(("TEXTCOLOR", (0, len(data) - 1), (-1, len(data) - 1), GREY))
    table = Table(data, colWidths=[label_w] + [num_w] * 7, repeatRows=2)
    table.setStyle(TableStyle(style))
    return table


# -- KPI and cash tables ------------------------------------------------------

def _drivers_block(pack: Pack, width=None) -> list:
    """
    "Main drivers of the variance against budget": for gross profit and
    EBIT when material, each driver line with its impact on profit in
    Fav/(Adv) form. The impact is stored in profit terms already, so no
    flip: a line that lowered profit is bracketed, a genuine offset is
    plain. Computed, not drafted, and not editable at review: attribution
    is arithmetic, which the live model runs could not convey reliably.
    """
    driver_rows = drivers_rows(pack)
    if not driver_rows:
        return []
    width = width or 13.2 * cm
    line_w = width - 4.5 * cm
    rows = [list(DRIVERS_HEADER[0]), list(DRIVERS_HEADER[1])]
    rows += [[r.subtotal, _label(r.line, line_w - 12), r.impact] for r in driver_rows]
    widths = [2.3 * cm, line_w, 2.2 * cm]
    style = _table_style(header_rows=2, units_row=True) + [
        ("LEFTPADDING", (0, 0), (0, -1), 0),          # on the paragraph edge
        ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),           # names read from the left
        ("FONT", (0, 2), (0, -1), "Helvetica-Bold", 8),
    ]
    # a hairline between one subtotal's drivers and the next
    for i, r in enumerate(driver_rows, start=2):
        if r.subtotal and i > 2:
            style.append(("LINEABOVE", (0, i), (-1, i), 0.4, HAIRLINE))
    table = Table(rows, colWidths=widths, hAlign="LEFT")
    table.setStyle(TableStyle(style))
    return [
        _para(DRIVERS_TITLE, _H3),
        table,
        Spacer(1, 4),
        _para(DRIVERS_NOTE, _SMALL),
    ]


_D0 = Decimal("0")


def _fit(text: str, width, size) -> str:
    """Text cut at a word, with an ellipsis, so it fits width at this size."""
    text = _safe(text)
    if stringWidth(text, "Helvetica", size) <= width:
        return text
    words = text.split()
    while words and stringWidth(" ".join(words) + "...", "Helvetica", size) > width:
        words.pop()
    return (" ".join(words) or text[:8]) + "..."


def _pt(value) -> int:
    """A chart coordinate in whole points: computed in Decimal, handed to reportlab as an int."""
    return int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _walk_chart(pack: Pack, width: Decimal, height: Decimal) -> Drawing:
    """
    The bridge from budget EBIT to actual EBIT: the two totals as solid
    bars, the effect of revenue, COGS and opex as floating steps between
    them, joined at each running level. Every label is a figure of the pack.
    """
    bars, running = [], _D0
    for step in ebit_walk(pack):
        if step.kind == "total":
            low, high = sorted((_D0, step.value))
            running = step.value
        else:
            start, running = running, running + step.value
            low, high = sorted((start, running))
        bars.append((step, low, high, running))
    lowest = min([_D0] + [b[1] for b in bars])
    highest = max([_D0] + [b[2] for b in bars])
    span = (highest - lowest) or Decimal(1)
    top, bottom = Decimal(14), Decimal(28)
    plot = height - top - bottom

    def y(value):
        return bottom + (value - lowest) * plot / span

    slot = width / len(bars)
    bar_w = slot * Decimal("0.56")
    drawing = Drawing(_pt(width), _pt(height))
    drawing.add(Line(0, _pt(y(_D0)), _pt(width), _pt(y(_D0)), strokeColor=HAIRLINE,
                     strokeWidth=0.7))
    for i, (step, low, high, level) in enumerate(bars):
        x = slot * i + (slot - bar_w) / 2
        drawing.add(Rect(_pt(x), _pt(y(low)), _pt(x + bar_w) - _pt(x),
                         max(_pt(y(high)) - _pt(y(low)), 1),
                         fillColor=INK if step.kind == "total" else BAR_STEP,
                         strokeColor=None))
        rises = step.value >= 0
        drawing.add(String(_pt(x + bar_w / 2), _pt(y(high)) + 4 if rises else _pt(y(low)) - 10,
                           signed_money(step.value), fontName="Helvetica-Bold",
                           fontSize=7.5, fillColor=INK, textAnchor="middle"))
        if i < len(bars) - 1:
            drawing.add(Line(_pt(x + bar_w), _pt(y(level)), _pt(x + slot), _pt(y(level)),
                             strokeColor=GREY, strokeWidth=0.5, strokeDashArray=[2, 2]))
        drawing.add(String(_pt(x + bar_w / 2), 6, step.label, fontName="Helvetica",
                           fontSize=7, fillColor=GREY, textAnchor="middle"))
    return drawing


def _effects_chart(pack: Pack, width: Decimal) -> Drawing:
    """
    Each line's effect on profit against budget, largest first, as bars
    either side of zero: left lowered profit, right raised it. Material
    lines are dark and marked *, as in the P&L table.
    """
    effects = line_effects(pack)
    row, pad = Decimal(13), Decimal(3)
    height = row * len(effects) + 2 * pad
    name_w, part_w, value_w = Decimal(112), Decimal(34), Decimal(46)
    below = max([-e.effect for e in effects if e.effect < 0] + [_D0])
    above = max([e.effect for e in effects if e.effect > 0] + [_D0])
    span = (below + above) or Decimal(1)
    area = width - name_w - part_w - 2 * value_w
    zero = name_w + part_w + value_w + area * below / span
    drawing = Drawing(_pt(width), _pt(height))
    drawing.add(Line(_pt(zero), 0, _pt(zero), _pt(height), strokeColor=HAIRLINE,
                     strokeWidth=0.7))
    for i, effect in enumerate(effects):
        middle = height - pad - row * i - row / 2
        text_y = _pt(middle) - 3
        name = f"{effect.name} *" if effect.material else effect.name
        drawing.add(String(0, text_y, _fit(name, name_w - 6, 7.5), fontName="Helvetica",
                           fontSize=7.5, fillColor=INK))
        # which step of the bridge on page 1 the line belongs to
        drawing.add(String(_pt(name_w), text_y, effect.part, fontName="Helvetica",
                           fontSize=6.5, fillColor=GREY))
        length = area * effect.effect.copy_abs() / span
        x = zero - length if effect.effect < 0 else zero
        # both edges rounded, so every bar meets the zero line exactly
        left, right = _pt(x), _pt(x + length)
        drawing.add(Rect(left, _pt(middle) - 4, max(right - left, 1), 8, strokeColor=None,
                         fillColor=INK if effect.material else BAR_LIGHT))
        label = signed_money(effect.effect)
        if effect.effect < 0:
            drawing.add(String(_pt(x) - 3, text_y, label, fontName="Helvetica", fontSize=7,
                               fillColor=GREY, textAnchor="end"))
        else:
            drawing.add(String(_pt(x + length) + 3, text_y, label, fontName="Helvetica",
                               fontSize=7, fillColor=GREY))
    return drawing


def _cash_chart(figures: dict, scale, width: Decimal) -> Drawing:
    """
    The cash balance against target and last year, as three bars from zero:
    the actual dark, the comparators light, each labelled in the prose scale.
    """
    bars = [(name, cash_pounds(figures[key], scale)) for name, key in
            (("Actual", "actual"), ("Target", "target"), ("Prior year", "prior_year"))
            if figures[key] is not None]
    row, pad, name_w, value_w = Decimal(15), Decimal(2), Decimal(70), Decimal(50)
    height = row * len(bars) + 2 * pad
    below = max([-v for _, v in bars if v < 0] + [_D0])
    above = max([v for _, v in bars if v > 0] + [_D0])
    span = (below + above) or Decimal(1)
    area = width - name_w - value_w - (value_w if below else _D0)
    zero = name_w + (value_w if below else _D0) + area * below / span
    drawing = Drawing(_pt(width), _pt(height))
    drawing.add(Line(_pt(zero), 0, _pt(zero), _pt(height), strokeColor=HAIRLINE,
                     strokeWidth=0.7))
    for i, (name, value) in enumerate(bars):
        middle = height - pad - row * i - row / 2
        text_y = _pt(middle) - 3
        drawing.add(String(0, text_y, name, fontName="Helvetica", fontSize=7.5, fillColor=INK))
        length = area * value.copy_abs() / span
        x = zero - length if value < 0 else zero
        left, right = _pt(x), _pt(x + length)
        drawing.add(Rect(left, _pt(middle) - 5, max(right - left, 1), 10, strokeColor=None,
                         fillColor=INK if i == 0 else BAR_LIGHT))
        label = signed_money(value)
        if value < 0:
            drawing.add(String(_pt(x) - 3, text_y, label, fontName="Helvetica", fontSize=7,
                               fillColor=GREY, textAnchor="end"))
        else:
            drawing.add(String(_pt(x + length) + 3, text_y, label, fontName="Helvetica",
                               fontSize=7, fillColor=GREY))
    return drawing


# -- The charts, named once for the PDF and the screen ------------------------------

BRIDGE_TITLE = "The budget-to-actual bridge"
BRIDGE_CAPTION = ("From budget EBIT to actual EBIT. Each step is that part of the P&L against "
                  "budget, as its effect on profit: revenue below budget, or a cost above it, "
                  "lowers profit.")
EFFECTS_TITLE = "Each line's effect on profit against budget"
EFFECTS_CAPTION = ("Largest first, each with its part of the P&L: to the left of the line "
                   "lowered profit, to the right raised it. Material lines are dark and marked *.")
_CHART_W = 8.3 * cm


def _bridge(pack: Pack) -> Drawing:
    return _walk_chart(pack, Decimal(str(_CHART_W - 12)), Decimal(170))


def _effects(pack: Pack) -> Drawing:
    return _effects_chart(pack, Decimal(str(TEXT_W)))


def _cash(pack: Pack) -> Drawing:
    return _cash_chart(pack.section(SectionType.CASH).figures, pack.cash_scale,
                       Decimal(str(TEXT_W * 0.6)))


@dataclass(frozen=True)
class ScreenChart:
    """A chart the PDF draws, as SVG for a web page, with the PDF's title and caption and its width in points."""
    title: str
    svg: str
    caption: str
    width: int


_SVG_FONT = "Helvetica, Arial, sans-serif"


def _svg(drawing: Drawing, title: str) -> str:
    """
    The drawing as inline SVG that scales to its column: the XML preamble
    dropped, the width made relative (the viewBox keeps the proportions), the
    PDF's font names given browser fallbacks, and the chart titled for a
    screen reader.
    """
    text = renderSVG.drawToString(drawing)
    text = text[text.index("<svg"):]
    text = re.sub(r'<svg width="[^"]*" height="[^"]*"', '<svg width="100%"', text, count=1)
    text = text.replace("<title>...</title>", f"<title>{escape(title)}</title>")
    text = text.replace("<desc>...</desc>", "")
    text = text.replace("font-family: Helvetica-Bold;", f"font-family: {_SVG_FONT}; font-weight: bold;")
    return text.replace("font-family: Helvetica;", f"font-family: {_SVG_FONT};")


def screen_charts(pack: Pack) -> dict[str, ScreenChart]:
    """
    The pack's charts for a web page, drawn by the same functions as the PDF:
    the budget-to-actual bridge, each line's effect on profit, and the cash
    balance when the KPI file gives one. Keys: "bridge", "effects", "cash".
    """
    charts = {"bridge": (BRIDGE_TITLE, _bridge(pack), BRIDGE_CAPTION),
              "effects": (EFFECTS_TITLE, _effects(pack), EFFECTS_CAPTION)}
    if pack.section(SectionType.CASH).figures["supplied"]:
        charts["cash"] = ("Cash balance", _cash(pack), "")
    return {key: ScreenChart(title, _svg(drawing, title), caption, _pt(drawing.width))
            for key, (title, drawing, caption) in charts.items()}


def _evidence(pack: Pack) -> list:
    """
    The summary's evidence, side by side: the bridge from budget to actual
    EBIT (by revenue, COGS and opex) and the drivers table (by line). With
    no material profit subtotal there are no drivers, and the bridge stands
    alone.
    """
    walk = [_para(BRIDGE_TITLE, _H3), _bridge(pack), _para(BRIDGE_CAPTION, _CAPTION)]
    drivers = _drivers_block(pack, BODY_W - _CHART_W - 24)
    if not drivers:
        return [KeepTogether(walk)]
    row = Table([[walk, drivers]], colWidths=[_CHART_W, BODY_W - _CHART_W])
    row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (1, 0), (1, 0), 18), ("RIGHTPADDING", (1, 0), (1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [Spacer(1, 4), row]


def _tiles(pack: Pack) -> Table:
    """Revenue, gross profit, gross margin and EBIT at a glance, from the P&L table's own figures."""
    tiles = headline_tiles(pack)
    cells = [[[_para(t.label, _TILE_LABEL), _para(t.value, _TILE_VALUE),
               _para(t.budget, _TILE_VERSUS), _para(t.last_year, _TILE_VERSUS)] for t in tiles]]
    table = Table(cells, colWidths=[BODY_W / len(tiles)] * len(tiles))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("LINEAFTER", (0, 0), (-2, -1), 4, colors.white),     # a gap between the tiles
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def _kpi_table(pack: Pack) -> Table:
    rows = [list(KPI_HEADER)] + [[_label(label, _LABEL_W - 12), *cells]
                                 for label, cells in kpi_rows(pack)]
    return _simple_table(rows)


def _cash_table(pack: Pack) -> Table:
    rows = [list(CASH_HEADER[0]), list(CASH_HEADER[1]), ["Cash balance", *cash_cells(pack)]]
    return _simple_table(rows, header_rows=2)


_LABEL_W = 5.0 * cm


def _simple_table(rows, header_rows: int = 1) -> Table:
    num_w = (BODY_W - _LABEL_W) / (len(rows[0]) - 1)
    table = Table(rows, colWidths=[_LABEL_W] + [num_w] * (len(rows[0]) - 1))
    style = _table_style(header_rows, units_row=header_rows > 1)
    style += [("LINEBELOW", (0, i), (-1, i), 0.4, HAIRLINE)
              for i in range(header_rows, len(rows) - 1)]
    style.append(("LINEBELOW", (0, len(rows) - 1), (-1, len(rows) - 1), 0.7, INK))
    table.setStyle(TableStyle(style))
    return table


def _boxed(text: str) -> Table:
    box = Table([[_para(text, ParagraphStyle("notice", parent=_BASE, fontName="Helvetica-Bold",
                                             fontSize=9))]],
                colWidths=[BODY_W])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, INK),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
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
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return banner


def _governance(pack: Pack) -> list:
    flags = pack.material_flags
    model_sections = [s.title for s in pack.sections if s.drafted_by != TEMPLATE]
    template_sections = [s.title for s in pack.sections if s.drafted_by == TEMPLATE]
    model = "the model (Claude, via the Anthropic API)"
    if not model_sections:
        drafted = f"the template; {model} was not used"
    elif not template_sections:
        drafted = f"{model}, {pack.narrative_model}"
    else:
        drafted = (f"{model}, {pack.narrative_model}; the template for "
                   f"{', '.join(template_sections)}")
    edited = [s.title for s in pack.sections if s.edited]
    if pack.status is PackStatus.FINAL:
        signed = f"Reviewed and signed off by {pack.sign_off_by} on {when_text(pack.sign_off_at)}."
    else:
        signed = "Not signed off."
    lines = [
        f"Entity and period: {pack.entity}, {pack.period}.",
        "Figures computed in tested Python from the source files.",
        "Headline, summary line and table messages: computed from the figures.",
        f"Input files (SHA-256, first 12 characters): P&L {_short(pack.pnl_sha256)}, "
        + (f"KPIs {_short(pack.kpis_sha256)}." if pack.kpis_supplied
           else "KPIs not supplied (no KPI file)."),
        f"Code version: {pack.code_version or 'not recorded'}.",
        f"Materiality: a variance against budget of £{table_value(flags.materiality_abs)} "
        f"or {pct(flags.materiality_pct)} or more, set by rule.",
        f"Commentary drafted by: {drafted}.",
        f"Edited at review: {', '.join(edited) if edited else 'none'}.",
        signed,
    ]
    if pack.run_id:
        lines.append(f"Review run: {pack.run_id}.")
    paras = []
    for line in lines:
        label, colon, rest = line.partition(": ")
        if colon and len(label) < 45:
            paras.append(Paragraph(f"<b>{escape(_safe(label))}:</b> {escape(_safe(rest))}",
                                   _PANEL_TEXT))
        else:
            paras.append(_para(line, _PANEL_TEXT))
    panel = Table([[paras]], colWidths=[BODY_W])
    panel.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [panel]


def _story(pack: Pack) -> list:
    pnl = pack.section(SectionType.PNL)
    kpis = pack.section(SectionType.KPIS)
    cash = pack.section(SectionType.CASH)
    flags = pack.material_flags

    story = [
        _para(pack.entity, _H1),
        _para(f"Monthly board pack, {pack.period}", _SUBTITLE),
        Spacer(1, 10),
        _banner(pack),
        Spacer(1, 2),
        # 1. The message, the numbers, the words, the evidence
        KeepTogether([*_heading("Executive summary"), _para(headline_sentence(pack), _HEADLINE),
                      _para(summary_line(pack), _SUMMARY_LINE),
                      # the headline's totals carry the same warning as the P&L table
                      *([_boxed(excluded_rows_note(pack)), Spacer(1, 8)]
                        if pack.excluded_pnl_rows else []),
                      _tiles(pack)]),
        _para("Commentary", _H3),
        _para(pack.section(SectionType.EXEC_SUMMARY).narrative),
        *_evidence(pack),
        # 2. The measures beyond the P&L
        KeepTogether([
            *_heading("Key performance indicators"),
            _kpi_table(pack),
            Spacer(1, 4),
            _para(KPI_NOTE, _SMALL),
        ]),
        Spacer(1, 8),
        _para(kpis.narrative),
    ]
    # 3. The P&L, read as one statement: its message, each line's effect on
    # profit, then the table. If it does not fit, it starts the next page whole.
    statement = [*_heading("Profit and loss"), _para(pnl_message(pack), _MESSAGE)]
    if pack.excluded_pnl_rows:
        statement += [_boxed(excluded_rows_note(pack)), Spacer(1, 8)]
    statement += [_para(EFFECTS_TITLE, _H3), _effects(pack), _para(EFFECTS_CAPTION, _CAPTION)]
    story += [
        KeepTogether([*statement, _pnl_table(pack)]),
        _para("Commentary on material lines", _H3),
        _para(pnl.narrative),
        Spacer(1, 6),
        *[_para(note, _NOTE) for note in pnl_notes(pack)],
    ]
    # 4. Cash
    if cash.figures["supplied"]:
        story += [
            KeepTogether([
                *_heading("Cash"),
                _cash(pack),
                Spacer(1, 8),
                _cash_table(pack),
                Spacer(1, 4),
                _para(cash_note(pack), _SMALL),
            ]),
            Spacer(1, 8),
            _para(cash.narrative),
        ]
    else:
        story += [*_heading("Cash"), _para(cash.figures["note"])]
        if cash.narrative != cash.figures["note"]:
            story.append(_para(cash.narrative))
    story += [KeepTogether([*_heading("Governance and sign-off"), *_governance(pack)])]

    if pack.status is not PackStatus.FINAL:
        notes = signoff_summary(pack)
        story += [PageBreak(), *_heading("Review notes"),
                  _para("Outstanding when this draft was rendered. The pack is a draft "
                        "until these are reviewed and it is signed off."),
                  Spacer(1, 6)]
        story += ([_para(f"{i}. {note}", _LIST) for i, note in enumerate(notes, start=1)]
                  or [_para("No outstanding flags or data notes.")])
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
        canvas.setStrokeColor(HAIRLINE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 1.35 * cm, PAGE_W - MARGIN, 1.35 * cm)
        if doc.page > 1:
            canvas.line(MARGIN, PAGE_H - 1.25 * cm, PAGE_W - MARGIN, PAGE_H - 1.25 * cm)
            canvas.setFillColor(GREY)
            canvas.setFont("Helvetica", 7)
            canvas.drawString(MARGIN, PAGE_H - 1.1 * cm,
                              _safe(f"{pack.entity}: monthly board pack, {pack.period}"))
            canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 1.1 * cm,
                                   pack.status.value.upper())
        canvas.setFillColor(GREY)
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
            self.setFillColor(GREY)
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
        title=_safe(f"{pack.entity} board pack, {pack.period}"),
        author="Board Pack Generator", subject=pack.status.value.upper(),
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


def save_pack(pack: Pack, output_dir: Path, format: str = "pdf",
              now: Optional[str] = None) -> Path:
    """
    Write the rendered pack to output_dir and append a "rendered" event to
    the audit log, linked to the review run by run_id. now fixes the event's
    timestamp, as for review().
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
        "timestamp": now or _utc_now(),
    }, output_dir)
    return path
