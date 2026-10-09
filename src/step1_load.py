# =============================================================================
# step1_load.py: Layer 2: CSV to typed records, amount coercion to Decimal
# =============================================================================
"""
Load pnl.csv and kpis.csv into PnlLine and Kpi records.

Every amount crosses the Decimal boundary here via _parse_amount, never
via Decimal(float). A row that cannot be read (unparseable amount, unknown
category, blank required field) is reported as a problem and skipped, never
silently dropped or treated as zero. This is the same report-and-skip
discipline P5 used for its reconciliation inputs.

One exception: a P&L row with a blank line_item but a recognised category
and readable amounts is LOADED, not skipped. Its money belongs in the
subtotals, and a pack whose totals do not tie to its own source file is
worse than one with an unnamed line. The loader labels it (for example
"Unnamed COGS line"), sets line_item_blank, and adds no note; step2 warns.

Single-period contract: one month per file, no period column.
"""

from __future__ import annotations

import csv
import hashlib
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NamedTuple

from src.state import Category, Kpi, PnlLine


# -- Amount parsing -----------------------------------------------------------

_CURRENCY_RE = re.compile(r"[£$\u20ac\u00a5]")
_THOUSANDS_RE = re.compile(r",(?=\d{3})")


def _parse_amount(raw: str | None) -> Decimal:
    """
    Coerce a raw string to an exact Decimal.

    Handles: thousands separators, currency symbols, accounting parentheses
    (1,234.56), and trailing minus (1,234.56-). Raises ValueError on
    anything it cannot parse, so the caller records a problem. None (a cell
    missing from a short CSV row) is treated as blank.
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("blank amount")

    s = _CURRENCY_RE.sub("", s)
    s = s.replace(" ", "")

    negate = False
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
        negate = True
    elif s.endswith("-"):
        s = s[:-1]
        negate = True

    s = _THOUSANDS_RE.sub("", s)

    try:
        value = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"cannot parse amount: {raw!r}")

    return -value if negate else value


# -- Load results -------------------------------------------------------------

class LoadResult(NamedTuple):
    pnl_lines: list[PnlLine]
    kpis: list[Kpi]
    problems: list[str]
    excluded_pnl_rows: int
    pnl_sha256: str
    kpis_sha256: str


# -- P&L loader ---------------------------------------------------------------

_CATEGORY_LOOKUP = {c.value: c for c in Category}
_AMOUNT_COLUMNS = ("actuals", "budget", "prior_year")


def load_pnl(path: Path) -> tuple[list[PnlLine], list[str], int]:
    """
    Load pnl.csv into PnlLine records.

    Returns (lines, problems, excluded_pnl_rows). A row with an unrecognised
    category is rejected with a note. A row with an unparseable amount is
    reported and skipped. A row with a blank line_item is loaded under its
    category's unnamed label (see the module docstring). A wholly blank row
    carries no money and is noted and skipped.

    excluded_pnl_rows counts the rows that carried data but could not be
    loaded, so the totals no longer tie to the source file. Wholly blank
    rows are not counted. Phase 7 reads this count, never the notes.
    """
    lines: list[PnlLine] = []
    problems: list[str] = []
    excluded = 0

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            if not any(v.strip() for v in row.values() if isinstance(v, str)):
                problems.append(f"pnl row {i}: blank row, skipped")
                continue

            line_item = (row.get("line_item") or "").strip()

            raw_cat = (row.get("category") or "").strip().lower()
            cat = _CATEGORY_LOOKUP.get(raw_cat)
            if cat is None:
                named = repr(line_item) if line_item else "an unnamed line"
                problems.append(
                    f"pnl row {i}: unrecognised category {raw_cat!r} "
                    f"for {named}, skipped"
                )
                excluded += 1
                continue

            line_item_blank = not line_item
            if line_item_blank:
                line_item = cat.unnamed_label

            amounts: dict[str, Decimal] = {}
            for column in _AMOUNT_COLUMNS:
                try:
                    amounts[column] = _parse_amount(row.get(column))
                except ValueError as e:
                    problems.append(
                        f"pnl row {i} ({line_item}): {column} {e}, skipped"
                    )
                    break
            if len(amounts) < len(_AMOUNT_COLUMNS):
                excluded += 1
                continue

            lines.append(PnlLine(
                line_item=line_item,
                category=cat,
                line_item_blank=line_item_blank,
                **amounts,
            ))

    _number_unnamed(lines)
    return lines, problems, excluded


def _number_unnamed(lines: list[PnlLine]) -> None:
    """
    When a category has more than one nameless line, number the labels
    ("Unnamed COGS line 1", "Unnamed COGS line 2") so the table never shows
    two identical labels. A single nameless line keeps the plain label.
    """
    for category in Category:
        unnamed = [l for l in lines if l.line_item_blank and l.category is category]
        if len(unnamed) > 1:
            for n, line in enumerate(unnamed, start=1):
                line.line_item = f"{category.unnamed_label} {n}"


# -- KPI loader ---------------------------------------------------------------

def load_kpis(path: Path) -> tuple[list[Kpi], list[str]]:
    """
    Load kpis.csv into Kpi records.

    Returns (kpis, problems). A row with a blank metric or unparseable
    actual is reported and skipped. prior_year is optional.
    """
    kpis: list[Kpi] = []
    problems: list[str] = []

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            metric = (row.get("metric") or "").strip()
            if not metric:
                problems.append(f"kpi row {i}: blank metric, skipped")
                continue

            try:
                actual = _parse_amount(row.get("actual", ""))
            except ValueError as e:
                problems.append(f"kpi row {i} ({metric}): actual {e}, skipped")
                continue

            try:
                target = _parse_amount(row.get("target", ""))
            except ValueError as e:
                problems.append(f"kpi row {i} ({metric}): target {e}, skipped")
                continue

            raw_py = (row.get("prior_year") or "").strip()
            prior_year = None
            if raw_py:
                try:
                    prior_year = _parse_amount(raw_py)
                except ValueError as e:
                    problems.append(
                        f"kpi row {i} ({metric}): prior_year {e}, skipped"
                    )
                    continue

            kpis.append(Kpi(
                metric=metric,
                actual=actual,
                target=target,
                prior_year=prior_year,
            ))

    return kpis, problems


# -- Combined loader ----------------------------------------------------------

def load(pnl_path: Path, kpis_path: Path) -> LoadResult:
    """
    Load both CSV files and return the records, the problems, the count of
    excluded P&L rows, and the SHA-256 of each file's raw bytes. The hashes
    let the audit show exactly which files produced a pack.
    """
    pnl_lines, pnl_problems, excluded_pnl_rows = load_pnl(pnl_path)
    kpis, kpi_problems = load_kpis(kpis_path)
    return LoadResult(
        pnl_lines, kpis, pnl_problems + kpi_problems, excluded_pnl_rows,
        file_sha256(pnl_path), file_sha256(kpis_path),
    )


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's raw bytes, as hex."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
