# =============================================================================
# lib/key_gate.py: the bring-your-own-key gate
# =============================================================================
# Renders the API key input in the sidebar, holds the key ONLY in this
# browser session's state, and builds a per-session client. The key is
# never written to disk, never logged, never stored server-side.
#
# The template is the default and needs no key: a key only makes the model
# available as an opt-in for drafting the commentary. Honest disclosure: the
# key is "used only for your session, never stored", not "never leaves your
# device", because it reaches this server to make the call. Anyone who wants
# their key to stay on their own machine is pointed to running it locally.
# =============================================================================

import streamlit as st

from streamlit_app.lib.claude_client import MODEL_ID, build_client, looks_like_anthropic_key
from streamlit_app.lib.errors import friendly_message


def render_key_gate():
    """
    The key input in the sidebar. Returns this session's client, or None
    when no valid key is present. Safe to call on every page.
    """
    st.sidebar.markdown("### Your API key (optional)")
    st.sidebar.caption(
        "The commentary is drafted by a template by default, which needs no key. "
        f"With your own Anthropic key, the model ({MODEL_ID}) can draft it instead, "
        "inside the same figures and checks.")

    key = st.sidebar.text_input(
        "Anthropic API key",
        type="password",
        placeholder="sk-ant-...",
        key="byo_api_key",
        help="Used only for this session. Never stored, never logged.",
    )
    st.sidebar.markdown(
        '<div class="bp-keynote">Your key is held only for this browser session to '
        'make the model call, then discarded. It is never stored or logged. Only the '
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
    st.sidebar.success("Key accepted for this session.")
    return client
