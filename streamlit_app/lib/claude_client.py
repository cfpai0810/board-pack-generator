# =============================================================================
# lib/claude_client.py: the client-provider seam
# =============================================================================
# The bring-your-own-key problem. The CLI builds its client from the
# environment at start-up. The web cannot: the user pastes a key after the
# app loads, and two users have two keys. So the client is built on demand,
# per session, never as a module global, and handed to run_pipeline as the
# injected client.
#
# The model id is P6's config (NARRATIVE_MODEL), never a value written here:
# the P5 cleanup point, so the web and the CLI always call the same model.
# =============================================================================

import anthropic

from config import NARRATIVE_MODEL

MODEL_ID = NARRATIVE_MODEL


class NoKeyError(RuntimeError):
    """A model run was asked for with no key available."""


def build_client(api_key: str) -> anthropic.Anthropic:
    """Build an Anthropic client from a pasted key. Does not store the key."""
    if not api_key or not api_key.strip():
        raise NoKeyError("No API key provided.")
    return anthropic.Anthropic(api_key=api_key.strip())


def looks_like_anthropic_key(api_key: str) -> bool:
    """
    A cheap check for obvious paste mistakes before any call. Not
    validation: only a real request proves a key works.
    """
    if not api_key:
        return False
    k = api_key.strip()
    return k.startswith("sk-ant-") and len(k) > 20
