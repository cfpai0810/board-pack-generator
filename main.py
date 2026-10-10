# =============================================================================
# main.py: the CLI: one board pack from two CSV files, reviewed at the terminal
# =============================================================================
"""
Run the board pack generator end to end.

    python main.py                         review at the terminal, sign with SIGN
    python main.py --draft-only            no prompts: a DRAFT pack and its review notes
    python main.py --use-model             have the model (Claude, via the Anthropic API) draft the commentary
    python main.py --pnl my_pnl.csv --kpis my_kpis.csv --output out/

main() only parses the arguments, builds the terminal ask and confirm (and
the model client when --use-model is given and a key is available), calls
src.pipeline.run_pipeline, and reports the outcome. All pipeline logic lives
in run_pipeline, which the web layer will call with its own ask and confirm.

The API key is never an argument. With --use-model it is read from
ANTHROPIC_API_KEY in the environment or a local .env file; without a key
the template drafts the commentary and the run says so.

Signing needs a person: the reviewer reads each section (Enter accepts, "e"
replaces the text), sees the outstanding flags, and types the word SIGN.
Anything else leaves the pack a DRAFT. There is no option that signs
without the prompts.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional, TextIO

from config import KPIS_PATH, NARRATIVE_MODEL, OUTPUT_DIR, PNL_PATH, ROOT
from src.pipeline import (
    CASH_UNITS, SIGN_WORD, PipelineError, PipelineResult, is_sign_word, run_pipeline,
)
from src.state import PackStatus

ENV_FILE = ROOT / ".env"
WIDTH = 88


# -- Terminal review: the injected ask and confirm -----------------------------

class TerminalReviewer:
    """
    ask and confirm for a person at a terminal. Reads lines from stdin and
    writes to stdout, so a test (or a transcript) can drive it. End of input
    accepts a section unchanged and never signs.
    """

    def __init__(self, stdin: TextIO, stdout: TextIO):
        self.stdin, self.stdout = stdin, stdout
        self.name = ""

    def _say(self, text: str = "") -> None:
        self.stdout.write(text + "\n")
        self.stdout.flush()

    def _read(self, prompt: str) -> Optional[str]:
        self.stdout.write(prompt)
        self.stdout.flush()
        line = self.stdin.readline()
        return None if line == "" else line.rstrip("\r\n")

    def ask_name(self) -> str:
        self.name = (self._read("Reviewer name: ") or "").strip()
        if not self.name:
            self._say("No name given: the pack can be reviewed but not signed.")
        return self.name

    def ask(self, title: str, text: str, warnings: list[str]) -> str:
        self._say()
        self._say(f"=== {title} ===")
        if warnings:
            self._say("Flags:")
            for i, warning in enumerate(warnings, start=1):
                self._say(textwrap.fill(f"{i}. {warning}", WIDTH, subsequent_indent="   "))
        else:
            self._say("Flags: none")
        self._say("Draft:")
        for paragraph in text.split("\n"):
            self._say(textwrap.fill(paragraph, WIDTH))
        while True:
            answer = self._read("Press Enter to accept, or type e to edit: ")
            if answer is None or answer.strip() == "":
                return text
            if answer.strip().lower() == "e":
                return self._replacement(text)
            self._say("Please press Enter to accept, or type e to edit.")

    def _replacement(self, text: str) -> str:
        self._say("Type the replacement text. End with a line containing only a full stop.")
        lines: list[str] = []
        while True:
            line = self._read("> ")
            if line is None or line.strip() == ".":
                break
            lines.append(line)
        replacement = "\n".join(lines).strip()
        if not replacement:
            self._say("Nothing typed: the draft is kept.")
            return text
        return replacement

    def confirm(self, summary: list[str]) -> bool:
        self._say()
        self._say("=== Sign-off ===")
        if summary:
            self._say("Outstanding before you sign:")
            for i, item in enumerate(summary, start=1):
                self._say(textwrap.fill(f"{i}. {item}", WIDTH, subsequent_indent="   "))
        else:
            self._say("Nothing is outstanding.")
        answer = self._read(
            f"Type {SIGN_WORD} to sign off this pack as {self.name}, or press Enter to "
            f"leave it as a DRAFT: ")
        return is_sign_word(answer)          # the one SIGN rule, shared with the web


# -- The model client, only when asked for ------------------------------------------

def build_client(use_model: bool):
    """
    (client or None, a sentence saying which path drafts the commentary).
    The SDK is imported only here, and only when --use-model was given and
    a key is available.
    """
    if not use_model:
        return None, ("Commentary: the template. Add --use-model to have the model (Claude, via the Anthropic API) "
                      f"draft it, as {NARRATIVE_MODEL}.")
    if ENV_FILE.is_file():
        try:
            from dotenv import load_dotenv
            load_dotenv(ENV_FILE, override=False)
        except ImportError:
            pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None, ("Commentary: the template. --use-model was given, but no "
                      "ANTHROPIC_API_KEY was found in the environment or .env.")
    try:
        import anthropic
    except ImportError:
        return None, ("Commentary: the template. --use-model was given, but the "
                      "anthropic package is not installed (pip install -r requirements.txt).")
    return anthropic.Anthropic(), (f"Commentary: the model (Claude, via the Anthropic API), as {NARRATIVE_MODEL}, with "
                                   f"the template as fallback.")


# -- Arguments ------------------------------------------------------------------

def _amount(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}")
    if value < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return value


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Build a monthly board pack from a P&L file and a KPI file.")
    parser.add_argument("--pnl", type=Path, default=PNL_PATH, help="P&L CSV (default: the sample)")
    parser.add_argument("--kpis", type=Path, default=KPIS_PATH, help="KPI CSV (default: the sample)")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR,
                        help="folder for the PDF and the audit log (default: output/)")
    parser.add_argument("--materiality-abs", type=_amount, default=None, metavar="POUNDS",
                        help="absolute materiality threshold (default: config)")
    parser.add_argument("--materiality-pct", type=_amount, default=None, metavar="PERCENT",
                        help="percentage materiality threshold (default: config)")
    parser.add_argument("--entity", default=None,
                        help="the entity the pack is for (required with your own --pnl)")
    parser.add_argument("--period", default=None,
                        help="the period, such as 'September 2026' (required with your own --pnl)")
    parser.add_argument("--cash-unit", choices=sorted(CASH_UNITS), default=None,
                        help="the unit the KPI file states cash in (default: thousands)")
    parser.add_argument("--use-model", action="store_true",
                        help="have the model (Claude, via the Anthropic API) draft the commentary; reads ANTHROPIC_API_KEY "
                             "from the environment or .env, never from an argument")
    parser.add_argument("--draft-only", action="store_true",
                        help="no review prompts: write a DRAFT pack with its review notes")
    return parser.parse_args(argv)


# -- The run ------------------------------------------------------------------

def _report(result: PipelineResult, say) -> None:
    pack = result.pack
    if pack.status is PackStatus.FINAL:
        say(f"Status: FINAL, signed off by {pack.sign_off_by} at {pack.sign_off_at}")
    else:
        say("Status: DRAFT (not signed off)")
    say(f"PDF: {result.pdf_path}")
    say(f"Audit: {result.audit_path}")
    if result.data_notes:
        say("Data notes:")
        for i, note in enumerate(result.data_notes, start=1):
            say(textwrap.fill(f"{i}. {note}", WIDTH, subsequent_indent="   "))
    else:
        say("Data notes: none")
    kinds = (("numeric", pack.numeric_warnings), ("cause", pack.cause_warnings),
             ("direction", pack.direction_warnings), ("glyph", pack.glyph_warnings))
    counts = ", ".join(f"{name} {sum(not f.resolved for f in flags)}" for name, flags in kinds)
    note = " (acknowledged at sign-off)" if pack.status is PackStatus.FINAL else ""
    say(f"Outstanding flags: {counts}{note}")


def main(argv: Optional[list[str]] = None, *, stdin: Optional[TextIO] = None,
         stdout: Optional[TextIO] = None) -> int:
    """Parse, build the seams, run. 0 for a FINAL or DRAFT pack; 2 for a problem with the inputs."""
    args = parse_args(argv)
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    reviewer = TerminalReviewer(stdin, stdout)
    say = reviewer._say

    own_file = Path(args.pnl).is_file() and Path(args.pnl).resolve() != PNL_PATH.resolve()
    if own_file and not (args.entity and args.period):
        say("Stopped: with your own P&L file, give --entity and --period, so the pack is "
            "not headed with the sample's name.")
        return 2

    client, path_note = build_client(args.use_model)
    say(path_note)
    name = "" if args.draft_only else reviewer.ask_name()

    try:
        result = run_pipeline(
            args.pnl, args.kpis, args.output,
            ask=None if args.draft_only else reviewer.ask,
            confirm=None if args.draft_only else reviewer.confirm,
            reviewer=name, client=client,
            materiality_abs=args.materiality_abs, materiality_pct=args.materiality_pct,
            entity=args.entity, period=args.period,
            cash_scale=None if args.cash_unit is None else CASH_UNITS[args.cash_unit],
            draft_only=args.draft_only,
        )
    except PipelineError as e:
        say(f"Stopped: {e}")
        return 2
    except KeyboardInterrupt:
        say("")
        say("Stopped. Nothing was signed.")
        return 130

    say("")
    _report(result, say)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
