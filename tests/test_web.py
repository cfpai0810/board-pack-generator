"""Tests for the Streamlit web layer.

The pages run in process with Streamlit's AppTest. W1: every page loads,
the sample draft shows the figures the PDF shows and offers a DRAFT PDF
whose text matches the CLI's. W2: the review stage edits each section with
live flags, signs only with a name and the word SIGN (the engine decides),
saves drafts, offers the FINAL PDF and the audit lines, never reruns the
pipeline on a page rerun, and starts over cleanly. Throughout, the web layer
imports only src.pipeline and hands no Decimal to a widget. No test opens a
network connection (conftest.py blocks sockets suite-wide).
"""

from __future__ import annotations

import ast
from html import escape as html_escape
import io
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = ROOT / "streamlit_app"
BOARD = "pages/2_Board_pack.py"
PAGES = ["Home.py", "pages/1_How_the_pack_is_built.py", BOARD,
         "pages/3_Your_own_data.py", "pages/4_How_its_built.py"]
SECTIONS = ("exec_summary", "pnl", "kpis", "cash")
REASON = " The Retail shortfall followed a fortnight's closure of the Leeds site."
APPROX = "\u2248"


def _app(script: str) -> AppTest:
    return AppTest.from_file(str(APP / script), default_timeout=120)


def _drafted() -> AppTest:
    """The Board pack page after "Run the sample as a draft"."""
    at = _app(BOARD).run()
    at.button(key="bp_run").click().run()
    assert not at.exception, at.exception
    return at


def _markdown(at) -> str:
    return " ".join(m.value for m in at.markdown)


def _edit(at, section: str, change) -> None:
    box = at.text_area(key=f"bp_edit_{section}")
    box.input(change(box.value)).run()


def _sign(at, name="A. Controller", word="SIGN") -> None:
    at.text_input(key="bp_reviewer").input(name)
    at.text_input(key="bp_sign").input(word)
    at.button(key="bp_signoff").click().run()


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(data)).pages]
    return " ".join(" ".join(pages).split())


def _without_run_details(text: str) -> str:
    """Drop what differs between two DRAFT runs of the same inputs: the time and the run id."""
    text = re.sub(r"Generated \d+ \w+ \d{4} at \d\d:\d\d UTC\.", "", text)
    return re.sub(r"Review run: [0-9a-f]{32}\.", "", text)


def _folder(at) -> Path:
    return Path(at.session_state["bp_folder"].name)


def _audit(at) -> list[dict]:
    path = _folder(at) / "audit.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def sample_run():
    return _drafted()


class TestPagesLoad:
    @pytest.mark.parametrize("script", PAGES)
    def test_page_loads_without_error(self, script):
        at = _app(script).run()
        assert not at.exception, at.exception

    def test_home_states_the_governance_promise(self):
        at = _app("Home.py").run()
        text = _markdown(at)
        for promise in ("Python computes.", "A rule selects.", "The commentary narrates.",
                        "A person signs."):
            assert promise in text


class TestSampleRun:
    def test_runs_without_error(self, sample_run):
        assert not sample_run.exception, sample_run.exception

    def test_shows_the_figures_the_pdf_shows(self, sample_run):
        html = _markdown(sample_run)
        assert "(46,120)" in html and "35.0%" in html and "DRAFT" in html
        assert sample_run.text_area(key="bp_edit_exec_summary").value.startswith(
            "Revenue was £2.48m, £112k (4.3%) below budget")

    def test_the_drivers_table_has_six_rows(self, sample_run):
        rows = re.findall(
            r'<tr><td>([^<]*)</td><td>([^<]*)</td><td class="num">([^<]*)</td></tr>',
            _markdown(sample_run))
        assert rows == [
            ("Gross profit", "Retail", "(56,180)"), ("", "Ingredients", "(37,310)"),
            ("", "Export", "(28,810)"), ("EBIT", "Retail", "(56,180)"),
            ("", "Marketing", "(37,640)"), ("", "Ingredients", "(37,310)")]

    def test_the_saved_draft_pdf_matches_the_cli_draft(self, tmp_path):
        import main as cli
        at = _drafted()
        at.button(key="bp_save").click().run()
        saved = at.session_state["bp_saved"]
        assert saved["pdf_name"] == "harmwell_foods_2026_06_board_pack_DRAFT.pdf"
        assert cli.main(["--draft-only", "--output", str(tmp_path)],
                        stdin=io.StringIO(), stdout=io.StringIO()) == 0
        cli_pdf = (tmp_path / saved["pdf_name"]).read_bytes()
        assert _without_run_details(_pdf_text(saved["pdf"])) == \
            _without_run_details(_pdf_text(cli_pdf))

    def test_no_decimal_reaches_the_screen(self):
        at = _drafted()
        at.button(key="bp_save").click().run()
        saved = at.session_state["bp_saved"]
        assert all(isinstance(v, (str, bytes, bool, list)) for v in saved.values())
        assert not any(isinstance(v, Decimal) for v in saved.values())
        assert all(isinstance(at.text_area(key=f"bp_edit_{k}").value, str) for k in SECTIONS)

    def test_the_table_notes_are_the_pdfs(self, sample_run):
        from src.pipeline import DRIVERS_NOTE, pnl_notes
        html = _markdown(sample_run)
        pack = sample_run.session_state["bp_pack"]
        for note in [*pnl_notes(pack), DRIVERS_NOTE]:
            assert html_escape(note) in html, note
        assert "Figures are calculated before rounding" in html


