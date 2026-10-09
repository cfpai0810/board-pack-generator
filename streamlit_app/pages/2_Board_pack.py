# =============================================================================
# pages/2_Board_pack.py: the tool, from a draft to a signed pack
# =============================================================================
# "Run it yourself":
#   1. Inputs (W3): the source (the sample, or your own P&L CSV and optional
#      KPI CSV with the entity, period and cash unit), the materiality
#      thresholds, and the commentary (the template, or the model when a key
#      is in the sidebar). "Build the draft" runs run_pipeline as a draft
#      through lib/inputs.build_draft. The Pack stays in session state; only
#      that button runs the pipeline, so a rerun never scatters run ids in the
#      audit. Inputs changed after a draft exists need a new draft (sign-off
#      waits until then), and unsaved edits are only discarded on request.
#      The data notes and how the commentary was drafted are shown first.
#   2. Review: each section is an editable box prefilled with the draft, its
#      flags shown live beneath it from check_text. The drivers and P&L tables
#      stay read only, as in the PDF.
#   3. Sign-off: the summary review() will show (signoff_summary), a name box,
#      a box for the word SIGN, and "Save as draft" or "Sign off". Both go
#      through review_and_save: the engine decides, with the same checks, the
#      same SIGN rule and the same audit as the CLI.
#   4. FINAL: the boxes turn read only and the PDF and audit lines are offered.
#      "Start a new draft" clears the session and returns to step 1.
#
# No pipeline logic lives here: the page imports only src.pipeline and its
# lib modules. Each session writes to its own temporary folder, which goes
# when the session ends or a new draft starts.
# =============================================================================

import html
import sys
import tempfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ENTITY_NAME, KPIS_PATH, PERIOD, PNL_PATH
from src.pipeline import (
    DRIVERS_NOTE, SIGN_WORD, PackStatus, PipelineError, SectionType, audit_text,
    check_text, commentary_source, drivers_rows, parse_materiality, pnl_notes, pnl_rows,
    review_and_save, signoff_summary, when_text,
)
from streamlit_app.lib import claude_client
from streamlit_app.lib.display import (
    drivers_table_html, narrative_html, pnl_table_html, status_chip,
)
from streamlit_app.lib.errors import friendly_message
from streamlit_app.lib.inputs import (
    CASH_CHOICES, MAX_MB, MAX_PNL_LINES, MODEL, OWN, SAMPLE, TEMPLATE, RunInputs, Upload,
    build_draft,
)
from streamlit_app.lib.key_gate import render_key_gate
from streamlit_app.lib.theme import header_html, inject_css

PREFIX = "bp_"
PACK, RESULT, ERROR, CONFIRM_NEW = "bp_pack", "bp_result", "bp_error", "bp_confirm_new"
SAVED = "bp_saved"
FOLDER, REVIEWER, SIGN = "bp_folder", "bp_reviewer", "bp_sign"
BUILT_FROM, RUN_NOTES, CONFIRM_BUILD = "bp_built_from", "bp_run_notes", "bp_confirm_build"

# The form's inputs: their own prefix, so starting a new draft keeps them
IN_SOURCE, IN_PNL, IN_KPIS = "in_source", "in_pnl", "in_kpis"
IN_ENTITY, IN_PERIOD, IN_CASH = "in_entity", "in_period", "in_cash"
IN_ABS, IN_PCT, IN_COMMENTARY = "in_abs", "in_pct", "in_commentary"
KEY = "byo_api_key"                       # the sidebar key, read only to build the client


def _edit_key(section_key: str) -> str:
    return f"{PREFIX}edit_{section_key}"


# -- Session helpers -------------------------------------------------------------

def _folder() -> Path:
    """This session's own temporary output folder."""
    if FOLDER not in st.session_state:
        st.session_state[FOLDER] = tempfile.TemporaryDirectory(prefix="board_pack_")
    return Path(st.session_state[FOLDER].name)


def _edits(pack) -> dict[str, str]:
    """The text in each section's box, keyed by section."""
    return {s.section_type.value: st.session_state.get(_edit_key(s.section_type.value),
                                                       s.narrative)
            for s in pack.sections}


