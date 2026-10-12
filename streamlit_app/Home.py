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

# Imports nothing of the project's: a release pulled into the running app
# replaces the old modules before this run imports them (lib/fresh.py).
import importlib
import threading

from streamlit_app.lib import fresh

# fresh.py is the release check itself, so it is never purged. Streamlit
# Cloud does not reload it either when a pull changes it (v1.2.1 met an older
# copy without held()), and this script is the one file always read afresh: so
# here, under a lock, the copy in memory is reloaded when its file has changed.
with sys.__dict__.setdefault("_board_pack_fresh_lock", threading.Lock()):
    if getattr(fresh, "LOADED_MTIME_NS", None) != Path(fresh.__file__).stat().st_mtime_ns:
        fresh = importlib.reload(fresh)

# The pages live in views/, not pages/: a folder named pages/ beside this
# script would let Streamlit run a page without this script (its older
# multipage mode), skipping the release check below.
PAGES_DIR = Path(__file__).resolve().parent / "views"

# Each page's address is pinned: links to them are published (the README, the
# docs, posts), and a renamed or moved file must not change them.
HOW_BUILT = st.Page(str(PAGES_DIR / "1_How_the_pack_is_built.py"), url_path="How_the_pack_is_built",
                    title="How the pack is built", icon=":material/menu_book:")
BOARD_PACK = st.Page(str(PAGES_DIR / "2_Board_pack.py"), url_path="Board_pack",
                     title="Board pack", icon=":material/description:")
OWN_DATA = st.Page(str(PAGES_DIR / "3_Your_own_data.py"), url_path="Your_own_data",
                   title="Your own data", icon=":material/upload_file:")
HOW_ITS_BUILT = st.Page(str(PAGES_DIR / "4_How_its_built.py"), url_path="How_its_built",
                        title="How it's built", icon=":material/build:")


def _home_page():
    from streamlit_app.lib.key_gate import render_key_gate
    from streamlit_app.lib.theme import header_html, inject_css

    st.markdown(inject_css(), unsafe_allow_html=True)
    st.markdown(header_html(
        "Board Pack Generator",
        "A monthly board pack: the figures computed in Python, the commentary drafted "
        "inside them, and the reviewer's sign-off."),
        unsafe_allow_html=True)
    render_key_gate()

    st.markdown("#### What it does")
    st.markdown(
        "- Reads a month's P&L and KPIs from two CSV files.\n"
        "- Computes every subtotal, variance and margin, and selects what is material by rule.\n"
        "- Drafts the commentary from those figures only, with a template or, if you choose, "
        "the model (Claude, via the Anthropic API).\n"
        "- Produces a PDF board pack that is a DRAFT until a named reviewer signs it.")

    st.markdown("#### The governance promise")
    st.markdown(
        "- **Python computes.** Every number in the pack is calculated and tested in code.\n"
        "- **A rule selects.** What counts as material is a threshold, not the model's opinion.\n"
        "- **The commentary reports.** It says what moved and by how much, never why.\n"
        "- **The reviewer signs.** Nothing is final until a named reviewer reads it and signs.")

    st.markdown("#### Pages")
    st.page_link(HOW_BUILT, label="How the pack is built: materiality, Fav/(Adv), drivers and sign-off")
    st.page_link(BOARD_PACK, label="Board pack: a signed example, and a run on your own files")
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



def _clear_caches() -> None:
    st.cache_data.clear()
    st.cache_resource.clear()


# The whole run, the page included, holds the loaded release: a purge waits
# for it, and it waits for a purge, so it never meets a half-loaded module.
with fresh.held(ROOT, clear_caches=_clear_caches) as generation:
    if fresh.reset_stale_session(st.session_state, generation, pack_key="bp_pack",
                                 edits_prefix="bp_edit_", kept_key="bp_kept_edits"):
        st.info(fresh.UPDATED_NOTICE)
    pg = st.navigation([
        st.Page(_home_page, title="Home", icon=":material/home:", default=True),
        HOW_BUILT,
        BOARD_PACK,
        OWN_DATA,
        HOW_ITS_BUILT,
    ])
    pg.run()
