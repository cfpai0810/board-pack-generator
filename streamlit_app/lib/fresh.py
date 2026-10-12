# =============================================================================
# lib/fresh.py: a release pulled into the running app takes effect at once
# =============================================================================
# Streamlit Community Cloud pulls a new commit into the running Python
# process, and Streamlit reloads changed files only under streamlit_app/.
# config.py and src/ would stay as the old release, and a page importing
# anything new would fail with an ImportError until someone rebooted the
# app (v1.2.0 did: "from config import CURRENCY").
#
# Home.py runs every page inside held(). When the project's files on disk
# are newer than the modules in memory, the first run to notice purges them:
# once per change, under a lock, after the runs already under way have
# finished, and with the new engine imported before any other run goes on.
# So no page view ever meets a half-loaded module or a mix of two releases.
# Each purge raises the release generation; a session built under an earlier
# one is reset on its next run (reset_stale_session): the engine objects in
# its state were built by the old classes (a signed pack's status no longer
# equals the new PackStatus.FINAL), so they are discarded, and the
# reviewer's edits are kept as plain strings.
#
# This module imports nothing of the project's and is never purged itself.
# What must outlive a purge (the lock, the generation, the loaded files'
# stamp) is kept on the sys module, which outlives every reload.
# =============================================================================

import importlib
import re
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, MutableMapping, Optional

UPDATED_NOTICE = "The app was updated. Please build the draft again; your edits have been kept."
SESSION_RELEASE = "fresh_release"             # the generation a session's state was built under
LOADED_STAMP = "_bp_files_stamp"              # set on config by the check before this one
PURGE_WAIT_SECONDS = 30                       # how long a purge waits for runs under way
ENGINE = ("config", "src.pipeline")           # imported again inside the purge, whole
_PROJECT = ("config", "src", "streamlit_app")
_VERSION = re.compile(r'^VERSION = "([^"]+)"', re.MULTILINE)


class Release:
    """The loaded release, shared by every session's thread in this process."""

    def __init__(self) -> None:
        self.lock = threading.Condition(threading.RLock())
        self.readers = 0          # runs holding the release now
        self.purging = False
        self.generation = 0       # raised by each purge
        self.stamp: Optional[int] = None    # the newest project file when the modules were loaded


def process_release() -> Release:
    """The process's one Release, kept on sys so it outlives any module reload."""
    return sys.__dict__.setdefault("_board_pack_release", Release())


# -- What is stale --------------------------------------------------------------------

def _project_files(root: Path) -> list[Path]:
    """The files Streamlit does not reload: config.py and src/."""
    return [p for p in [root / "config.py", *sorted((root / "src").glob("*.py"))] if p.is_file()]


def files_stamp(root: Path) -> int:
    """The modification time of the newest of those files, in nanoseconds."""
    return max(p.stat().st_mtime_ns for p in _project_files(root))


def _ours(module, root: Path) -> bool:
    """A module loaded from config.py, src/ or streamlit_app/, other than this one."""
    path = getattr(module, "__file__", None)
    if not path or getattr(module, "__name__", None) == __name__:
        return False
    path = Path(path).resolve()
    return path == (root / "config.py").resolve() or any(
        path.is_relative_to((root / folder).resolve()) for folder in ("src", "streamlit_app"))


def is_stale(root: Path, modules: MutableMapping, release: Release) -> bool:
    """
    True when the project's modules in memory are older than its files: the
    VERSION on disk is not config's VERSION in memory (a release always sets
    it), or a file is newer than the stamp recorded when the modules were
    loaded (config's own stamp, for modules loaded before this check existed).
    Either test alone could miss an update: a hotfix may keep the VERSION, and
    a deploy that copies files with their old times keeps the stamp.
    """
    config = modules.get("config")
    if config is None:
        return False                                  # nothing loaded yet: this run reads the disk
    on_disk = _VERSION.search((root / "config.py").read_text(encoding="utf-8"))
    if on_disk and on_disk.group(1) != getattr(config, "VERSION", None):
        return True
    loaded = release.stamp if release.stamp is not None else getattr(config, LOADED_STAMP, None)
    return loaded is not None and loaded < files_stamp(root)