def _unsaved(pack) -> bool:
    """Edits on screen that no review has recorded yet."""
    if pack.status is PackStatus.FINAL:
        return False
    edits = _edits(pack)
    return any(edits[s.section_type.value] != s.narrative for s in pack.sections)


def _reset() -> None:
    """Clear everything this page keeps for the session, and its folder."""
    folder = st.session_state.get(FOLDER)
    if folder is not None:
        folder.cleanup()
    for key in [k for k in st.session_state if str(k).startswith(PREFIX)]:
        del st.session_state[key]


def _upload(key: str):
    f = st.session_state.get(key)
    return None if f is None else Upload(f.name, f.getvalue())


def _current_inputs() -> RunInputs:
    """The form as it stands, as the inputs a draft would be built from."""
    ss = st.session_state
    return RunInputs(
        source=ss.get(IN_SOURCE, SAMPLE),
        pnl=_upload(IN_PNL), kpis=_upload(IN_KPIS),
        entity=ss.get(IN_ENTITY, ""), period=ss.get(IN_PERIOD, ""),
        cash_unit=ss.get(IN_CASH, "thousands"),
        materiality_abs=ss.get(IN_ABS, "50,000"), materiality_pct=ss.get(IN_PCT, "10"),
        commentary=ss.get(IN_COMMENTARY, TEMPLATE),
    ).effective()


def _stale(pack) -> bool:
    """The form no longer matches the inputs the draft on screen was built from."""
    return pack is not None and st.session_state.get(BUILT_FROM) != _current_inputs()


# -- Button callbacks: the only places the pipeline runs -----------------------

def _build() -> None:
    """Build the draft from the form; first ask before discarding unsaved edits."""
    pack = st.session_state.get(PACK)
    if pack is not None and _unsaved(pack) and not st.session_state.get(CONFIRM_BUILD):
        st.session_state[CONFIRM_BUILD] = True
        return
    inputs = _current_inputs()
    _reset()
    try:
        client = None
        if inputs.commentary == MODEL:     # built here, from the session key, for this run only
            client = claude_client.build_client(st.session_state.get(KEY, ""))
        result = build_draft(inputs, _folder(), client=client)
    except Exception as exc:  # a reader never sees a traceback
        st.session_state[ERROR] = friendly_message(exc)
        return
    st.session_state[PACK] = result.pack
    st.session_state[BUILT_FROM] = inputs
    st.session_state[RUN_NOTES] = {"data": list(result.data_notes),
                                   "narrate": list(result.narrate_notices)}
    for section in result.pack.sections:
        st.session_state[_edit_key(section.section_type.value)] = section.narrative


def _keep_draft() -> None:
    st.session_state[CONFIRM_BUILD] = False


def _result_view(result) -> dict:
    """What the page keeps of a run: strings and bytes only, never the figures themselves."""
    return {
        "status": result.pack.status.value.upper(),
        "pdf_name": result.pdf_path.name,
        "pdf": result.pdf_path.read_bytes(),
        "run_id": result.pack.run_id,
        "notices": list(result.notices),
        "saved_at": result.saved_at,
    }


def _submit(sign_word) -> None:
    """Save as draft (sign_word None) or sign off: review_and_save decides."""
    st.session_state[ERROR] = None
    pack = st.session_state[PACK]
    try:
        result = review_and_save(pack, _folder(), edits=_edits(pack),
                                 reviewer=st.session_state.get(REVIEWER, ""),
                                 sign_word=sign_word)
    except Exception as exc:
        st.session_state[ERROR] = friendly_message(exc)
        return
    view = _result_view(result)
    st.session_state[RESULT] = view
    if sign_word is None:                 # only "Save as draft" offers a DRAFT download
        st.session_state[SAVED] = view


def _save_draft() -> None:
    _submit(None)


def _sign_off() -> None:
    _submit(st.session_state.get(SIGN, ""))


def _start_new() -> None:
    pack = st.session_state.get(PACK)
    if pack is not None and _unsaved(pack) and not st.session_state.get(CONFIRM_NEW):
        st.session_state[CONFIRM_NEW] = True
        return
    _reset()


