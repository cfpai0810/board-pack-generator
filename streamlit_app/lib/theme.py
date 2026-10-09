# =============================================================================
# lib/theme.py: one visual identity, shared with the PDF
# =============================================================================
# The status and materiality colours are the PDF's own (src/tables.py, via
# src.pipeline), so
# the screen and the signed pack read as one product: amber for DRAFT, green
# for FINAL, the pale shading for material rows. Colour carries status and
# materiality only; numbers are never coloured (the P5 restraint).
#
# Typography follows the portfolio: Source Serif 4 for headings and Inter for
# body, UI and data, with tabular figures so numbers align in tables.
# =============================================================================

from src.pipeline import DRAFT_HEX, FINAL_HEX, MATERIAL_HEX, RULE_HEX

INK = "#1E2A2E"
HEADER_BAND = "#272C30"
HEADER_SUB = "#CDD2D6"
MUTED = "#6A7378"
RULE = RULE_HEX
SOFT_RULE = "#D5D9DB"
NEAR_WHITE = "#FAFAF8"
DRAFT = DRAFT_HEX
FINAL = FINAL_HEX
MATERIAL = MATERIAL_HEX

SERIF = "'Source Serif 4', Georgia, 'Times New Roman', serif"
SANS = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"


def inject_css() -> str:
    """The app's CSS, font imports included, kept in one place for every page."""
    return f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap');

      html, body, [class*="css"], .stMarkdown, .stText, p, span, div, label,
      input, button, table, td, th {{
        font-family: {SANS};
        font-feature-settings: "tnum" 1;
      }}
      h1, h2, h3, h4 {{
        font-family: {SERIF};
        color: {INK};
        letter-spacing: -0.01em;
        font-weight: 600;
      }}

      /* The page header band */
      .bp-header {{
        background: {HEADER_BAND};
        color: white;
        padding: 22px 26px;
        border-radius: 10px;
        margin-bottom: 8px;
      }}
      .bp-header h1 {{
        font-family: {SERIF};
        color: white; margin: 0; font-size: 1.7rem; font-weight: 700;
        letter-spacing: -0.02em;
      }}
      .bp-header p {{
        color: {HEADER_SUB}; margin: 6px 0 0; font-size: 0.92rem;
      }}

      /* Status chip: the PDF's banner colours */
      .bp-status {{
        display: inline-block;
        padding: 3px 10px;
        border-radius: 4px;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        color: white;
      }}
      .bp-status.draft {{ background: {DRAFT}; }}
      .bp-status.final {{ background: {FINAL}; }}

      /* Narrative block */
      .bp-narrative {{
        background: {NEAR_WHITE};
        border-left: 3px solid {RULE};
        border-radius: 4px;
        padding: 14px 18px;
        margin: 8px 0 14px;
        font-size: 0.95rem;
        line-height: 1.6;
        color: {INK};
      }}

      /* Tables in the PDF's conventions */
      .bp-table-wrap {{ overflow-x: auto; margin: 6px 0 4px; }}
      table.bp-table {{
        border-collapse: collapse;
        width: 100%;
        font-size: 0.82rem;
        color: {INK};
      }}
      table.bp-table th, table.bp-table td {{
        padding: 4px 8px;
        border: none;
        white-space: nowrap;
      }}
      table.bp-table thead th {{ font-weight: 600; text-align: left; }}
      table.bp-table thead th.num {{ text-align: right; }}
      table.bp-table thead tr:last-child th {{ border-bottom: 1px solid {RULE}; }}
      table.bp-table td.num {{ text-align: right; }}
      table.bp-table td.label {{ white-space: normal; min-width: 10em; max-width: 22em; }}
      table.bp-table th.group {{ text-align: center; }}
      table.bp-table tr.line td:first-child {{ padding-left: 20px; }}
      table.bp-table tr.subtotal td {{ font-weight: 700; border-top: 1px solid {RULE}; }}
      table.bp-table tr.margin td {{ border-top: 1px solid {RULE}; border-bottom: 1px solid {RULE}; }}
      table.bp-table tr.material td {{ background: {MATERIAL}; }}
      .bp-note, [data-testid="stMarkdownContainer"] p.bp-note {{
        font-size: 0.76rem; color: {MUTED}; margin: 2px 0;
      }}
      ol.bp-datanotes {{ margin: 0; padding-left: 1.4em; font-size: 0.85rem; color: {INK}; }}
      ol.bp-datanotes li {{ margin: 2px 0; }}
      ul.bp-flags {{ margin: 0 0 14px; padding-left: 1.1em; font-size: 0.82rem; color: {INK}; }}
      ul.bp-flags li {{ margin: 2px 0; }}

      /* Controls in ink, not Streamlit's default red: colour is kept for
         status and materiality only */
      [data-testid="stBaseButton-primary"] {{
        background: {INK}; border-color: {INK}; color: white;
      }}
      [data-testid="stBaseButton-primary"]:hover {{
        background: {HEADER_BAND}; border-color: {HEADER_BAND}; color: white;
      }}
      [data-testid="stTab"][aria-selected="true"],
      [data-testid="stTab"][aria-selected="true"] p {{ color: {INK}; font-weight: 600; }}
      [data-testid="stTab"]:hover, [data-testid="stTab"]:hover p {{ color: {INK}; }}
      [data-testid="stTextInputRootElement"]:focus-within,
      [data-testid="stTextAreaRootElement"]:focus-within {{ border-color: {INK} !important; }}
      [data-testid="stTab"] .react-aria-SelectionIndicator {{
        background-color: {INK} !important; border-color: {INK} !important;
      }}

      /* Key disclosure note in the sidebar */
      .bp-keynote {{
        font-size: 0.8rem;
        color: {MUTED};
        border-left: 2px solid {SOFT_RULE};
        padding-left: 10px;
        margin-top: 6px;
      }}
    </style>
    """


def header_html(title: str, subtitle: str) -> str:
    import html
    return (f'<div class="bp-header"><h1>{html.escape(title)}</h1>'
            f'<p>{html.escape(subtitle)}</p></div>')
