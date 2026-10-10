"""Tests for the Streamlit web layer.

The pages run in process with Streamlit's AppTest. W1: every page loads,
the sample draft shows the figures the PDF shows and offers a DRAFT PDF
whose text matches the CLI's. W2: the review stage edits each section with
live flags, signs only with a name and the word SIGN (the engine decides),
saves drafts, offers the FINAL PDF and the audit lines, never reruns the
pipeline on a page rerun, and starts over cleanly. Throughout, the web layer
imports only src.pipeline and hands no Decimal to a widget. W3: own files
(uploaded through AppTest's file uploader, and staged by lib/inputs, which
is also tested directly), the entity, period and cash unit, the thresholds,
and the model choice with a fake client; inputs changed after a draft need
a new one. No test opens a network connection (conftest.py blocks sockets
suite-wide).
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

import types

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


def _page(script: str) -> AppTest:
    """A page as a visitor reaches it: through Home's navigation, so its page links resolve."""
    at = _app("Home.py").run()
    if script != "Home.py":
        at.switch_page(script).run()
    return at


def _drafted() -> AppTest:
    """The Board pack page after "Run the sample as a draft"."""
    at = _app(BOARD).run()
    at.button(key="bp_run").click().run()
    assert not at.exception, at.exception
    return at


def _beyond_example(at, kind: str) -> list:
    """
    The page's elements of one kind, leaving out the worked example tab: the
    Board pack page's run tests read the page around the run, and the worked
    example (a signed pack, with its own flag and downloads) is tested on its own.
    """
    elements = list(at.get(kind))
    if not at.tabs:
        return elements
    skip = {id(e) for e in at.tabs[0].get(kind)}
    return [e for e in elements if id(e) not in skip]


def _markdown(at) -> str:
    return " ".join(m.value for m in _beyond_example(at, "markdown"))


def _downloads(at) -> list:
    return _beyond_example(at, "download_button")


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
        at = _page(script)
        assert not at.exception, at.exception

    def test_home_states_the_governance_promise(self):
        at = _app("Home.py").run()
        text = _markdown(at)
        for promise in ("Python computes.", "A rule selects.", "The commentary reports.",
                        "The reviewer signs."):
            assert promise in text


