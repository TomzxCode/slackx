"""Tests for Slack mrkdwn to rich markup conversion and styled rendering."""

from slack_cached.cli._internal._mrkdwn import _mrkdwn_to_markup
from slack_cached.cli._internal._render import _render_human
from slack_cached.cli._internal._style import _styler
from slack_cached.storage import CachedMessage
from slack_cached.urls import ThreadRef

# ---------------------------------------------------------------------------
# Converter: emphasis and code
# ---------------------------------------------------------------------------


def test_bold() -> None:
    assert _mrkdwn_to_markup("*bold* text") == "[bold]bold[/bold] text"


def test_italic_does_not_hit_snake_case() -> None:
    assert _mrkdwn_to_markup("snake_case_word") == "snake_case_word"
    assert _mrkdwn_to_markup("_italic_ text") == "[italic]italic[/italic] text"


def test_strikethrough() -> None:
    assert _mrkdwn_to_markup("~gone~ text") == "[strike]gone[/strike] text"


def test_inline_code_is_stashed_from_emphasis() -> None:
    out = _mrkdwn_to_markup("use `x_y *z*` here")
    assert "[dim]x_y *z*[/dim]" in out
    assert "[bold]" not in out
    assert "[italic]" not in out


def test_code_fence_styles_lines() -> None:
    out = _mrkdwn_to_markup("```\na*b\n```")
    assert out == "[dim]```[/dim]\n[dim]a*b[/dim]\n[dim]```[/dim]"


# ---------------------------------------------------------------------------
# Converter: links, mentions, entities
# ---------------------------------------------------------------------------


def test_labeled_link() -> None:
    out = _mrkdwn_to_markup("see <https://example.com|the site>")
    assert out == "see [link=https://example.com]the site[/link]"


def test_bare_link() -> None:
    assert _mrkdwn_to_markup("<https://example.com>") == (
        "[link=https://example.com]https://example.com[/link]"
    )


def test_user_mention() -> None:
    assert _mrkdwn_to_markup("hi <@U123|alice>!") == "hi @alice!"
    assert _mrkdwn_to_markup("hi <@U123>!") == "hi @U123!"


def test_channel_mention() -> None:
    assert _mrkdwn_to_markup("in <#C1|dev> now") == "in #dev now"


def test_special_mentions() -> None:
    assert _mrkdwn_to_markup("<!here>") == "@here"
    assert _mrkdwn_to_markup("<!channel>") == "@channel"
    assert _mrkdwn_to_markup("<!subteam^S1|ops>") == "@ops"
    assert _mrkdwn_to_markup("<!subteam^S1>") == "@group"


def test_date_construct_renders_fallback() -> None:
    out = _mrkdwn_to_markup("<!date^1700000000^{date_num}|Feb 18>")
    assert out == "Feb 18"


def test_entities_decoded() -> None:
    assert _mrkdwn_to_markup("a &amp; b &lt;c&gt;") == "a & b <c>"


# ---------------------------------------------------------------------------
# Converter: escaping
# ---------------------------------------------------------------------------


def test_literal_brackets_are_escaped() -> None:
    out = _mrkdwn_to_markup("array[0] and [red]fake[/red]")
    assert "\\[red]" in out
    assert "\\[/red]" in out


def test_trailing_backslash_does_not_break_markup() -> None:
    out = _mrkdwn_to_markup("path C:\\ *bold*")
    assert "[bold]bold[/bold]" in out


# ---------------------------------------------------------------------------
# Styler integration
# ---------------------------------------------------------------------------


def test_styler_mrkdwn_verbatim_when_disabled() -> None:
    assert _styler(False).mrkdwn("*bold* <https://x.com|link>") == ("*bold* <https://x.com|link>")


def test_styler_mrkdwn_renders_when_enabled() -> None:
    out = _styler(True).mrkdwn("*bold* and <https://x.com|link>")
    assert "\x1b[1mbold\x1b[0m" in out
    assert "\x1b]8;" in out
    assert "https://x.com" in out


def test_styler_mrkdwn_literal_brackets_stay_plain() -> None:
    out = _styler(True).mrkdwn("[red]not a tag[/red]")
    assert "\x1b[31m" not in out
    assert "[red]" in out


def test_render_human_styled_renders_mrkdwn() -> None:
    messages = [
        CachedMessage(
            ts="1700000000.000100",
            user="U1",
            text="*bold* and <https://x.com|link>",
            payload={},
        )
    ]
    out = _render_human(ThreadRef("C1", "1700000000.000100"), messages, styled=True)
    assert "\x1b[1mbold\x1b[0m" in out
    assert "\x1b]8;" in out
    # The link sits on an indented message line.
    line = next(line for line in out.splitlines() if "]8;" in line)
    assert line.startswith("    ")


def test_render_human_plain_keeps_verbatim_text() -> None:
    messages = [
        CachedMessage(
            ts="1700000000.000100",
            user="U1",
            text="*bold* and <https://x.com|link>",
            payload={},
        )
    ]
    out = _render_human(ThreadRef("C1", "1700000000.000100"), messages)
    assert "*bold*" in out
    assert "<https://x.com|link>" in out
