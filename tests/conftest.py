"""Suite-wide guard: no test may open a network connection.

The model path is tested only with fake clients. If anything in the suite
tried to reach the network (a real SDK client, a stray request), the
connection attempt fails loudly instead of quietly calling an API.

The test counts: after a full, passing run of the whole suite, the number
of tests by area is written to generated/test_counts.json, which the "How
it's built" page reads. The page never types a count, and a partial run
(a -k filter, one file, a failure) writes nothing, so it never shows the
count of a subset.
"""

import json
import socket
from collections import Counter
from pathlib import Path

import pytest

COUNTS_FILE = Path(__file__).resolve().parent.parent / "generated" / "test_counts.json"
SUITE_FILES = {"test_pipeline.py", "test_web.py"}
SUITES = {"test_pipeline.py": "engine", "test_web.py": "web"}

# Each test class, by the area of the tool it pins, in the order the page lists them.
AREAS = {
    "Loading the files": ["TestLoad"],
    "Validation": ["TestValidate"],
    "Computation": ["TestCompute"],
    "Materiality and placement": ["TestAssemble", "TestItemKeys"],
    "Formatting and tables": ["TestFormatting", "TestTableFormatting", "TestSharedTables",
                              "TestBillions"],
    "Commentary and its checks": ["TestNarrateTemplate", "TestNumericCheck", "TestNarrateModel",
                                  "TestNarrativeSafeguards", "TestDirectionFlag",
                                  "TestNegativeCash", "TestModelFailures"],
    "Review, sign-off and audit": ["TestReview", "TestAuditAdditions", "TestCheckText",
                                   "TestGlyphsAndDraftRecord", "TestPipelineSurface"],
    "The PDF": ["TestRender", "TestPackLayout", "TestStory", "TestComputedText"],
    "Command line": ["TestMain", "TestCliOwnFiles", "TestPublishedCommands"],
    "Your own data and the notes": ["TestOwnData", "TestPlainNotes", "TestNamedExclusions",
                                    "TestCashUnitGuards"],
    "The worked example and the test counts": ["TestWorkedExample", "TestTestCounts"],
    "One language: the glossary": ["TestGlossary"],
    "Currency": ["TestCurrency", "TestFit"],
    "Web app: review stage": ["TestPagesLoad", "TestSampleRun", "TestReviewStage",
                              "TestWebLayerBoundary", "TestFreshModules",
                              "TestSignedPackAcrossAnUpdate"],
    "Web app: own files and the model": ["TestOwnFiles", "TestChangedInputs", "TestModelChoice",
                                         "TestUploadHandling", "TestCurrencyChoice",
                                         "TestKeyGate"],
    "Web app: content pages": ["TestContentPages", "TestWorkedExampleTab"],
}
AREA_OF = {cls: area for area, classes in AREAS.items() for cls in classes}

_deselected: list = []


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def pytest_deselected(items):
    _deselected.extend(items)


def _full_run(session, exitstatus) -> bool:
    option = session.config.option
    files = {Path(str(item.fspath)).name for item in session.items}
    return (exitstatus == 0 and not _deselected and not option.collectonly
            and not option.keyword and not option.markexpr and SUITE_FILES <= files
            and session.testscollected == len(session.items))


def pytest_sessionfinish(session, exitstatus):
    if not _full_run(session, exitstatus):
        return
    by_class = Counter(item.cls.__name__ if item.cls else "(no class)" for item in session.items)
    by_suite = Counter(SUITES[Path(str(item.fspath)).name] for item in session.items)
    by_area = Counter(AREA_OF.get(cls, cls) for cls in by_class.elements())
    order = list(AREAS) + sorted(set(by_area) - set(AREAS))
    counts = {
        "written_by": "tests/conftest.py, after a full passing run of the suite",
        "total": len(session.items),
        "by_suite": {suite: by_suite[suite] for suite in ("engine", "web")},
        "by_area": [{"area": area, "tests": by_area[area]} for area in order if by_area[area]],
        "by_class": dict(sorted(by_class.items())),
    }
    text = json.dumps(counts, indent=2) + "\n"
    if not COUNTS_FILE.is_file() or COUNTS_FILE.read_text(encoding="utf-8") != text:
        COUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        COUNTS_FILE.write_text(text, encoding="utf-8", newline="\n")
