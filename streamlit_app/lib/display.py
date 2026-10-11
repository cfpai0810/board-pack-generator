# =============================================================================
# lib/display.py: the pack's tables and text as HTML for the screen
# =============================================================================
# Presentation only. Every cell arrives as a finished string from
# src/tables.py, the same rows the PDF draws, so the screen and the signed
# pack can never disagree and no Decimal reaches a Streamlit widget. Nothing
# here computes, selects or formats a figure.
# =============================================================================

import html

from src.pipeline import DriverRow, PnlRow, ScreenChart, Tile

_E = html.escape


def status_chip(status: str) -> str:
    """'DRAFT' or 'FINAL' in the PDF's banner colour."""
    kind = "final" if status.upper() == "FINAL" else "draft"
    return f'<span class="bp-status {kind}">{_E(status.upper())}</span>'


def headline_html(headline: str, summary_line: str) -> str:
    """The pack's headline and its summary line, as the PDF opens."""
    return (f'<p class="bp-headline">{_E(headline)}</p>'
            f'<p class="bp-summary-line">{_E(summary_line)}</p>')


def tiles_html(tiles: list[Tile]) -> str:
    """The four headline tiles: each figure, then how it did against budget and last year."""
    cells = "".join(
        f'<div class="bp-tile"><div class="bp-tile-label">{_E(t.label)}</div>'
        f'<div class="bp-tile-value">{_E(t.value)}</div>'
        f'<div class="bp-tile-versus">{_E(t.budget)}</div>'
        f'<div class="bp-tile-versus">{_E(t.last_year)}</div></div>'
        for t in tiles)
    return f'<div class="bp-tiles">{cells}</div>'


def chart_html(chart: ScreenChart, *, title: bool = True) -> str:
    """
    A chart the PDF draws, as its SVG, between a quarter and a half as large
    again as it prints, so its labels stay readable: on a phone a wide chart
    scrolls sideways in its own box, as the tables do. Its caption beneath.
    """
    heading = f'<p class="bp-chart-title">{_E(chart.title)}</p>' if title else ""
    caption = f'<p class="bp-note">{_E(chart.caption)}</p>' if chart.caption else ""
    return (f'{heading}<div class="bp-chart" style="max-width:{chart.width * 3 // 2}px">'
            f'<div style="min-width:{chart.width * 5 // 4}px">{chart.svg}</div></div>{caption}')


def commentary_html(text: str) -> str:
    """A section's signed commentary, line breaks kept."""
    return f'<div class="bp-commentary">{_E(text).replace(chr(10), "<br>")}</div>'


def pnl_table_html(rows: list[PnlRow], header) -> str:
    """The P&L table; header is pnl_header(pack.currency), as the PDF draws it."""
    top, units = header
    head = (
        "<tr>"
        f'<th>{_E(top[0])}</th><th class="num">{_E(top[1])}</th>'
        f'<th class="num">{_E(top[2])}</th><th class="num">{_E(top[3])}</th>'
        f'<th class="group" colspan="2">{_E(top[4])}</th>'
        f'<th class="group" colspan="2">{_E(top[6])}</th>'
        "</tr>"
        "<tr><th></th>" + "".join(f'<th class="num">{_E(u)}</th>' for u in units[1:]) + "</tr>"
    )
    body = []
    for row in rows:
        classes = row.kind + (" material" if row.material else "")
        cells = "".join(f'<td class="num">{_E(c)}</td>' for c in row.cells)
        body.append(f'<tr class="{classes}"><td class="label">{_E(row.label)}</td>{cells}</tr>')
    return (f'<div class="bp-table-wrap"><table class="bp-table"><thead>{head}</thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def drivers_table_html(rows: list[DriverRow], header) -> str:
    """The drivers table; header is drivers_header(pack.currency), as the PDF draws it."""
    top, units = header
    head = (f'<tr><th>{_E(top[0])}</th><th>{_E(top[1])}</th><th class="num">{_E(top[2])}</th></tr>'
            f'<tr><th></th><th></th><th class="num">{_E(units[2])}</th></tr>')
    body = "".join(
        f'<tr><td>{_E(r.subtotal)}</td><td class="label">{_E(r.line)}</td>'
        f'<td class="num">{_E(r.impact)}</td></tr>'
        for r in rows
    )
    return (f'<div class="bp-table-wrap"><table class="bp-table" style="width:auto">'
            f'<thead>{head}</thead><tbody>{body}</tbody></table></div>')


def table_html(header: list[str], rows: list[list[str]], *, numeric: tuple[int, ...] = (),
               wrap: tuple[int, ...] = (), caption: str = "") -> str:
    """
    A plain table in the pack's style, for the explanation pages: numeric
    columns right aligned, text columns that may wrap (so the table fits a
    phone), and a horizontal scroll if it still does not.
    """
    def cls(i: int) -> str:
        return ' class="num"' if i in numeric else (' class="label"' if i in wrap else "")
    head = "".join(f"<th{cls(i)}>{_E(h)}</th>" for i, h in enumerate(header))
    body = "".join(
        "<tr>" + "".join(f"<td{cls(i)}>{_E(c)}</td>" for i, c in enumerate(row)) + "</tr>"
        for row in rows)
    title = f"<caption>{_E(caption)}</caption>" if caption else ""
    return (f'<div class="bp-table-wrap"><table class="bp-table bp-plain">{title}'
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>")


def flow_html(steps: list[tuple[str, str]]) -> str:
    """The pipeline as a column of numbered steps, each with what it owns."""
    items = "".join(
        f'<li><span class="bp-step">{i}. {_E(name)}</span>'
        f'<span class="bp-owns">{_E(owns)}</span></li>'
        for i, (name, owns) in enumerate(steps, start=1))
    return f'<ol class="bp-flow">{items}</ol>'