class TestReviewStage:
    def test_a_typed_typo_raises_a_live_flag_and_clears_when_fixed(self):
        at = _drafted()
        _edit(at, "pnl", lambda t: t.replace("£1.64m", "£1.46m"))
        assert ("<li>Profit and loss: &#x27;£1.46m&#x27; matches no figure in the pack "
                "(in the reviewer&#x27;s text)</li>") in _markdown(at)
        _edit(at, "pnl", lambda t: t.replace("£1.46m", "£1.64m"))
        assert "£1.46m" not in _markdown(at)

    def test_an_unprintable_character_raises_a_glyph_flag(self):
        at = _drafted()
        _edit(at, "exec_summary", lambda t: t + f" Cost {APPROX} lost sales.")
        assert ("<li>Executive summary: &#x27;\u2248&#x27; (U+2248) cannot be printed in "
                "the PDF font" in _markdown(at))

    def test_sign_off_with_a_name_and_sign(self):
        at = _drafted()
        _edit(at, "exec_summary", lambda t: t + REASON)
        _sign(at)
        assert not at.exception, at.exception
        result = at.session_state["bp_result"]
        assert result["status"] == "FINAL"
        assert 'class="bp-status final">FINAL<' in _markdown(at)
        assert len(at.text_area) == 0                       # signed text is text, not inputs
        assert "fortnight&#x27;s closure of the Leeds site.</div>" in _markdown(at)
        text = _pdf_text(result["pdf"])
        assert "Reviewed and signed off by A. Controller" in text
        assert "fortnight's closure of the Leeds site" in text

    def test_flags_on_a_final_pack_read_as_acknowledged(self):
        at = _drafted()
        _edit(at, "exec_summary", lambda t: t + " The closure cost £20k.")
        _sign(at)
        html = _markdown(at)
        assert "Acknowledged at sign-off:" in html
        assert ("<li>Executive summary: &#x27;£20k&#x27; matches no figure in the pack "
                "(in the reviewer&#x27;s text)</li>") in html

    def test_the_final_line_uses_the_pdfs_date_form(self):
        from src.pipeline import when_text
        at = _drafted()
        _sign(at)
        pack = at.session_state["bp_pack"]
        assert f"Signed off by A. Controller on {when_text(pack.sign_off_at)}." in _markdown(at)
        assert " UTC." in _markdown(at) and "T0" not in pack.sign_off_at[:10]

    def test_no_draft_download_until_saved_and_then_it_is_timed(self):
        from src.pipeline import when_text
        at = _drafted()
        assert len(at.get("download_button")) == 0          # the unedited draft is not offered
        _edit(at, "exec_summary", lambda t: t + REASON)
        at.button(key="bp_save").click().run()
        (download,) = at.get("download_button")
        saved = at.session_state["bp_saved"]
        assert download.proto.label == f"Download the DRAFT PDF saved {when_text(saved['saved_at'])}"
        assert "fortnight's closure of the Leeds site" in _pdf_text(saved["pdf"])

    def test_a_refused_sign_off_does_not_offer_a_draft_download(self):
        at = _drafted()
        _sign(at, word="sign")
        assert len(at.get("download_button")) == 0

    @pytest.mark.parametrize("name, word, warning", [
        ("A. Controller", "sign",
         "review: sign-off needs the word SIGN typed exactly, so the pack stays DRAFT"),
        ("A. Controller", "",
         "review: sign-off needs the word SIGN typed exactly, so the pack stays DRAFT"),
        ("", "SIGN", "review: sign-off needs a reviewer name, so the pack stays DRAFT"),
    ])
    def test_a_wrong_word_or_blank_name_stays_draft_with_the_engines_warning(
            self, name, word, warning):
        at = _drafted()
        _sign(at, name=name, word=word)
        assert at.session_state["bp_result"]["status"] == "DRAFT"
        assert [w.value for w in at.warning] == [warning]
        assert not any(at.text_area(key=f"bp_edit_{k}").disabled for k in SECTIONS)

    def test_a_refused_attempt_does_not_haunt_the_next_one(self):
        at = _drafted()
        _sign(at, name="", word="SIGN")
        _sign(at)
        assert at.session_state["bp_result"]["status"] == "FINAL"
        final_line = [l for l in _audit(at) if l["event"] == "review"][-1]
        assert final_line["acknowledged"] == []

    def test_save_as_draft_keeps_the_edits(self):
        at = _drafted()
        _edit(at, "exec_summary", lambda t: t + REASON)
        at.button(key="bp_save").click().run()
        result = at.session_state["bp_saved"]
        assert result["status"] == "DRAFT"
        assert "fortnight's closure of the Leeds site" in _pdf_text(result["pdf"])
        last_review = [l for l in _audit(at) if l["event"] == "review"][-1]
        assert (last_review["status"], last_review["mode"]) == ("draft", "interactive")
        assert last_review["sections"][0]["edited"] is True

    def test_the_audit_download_holds_the_linked_pair(self):
        from src.pipeline import audit_text
        at = _drafted()
        _sign(at)
        run_id = at.session_state["bp_result"]["run_id"]
        lines = [json.loads(l) for l in audit_text(_folder(at), run_id).splitlines()]
        assert [(l["event"], l["run_id"]) for l in lines] == [
            ("review", run_id), ("rendered", run_id)]
        assert lines[0]["status"] == "final"

    def test_a_page_rerun_never_runs_the_pipeline(self):
        at = _drafted()
        run_id = at.session_state["bp_pack"].run_id
        _edit(at, "kpis", lambda t: t + " Noted.")
        at.run()
        at.run()
        assert at.session_state["bp_pack"].run_id == run_id
        assert [l["event"] for l in _audit(at)] == ["review", "rendered"]

    def test_start_a_new_draft_after_final_clears_everything(self):
        at = _drafted()
        _sign(at)
        at.button(key="bp_new").click().run()
        kept = ["bp_pack", "bp_result", "bp_folder", "bp_error", "bp_reviewer", "bp_sign",
                *(f"bp_edit_{k}" for k in SECTIONS)]
        assert not any(key in at.session_state for key in kept)
        assert at.button(key="bp_run")             # back to step 1

    def test_unsaved_edits_are_confirmed_before_they_are_discarded(self):
        at = _drafted()
        _edit(at, "cash", lambda t: t + " A customer paid late.")
        at.button(key="bp_new").click().run()
        assert "bp_pack" in at.session_state
        assert [w.value for w in at.warning] == [
            "You have edits that are not saved. Starting a new draft discards them."]
        at.button(key="bp_keep").click().run()
        assert at.text_area(key="bp_edit_cash").value.endswith("A customer paid late.")
        at.button(key="bp_new").click().run()
        at.button(key="bp_discard").click().run()
        assert "bp_pack" not in at.session_state

    def test_the_summary_on_screen_is_what_review_passes_to_confirm(self, monkeypatch):
        import src.pipeline as pipeline
        seen = []
        real = pipeline.confirm_by_word

        def recording(pack, word):
            inner = real(pack, word)
            return lambda summary: seen.append(list(summary)) or inner(summary)
        monkeypatch.setattr(pipeline, "confirm_by_word", recording)

        at = _drafted()
        _edit(at, "exec_summary", lambda t: t + " The closure cost £20k.")
        on_screen = re.findall(r"^\d+\. (.*)$", "\n".join(m.value for m in at.markdown),
                               flags=re.MULTILINE)
        _sign(at)
        assert seen and on_screen == seen[0]
        assert on_screen == ["Executive summary: '£20k' matches no figure in the pack "
                             "(in the reviewer's text)"]