def _keep_editing() -> None:
    st.session_state[CONFIRM_NEW] = False


# -- Rendering -------------------------------------------------------------------

LABELS = {
    "exec_summary": "Executive summary",
    "pnl": "Profit and loss: commentary on material lines",
    "kpis": "Key performance indicators: commentary",
    "cash": "Cash balance: commentary",
}
def _flags_html(flags, final: bool = False) -> str:
    """
    The section's flags in their one display form (Flag.message, titled, the
    same words as the sign-off summary and the PDF). Escaped: the text can
    be the reviewer's. On a FINAL pack they are listed as acknowledged.
    """
    if not flags:
        return '<p class="bp-note">No flags.</p>'
    lead = '<p class="bp-note">Acknowledged at sign-off:</p>' if final else ""
    items = "".join(f"<li>{html.escape(f.message)}</li>" for f in flags)
    return f'{lead}<ul class="bp-flags">{items}</ul>'


def _section_box(pack, section, final: bool) -> None:
    """An edit box while the pack is a draft; the signed text, readable, once FINAL."""
    key = section.section_type.value
    if final:
        st.markdown(f"**{LABELS.get(key, section.title)}**")
        st.markdown(narrative_html(section.narrative), unsafe_allow_html=True)
        text = section.narrative
    else:
        st.text_area(LABELS.get(key, section.title), key=_edit_key(key),
                     height=170 if key == SectionType.EXEC_SUMMARY.value else 110)
        text = st.session_state.get(_edit_key(key), section.narrative)
    st.markdown(_flags_html(check_text(pack, key, text), final), unsafe_allow_html=True)


def _signed_line(pack) -> str:
    return f"Signed off by {pack.sign_off_by} on {when_text(pack.sign_off_at)}."


def _review_stage(pack, stale: bool = False) -> None:
    final = pack.status is PackStatus.FINAL
    chip = status_chip(pack.status.value)
    note = _signed_line(pack) if final else "Not signed off."
    st.markdown(f"{chip}&nbsp; {note}", unsafe_allow_html=True)
    if not final:
        st.caption("Edit any section below; flags update as you type. The figures, the "
                   "drivers table and the P&L table are computed and cannot be edited.")

    sections = {s.section_type: s for s in pack.sections}
    _section_box(pack, sections[SectionType.EXEC_SUMMARY], final)
    drivers = drivers_rows(pack)
    if drivers:
        st.markdown("##### Main drivers of the variance against budget")
        st.markdown(drivers_table_html(drivers), unsafe_allow_html=True)
        st.markdown(f'<p class="bp-note">{html.escape(DRIVERS_NOTE)}</p>', unsafe_allow_html=True)
    st.markdown("##### Profit and loss")
    st.markdown(pnl_table_html(pnl_rows(pack)), unsafe_allow_html=True)
    st.markdown("".join(f'<p class="bp-note">{html.escape(note)}</p>' for note in pnl_notes(pack)),
                unsafe_allow_html=True)
    for section_type in (SectionType.PNL, SectionType.KPIS, SectionType.CASH):
        _section_box(pack, sections[section_type], final)

    result = st.session_state.get(RESULT)
    if final:
        _final_downloads(pack, result)
    else:
        _signoff_panel(pack, result, stale)


def _signoff_panel(pack, result, stale: bool = False) -> None:
    st.markdown("#### Sign-off")
    summary = signoff_summary(pack, _edits(pack))
    if summary:
        st.markdown("Outstanding before you sign:")
        st.markdown("\n".join(f"{i}. {line}" for i, line in enumerate(summary, start=1)))
    else:
        st.markdown("Nothing is outstanding.")
    st.text_input("Reviewer name", key=REVIEWER)
    st.text_input(f"Type {SIGN_WORD} to sign off", key=SIGN,
                  help=f"Exactly {SIGN_WORD}, in capitals. Anything else leaves the pack a DRAFT.")
    left, right = st.columns(2)
    left.button("Save as draft", key=f"{PREFIX}save", on_click=_save_draft,
                width="stretch")
    right.button("Sign off", key=f"{PREFIX}signoff", on_click=_sign_off, type="primary",
                 width="stretch", disabled=stale)
    if stale:
        st.caption("Sign-off waits for a draft built from the inputs as they now stand.")

    if result:
        for notice in result["notices"]:
            st.warning(notice)
    saved = st.session_state.get(SAVED)
    if saved:
        st.download_button(f"Download the DRAFT PDF saved {when_text(saved['saved_at'])}",
                           data=saved["pdf"], file_name=saved["pdf_name"],
                           mime="application/pdf", key=f"{PREFIX}dl_draft")


