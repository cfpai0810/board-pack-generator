# =============================================================================
# notes.py: the one plain form of every note about the inputs and the run
# =============================================================================
"""
A note tells whoever prepared the files what the code did with them
that they might not expect: a row left out, a line kept under a
label, a comparison that cannot be made, a figure worth a second look.

Finance reasoning: these notes are read by whoever prepared the files and,
through the review notes, by the reviewer. They must say what happened in the reader's
terms (the file, the row, the line's name) and what the pack does about it,
never in the code's terms (column keys, exception text). So every note has
one form, built here from readable names:

    "<where>: <what happened>, so <what the pack does about it>."

<where> is "P&L row 13 (Rent)", "P&L", "KPI file row 4 (Headcount)", "KPI
file", "KPIs", "Cash" or "Commentary". Every note in the engine is built by
a function in this module, so the wording lives in one place: the data notes
panel, the CLI, the sign-off summary and the PDF's review notes all show
these sentences, and the page that explains the rules (row_handling) quotes
the same sentences the engine writes.

A Note is a str (its message), so it joins, prints and compares as text
wherever the data notes are read. It also carries structured fields
(kind, file, row, name), which the audit records beside the message.
"""

from __future__ import annotations

from typing import NamedTuple, Optional

PNL, KPI_FILE, CASH, COMMENTARY = "pnl", "kpis", "cash", "commentary"
MAX_NAME_LENGTH = 60
NAMED_ROWS = 3          # the excluded rows named in full; the rest are counted

_COLUMN_WORDS = {"actuals": "the actual", "actual": "the actual", "budget": "the budget",
                 "prior_year": "last year's figure", "target": "the target"}
_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
                 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


class Note(str):
    """A note's message, with the structured fields the audit keeps beside it."""

    def __new__(cls, message: str = "", *, kind: str = "", file: str = "",
                row: Optional[int] = None, name: str = ""):
        note = super().__new__(cls, message)
        note.kind, note.file, note.row, note.name = kind, file, row, name
        return note

    def record(self) -> dict:
        """The note for the audit: its fields and its message."""
        return {"kind": self.kind, "file": self.file, "row": self.row,
                "name": self.name, "message": str(self)}


class SkippedRow(NamedTuple):
    """A P&L row that carried data but could not be loaded: its CSV row number and name."""
    row: int
    name: str


# -- Small wording helpers ----------------------------------------------------

def count_words(n: int) -> str:
    """'one' to 'ten' in words, larger counts in figures."""
    return _NUMBER_WORDS.get(n, f"{n:,}")


