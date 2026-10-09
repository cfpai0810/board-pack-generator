# =============================================================================
# Home.py: the app shell and landing page (Streamlit entry point)
# =============================================================================
# Run locally: streamlit run streamlit_app/Home.py
# Multipage navigation through st.navigation and st.Page, the P5 pattern.
# Paths resolve from this file, so the app runs from any working directory.
# =============================================================================

import sys

sys.dont_write_bytecode = True

from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit_app.lib.key_gate import render_key_gate
from streamlit_app.lib.theme import header_html, inject_css

PAGES_DIR = Path(__file__).resolve().parent / "pages"

HOW_BUILT = st.Page(str(PAGES_DIR / "1_How_the_pack_is_built.py"),
                    title="How the pack is built", icon=":material/menu_book:")
BOARD_PACK = st.Page(str(PAGES_DIR / "2_Board_pack.py"),
                     title="Board pack", icon=":material/description:")
OWN_DATA = st.Page(str(PAGES_DIR / "3_Your_own_data.py"),
                   title="Your own data", icon=":material/upload_file:")
HOW_ITS_BUILT = st.Page(str(PAGES_DIR / "4_How_its_built.py"),
                        title="How it's built", icon=":material/build:")


def _home_page():
    st.markdown(inject_css(), unsafe_allow_html=True)
    st.markdown(header_html(
        "Board Pack Generator",
        "A monthly management pack for a board: the figures computed in Python, "
        "the commentary drafted inside them, and a named person's sign-off."),
        unsafe_allow_html=True)
    render_key_gate()

    st.markdown("#### What it does")
    st.markdown(
        "- Reads a month's P&L and KPIs from two CSV files.\n"
        "- Computes every subtotal, variance and margin, and selects what is material by rule.\n"
        "- Drafts the commentary from those figures only, with a template or, if you choose, the model.\n"
        "- Produces a PDF board pack that is a DRAFT until a named reviewer signs it.")

    st.markdown("#### The governance promise")
    st.markdown(
        "- **Python computes.** Every number in the pack is calculated and tested in code.\n"
        "- **A rule selects.** What counts as material is a threshold, not the model's opinion.\n"
        "- **The commentary narrates.** It says what moved and by how much, never why.\n"
        "- **A person signs.** Nothing is final until a named reviewer reads it and signs.")

    st.markdown("#### Pages")
    st.page_link(HOW_BUILT, label="How the pack is built: materiality, Fav/(Adv), drivers and sign-off")
    st.page_link(BOARD_PACK, label="Board pack: run the sample and download the PDF")
    st.page_link(OWN_DATA, label="Your own data: the two CSV formats and how to run locally")
    st.page_link(HOW_ITS_BUILT, label="How it's built: the pipeline, the tests and the audit trail")

    st.divider()
    st.caption("Sample data only: Harmwell Foods Ltd is a fictional company. "
               "All figures are illustrative.")


st.set_page_config(
    page_title="Board Pack Generator",
    page_icon=":material/description:",
    layout="centered",
    initial_sidebar_state="expanded",
)

pg = st.navigation([
    st.Page(_home_page, title="Home", icon=":material/home:", default=True),
    HOW_BUILT,
    BOARD_PACK,
    OWN_DATA,
    HOW_ITS_BUILT,
])
pg.run()