class TestSampleRun:
    def test_runs_without_error(self, sample_run):
        assert not sample_run.exception, sample_run.exception

    def test_shows_the_figures_the_pdf_shows(self, sample_run):
        html = _markdown(sample_run)
        assert "(46,120)" in html and "35.0%" in html and "DRAFT" in html
        assert sample_run.text_area(key="bp_edit_exec_summary").value.startswith(
            "Marketing was £298k, £38k (14.5%) above budget")

    def test_opens_as_the_pdf_opens(self, sample_run):
        """The headline, summary line and tiles, from the src functions the PDF draws them with."""
        from html import escape
        from src.pipeline import headline_sentence, headline_tiles, summary_line
        pack, md = sample_run.session_state["bp_pack"], _markdown(sample_run)
        assert headline_sentence(pack) == ("EBIT was a loss of £46k: £193k below budget and "
                                           "£147k below last year.")
        tiles = [escape(text) for t in headline_tiles(pack)
                 for text in (t.label, t.value, t.budget, t.last_year)]
        at = 0
        for text in [escape(headline_sentence(pack)), escape(summary_line(pack)), *tiles]:
            at = md.index(text, at) + len(text)        # each one after the one before
        assert "£128k (5.5%) above last year" in tiles

    def test_shows_the_charts_the_pdf_draws(self, sample_run):
        md = _markdown(sample_run)
        titles = ["The budget-to-actual bridge", "Each line's effect on profit against budget",
                  "Cash balance"]
        positions = [md.index(f"<title>{title}</title>") for title in titles]
        assert positions == sorted(positions) and md.count("<svg") == 3
        assert "\n" not in md[md.index("<svg"):md.rindex("</svg>")]    # never a code block
        ids = re.findall(r'(?<![\w-])id="([^"]+)"', md)
        assert len(ids) == len(set(ids))      # no chart takes another's clip path
        assert set(re.findall(r"url\(#([^)]+)\)", md)) <= set(ids)
        assert md.index("<title>The budget-to-actual bridge") < md.index("Main drivers of the")
        assert md.index("Revenue was £112k (4.3%) below budget, with all three") < positions[1]

    def test_the_drivers_table_has_six_rows(self, sample_run):
        rows = re.findall(
            r'<tr><td>([^<]*)</td><td class="label">([^<]*)</td><td class="num">([^<]*)</td></tr>',
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
        assert len(_downloads(at)) == 0                     # the unedited draft is not offered
        _edit(at, "exec_summary", lambda t: t + REASON)
        at.button(key="bp_save").click().run()
        (download,) = _downloads(at)
        saved = at.session_state["bp_saved"]
        assert download.proto.label == f"Download the DRAFT PDF saved {when_text(saved['saved_at'])}"
        assert "fortnight's closure of the Leeds site" in _pdf_text(saved["pdf"])

    def test_a_refused_sign_off_does_not_offer_a_draft_download(self):
        at = _drafted()
        _sign(at, word="sign")
        assert len(_downloads(at)) == 0

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
        on_screen = re.findall(r"^\d+\. (.*)$",
                               "\n".join(m.value for m in _beyond_example(at, "markdown")),
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

    def test_controls_are_ink_not_the_default_red(self):
        import tomllib
        from streamlit_app.lib.theme import INK
        theme = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
        assert theme["theme"]["primaryColor"] == INK

    def test_the_hosted_app_matches_what_the_pages_state(self):
        # The server's upload limit is the one page 3 states, and visitors get no
        # developer toolbar or Deploy button.
        import tomllib
        from streamlit_app.lib.inputs import MAX_MB
        config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
        assert config["server"]["maxUploadSize"] == MAX_MB
        assert config["client"]["toolbarMode"] == "minimal"
        assert not (ROOT / ".streamlit" / "secrets.toml").exists()

    def test_the_key_never_reaches_a_file(self, monkeypatch):
        # Privacy: the key lives in session state only. After a model run, no
        # file the session wrote (the PDF, the audit lines) contains it.
        from streamlit_app.lib import claude_client
        monkeypatch.setattr(claude_client, "build_client", lambda key: FakeClient())
        at = _with_key(_app(BOARD).run())
        at.radio(key="in_commentary").set_value("Model").run()
        at.button(key="bp_run").click().run()
        assert at.session_state["bp_pack"].narrative_model == "claude-sonnet-4-6"
        written = [p for p in _folder(at).rglob("*") if p.is_file()]
        assert written and not any(FAKE_KEY.encode() in p.read_bytes() for p in written)
        assert sorted(p.suffix for p in written) == [".jsonl", ".pdf"]

    def test_the_summary_box_is_not_status_green(self):
        from streamlit_app.lib.theme import FINAL, inject_css
        css = inject_css()
        start = css.index(".bp-commentary")
        assert FINAL not in css[start:css.index("}", start)]
        assert css.count(FINAL) == 1          # green appears only on the FINAL chip


# ── W3: YOUR OWN DATA, THRESHOLDS AND THE MODEL ───────────────────────

SAMPLE_PNL = (ROOT / "data" / "pnl.csv").read_bytes()
SAMPLE_KPIS = (ROOT / "data" / "kpis.csv").read_bytes()
POUNDS_KPIS = (b"metric,actual,target,prior_year\r\nHeadcount,214,205,198\r\n"
               b"Cash balance (GBP),1176000,1350000,1288000\r\n")
FAKE_KEY = "sk-ant-" + "0" * 40              # shaped like a key; never sent anywhere
MODEL_SECTIONS = {
    "exec_summary": "Revenue was £2.48m, £112k (4.3%) below budget.",
    "pnl": "Retail was £56k (3.3%) below budget.",
    "kpis": "Headcount was 214, 9 above target.",
    "cash": "The cash balance was £1.18m, £174k below target.",
}


class FakeClient:
    """Stands in for anthropic.Anthropic: client.messages.create(**kwargs)."""

    def __init__(self, error=None):
        self.error, self.calls = error, []
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return types.SimpleNamespace(
            model="claude-sonnet-4-6", stop_reason="end_turn",
            content=[types.SimpleNamespace(type="text", text=json.dumps(MODEL_SECTIONS))],
            usage=types.SimpleNamespace(input_tokens=1840, output_tokens=412))


def _own(at, pnl=SAMPLE_PNL, kpis=SAMPLE_KPIS, entity="Test Co", period="September 2026",
         cash="thousands", build=True):
    """Choose own files on the form, fill it in, and (by default) build the draft."""
    at.radio(key="in_source").set_value("Use my own files").run()
    if pnl is not None:
        at.file_uploader(key="in_pnl").set_value(("pnl.csv", pnl, "text/csv"))
    if kpis is not None:
        at.file_uploader(key="in_kpis").set_value(("kpis.csv", kpis, "text/csv"))
    at.text_input(key="in_entity").input(entity)
    at.text_input(key="in_period").input(period)
    at.radio(key="in_cash").set_value(cash)
    at.run()
    if build:
        at.button(key="bp_run").click().run()
    assert not at.exception, at.exception
    return at


def _text(at) -> str:
    """Everything the page says: markdown, captions, alerts and the edit boxes."""
    parts = [m.value for m in _beyond_example(at, "markdown")]
    parts += [c.value for c in _beyond_example(at, "caption")]
    parts += [e.value for e in at.error] + [w.value for w in at.warning]
    parts += [t.value for t in at.text_area]
    return " ".join(parts)


def _final_pdf(at) -> bytes:
    _sign(at)
    assert at.session_state["bp_result"]["status"] == "FINAL"
    return at.session_state["bp_result"]["pdf"]


def _no_dates(text: str) -> str:
    text = re.sub(r"\d{1,2} \w+ \d{4} at \d\d:\d\d UTC", "<when>", text)
    return re.sub(r"Review run: [0-9a-f]{32}\.", "", text)


def _with_key(at):
    at.sidebar.text_input(key="byo_api_key").input(FAKE_KEY).run()
    return at


class TestOwnFiles:
    def test_the_sample_as_own_files_gives_the_sample_pack(self):
        sample = _app(BOARD).run()
        sample.button(key="bp_run").click().run()
        own = _own(_app(BOARD).run(), entity="Harmwell Foods Ltd", period="June 2026")
        a, b = _final_pdf(sample), _final_pdf(own)
        assert _no_dates(_pdf_text(a)) == _no_dates(_pdf_text(b))
        assert own.session_state["bp_result"]["pdf_name"] == \
            "harmwell_foods_2026_06_board_pack_FINAL.pdf"

    def test_test_co_september(self):
        at = _own(_app(BOARD).run())
        pack = at.session_state["bp_pack"]
        assert (pack.entity, pack.period) == ("Test Co", "September 2026")
        _edit(at, "exec_summary", lambda t: t + " The September 2026 close ran to plan.")
        assert "matches no figure" not in _markdown(at)       # the period is not a figure
        pdf = _final_pdf(at)
        assert at.session_state["bp_result"]["pdf_name"] == "test_co_2026_09_board_pack_FINAL.pdf"
        text = _pdf_text(pdf)
        assert "Test Co Monthly board pack, September 2026" in text
        assert "Entity and period: Test Co, September 2026." in text
        page = _text(at)
        for stale in ("Harmwell", "June"):
            assert stale not in text and stale not in page, stale

    def test_cash_stated_in_pounds(self):
        at = _own(_app(BOARD).run(), kpis=POUNDS_KPIS, cash="pounds")
        cash = at.text_area(key="bp_edit_cash").value
        assert "£1.18m" in cash and "bn" not in cash

    def test_no_kpi_file(self):
        at = _own(_app(BOARD).run(), kpis=None)
        pack = at.session_state["bp_pack"]
        assert [k["metric"] for k in pack.section(pack.sections[2].section_type).figures["kpis"]] \
            == ["Gross margin (%)"]
        assert at.text_area(key="bp_edit_cash").value == "No cash balance was supplied."
        assert "No KPI file was supplied, so the KPIs show only the gross margin" in _markdown(at)

    def test_45k_puts_opex_in_the_executive_summary(self):
        at = _app(BOARD).run()
        at.text_input(key="in_abs").input("45,000").run()
        at.button(key="bp_run").click().run()
        pack = at.session_state["bp_pack"]
        assert "Opex" in [pack.item(k)["name"] for k in pack.material_flags.exec_summary_items]
        assert "£45,000" in _markdown(at)                    # the material key under the P&L

    @pytest.mark.parametrize("abs_text, pct_text, says", [
        ("0", "10", "The absolute threshold must be a positive amount"),
        ("50,000", "150", "The percentage threshold must be above 0 and at most 100")])
    def test_a_bad_threshold_is_refused_plainly(self, abs_text, pct_text, says):
        at = _app(BOARD).run()
        at.text_input(key="in_abs").input(abs_text)
        at.text_input(key="in_pct").input(pct_text).run()
        assert says in " ".join(e.value for e in at.error)
        at.button(key="bp_run").click().run()
        assert not at.exception and "bp_pack" not in at.session_state

    @pytest.mark.parametrize("pnl, says", [
        (SAMPLE_PNL + b"x" * (1024 * 1024), "the limit is 1 MB"),
        (b"line_item,category,actuals,budget,prior_year\n"
         + b"Rent,opex,1,1,1\n" * 501, "has 501 lines; the limit is 500"),
        (b"line_item,category,actuals,prior_year\nRetail,revenue,1,1\n",
         "The P&L file is missing the column budget"),
        (b"line_item,category,actuals,budget,prior_year\nRetail,revenue,lots,1,1\n",
         "no lines that could be loaded"),
    ], ids=["over-1MB", "over-500-lines", "missing-column", "no-loadable-lines"])
    def test_a_file_that_cannot_be_used_gives_a_plain_message_and_no_pack(self, pnl, says):
        at = _own(_app(BOARD).run(), pnl=pnl)
        assert says in " ".join(e.value for e in at.error)
        assert "Traceback" not in _text(at)
        assert "bp_pack" not in at.session_state and len(at.text_area) == 0
        assert list(_folder(at).iterdir()) == []                # nothing written, nothing kept

    def test_the_form_must_be_complete(self):
        at = _own(_app(BOARD).run(), pnl=None, entity="", period="")
        assert ("To build from your own files, upload a P&L CSV file (the KPI file is "
                "optional); type the entity name; type the period, such as September 2026."
                in " ".join(e.value for e in at.error))
        assert "bp_pack" not in at.session_state

    def test_the_data_notes_panel(self):
        long_name = b"Ingredients, packaging and inbound freight for the Leeds and York sites"
        rows = SAMPLE_PNL.splitlines()
        rows[4] = b'"' + long_name + b'"' + rows[4][rows[4].index(b","):]
        rows[5] = rows[5][rows[5].index(b","):]
        pnl = b"\r\n".join(rows + [b"Rent,opex,n/a,1,1"]) + b"\r\n"
        at = _own(_app(BOARD).run(), pnl=pnl)
        html = _markdown(at)
        notes = at.session_state["bp_run_notes"]["data"]
        assert len(notes) >= 4
        for note in notes:
            assert html_escape(note) in html, note
        assert html.index("Data notes") < html.index("Profit and loss")
        joined = " ".join(notes)
        for expected in ("P&L row 13 (Rent): the actual 'n/a' could not be read",
                         "it is kept as 'Unnamed COGS line'", "is longer than 60 characters",
                         "These totals exclude 1 row of the source file that could not be "
                         "read: Rent (row 13)."):
            assert expected in joined, expected

    def test_a_clean_sample_has_no_data_notes(self, sample_run):
        assert "None: every row loaded and passed the checks." in _markdown(sample_run)
        assert "Commentary drafted by: Template" in _text(sample_run)

    def test_uploads_are_deleted_after_the_run(self):
        at = _own(_app(BOARD).run())
        assert not (_folder(at) / "inputs").exists()
        assert sorted(p.suffix for p in _folder(at).iterdir()) == [".jsonl", ".pdf"]

    def test_the_page_says_what_happens_to_the_files(self):
        at = _own(_app(BOARD).run(), build=False)
        text = _text(at)
        assert "Amounts are treated as pounds sterling." in text
        assert ("Your files are written only to this session's own temporary folder on "
                "the server, read once to build the pack, then deleted." in text)
        assert [d.proto.label for d in _downloads(at)] == [
            "Sample P&L CSV", "Sample KPI CSV"]

    def test_the_header_names_no_sample_entity(self):
        at = _own(_app(BOARD).run(), build=False)
        assert "Harmwell" not in _markdown(at)


class TestChangedInputs:
    def test_changed_inputs_need_a_new_draft(self):
        at = _drafted()
        assert not at.button(key="bp_signoff").disabled
        at.text_input(key="in_abs").input("45,000").run()
        assert "The inputs have changed since this draft was built." in _text(at)
        assert at.button(key="bp_signoff").disabled
        at.text_input(key="in_abs").input("50,000").run()        # put back: the same inputs
        assert not at.button(key="bp_signoff").disabled
        at.text_input(key="in_abs").input("45,000").run()
        first = at.session_state["bp_pack"].run_id
        at.button(key="bp_run").click().run()
        assert at.session_state["bp_pack"].run_id != first
        assert not at.button(key="bp_signoff").disabled
        assert "The inputs have changed" not in _text(at)

    def test_unsaved_edits_are_confirmed_before_a_new_build(self):
        at = _drafted()
        _edit(at, "exec_summary", lambda t: t + REASON)
        at.text_input(key="in_abs").input("45,000").run()
        at.button(key="bp_run").click().run()
        assert "Building a new draft discards them." in _text(at)
        at.button(key="bp_keep_build").click().run()
        assert REASON in at.text_area(key="bp_edit_exec_summary").value
        at.button(key="bp_run").click().run()
        at.button(key="bp_discard_build").click().run()
        assert REASON not in at.text_area(key="bp_edit_exec_summary").value
        assert at.session_state["bp_built_from"].materiality_abs == "45,000"

    def test_saved_edits_need_no_confirmation(self):
        at = _drafted()
        _edit(at, "cash", lambda t: t + " A customer paid late.")
        at.button(key="bp_save").click().run()
        at.text_input(key="in_pct").input("5").run()
        at.button(key="bp_run").click().run()
        assert "Building a new draft discards them." not in _text(at)
        assert at.session_state["bp_built_from"].materiality_pct == "5"


class TestModelChoice:
    def test_no_key_disables_the_model(self):
        at = _app(BOARD).run()
        radio = at.radio(key="in_commentary")
        assert radio.disabled and radio.value == "Template"
        assert ("Add your Anthropic API key in the sidebar to have the model (Claude, via "
                "the Anthropic API) draft it.") in _text(at)

    def test_the_model_drafts_every_section_with_the_token_line(self, monkeypatch):
        from streamlit_app.lib import claude_client
        fake, built = FakeClient(), []
        monkeypatch.setattr(claude_client, "build_client",
                            lambda key: built.append(key == FAKE_KEY) or fake)
        at = _with_key(_app(BOARD).run())
        radio = at.radio(key="in_commentary")
        assert not radio.disabled
        radio.set_value("Model").run()
        assert ("Only the formatted figures and names in the facts are sent to it, never "
                "your files.") in _text(at)
        at.button(key="bp_run").click().run()
        assert not at.exception, at.exception
        pack = at.session_state["bp_pack"]
        assert {s.drafted_by for s in pack.sections} == {"model"}
        assert built == [True] and len(fake.calls) == 1        # one client, one call
        assert ("Commentary drafted by: claude-sonnet-4-6, 1,840 input and 412 output tokens"
                in _text(at))
        assert at.text_area(key="bp_edit_exec_summary").value == MODEL_SECTIONS["exec_summary"]

    def test_the_model_sees_no_file_bytes(self, monkeypatch):
        from streamlit_app.lib import claude_client
        fake = FakeClient()
        monkeypatch.setattr(claude_client, "build_client", lambda key: fake)
        at = _with_key(_app(BOARD).run())
        at.radio(key="in_commentary").set_value("Model").run()
        _own(at)
        sent = json.dumps(fake.calls[0])
        assert "line_item,category" not in sent and "1643820" not in sent
        assert "Test Co" in sent and "September 2026" in sent

    def test_a_failed_call_shows_the_template_and_the_notice(self, monkeypatch):
        from streamlit_app.lib import claude_client
        monkeypatch.setattr(claude_client, "build_client",
                            lambda key: FakeClient(error=RuntimeError("down")))
        at = _with_key(_app(BOARD).run())
        at.radio(key="in_commentary").set_value("Model").run()
        at.button(key="bp_run").click().run()
        pack = at.session_state["bp_pack"]
        assert {s.drafted_by for s in pack.sections} == {"template"}
        assert ("Commentary: the model call failed (RuntimeError), so the template drafted "
                "every section." in " ".join(w.value for w in at.warning))
        assert "Commentary drafted by: Template" in _text(at)

    def test_removing_the_key_falls_back_to_the_template(self, monkeypatch):
        at = _with_key(_app(BOARD).run())
        at.radio(key="in_commentary").set_value("Model").run()
        at.sidebar.text_input(key="byo_api_key").input("").run()
        radio = at.radio(key="in_commentary")
        assert radio.disabled and radio.value == "Template"


class TestUploadHandling:
    """lib/inputs directly: the limits, the staging folder, the clean-up."""

    def test_size_and_line_limits(self):
        from streamlit_app.lib.inputs import MAX_BYTES, Upload, UploadError, check_upload
        check_upload("P&L", Upload("p.csv", b"h\n" + b"x\n" * 500), 500)
        with pytest.raises(UploadError, match="has 501 lines; the limit is 500"):
            check_upload("P&L", Upload("p.csv", b"h\n" + b"x\n" * 501), 500)
        check_upload("KPI", Upload("k.csv", b"x" * MAX_BYTES))
        with pytest.raises(UploadError, match="is 1,025 KB; the limit is 1 MB"):
            check_upload("KPI", Upload("k.csv", b"x" * (MAX_BYTES + 1)))

    def test_blank_lines_do_not_count(self):
        from streamlit_app.lib.inputs import Upload, check_upload
        check_upload("P&L", Upload("p.csv", b"h\n" + b"x\n\n\n" * 500), 500)

    def test_staged_under_fixed_names_in_the_session_folder(self, tmp_path):
        from streamlit_app.lib.inputs import OWN, RunInputs, Upload, stage
        inputs = RunInputs(source=OWN, pnl=Upload("../../evil.csv", SAMPLE_PNL),
                           kpis=Upload("C:/Windows/kpis.csv", SAMPLE_KPIS),
                           entity="Test Co", period="September 2026")
        pnl, kpis = stage(inputs, tmp_path)
        assert (pnl, kpis) == (tmp_path / "inputs" / "pnl.csv", tmp_path / "inputs" / "kpis.csv")
        assert pnl.read_bytes() == SAMPLE_PNL and kpis.read_bytes() == SAMPLE_KPIS
        assert sorted(p for p in tmp_path.rglob("*") if p.is_file()) == sorted([kpis, pnl])

    def test_the_sample_is_never_copied(self, tmp_path):
        from config import KPIS_PATH, PNL_PATH
        from streamlit_app.lib.inputs import RunInputs, stage
        assert stage(RunInputs(), tmp_path) == (PNL_PATH, KPIS_PATH)
        assert list(tmp_path.iterdir()) == []

    def test_build_draft_deletes_the_uploads_whatever_happens(self, tmp_path):
        from src.pipeline import PipelineError
        from streamlit_app.lib.inputs import OWN, RunInputs, Upload, build_draft
        good = RunInputs(source=OWN, pnl=Upload("p.csv", SAMPLE_PNL), entity="Test Co",
                         period="September 2026")
        result = build_draft(good, tmp_path / "a")
        assert result.pack.entity == "Test Co" and not (tmp_path / "a" / "inputs").exists()
        bad = RunInputs(source=OWN, pnl=Upload("p.csv", b"line_item,category\nRetail,revenue\n"),
                        entity="Test Co", period="September 2026")
        with pytest.raises(PipelineError, match="missing the columns actuals, budget, prior_year"):
            build_draft(bad, tmp_path / "b")
        assert list((tmp_path / "b").iterdir()) == []

    def test_a_refused_form_writes_nothing(self, tmp_path):
        from streamlit_app.lib.inputs import OWN, RunInputs, UploadError, build_draft
        with pytest.raises(UploadError, match="upload a P&L CSV file"):
            build_draft(RunInputs(source=OWN, entity="Test Co", period="May 2026"), tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_with_the_sample_the_own_file_fields_do_not_count(self):
        from streamlit_app.lib.inputs import RunInputs, Upload
        assert RunInputs(entity="Test Co", pnl=Upload("p.csv", b"x")).effective() == RunInputs()


# ── W4: THE CONTENT PAGES AND THE WORKED EXAMPLE ───────────────────────

CONTENT = ["pages/1_How_the_pack_is_built.py", "pages/3_Your_own_data.py",
           "pages/4_How_its_built.py"]
PLACEHOLDER = re.compile(r"will (show|explain|describe)|until then|placeholder|coming soon|"
                         r"\bTODO\b|\bW[1-5]\b|lorem", re.IGNORECASE)


def _everything(at) -> str:
    """All the text a page shows: markdown, captions, code, alerts and link labels."""
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    parts += [c.value for c in at.code] + [e.value for e in at.error]
    parts += [w.value for w in at.warning] + [p.proto.label for p in at.get("page_link")]
    return " ".join(parts)


def _sample_figures() -> set[str]:
    """
    Every figure of the sample in every form a page could print it: the table
    cells, the prose amounts, the percentages and points, the KPI values, the
    thresholds, the material item count, and the test counts.
    """
    from config import KPIS_PATH, PNL_PATH
    from src.formatting import prose_money, table_number, table_value
    from src.pipeline import (
        build_pack, count_words, drivers_rows, material_items, pnl_rows, thresholds,
    )
    pack = build_pack(PNL_PATH, KPIS_PATH)
    figures = set()
    for row in pnl_rows(pack):
        figures |= {c for c in row.cells if c not in ("", "n/m")}
    figures |= {r.impact for r in drivers_rows(pack)}
    values = [getattr(pack.subtotals, f) for f in vars(pack.subtotals)
              if getattr(pack.subtotals, f) is not None]
    for line in pack.pnl_lines:
        values += [line.actuals, line.budget, line.prior_year, line.var_budget_abs, line.var_py_abs]
    figures |= {prose_money(v) for v in values if abs(v) >= 1000}
    figures |= {table_value(v) for v in values}
    for kpi in pack.kpis:
        figures |= {table_number(v) for v in (kpi.actual, kpi.target, kpi.prior_year,
                                              kpi.delta_target, kpi.delta_py) if v is not None}
    figures |= set(thresholds(pack)) | {t.lstrip("£") for t in thresholds(pack)}
    figures.add(f"{count_words(len(material_items(pack)))} material")
    counts = json.loads((ROOT / "generated" / "test_counts.json").read_text(encoding="utf-8"))
    figures.add(str(counts["total"]))
    figures |= {str(a["tests"]) for a in counts["by_area"]}
    cleaned = {f.strip("()+-") for f in figures}
    return {f for f in cleaned if sum(ch.isdigit() for ch in f) >= 2 or " material" in f}


def _string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


class TestContentPages:
    def test_no_placeholder_text_on_any_page(self):
        for script in PAGES:
            at = _page(script)
            text = _everything(at)
            assert not PLACEHOLDER.search(text), (script, PLACEHOLDER.search(text))

    def test_every_internal_link_works(self):
        names = {Path(p).stem.split("_", 1)[1] for p in PAGES if p.startswith("pages/")}
        seen = set()
        for script in PAGES:
            for link in _page(script).get("page_link"):
                assert link.proto.page in names, (script, link.proto.page)
                seen.add(link.proto.page)
        assert seen == names                              # every page is reachable by a link
        for script in PAGES[1:]:
            assert not _page(script).exception

    def test_no_sample_figure_is_typed_into_a_page(self):
        figures = _sample_figures()
        assert {"50,000", "£50,000", "10.0%", "193,120", "£2.48m", "six material"} <= figures
        sources = [APP / "Home.py", *(APP / "pages").glob("*.py"), *(APP / "lib").glob("*.py")]
        for path in sources:
            for text in _string_constants(path):
                for figure in figures:
                    found = re.search(rf"(?<![\w.,]){re.escape(figure)}(?![\w.,])", text)
                    assert not found, (path.name, figure, text[:80])

    def test_the_method_page_quotes_the_engine(self):
        from config import KPIS_PATH, PNL_PATH
        from src.pipeline import (
            build_pack, drivers_rows, fav_adv_examples, headline, material_items, thresholds,
        )
        pack = build_pack(PNL_PATH, KPIS_PATH)
        text = _everything(_page(CONTENT[0]))
        top = headline(pack)
        assert f"EBIT is {top['ebit']} against {top['ebit_budget']}" in text
        abs_text, pct_text = thresholds(pack)
        assert f"{abs_text} or more, or {pct_text} of budget" in text
        assert "the rule finds six material items" in text
        for item in material_items(pack):
            assert f"<td>{html_escape(item.name)}</td>" in text and item.variance in text
        for row in drivers_rows(pack):
            assert row.impact in text
        for example in fav_adv_examples(pack):
            assert example.reading in text and example.shown in text
        assert ("with the drivers grouped as lines that lowered profit. In two of three runs it "
                "still described the ingredients overspend as an offset, and the very first live "
                "run had made the same error.") in text
        assert f"In the sample, the three revenue lines sum to revenue of {top['revenue']}" in text

    def test_the_data_page_uses_the_engines_notes_and_limits(self):
        from src.pipeline import CATEGORIES, KPI_COLUMNS, PNL_COLUMNS, row_handling
        from streamlit_app.lib.inputs import MAX_MB, MAX_PNL_LINES
        text = _everything(_page(CONTENT[1]))
        for _, _, note in row_handling():
            assert html_escape(note) in text, note
        for column in PNL_COLUMNS + KPI_COLUMNS:
            assert f"<td>{column}</td>" in text
        assert "One of revenue, cogs or opex." in text and len(CATEGORIES) == 3
        assert f"Each file up to {MAX_MB} MB, and the P&L up to {MAX_PNL_LINES} lines." in text
        assert "python main.py --draft-only" in text

    def test_the_build_page_reads_its_figures_from_files_and_the_engine(self):
        from config import KPIS_PATH, PNL_PATH
        from src.pipeline import build_pack, model_prompt
        at = _page(CONTENT[2])
        text = _everything(at)
        counts = json.loads((ROOT / "generated" / "test_counts.json").read_text(encoding="utf-8"))
        assert f"{counts['total']:,} tests pin the behaviour" in text
        for area in counts["by_area"]:
            assert f"<td class=\"label\">{html_escape(area['area'])}</td>" in text
        audit = (ROOT / "generated" / "worked_example" / "audit.jsonl").read_text(encoding="utf-8")
        assert audit.strip() in [c.value.strip() for c in at.code]
        assert "They match." in text
        _, user = model_prompt(build_pack(PNL_PATH, KPIS_PATH))
        assert user in [c.value for c in at.code]
        assert "£3m raises no flag against a revenue budget of £2.59m" in text

    def test_the_pipeline_reads_on_a_phone(self):
        # The steps are a single column of blocks, and every table sits in a
        # wrapper that scrolls sideways, so nothing widens the page.
        from streamlit_app.lib.theme import inject_css
        css = inject_css()
        assert "ol.bp-flow li" in css and ".bp-table-wrap { overflow-x: auto;" in css
        for script in CONTENT:
            for value in [m.value for m in _page(script).markdown]:
                if "<table" in value:
                    assert value.startswith('<div class="bp-table-wrap">'), value[:60]


class TestWorkedExampleTab:
    def test_it_loads_without_building_anything(self, monkeypatch):
        import src.pipeline as pipeline
        from streamlit_app.lib import content, inputs

        def refuse(*args, **kwargs):
            raise AssertionError("the worked example tab must not build a pack")
        for module, name in ((pipeline, "run_pipeline"), (pipeline, "build_pack"),
                             (inputs, "run_pipeline"), (content, "build_pack")):
            monkeypatch.setattr(module, name, refuse)
        at = _app(BOARD).run()
        assert not at.exception, at.exception
        assert "bp_pack" not in at.session_state

    def test_the_walkthrough_and_the_signed_pages(self):
        at = _app(BOARD).run()
        tab = " ".join(m.value for m in at.tabs[0].markdown)
        assert "1. The template drafted the commentary for Harmwell Foods Ltd, June 2026" in tab
        assert "2. The reviewer, A. Controller, added a reason to the executive summary" in tab
        assert "3. Their figure, '£20k', matches no figure in the pack" in tab
        captions = " ".join(c.value for c in at.tabs[0].caption)
        assert ("They were drawn from the file whose SHA-256 its rendered audit line records, "
                "checked as this page loaded.") in captions
        manifest = json.loads((ROOT / "generated" / "worked_example" / "pages.json")
                              .read_text(encoding="utf-8"))
        images = at.tabs[0].get("image")
        n = len(manifest["pages"])
        assert len(images) == n >= 2
        shown = [img.proto.imgs[0].caption for img in images]
        assert shown == [f"Page {i} of {n}" for i in range(1, n + 1)]

    def test_the_downloads_are_the_committed_files(self):
        at = _app(BOARD).run()
        worked = ROOT / "generated" / "worked_example"
        labels = {d.proto.label for d in at.tabs[0].get("download_button")}
        assert labels == {"Download the FINAL PDF", "Download its audit lines (.jsonl)"}
        from streamlit_app.lib.content import worked_example
        example = worked_example()
        assert example["pdf"] == next(worked.glob("*.pdf")).read_bytes()
        assert example["audit_text"] == (worked / "audit.jsonl").read_text(encoding="utf-8")