class TestWebLayerBoundary:
    def _sources(self):
        return sorted(APP.rglob("*.py"))

    def test_no_pipeline_logic_in_the_web_layer(self):
        # src.pipeline is the one public surface: no other src module, ever.
        forbidden_calls = {"load", "validate", "compute", "assemble", "narrate",
                           "review", "record_draft", "render", "save_pack"}
        for path in self._sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            src_modules = {m for m in modules if m and (m == "src" or m.startswith("src."))}
            assert src_modules <= {"src.pipeline"}, (path, src_modules)
            calls = {n.func.id for n in ast.walk(tree)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
            assert not calls & forbidden_calls, (path, calls & forbidden_calls)

    def test_the_web_layer_never_handles_decimal_or_float(self):
        for path in self._sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            assert "decimal" not in imported, path
            names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            assert not names & {"Decimal", "float"}, (path, names & {"Decimal", "float"})

    def test_model_id_comes_from_config(self):
        from config import NARRATIVE_MODEL
        from streamlit_app.lib.claude_client import MODEL_ID
        assert MODEL_ID == NARRATIVE_MODEL
        source = (APP / "lib" / "claude_client.py").read_text(encoding="utf-8")
        assert "claude-" not in source

    def test_the_summary_box_is_not_status_green(self):
        from streamlit_app.lib.theme import FINAL, inject_css
        css = inject_css()
        start = css.index(".bp-narrative")
        assert FINAL not in css[start:css.index("}", start)]
        assert css.count(FINAL) == 1          # green appears only on the FINAL chip
