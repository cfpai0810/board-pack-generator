# =============================================================================
# live_smoke.py: one real model call on the sample pack (not part of pytest)
# =============================================================================
"""
The first real test of the step5 prompt. Builds the sample pack, calls
narrate() with a real Anthropic client, and prints the four sections, the
numeric and cause warnings, the model that answered and the token counts.

This makes one paid API call. It is never run by the test suite (pytest
only collects tests/, and the suite blocks the network).

The key comes from the environment: ANTHROPIC_API_KEY, or a .env file at
the project root (the portfolio convention), or a .env path given with
--env. The key is never printed.

    python scripts/live_smoke.py
    python scripts/live_smoke.py --env path/to/.env
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def build_sample_pack():
    from config import KPIS_PATH, PNL_PATH
    from src.step1_load import load
    from src.step2_validate import validate
    from src.step3_compute import compute
    from src.step4_assemble import assemble

    loaded = load(PNL_PATH, KPIS_PATH)
    problems = validate(loaded.pnl_lines, loaded.kpis, loaded.problems)
    c = compute(loaded.pnl_lines, loaded.kpis, problems)
    return assemble(c.pnl_lines, c.kpis, c.subtotals, c.problems,
                    loaded.excluded_pnl_rows, pnl_sha256=loaded.pnl_sha256,
                    kpis_sha256=loaded.kpis_sha256)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--env", type=Path, default=ROOT / ".env",
                        help="a .env file holding ANTHROPIC_API_KEY")
    args = parser.parse_args()

    try:
        import anthropic
    except ImportError:
        print("The anthropic package is not installed: pip install anthropic")
        return 1
    if args.env.exists():
        from dotenv import load_dotenv
        load_dotenv(args.env, override=False)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("No ANTHROPIC_API_KEY in the environment or the .env file.")
        return 1

    from config import NARRATIVE_MODEL
    from src.step5_narrate import narrate

    sys.stdout.reconfigure(encoding="utf-8")
    pack = narrate(build_sample_pack(), client=anthropic.Anthropic())

    print(f"Configured model: {NARRATIVE_MODEL}")
    print(f"Model that answered: {pack.narrative_model or '(none, template used)'}")
    print(f"Tokens: {pack.narrative_input_tokens} in, {pack.narrative_output_tokens} out")
    for section in pack.sections:
        print(f"\n== {section.title} [{section.drafted_by}] ==")
        print(section.narrative)
    print("\nnumeric_warnings:", [f.message for f in pack.numeric_warnings] or "none")
    print("cause_warnings:", [f.message for f in pack.cause_warnings] or "none")
    print("direction_warnings:", [f.message for f in pack.direction_warnings] or "none")
    print("warnings:", pack.warnings or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
