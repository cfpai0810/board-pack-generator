# =============================================================================
# pages/2_Board_pack.py: the tool
# =============================================================================
# W1 skeleton. "Run it yourself" runs the SAMPLE through run_pipeline as a
# draft with the template and shows what the pack holds: the executive
# summary, the drivers table and the P&L table, as the same formatted rows
# the PDF draws (src/tables.py), plus the DRAFT PDF to download.
#
# No pipeline logic lives here: the page calls run_pipeline and reads the
# shared rows. Each session writes to its own temporary folder, which goes
# when the session ends; nothing is kept between sessions.
# =============================================================================

import sys
import tempfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ENTITY_NAME, KPIS_PATH, PERIOD, PNL_PATH
from src.pipeline import run_pipeline
from src.state import SectionType
from src.tables import drivers_rows, pnl_rows
from streamlit_app.lib.display import (
    drivers_table_html, narrative_html, pnl_table_html, status_chip,
)
from streamlit_app.lib.errors import friendly_message
from streamlit_app.lib.key_gate import render_key_gate
from streamlit_app.lib.theme import header_html, inject_css

st.markdown(inject_css(), unsafe_allow_html=True)
st.markdown(header_html(
    "Board pack",
    f"{ENTITY_NAME}, {PERIOD}: the monthly management pack, from the source files "
    "to a PDF a named reviewer signs."), unsafe_allow_html=True)
render_key_gate()


def _session_folder() -> Path:
    """This session's own temporary output folder, removed when the session ends."""
    if "workdir" not in st.session_state:
        st.session_state["workdir"] = tempfile.TemporaryDirectory(prefix="board_pack_")
    return Path(st.session_state["workdir"].name)


def _run_sample() -> None:
    """Run the sample as a draft and keep only display-ready strings and bytes."""
    result = run_pipeline(PNL_PATH, KPIS_PATH, _session_folder(), draft_only=True)
    pack = result.pack
    st.session_state["sample_pack"] = pack            # for the review stage (W2)
    st.session_state["sample_draft"] = {
        "status": pack.status.value.upper(),
        "exec_summary": pack.section(SectionType.EXEC_SUMMARY).narrative,
        "drivers": drivers_rows(pack),
        "pnl": pnl_rows(pack),
        "pdf_name": result.pdf_path.name,
        "pdf": result.pdf_path.read_bytes(),
    }


example_tab, run_tab = st.tabs(["View a worked example", "Run it yourself"])

with example_tab:
    st.markdown("#### The signed sample pack")
    st.write(
        "This tab will show the signed sample pack and its audit trail, with no run "
        "needed. Until then, run the sample yourself in the next tab.")

with run_tab:
    st.markdown("#### Run the sample")
    st.write(
        f"Builds the pack for {ENTITY_NAME}, {PERIOD}, from the sample files: the figures "
        "are computed, the material items selected by rule, and the commentary drafted "
        "by the template. The result is a DRAFT; review and sign-off come next.")
    if st.button("Run the sample as a draft", key="run_sample", type="primary"):
        try:
            with st.spinner("Building the pack..."):
                _run_sample()
        except Exception as exc:  # a reader never sees a traceback
            st.error(friendly_message(exc))

    view = st.session_state.get("sample_draft")
    if view:
        st.markdown(status_chip(view["status"]) + "&nbsp; Not signed off.",
                    unsafe_allow_html=True)

        st.markdown("#### Executive summary")
        st.markdown(narrative_html(view["exec_summary"]), unsafe_allow_html=True)

        if view["drivers"]:
            st.markdown("##### Main drivers of the variance against budget")
            st.markdown(drivers_table_html(view["drivers"]), unsafe_allow_html=True)
            st.markdown('<p class="bp-note">Computed from the P&amp;L: each line\'s budget '
                        'variance as its effect on profit. The commentary does not attribute; '
                        'this table does.</p>', unsafe_allow_html=True)

        st.markdown("#### Profit and loss")
        st.markdown(pnl_table_html(view["pnl"]), unsafe_allow_html=True)
        st.markdown(
            '<p class="bp-note">* Material rows are shaded and marked *. Fav/(Adv): favourable '
            'variances plain, adverse in brackets; for costs an overspend is adverse. n/m: not '
            'meaningful, because the comparator is zero or the sign changed. Figures are '
            'calculated before rounding, so totals and differences may not add exactly.</p>',
            unsafe_allow_html=True)

        st.download_button(
            "Download the DRAFT PDF",
            data=view["pdf"],
            file_name=view["pdf_name"],
            mime="application/pdf",
            key="download_draft",
        )
