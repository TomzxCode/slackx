"""Terminal styling helpers for human-readable CLI output.

Styling is opt-in per render call: commands pass
``_supports_styles(sys.stdout)`` so output stays plain text when piped and
gains ANSI styles (bold, italics, dim, OSC 8 hyperlinks) when written to a
terminal that supports them. Style emission is delegated to rich.
"""

from __future__ import annotations

import io
import os
import sys
from typing import TextIO

from rich.console import Console
from rich.style import Style
from rich.text import Text

from slack_cached.cli._internal._mrkdwn import _mrkdwn_to_markup

_BOLD = Style(bold=True)
_ITALIC = Style(italic=True)
_DIM = Style(dim=True)

# A private console that always emits ANSI codes, used to serialize styled
# fragments into strings embedded in the renderers' line-based output.
_ANSI_CONSOLE = Console(
    file=io.StringIO(),
    force_terminal=True,
    color_system="truecolor",
    width=10**6,
)


def _supports_styles(stream: TextIO | None = None) -> bool:
    """Return whether the given stream (default stdout) supports ANSI styling.

    Respects the common environment conventions: ``NO_COLOR`` disables,
    ``TERM=dumb`` or an unset ``TERM`` disables, and ``FORCE_COLOR`` forces
    styling on even when the stream is not a TTY.
    """
    force = os.environ.get("FORCE_COLOR")
    if force is not None:
        return force != "0"
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "dumb") == "dumb":
        return False
    stream = sys.stdout if stream is None else stream
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


class _Styler:
    """Apply rich styles when enabled; return text unchanged otherwise."""

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Whether this styler applies styles to its output."""
        return self._enabled

    def bold(self, text: str) -> str:
        """Wrap ``text`` in bold when styling is enabled."""
        return self._wrap(_BOLD, text)

    def italic(self, text: str) -> str:
        """Wrap ``text`` in italics when styling is enabled."""
        return self._wrap(_ITALIC, text)

    def dim(self, text: str) -> str:
        """Wrap ``text`` in dim when styling is enabled."""
        return self._wrap(_DIM, text)

    def link(self, text: str, url: str) -> str:
        """Wrap ``text`` in an OSC 8 hyperlink to ``url`` when styling is enabled."""
        if not self._enabled or not text:
            return text
        return self._render(Text(text, style=Style(link=url)))

    def mrkdwn(self, text: str) -> str:
        """Render Slack mrkdwn message text to ANSI when styling is enabled.

        Converts Slack-specific constructs (bold, italics, strikethrough,
        code, links, mentions) so the output resembles how Slack displays the
        message. When styling is disabled, ``text`` is returned verbatim so
        piped output stays stable for scripts.
        """
        if not self._enabled or not text:
            return text
        with _ANSI_CONSOLE.capture() as capture:
            _ANSI_CONSOLE.print(
                _mrkdwn_to_markup(text),
                end="",
                highlight=False,
                emoji=False,
                soft_wrap=True,
            )
        return capture.get()

    def _wrap(self, style: Style, text: str) -> str:
        if not self._enabled or not text:
            return text
        return self._render(Text(text, style=style))

    @staticmethod
    def _render(text: Text) -> str:
        """Serialize a styled fragment to a string carrying ANSI codes."""
        with _ANSI_CONSOLE.capture() as capture:
            _ANSI_CONSOLE.print(text, end="", soft_wrap=True)
        return capture.get()


def _styler(enabled: bool) -> _Styler:
    """Return a styler that applies rich styles only when ``enabled``."""
    return _Styler(enabled)