def _purge(root: Path, modules: MutableMapping, clear_caches, engine) -> list[str]:
    names = [name for name, module in list(modules.items())
             if name != "__main__" and _ours(module, root)]
    for name in names:
        del modules[name]
    if clear_caches is not None:
        clear_caches()
    for name in engine:                               # whole, before any other run goes on
        importlib.import_module(name)
    return names


# -- One run, holding the release ------------------------------------------------------

@contextmanager
def held(root: Path, *, clear_caches: Optional[Callable[[], None]] = None,
         modules: Optional[MutableMapping] = None, release: Optional[Release] = None,
         engine=ENGINE, wait_seconds: int = PURGE_WAIT_SECONDS) -> Iterator[int]:
    """
    Hold the loaded release for one run and yield its generation. A run that
    arrives during a purge waits for it. The first run to find the modules
    stale purges them, once per change: it waits (up to wait_seconds) for the
    runs already under way to finish, drops the project's modules, clears the
    caches, imports the engine again whole, and raises the generation.
    """
    modules = sys.modules if modules is None else modules
    release = process_release() if release is None else release
    with release.lock:
        while release.purging:
            release.lock.wait()
        if is_stale(root, modules, release):
            release.purging = True
            try:
                deadline = time.monotonic() + wait_seconds
                while release.readers and time.monotonic() < deadline:
                    release.lock.wait(deadline - time.monotonic())
                _purge(root, modules, clear_caches, engine)
                release.stamp = files_stamp(root)
                release.generation += 1
            finally:
                release.purging = False
                release.lock.notify_all()
        release.readers += 1
        generation = release.generation
    try:
        yield generation
    finally:
        with release.lock:
            release.readers -= 1
            if release.stamp is None and "config" in modules:
                release.stamp = files_stamp(root)     # a fresh process: the release now loaded
            release.lock.notify_all()


# -- A session built under an earlier release ------------------------------------------

def _engine_object(value) -> bool:
    """A value built by the project's classes, or a container holding one."""
    if isinstance(value, dict):
        return any(_engine_object(v) for v in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_engine_object(v) for v in value)
    module = type(value).__module__ or ""
    return module in _PROJECT or module.startswith(tuple(f"{p}." for p in _PROJECT))


def _drafts(pack) -> dict[str, str]:
    """Each section's first draft, by section key, read from a pack of any release."""
    return {str(s.section_type.value): str(getattr(s, "draft", ""))
            for s in getattr(pack, "sections", None) or []}


def reset_stale_session(state: MutableMapping, generation: int, *, pack_key: str,
                        edits_prefix: str, kept_key: str) -> bool:
    """
    Reset a session whose state was built under an earlier release: discard
    every engine object (a pack, the inputs it was built from, its notes), and
    keep the reviewer's edits as plain strings under kept_key, by section, for
    the next build: the text in an edit box, or for a pack with no boxes on
    screen (a signed one) its sections' text, wherever it differs from the
    first draft. Plain values stay: a signed pack's PDF and its audit, on disk,
    remain downloadable. True when the session was reset, so the page shows
    UPDATED_NOTICE once.
    """
    seen = state.get(SESSION_RELEASE)
    state[SESSION_RELEASE] = generation
    if seen == generation:
        return False                                  # already current
    if seen is None and not (generation and any(_engine_object(v) for v in state.values())):
        return False                                  # a new session: nothing built yet
    # Otherwise built under an earlier release, or before this check existed
    # (no generation recorded, yet holding engine objects after a purge)
    pack = state.get(pack_key)
    drafts = _drafts(pack)
    kept = dict(state.get(kept_key) or {})
    for s in getattr(pack, "sections", None) or []:
        key, text = str(s.section_type.value), getattr(s, "narrative", "")
        if isinstance(text, str) and text != drafts.get(key):
            kept[key] = str(text)
    for key in list(state.keys()):
        value = state[key]
        if str(key).startswith(edits_prefix) and isinstance(value, str):
            section = str(key)[len(edits_prefix):]
            if value != drafts.get(section):
                kept[section] = str(value)            # unsaved typing beats the pack's text
            del state[key]
        elif _engine_object(value):
            del state[key]
    if kept:
        state[kept_key] = kept
    return True
