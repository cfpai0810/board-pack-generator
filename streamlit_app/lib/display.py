# =============================================================================
# lib/display.py: the pack's tables and text as HTML for the screen
# =============================================================================
# Presentation only. Every cell arrives as a finished string from
# src/tables.py, the same rows the PDF draws, so the screen and the signed
# pack can never disagree and no Decimal reaches a Streamlit widget. Nothing
# here computes, selects or formats a figure.
# =============================================================================

import html

from src.pipeline import DRIVERS_HEADER, PNL_HEADER, DriverRow, PnlRow

_E = html.escape


def status_chip(status: str) -> str:
    """'DRAFT' or 'FINAL' in the PDF's banner colour."""
    kind = "final" if status.upper() == "FINAL" else "draft"
    return f'<span class="bp-status {kind}">{_E(status.upper())}</span>'


def narrative_html(text: str) -> str:
    """A narrative block, line breaks kept."""
    return f'<div class="bp-narrative">{_E(text).replace(chr(10), "<br>")}</div>'


def pnl_table_html(rows: list[PnlRow]) -> str:
    top, units = PNL_HEADER
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


def drivers_table_html(rows: list[DriverRow]) -> str:
    top, units = DRIVERS_HEADER
    head = (f'<tr><th>{_E(top[0])}</th><th>{_E(top[1])}</th><th class="num">{_E(top[2])}</th></tr>'
            f'<tr><th></th><th></th><th class="num">{_E(units[2])}</th></tr>')
    body = "".join(
        f'<tr><td>{_E(r.subtotal)}</td><td class="label">{_E(r.line)}</td>'
        f'<td class="num">{_E(r.impact)}</td></tr>'
        for r in rows
    )
    return (f'<div class="bp-table-wrap"><table class="bp-table" style="width:auto">'
            f'<thead>{head}</thead><tbody>{body}</tbody></table></div>')
