"""Shared plumbing for the export layer: honest failures and native library discovery.

Two small concerns live here so that every exporter agrees on them.

**Honest failures.** PNG and PDF rendering depend on optional packages that in turn
depend on system libraries. When they are missing we raise :class:`ExportUnavailable`
with the exact command that fixes it, rather than silently producing a degraded or
fake artifact. The registry in ``exports/__init__`` surfaces the same message as
``unavailable_reason`` so the UI never offers a button that cannot work.

**Native library discovery.** ``cairosvg`` and ``weasyprint`` load libcairo/pango
through ``ctypes.util.find_library``, which on macOS does not look in Homebrew's
prefix. ``find_library`` reads ``DYLD_FALLBACK_LIBRARY_PATH`` from ``os.environ`` at
call time (the search is pure Python), so setting it before the first import is enough
— no relaunch, no wrapper script, no change to the user's shell.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Homebrew's two prefixes (Apple silicon, Intel) plus MacPorts. Only directories that
# actually exist are added, so this is a no-op on a machine that does not need it.
_MACOS_LIBRARY_DIRS = ("/opt/homebrew/lib", "/usr/local/lib", "/opt/local/lib")

_native_path_prepared = False


class ExportUnavailable(RuntimeError):
    """Raised when a format cannot be produced in this installation.

    ``reason`` is written for a person reading it in a UI toast: it says what is
    missing and what to type to fix it.
    """

    def __init__(self, reason: str, *, format_id: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.format_id = format_id


def ensure_native_library_path() -> None:
    """Make Homebrew/MacPorts shared libraries visible to ``ctypes.util.find_library``."""
    global _native_path_prepared
    if _native_path_prepared or not sys.platform.startswith("darwin"):
        _native_path_prepared = True
        return
    existing = [p for p in os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "").split(":") if p]
    for candidate in _MACOS_LIBRARY_DIRS:
        if candidate not in existing and Path(candidate).is_dir():
            existing.append(candidate)
    if existing:
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(existing)
    _native_path_prepared = True


def probe_cairosvg() -> str:
    """Return "" if PNG export will work, otherwise the reason it will not."""
    ensure_native_library_path()
    try:
        import cairosvg  # noqa: F401
    except ImportError:
        return (
            "PNG export needs cairosvg installed: "
            "pip install 'api-galaxy-api[png]' (or pip install cairosvg)"
        )
    except OSError as exc:  # cairocffi raises OSError when libcairo is not on the system
        return f"PNG export needs the cairo system library: brew install cairo ({exc})".split(
            "\n"
        )[0]
    return ""


def probe_weasyprint() -> str:
    """Return "" if PDF export will work, otherwise the reason it will not."""
    ensure_native_library_path()
    try:
        import weasyprint  # noqa: F401
    except ImportError:
        return (
            "PDF export needs weasyprint installed: "
            "pip install 'api-galaxy-api[pdf]' (or pip install weasyprint)"
        )
    except OSError as exc:
        return (
            "PDF export needs the pango and cairo system libraries: "
            f"brew install pango cairo ({exc})".split("\n")[0]
        )
    return ""


def truncate(value: str, limit: int) -> str:
    """Shorten for display, with a real ellipsis so the cut is obvious."""
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"
