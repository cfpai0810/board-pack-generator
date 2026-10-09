"""Tests for the Streamlit web layer (W1 skeleton).

The pages are run in process with Streamlit's AppTest: every page loads
without an exception, the sample run shows the figures the PDF shows and
offers a DRAFT PDF whose text matches the CLI's, and the web layer holds no
pipeline logic and hands no Decimal to a widget. No test opens a network
connection (conftest.py blocks sockets suite-wide).
"""

from __future__ import annotations

import ast
import io
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
PAGES = ["Home.py", "pages/1_How_the_pack_is_built.py", "pages/2_Board_pack.py",
         "pages/3_Your_own_data.py", "pages/4_How_its_built.py"]


def _app(script: str) -> AppTest:
    return AppTest.from_file(str(APP / script), default_timeout=120)


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(data)).pages]
    return " ".join(" ".join(pages).split())


def _without_run_details(text: str) -> str:
    """Drop what differs between two DRAFT runs of the same inputs: the time and the run id."""
    text = re.sub(r"Generated \d+ \w+ \d{4} at \d\d:\d\d UTC\.", "", text)
    return re.sub(r"Review run: [0-9a-f]{32}\.", "", text)


@pytest.fixture(scope="module")
def sample_run():
    at = _app("pages/2_Board_pack.py").run()
    at.button(key="run_sample").click().run()
    return at


class TestPagesLoad:
    @pytest.mark.parametrize("script", PAGES)
    def test_page_loads_without_error(self, script):
        at = _app(script).run()
        assert not at.exception, at.exception

    def test_home_states_the_governance_promise(self):
        at = _app("Home.py").run()
        text = " ".join(m.value for m in at.markdown)
        for promise in ("Python computes.", "A rule selects.", "The commentary narrates.",
                        "A person signs."):
            assert promise in text


class TestSampleRun:
    def test_runs_without_error(self, sample_run):
        assert not sample_run.exception, sample_run.exception

    def test_shows_the_figures_the_pdf_shows(self, sample_run):
        html = " ".join(m.value for m in sample_run.markdown)
        assert "(46,120)" in html and "35.0%" in html
        assert "Revenue was £2.48m, £112k (4.3%) below budget" in html
        assert "DRAFT" in html

    def test_the_drivers_table_has_six_rows(self, sample_run):
        view = sample_run.session_state["sample_draft"]
        assert [(r.subtotal, r.line, r.impact) for r in view["drivers"]] == [
            ("Gross profit", "Retail", "(56,180)"), ("", "Ingredients", "(37,310)"),
            ("", "Export", "(28,810)"), ("EBIT", "Retail", "(56,180)"),
            ("", "Marketing", "(37,640)"), ("", "Ingredients", "(37,310)")]

    def test_the_draft_pdf_matches_the_cli_draft(self, sample_run, tmp_path):
        import main as cli
        view = sample_run.session_state["sample_draft"]
        assert view["pdf_name"] == "harmwell_foods_2026_06_board_pack_DRAFT.pdf"
        assert cli.main(["--draft-only", "--output", str(tmp_path)],
                        stdin=io.StringIO(), stdout=io.StringIO()) == 0
        cli_pdf = (tmp_path / view["pdf_name"]).read_bytes()
        assert _without_run_details(_pdf_text(view["pdf"])) == \
            _without_run_details(_pdf_text(cli_pdf))

    def test_no_decimal_reaches_the_screen(self, sample_run):
        view = sample_run.session_state["sample_draft"]

        def values(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    yield from values(v)
            elif isinstance(obj, (list, tuple)):
                for v in obj:
                    yield from values(v)
            elif hasattr(obj, "__dataclass_fields__"):
                for name in obj.__dataclass_fields__:
                    yield from values(getattr(obj, name))
            else:
                yield obj

        found = list(values(view))
        assert found and not any(isinstance(v, Decimal) for v in found)
        assert all(isinstance(v, (str, bytes, bool)) for v in found)


class TestWebLayerBoundary:
    def _sources(self):
        return sorted(APP.rglob("*.py"))

    def test_no_pipeline_logic_in_the_web_layer(self):
        forbidden_modules = ("src.step1_load", "src.step2_validate", "src.step3_compute",
                             "src.step4_assemble", "src.step5_narrate")
        forbidden_calls = {"load", "validate", "compute", "assemble", "narrate",
                           "review", "record_draft", "render", "save_pack"}
        for path in self._sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            assert not any(m and m.startswith(forbidden_modules) for m in modules), path
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
