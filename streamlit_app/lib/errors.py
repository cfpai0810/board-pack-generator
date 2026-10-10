# =============================================================================
# lib/errors.py: friendly error handling for a finance reader
# =============================================================================
# A finance user must never see a Python traceback. Every failure becomes a
# plain sentence saying what went wrong and what to do. A PipelineError
# already speaks plainly (a missing file, a P&L with nothing loadable), so
# its own message is shown as it is.
# =============================================================================

import anthropic

from src.pipeline import PipelineError


def friendly_message(exc: BaseException) -> str:
    """A short plain-language message for an exception. Never a stack trace."""
    if isinstance(exc, PipelineError):
        return str(exc)

    if isinstance(exc, anthropic.AuthenticationError):
        return ("That API key was not accepted. Check you pasted the whole key "
                "(it starts with sk-ant-) and that it is active in your Anthropic "
                "console, then try again.")
    if isinstance(exc, anthropic.RateLimitError):
        return ("Your account hit a rate limit. Wait a moment and try again. If it "
                "keeps happening, check your usage limits in the Anthropic console.")
    if isinstance(exc, anthropic.APIStatusError):
        return ("The Anthropic API returned an error and could not complete the "
                "request. This is usually temporary; please try again shortly.")
    if isinstance(exc, anthropic.APIConnectionError):
        return "Could not reach the Anthropic API. Check your connection and try again."

    if exc.__class__.__name__ == "NoKeyError":
        return ("Paste your Anthropic API key in the sidebar to draft the commentary "
                "with the model, or leave it empty to use the template.")

    return "Something went wrong building the pack. Please try again."
