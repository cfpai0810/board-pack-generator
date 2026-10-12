# =============================================================================
# lib/fresh.py: a release pulled into the running app takes effect at once
# =============================================================================
# Streamlit Community Cloud pulls a new commit into the running Python
# process, and Streamlit reloads changed files only under streamlit_app/.
# config.py and src/ would stay as the old release, and a page importing
# anything new would fail with an ImportError until someone rebooted the
# app (v1.2.0 did: "from config import CURRENCY").
#
# Home.py calls drop_stale_modules first on every run, before it imports
# anything of the project's own. If the project's files on disk are newer
# than the modules in memory, every project module is dropped from
# sys.modules and Streamlit's caches are cleared (the cached sample pack was
# built by the old classes), so this run imports the release on disk. A
# reboot is no longer needed; it remains the fallback.
#
# This module imports nothing of the project's, so it is never stale itself.
# =============================================================================

import re
import sys
from pathlib import Path
from typing import Callable, MutableMapping, Optional

LOADED_STAMP = "_bp_files_stamp"     # set on the config module: the newest file when loaded
_VERSION = re.compile(r'^VERSION = "([^"]+)"', re.MULTILINE)


def _project_files(root: Path) -> list[Path]:
    """The files Streamlit does not reload: config.py and src/."""
    return [p for p in [root / "config.py", *sorted((root / "src").glob("*.py"))] if p.is_file()]


def files_stamp(root: Path) -> int:
    """The modification time of the newest of those files, in nanoseconds."""
    return max(p.stat().st_mtime_ns for p in _project_files(root))


def _ours(module, root: Path) -> bool:
    """A module loaded from config.py, src/ or streamlit_app/ (not a page script or a package elsewhere)."""
    path = getattr(module, "__file__", None)
    if not path:
        return False
    path = Path(path).resolve()
    return path == (root / "config.py").resolve() or any(
        path.is_relative_to((root / folder).resolve()) for folder in ("src", "streamlit_app"))


def drop_stale_modules(root: Path, modules: Optional[MutableMapping] = None,
                       clear_caches: Optional[Callable[[], None]] = None) -> list[str]:
    """
    Drop the project's modules when they are older than its files; return their
    names (none when nothing was stale). Stale means config was loaded before
    the newest file under config.py and src/ was written, or, for a module
    loaded before this check existed, that config's VERSION in memory is not
    the VERSION on disk.
    """
    modules = sys.modules if modules is None else modules
    config = modules.get("config")
    if config is None:
        return []                                   # nothing loaded yet: this run reads the disk
    stamp = files_stamp(root)
    loaded = getattr(config, LOADED_STAMP, None)
    if loaded is None:
        on_disk = _VERSION.search((root / "config.py").read_text(encoding="utf-8"))
        if on_disk and on_disk.group(1) == getattr(config, "VERSION", None):
            setattr(config, LOADED_STAMP, stamp)    # current, first seen by this check
            return []
    elif loaded >= stamp:
        return []
    names = [name for name, module in list(modules.items())
             if name != "__main__" and _ours(module, root)]
    for name in names:
        del modules[name]
    if clear_caches is not None:
        clear_caches()
    return names


def mark_loaded(root: Path, modules: Optional[MutableMapping] = None) -> None:
    """Record on config when the project's files were loaded, for the next run's check."""
    config = (sys.modules if modules is None else modules).get("config")
    if config is not None and getattr(config, LOADED_STAMP, None) is None:
        setattr(config, LOADED_STAMP, files_stamp(root))
