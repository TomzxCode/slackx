"""Tests for ANSI styling of human-readable CLI output."""

import io
import sys

import pytest

from slack_cached.cli._internal._render import (
    _render_channel_human,
    _render_human,
    _render_search_human,
    _render_status_human,
)
from slack_cached.cli._internal._style import _styler, _supports_styles
from slack_cached.storage import CachedMessage, ChannelMessageEntry, DbStatus
from slack_cached.urls import ThreadRef

# ---------------------------------------------------------------------------
# _supports_styles detection
# ---------------------------------------------------------------------------


def test_supports_styles_true_for_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """A TTY on a normal terminal gets styles."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    stream = io.StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    assert _supports_styles(stream) is True


def test_supports_styles_false_for_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-TTY stream gets plain output."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    stream = io.StringIO()
    stream.isatty = lambda: False  # type: ignore[method-assign]
    assert _supports_styles(stream) is False


def test_supports_styles_false_when_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    """NO_COLOR disables styles even on a TTY."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    stream = io.StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    assert _supports_styles(stream) is False


def test_supports_styles_false_for_dumb_term(monkeypatch: pytest.MonkeyPatch) -> None:
    """TERM=dumb disables styles even on a TTY."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    stream = io.StringIO()
    stream.isatty = lambda: True  # type: ignore[method-assign]
    assert _supports_styles(stream) is False


@pytest.mark.parametrize("value", ["1", "0", ""])
def test_supports_styles_force_color(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """FORCE_COLOR=1 forces styles on, FORCE_COLOR=0 forces them off."""
    monkeypatch.setenv("FORCE_COLOR", value)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    stream = io.StringIO()
    stream.isatty = lambda: False  # type: ignore[method-assign]
    assert _supports_styles(stream) is (value != "0")


def test_supports_styles_defaults_to_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a stream argument, detection uses sys.stdout."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert _supports_styles() is sys.stdout.isatty()


# ---------------------------------------------------------------------------
# _Styler behavior
# ---------------------------------------------------------------------------


def test_styler_noop_when_disabled() -> None:
    """A disabled styler returns text unchanged."""
    s = _styler(False)
    assert s.bold("x") == "x"
    assert s.italic("x") == "x"
    assert s.dim("x") == "x"
    assert s.link("x", "https://example.com") == "x"


def test_styler_applies_ansi_when_enabled() -> None:
    """An enabled styler wraps text in the matching ANSI codes."""
    s = _styler(True)
    assert s.bold("x") == "\x1b[1mx\x1b[0m"
    assert s.italic("x") == "\x1b[3mx\x1b[0m"
    assert s.dim("x") == "\x1b[2mx\x1b[0m"


def test_styler_link_uses_osc8() -> None:
    """An enabled styler wraps text in an OSC 8 hyperlink sequence."""
    s = _styler(True)
    out = s.link("text", "https://example.com")
    assert out.startswith("\x1b]8;")
    assert "https://example.com" in out
    assert "text" in out
    assert out.endswith("\x1b]8;;\x1b\\")


def test_styler_handles_empty_text() -> None:
    """Empty text stays empty regardless of styling."""
    s = _styler(True)
    assert s.bold("") == ""
    assert s.link("", "https://example.com") == ""


# ---------------------------------------------------------------------------
# Styled renderers
# ---------------------------------------------------------------------------


def _thread_messages() -> list[CachedMessage]:
    return [CachedMessage(ts="1700000000.000100", user="U1", text="hello", payload={})]


def test_render_human_styled() -> None:
    """The styled thread render wraps header and author in bold."""
    out = _render_human(ThreadRef("C1", "1700000000.000100"), _thread_messages(), styled=True)
    assert "\x1b[1mThread C1/1700000000.000100\x1b[0m" in out
    assert "\x1b[1mU1\x1b[0m" in out
    assert "\x1b[3m[2023-11-14T22:13:20+00:00]\x1b[0m" in out


def test_render_human_plain_by_default() -> None:
    """Without styled=True the render carries no escape codes."""
    out = _render_human(ThreadRef("C1", "1700000000.000100"), _thread_messages())
    assert "\x1b" not in out
    assert "Thread C1/1700000000.000100" in out


def test_render_channel_human_styled_marks_thread_reply() -> None:
    """The styled channel render dims the thread reply marker and annotation."""
    top = CachedMessage(ts="1700000000.000100", user="U1", text="top", payload={})
    reply = CachedMessage(
        ts="1700000000.000200", user="U1", text="reply", payload={"thread_ts": "1700000000.000100"}
    )

    entries = [
        ChannelMessageEntry(
            ts=top.ts,
            user=top.user,
            text=top.text,
            payload={},
            thread_ts="1700000000.000100",
        ),
        ChannelMessageEntry(
            ts=reply.ts,
            user=reply.user,
            text=reply.text,
            payload={},
            thread_ts="1700000000.000100",
        ),
    ]
    out = _render_channel_human("C1", entries, styled=True)
    assert "\x1b[2m\u21b3\x1b[0m" in out
    assert "\x1b[2m(thread 1700000000.000100)\x1b[0m" in out


def test_render_search_human_styled_links_permalink() -> None:
    """The styled search render turns the permalink into an OSC 8 hyperlink."""
    match = {
        "channel": "C1",
        "ts": "1700000000.000100",
        "user": "U1",
        "text": "found",
        "permalink": "https://acme.slack.com/archives/C1/p1700000000000100",
    }
    out = _render_search_human("needle", [match], styled=True)
    assert "\x1b]8;" in out
    assert "https://acme.slack.com/archives/C1/p1700000000000100" in out
    assert "\x1b]8;;\x1b\\" in out


def test_render_status_human_styled() -> None:
    """The styled status render bolds counts and italics timestamps."""
    status = DbStatus(
        channel_count=2,
        user_count=3,
        thread_count=1,
        message_count=4,
        channels_updated_at=1700000000.0,
        users_updated_at=None,
        threads_updated_at=None,
    )
    out = _render_status_human(status, styled=True)
    assert "\x1b[1m2\x1b[0m channel(s)" in out
    assert "\x1b[3m(never)\x1b[0m" in out