def _final_downloads(pack, result) -> None:
    st.markdown("#### Signed pack")
    st.download_button("Download the FINAL PDF", data=result["pdf"],
                       file_name=result["pdf_name"], mime="application/pdf",
                       key=f"{PREFIX}dl_final")
    st.download_button("Download this pack's audit lines (.jsonl)",
                       data=audit_text(_folder(), result["run_id"]),
                       file_name=f"{Path(result['pdf_name']).stem}_audit.jsonl",
                       mime="application/jsonl", key=f"{PREFIX}dl_audit_pack")
    st.download_button("Download the session's audit log (.jsonl)",
                       data=audit_text(_folder()),
                       file_name="board_pack_session_audit.jsonl",
                       mime="application/jsonl", key=f"{PREFIX}dl_audit_session")


# -- The inputs ------------------------------------------------------------------

def _source_inputs() -> None:
    st.markdown("##### 1. Source")
    st.radio("Source", [SAMPLE, OWN], key=IN_SOURCE, horizontal=True,
             label_visibility="collapsed")
    if st.session_state.get(IN_SOURCE, SAMPLE) == SAMPLE:
        st.caption(f"The sample: {ENTITY_NAME}, {PERIOD}. Its KPI file states cash in thousands.")
        return
    left, right = st.columns(2)
    left.file_uploader("P&L CSV (required)", type=["csv"], key=IN_PNL, max_upload_size=MAX_MB,
                       help="Columns: line_item, category, actuals, budget, prior_year. "
                            "Category is revenue, cogs or opex.")
    right.file_uploader("KPI CSV (optional)", type=["csv"], key=IN_KPIS,
                        max_upload_size=MAX_MB,
                        help="Columns: metric, actual, target, prior_year. Without it the "
                             "KPIs show only the gross margin and no cash balance.")
    st.caption(f"Each file up to {MAX_MB} MB; the P&L up to {MAX_PNL_LINES} lines.")
    left, right = st.columns(2)
    left.text_input("Entity name (required)", key=IN_ENTITY, placeholder="e.g. Test Co Ltd")
    right.text_input("Period (required)", key=IN_PERIOD, placeholder="e.g. September 2026")
    st.radio("Cash in the KPI file is stated in", list(CASH_CHOICES), key=IN_CASH,
             format_func=CASH_CHOICES.get, horizontal=True)
    st.markdown("Start from the sample files:")
    left, right = st.columns(2)
    left.download_button("Sample P&L CSV", data=PNL_PATH.read_bytes(), file_name="pnl.csv",
                         mime="text/csv", key="in_dl_pnl", on_click="ignore")
    right.download_button("Sample KPI CSV", data=KPIS_PATH.read_bytes(), file_name="kpis.csv",
                          mime="text/csv", key="in_dl_kpis", on_click="ignore")
    st.markdown(
        '<p class="bp-note">Amounts are treated as pounds sterling. Your files are written '
        "only to this session's own temporary folder on the server, read once to build the "
        "pack, then deleted.</p>", unsafe_allow_html=True)


def _materiality_inputs() -> None:
    st.markdown("##### 2. Materiality")
    left, right = st.columns(2)
    left.text_input("Absolute threshold (£)", key=IN_ABS)
    right.text_input("Percentage threshold (%)", key=IN_PCT)
    try:
        parse_materiality(st.session_state[IN_ABS], st.session_state[IN_PCT])
    except PipelineError as exc:
        st.error(str(exc))
    st.caption("A line or subtotal is material when its variance against budget reaches "
               "either threshold.")