def and_join(items: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def shortened(name: str) -> str:
    """A long name cut at a word near 40 characters, for a note to quote."""
    if len(name) <= 40:
        return name
    cut = name[:40]
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip(" ,;:") + "..."


def _value(raw: Optional[str]) -> str:
    raw = (raw or "").strip()
    return "is blank" if not raw else f"'{raw}' could not be read"


def _row(file: str, row: int, name: str = "") -> str:
    label = "P&L" if file == PNL else "KPI file"
    return f"{label} row {row} ({name})" if name else f"{label} row {row}"


# -- P&L file: rows that could not be loaded -------------------------------------

def blank_row(row: int) -> Note:
    return Note(f"P&L row {row}: the row is empty, so it was ignored.",
                kind="blank_row", file=PNL, row=row)


def unknown_category(row: int, name: str, category: str) -> Note:
    found = (f"the category '{category}' is not revenue, cogs or opex" if category
             else "the category is blank")
    return Note(f"{_row(PNL, row, name or 'no name')}: {found}, so the row was left out.",
                kind="unknown_category", file=PNL, row=row, name=name)


def unreadable_amount(row: int, name: str, column: str, raw: Optional[str]) -> Note:
    return Note(f"{_row(PNL, row, name)}: {_COLUMN_WORDS[column]} {_value(raw)}, "
                f"so the row was left out.",
                kind="unreadable_amount", file=PNL, row=row, name=name)


def excluded_rows(rows: list[SkippedRow], count: Optional[int] = None) -> Note:
    """
    The totals leave out rows that carried data, so they do not tie to the
    source file. The same sentence boxes the P&L in the PDF and closes the
    data notes. Up to three rows are named; the rest are counted.
    """
    n = len(rows) if count is None else count
    noun = "row" if n == 1 else "rows"
    text = f"These totals exclude {n} {noun} of the source file that could not be read"
    named = [f"{r.name} (row {r.row})" if r.name else f"row {r.row} (no name)"
             for r in rows[:NAMED_ROWS]]
    rest = n - len(named)
    if named and rest > 0:
        text += f": {', '.join(named)} and {rest} more"
    elif named:
        text += f": {and_join(named)}"
    return Note(text + ".", kind="excluded_rows", file=PNL)


# -- P&L file: lines kept, with a note ------------------------------------------

def unnamed_lines(category: str, labels: list[str]) -> Note:
    """One note per category for the lines loaded with no name, naming the labels they show under."""
    quoted = [f"'{label}'" for label in labels]
    if len(labels) == 1:
        text = f"P&L: one {category} line has no name; it is kept as {quoted[0]}."
    else:
        text = (f"P&L: {count_words(len(labels))} {category} lines have no name; "
                f"they are kept as {and_join(quoted)}.")
    return Note(text, kind="unnamed_line", file=PNL, name=category)


def shared_name(name: str, n: int) -> Note:
    return Note(f"P&L: {count_words(n)} lines are called '{name}'; they are kept as "
                f"separate lines.", kind="shared_name", file=PNL, name=name)


def subtotal_name(name: str, subtotal: str) -> Note:
    return Note(f"P&L: the line '{name}' has the same name as the {prose_name(subtotal)} subtotal; "
                f"it is kept as a separate line.", kind="subtotal_name", file=PNL, name=name)


def odd_category(name: str, category) -> Note:
    return Note(f"P&L: the line '{name or 'with no name'}' has the category '{category}', "
                f"which is not revenue, cogs or opex; it is kept but counts in no subtotal.",
                kind="odd_category", file=PNL, name=name)


def long_name(file: str, name: str) -> Note:
    if file == PNL:
        text = (f"P&L: the line name '{shortened(name)}' is longer than {MAX_NAME_LENGTH} "
                f"characters; it is kept and wraps in the tables.")
    else:
        text = (f"KPIs: the KPI name '{shortened(name)}' is longer than {MAX_NAME_LENGTH} "
                f"characters; it is kept and wraps in the table.")
    return Note(text, kind="long_name", file=file, name=name)


def no_revenue() -> Note:
    return Note("P&L: there is no revenue line, so revenue is nil and the gross margin "
                "cannot be computed.", kind="no_revenue", file=PNL)


def no_costs() -> Note:
    return Note("P&L: there is no cost line (COGS or opex), so gross profit and EBIT "
                "equal revenue.", kind="no_costs", file=PNL)


# -- P&L: comparisons that cannot be made ------------------------------------------

def line_subject(name: str) -> str:
    return f"the line '{name}'"


def prose_name(label: str) -> str:
    """A subtotal's table label as prose writes it: 'Gross profit' reads 'gross profit'; 'COGS' and 'EBIT' stay."""
    return label if label.isupper() else label.lower()


def subtotal_subject(name: str) -> str:
    return f"the {prose_name(name)} subtotal"


def zero_comparator(subject: str, against: str) -> Note:
    """subject from line_subject or subtotal_subject; against is 'budget' or 'last year'."""
    found = "has a zero budget" if against == "budget" else "was zero last year"
    return Note(f"P&L: {subject} {found}, so its % variance against {against} "
                f"is not meaningful (n/m).", kind="zero_comparator", file=PNL, name=subject)


_FOR = {"actual": "the month", "budget": "the budget", "last year": "last year"}


def zero_revenue(columns: list[str]) -> Note:
    """columns among 'actual', 'budget' and 'last year'."""
    them = "it" if len(columns) == 1 else "them"
    return Note(f"P&L: revenue is zero for {and_join([_FOR[c] for c in columns])}, so the "
                f"gross margin cannot be computed for {them}.", kind="zero_revenue", file=PNL)


# -- KPI file -----------------------------------------------------------------------

def no_kpi_file() -> Note:
    return Note("No KPI file was supplied, so the KPIs show only the gross margin from "
                "the P&L and there is no cash balance.", kind="no_kpi_file", file=KPI_FILE)


def kpi_no_name(row: int) -> Note:
    return Note(f"KPI file row {row}: the metric has no name, so the row was left out.",
                kind="kpi_no_name", file=KPI_FILE, row=row)


def kpi_unreadable(row: int, metric: str, column: str, raw: Optional[str]) -> Note:
    return Note(f"{_row(KPI_FILE, row, metric)}: {_COLUMN_WORDS[column]} {_value(raw)}, "
                f"so the KPI was left out.",
                kind="kpi_unreadable", file=KPI_FILE, row=row, name=metric)


def kpi_no_actual(metric: str) -> Note:
    return Note(f"KPIs: '{metric or 'unnamed metric'}' has no actual; it is kept, without "
                f"comparisons.", kind="kpi_no_actual", file=KPI_FILE, name=metric)


def margin_row_ignored(metric: str) -> Note:
    return Note(f"KPI file: the row '{metric}' was ignored; the gross margin shown is "
                f"computed from the P&L.", kind="margin_row_ignored", file=KPI_FILE, name=metric)


def margin_not_shown() -> Note:
    return Note("KPIs: the gross margin is not shown, because the actual or budget margin "
                "could not be computed.", kind="margin_not_shown", file=KPI_FILE)


def no_cash_kpi() -> Note:
    return Note("KPI file: there is no cash balance row, so the cash section shows no "
                "balance.", kind="no_cash_kpi", file=KPI_FILE)


# -- Cash: guards against the wrong unit (soft, never a block) ----------------------

def cash_unit_hint(metric: str, hinted: int, chosen: int, currency_name: str) -> Note:
    words = {1000: "thousands", 1: f"whole {currency_name}"}
    return Note(f"Cash: the KPI name '{metric}' suggests {words[hinted]}, but cash was "
                f"read as {words.get(chosen, f'{chosen:,} {currency_name} per unit')}. Check the "
                f"unit chosen for cash.", kind="cash_unit_hint", file=CASH, name=metric)


def cash_currency_hint(metric: str, named: str, chosen: str) -> Note:
    """named and chosen are currency names in prose: 'US dollars', 'euros'."""
    return Note(f"Cash: the KPI name '{metric}' suggests {named}, but the pack is in {chosen}. "
                f"Check the currency chosen for the run.", kind="cash_currency_hint",
                file=CASH, name=metric)


def cash_vs_revenue(cash_text: str, revenue_text: str) -> Note:
    return Note(f"Cash: the balance of {cash_text} is more than 100 times this month's "
                f"revenue of {revenue_text}. Check the unit chosen for cash.",
                kind="cash_vs_revenue", file=CASH)


# -- Commentary: the model path ------------------------------------------------------

def model_failed(error: str) -> Note:
    return Note(f"Commentary: the model call failed ({error}), so the template drafted "
                f"every section.", kind="model_failed", file=COMMENTARY)


def model_declined() -> Note:
    return Note("Commentary: the model declined the request, so the template drafted every "
                "section.", kind="model_declined", file=COMMENTARY)


def model_unreadable() -> Note:
    return Note("Commentary: the model's reply could not be read, so the template drafted "
                "every section.", kind="model_unreadable", file=COMMENTARY)


def model_missing(section_title: str) -> Note:
    return Note(f"Commentary: the model's reply had no {section_title} section, so the "
                f"template drafted it.", kind="model_missing", file=COMMENTARY,
                name=section_title)


# -- What happens to each kind of row, for the page that explains it ---------------

def row_handling() -> list[tuple[str, str, Note]]:
    """
    (what is in the file, what the pack does, the note as the engine writes
    it) for each kind of row a file may hold. Built from the functions
    above with example names, so the explanation cannot drift from the notes.
    """
    return [
        ("An empty row", "Ignored: it carries no money.", blank_row(7)),
        ("A line with no name", "Kept, under a label for its category.",
         unnamed_lines("COGS", ["Unnamed COGS line"])),
        ("An amount that cannot be read", "The row is left out and the totals say so.",
         unreadable_amount(13, "Rent", "actuals", "n/a")),
        ("A category other than revenue, cogs or opex",
         "The row is left out and the totals say so.",
         unknown_category(9, "Corporation tax", "tax")),
        ("Rows left out of the totals", "Named in a box above the P&L table.",
         excluded_rows([SkippedRow(13, "Rent")])),
        ("A name longer than 60 characters", "Kept; it wraps inside its column.",
         long_name(PNL, "Ingredients, packaging and inbound freight for the Leeds and York sites")),
        ("Two lines with the same name", "Kept as separate lines.", shared_name("Retail", 2)),
        ("A line named like a subtotal", "Kept as a separate line.",
         subtotal_name("Revenue", "Revenue")),
        ("A KPI value that cannot be read", "The KPI is left out.",
         kpi_unreadable(4, "Headcount", "target", "tbc")),
        ("A gross margin row in the KPI file", "Ignored: the margin comes from the P&L.",
         margin_row_ignored("Gross margin (%)")),
    ]
