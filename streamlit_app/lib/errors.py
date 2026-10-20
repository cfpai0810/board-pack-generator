# =============================================================================
# lib/errors.py: friendly error handling for a finance reader
# =============================================================================
# A finance user must never see a Python traceback. Every failure becomes a
# plain sentence saying what went wrong and what to do. A PipelineError
# already speaks plainly (a missing file, a P&L with nothing loadable), so
# its own message is shown as it is. A failed model call is worded by the
# engine's one mapping (src/notes.py, through src.pipeline), so the screen,
# the PDF and the audit give the same message and the same short code.
# =============================================================================

from src.pipeline import PipelineError, failure_code, failure_message

KEY_LOOKS_COMPLETE = "Key looks complete. It is checked when you first run the model."


def model_failure_message(code: str) -> str:
    """The plain line for a failed model call, ending with its code."""
    return f"{failure_message(code)} Code: `{code}`"


def friendly_message(exc: BaseException) -> str:
    """A short plain-language message for an exception. Never a class name or a stack trace."""
    if isinstance(exc, PipelineError):
        return str(exc)

    code = failure_code(exc)
    if code:
        return model_failure_message(code)

    if exc.__class__.__name__ == "NoKeyError":
        return ("Paste your Anthropic API key in the sidebar to draft the commentary "
                "with the model, or leave it empty to use the template.")

    return "Something went wrong building the pack. Please try again."