def _commentary_inputs(has_key: bool) -> None:
    st.markdown("##### 3. Commentary")
    st.radio("Draft the commentary with", [TEMPLATE, MODEL], key=IN_COMMENTARY,
             horizontal=True, disabled=not has_key)
    if has_key:
        st.markdown(
            '<p class="bp-note">With Model, only the formatted figures and names in the pack '
            f"facts are sent to {claude_client.MODEL_ID}, never your files. The figures, the "
            "materiality and the checks are the same either way, and if the call fails the "
            "template drafts instead.</p>", unsafe_allow_html=True)
    else:
        st.caption("Add your Anthropic API key in the sidebar to draft with the model.")


def _inputs(has_key: bool) -> None:
    for key, value in ((IN_ABS, "50,000"), (IN_PCT, "10"), (IN_COMMENTARY, TEMPLATE)):
        st.session_state.setdefault(key, value)
    if not has_key:                        # no key, no model: the choice falls back
        st.session_state[IN_COMMENTARY] = TEMPLATE
    _source_inputs()
    _materiality_inputs()
    _commentary_inputs(has_key)
    if st.session_state.get(CONFIRM_BUILD):
        st.warning("You have edits that are not saved. Building a new draft discards them.")
        left, right = st.columns(2)
        left.button("Discard edits and build the new draft", key=f"{PREFIX}discard_build",
                    on_click=_build, width="stretch")
        right.button("Keep editing", key=f"{PREFIX}keep_build", on_click=_keep_draft,
                     width="stretch")
    else:
        st.button("Build the draft", key=f"{PREFIX}run", type="primary", on_click=_build)


def _run_notes(pack) -> None:
    """The data notes, then how the commentary was drafted: read before reviewing."""
    notes = st.session_state.get(RUN_NOTES, {"data": [], "narrate": []})
    with st.container(border=True):
        st.markdown("##### Data notes")
        if notes["data"]:
            items = "".join(f"<li>{html.escape(n)}</li>" for n in notes["data"])
            st.markdown(f'<ol class="bp-datanotes">{items}</ol>', unsafe_allow_html=True)
        else:
            st.markdown('<p class="bp-note">None: every row loaded and passed the checks.</p>',
                        unsafe_allow_html=True)
    for notice in notes["narrate"]:
        st.warning(notice)
    st.caption(f"Commentary drafted by: {commentary_source(pack)}")


# -- The page --------------------------------------------------------------------

st.markdown(inject_css(), unsafe_allow_html=True)
st.markdown(header_html(
    "Board pack",
    "The monthly management pack, from the source files to a PDF a named reviewer signs."),
    unsafe_allow_html=True)
has_key = render_key_gate() is not None

example_tab, run_tab = st.tabs(["View a worked example", "Run it yourself"])

with example_tab:
    st.markdown("#### The signed sample pack")
    st.write(
        "This tab will show the signed sample pack and its audit trail, with no run "
        "needed. Until then, run the sample yourself in the next tab.")

with run_tab:
    pack = st.session_state.get(PACK)
    if pack is None:
        st.markdown("#### Build a draft")
        st.write(
            "Choose the files, the materiality thresholds and how the commentary is drafted. "
            "The figures are computed and the material items selected by rule; you then "
            "review the draft, add the reasons only you know, and sign it.")
        _inputs(has_key)
        if st.session_state.get(ERROR):
            st.error(st.session_state[ERROR])
    else:
        stale = _stale(pack)
        with st.expander("Inputs for this draft", expanded=stale):
            _inputs(has_key)
        if stale:
            st.warning("The inputs have changed since this draft was built. Build a new "
                       "draft to use them.")
        if st.session_state.get(ERROR):
            st.error(st.session_state[ERROR])
        _run_notes(pack)
        _review_stage(pack, stale)
        st.divider()
        if st.session_state.get(CONFIRM_NEW):
            st.warning("You have edits that are not saved. Starting a new draft discards them.")
            left, right = st.columns(2)
            left.button("Discard edits and start a new draft", key=f"{PREFIX}discard",
                        on_click=_start_new, width="stretch")
            right.button("Keep editing", key=f"{PREFIX}keep", on_click=_keep_editing,
                         width="stretch")
        else:
            st.button("Start a new draft", key=f"{PREFIX}new", on_click=_start_new)
