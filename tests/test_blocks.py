"""Tests for CLI rendering of message blocks and attachments."""

from slack_cached.cli._internal._blocks import (
    _message_body_lines,
    _render_attachments,
    _render_blocks,
)
from slack_cached.cli._internal._render import _render_channel_human, _render_human
from slack_cached.cli._internal._style import _styler
from slack_cached.storage import CachedMessage, ChannelMessageEntry
from slack_cached.urls import ThreadRef

# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def test_section_mrkdwn_text_styled_is_clickable() -> None:
    s = _styler(True)
    lines = _render_blocks(
        [{"type": "section", "text": {"type": "mrkdwn", "text": "<https://x.com|site>"}}], s
    )
    assert len(lines) == 1
    assert "]8;" in lines[0]
    assert "https://x.com" in lines[0]


def test_section_mrkdwn_text_plain_stays_verbatim() -> None:
    s = _styler(False)
    lines = _render_blocks(
        [{"type": "section", "text": {"type": "mrkdwn", "text": "<https://x.com|site>"}}], s
    )
    assert lines == ["<https://x.com|site>"]


def test_section_fields_render_each() -> None:
    s = _styler(False)
    lines = _render_blocks(
        [
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": "*one*"},
                    {"type": "mrkdwn", "text": "two"},
                ],
            }
        ],
        s,
    )
    assert lines == ["*one*", "two"]


def test_header_and_divider() -> None:
    s = _styler(False)
    lines = _render_blocks(
        [
            {"type": "header", "text": {"type": "plain_text", "text": "Build"}},
            {"type": "divider"},
        ],
        s,
    )
    assert lines == ["Build", "---"]


def test_context_joins_elements() -> None:
    s = _styler(False)
    lines = _render_blocks(
        [
            {
                "type": "context",
                "elements": [
                    {"type": "plain_text", "text": "main"},
                    {"type": "mrkdwn", "text": "<https://ci.dev|passed>"},
                ],
            }
        ],
        s,
    )
    assert lines == ["main  <https://ci.dev|passed>"]


def test_action_button_styled_and_plain() -> None:
    s = _styler(True)
    lines = _render_blocks(
        [
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Deploy"},
                        "url": "https://ci.dev/runs/1",
                    }
                ],
            }
        ],
        s,
    )
    assert "]8;" in lines[0]
    assert "https://ci.dev/runs/1" in lines[0]

    plain = _render_blocks(
        [
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Deploy"},
                        "url": "https://ci.dev/runs/1",
                    }
                ],
            }
        ],
        _styler(False),
    )
    assert plain == ["Deploy (https://ci.dev/runs/1)"]


def test_non_dict_entries_are_skipped() -> None:
    s = _styler(False)
    assert _render_blocks([None, "x"], s) == []
    assert _render_attachments([None, 3], s) == []


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


def test_attachment_title_link_and_text() -> None:
    s = _styler(True)
    lines = _render_attachments(
        [
            {
                "title": "PR #7",
                "title_link": "https://git.dev/pr/7",
                "text": "*merged*",
            }
        ],
        s,
    )
    assert "]8;" in lines[0]
    assert "PR #7" in lines[0]
    assert "\x1b[1mmerged\x1b[0m" in lines[1]


def test_attachment_title_without_link() -> None:
    s = _styler(False)
    lines = _render_attachments([{"title": "Just a title"}], s)
    assert lines == ["Just a title"]


# ---------------------------------------------------------------------------
# Message body assembly
# ---------------------------------------------------------------------------


def test_body_prefers_blocks_over_text() -> None:
    s = _styler(False)
    lines = _message_body_lines(
        "fallback text",
        {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "from blocks"}}]},
        s,
    )
    assert lines == ["from blocks"]


def test_body_falls_back_to_text_without_blocks() -> None:
    s = _styler(False)
    lines = _message_body_lines("plain *old* message", {}, s)
    assert lines == ["plain *old* message"]


def test_body_appends_attachments_after_blocks() -> None:
    s = _styler(False)
    lines = _message_body_lines(
        None,
        {
            "blocks": [{"type": "header", "text": {"type": "plain_text", "text": "Head"}}],
            "attachments": [{"title": "Attached"}],
        },
        s,
    )
    assert lines == ["Head", "Attached"]


def test_body_empty_message_renders_blank_line() -> None:
    assert _message_body_lines(None, {}, _styler(False)) == [""]


# ---------------------------------------------------------------------------
# Renderer integration
# ---------------------------------------------------------------------------


def test_render_human_shows_bot_links() -> None:
    messages = [
        CachedMessage(
            ts="1700000000.000100",
            user="U1",
            text=None,
            payload={
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Build <https://ci.dev/1|failed>",
                        },
                    }
                ]
            },
        )
    ]
    out = _render_human(ThreadRef("C1", "1700000000.000100"), messages, styled=True)
    body_line = next(line for line in out.splitlines() if "]8;" in line)
    assert body_line.startswith("    ")
    assert "https://ci.dev/1" in body_line


def test_render_channel_human_shows_bot_links_plain() -> None:
    entries = [
        ChannelMessageEntry(
            ts="1700000000.000100",
            user="U1",
            text=None,
            payload={
                "attachments": [
                    {"title": "PR #7", "title_link": "https://git.dev/pr/7"},
                ]
            },
            thread_ts="1700000000.000100",
        )
    ]
    out = _render_channel_human("C1", entries, styled=False)
    assert "PR #7 (https://git.dev/pr/7)" in out
