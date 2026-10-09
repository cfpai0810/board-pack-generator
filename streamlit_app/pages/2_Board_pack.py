# =============================================================================
# pages/2_Board_pack.py: the tool, from a draft to a signed pack
# =============================================================================
# "Run it yourself" (W2, the review stage):
#   1. Draft: "Run the sample as a draft" runs run_pipeline with
#      draft_only=True. The Pack stays in session state; only that button runs
#      the pipeline, so a rerun of the page never scatters run ids in the audit.
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
    DRIVERS_NOTE, SIGN_WORD, PackStatus, SectionType, audit_text, check_text,
    drivers_rows, pnl_notes, pnl_rows, review_and_save, run_pipeline, signoff_summary,
    when_text,
)
from streamlit_app.lib.display import (
    drivers_table_html, narrative_html, pnl_table_html, status_chip,
)
from streamlit_app.lib.errors import friendly_message
from streamlit_app.lib.key_gate import render_key_gate
from streamlit_app.lib.theme import header_html, inject_css

PREFIX = "bp_"
PACK, RESULT, ERROR, CONFIRM_NEW = "bp_pack", "bp_result", "bp_error", "bp_confirm_new"
SAVED = "bp_saved"
FOLDER, REVIEWER, SIGN = "bp_folder", "bp_reviewer", "bp_sign"


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


# -- Button callbacks: the only places the pipeline runs -----------------------

def _run_draft() -> None:
    _reset()
    try:
        result = run_pipeline(PNL_PATH, KPIS_PATH, _folder(), draft_only=True)
    except Exception as exc:  # a reader never sees a traceback
        st.session_state[ERROR] = friendly_message(exc)
        return
    st.session_state[PACK] = result.pack
    for section in result.pack.sections:
        st.session_state[_edit_key(section.section_type.value)] = section.narrative


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


def _review_stage(pack) -> None:
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
        _signoff_panel(pack, result)


def _signoff_panel(pack, result) -> None:
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
                 width="stretch")

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


# -- The page --------------------------------------------------------------------

st.markdown(inject_css(), unsafe_allow_html=True)
st.markdown(header_html(
    "Board pack",
    f"{ENTITY_NAME}, {PERIOD}: the monthly management pack, from the source files "
    "to a PDF a named reviewer signs."), unsafe_allow_html=True)
render_key_gate()

example_tab, run_tab = st.tabs(["View a worked example", "Run it yourself"])

with example_tab:
    st.markdown("#### The signed sample pack")
    st.write(
        "This tab will show the signed sample pack and its audit trail, with no run "
        "needed. Until then, run the sample yourself in the next tab.")

with run_tab:
    if st.session_state.get(ERROR):
        st.error(st.session_state[ERROR])

    pack = st.session_state.get(PACK)
    if pack is None:
        st.markdown("#### Run the sample")
        st.write(
            f"Builds the pack for {ENTITY_NAME}, {PERIOD}, from the sample files: the "
            "figures are computed, the material items selected by rule, and the commentary "
            "drafted by the template. You then review it, add the reasons only you know, "
            "and sign it.")
        st.button("Run the sample as a draft", key=f"{PREFIX}run", type="primary",
                  on_click=_run_draft)
    else:
        _review_stage(pack)
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
