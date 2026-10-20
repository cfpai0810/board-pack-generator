# =============================================================================
# lib/key_gate.py: the bring-your-own-key gate
# =============================================================================
# Renders the API key input in the sidebar, holds the key ONLY in this
# session's state (the server's memory, for this session), and builds a
# client when one is needed. The key is never written to disk, never
# logged, and never kept beyond the session. It is kept under a non-widget
# key, so a key entered on one page stays in effect on every page.
#
# The template is the default and needs no key: a key only makes the model
# available as an opt-in for drafting the commentary. Honest disclosure: the
# key is "used only for your session, never stored", not "never leaves your
# device", because it reaches this server to make the call. Anyone who wants
# their key to stay on their own machine is pointed to running it locally.
# =============================================================================

import streamlit as st

from streamlit_app.lib.claude_client import MODEL_ID, build_client, looks_like_anthropic_key
from streamlit_app.lib.errors import KEY_LOOKS_COMPLETE, friendly_message

_KEPT = "anthropic_api_key"   # survives page changes; the widget's own state does not


def _keep_key():
    st.session_state[_KEPT] = st.session_state.get("byo_api_key", "")


def render_key_gate():
    """
    The key input in the sidebar. Returns this session's client, or None
    when no valid key is present. Safe to call on every page.
    """
    st.sidebar.markdown("### Your API key (optional)")
    st.sidebar.caption(
        "The commentary is drafted by a template by default, which needs no key. "
        f"With your own key, the model (Claude, via the Anthropic API) can draft it instead, as {MODEL_ID}, "
        "inside the same figures and checks.")

    if _KEPT in st.session_state:
        st.session_state["byo_api_key"] = st.session_state[_KEPT]
    key = st.sidebar.text_input(
        "Anthropic API key",
        type="password",
        placeholder="sk-ant-...",
        key="byo_api_key",
        on_change=_keep_key,
        help="Held in the server's memory for this session only. Never stored, never logged.",
    )
    st.sidebar.caption(
        "Drafting with the model uses your own Anthropic API key and bills your Anthropic "
        "account a small amount per run. The worked example needs no key.")
    st.sidebar.markdown(
        '<div class="bp-keynote">Your key is held in the server\'s memory for your '
        'session only, used to make the call, and never stored or logged. Only the '
        'formatted figures and names in the pack facts are sent to the model, never '
        'your files. To keep your key on your own machine, run the project locally.'
        '</div>',
        unsafe_allow_html=True,
    )

    if not key:
        return None
    if not looks_like_anthropic_key(key):
        st.sidebar.warning(
            "That does not look like a complete Anthropic key. It should start with "
            "sk-ant- and be the full string.")
        return None
    try:
        client = build_client(key)
    except Exception as exc:
        st.sidebar.error(friendly_message(exc))
        return None
    st.sidebar.success(KEY_LOOKS_COMPLETE)
    return client
