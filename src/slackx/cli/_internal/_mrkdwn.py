"""Convert Slack mrkdwn message text to rich markup.

Slack messages arrive as mrkdwn, which differs from markdown: single
asterisks for bold, ``<url|label>`` for links, ``<@U123>`` for mentions, and
HTML entities for reserved characters. This module translates those
constructs into rich markup so the styled renderers can display them the way
Slack does. Translation is best-effort and line-local: no construct spans a
newline, so each rendered line stays self-contained.
"""

from __future__ import annotations

import re

from rich.markup import escape

_ENTITIES = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
}

_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_TAG = re.compile(r"<([^<>|]+?)(?:\|([^<>]*))?>")
_BOLD = re.compile(r"\*([^*\n]+)\*")
_ITALIC = re.compile(r"(?<!\w)_([^_\n]+)_(?!\w)")
_STRIKE = re.compile(r"(?<!\w)~([^~\n]+)~(?!\w)")

# Sentinel guarding inline-code content from the emphasis and link parsers.
_SENTINEL = "\x00{}\x00"


def _replace_tag(match: re.Match[str]) -> str:
    """Translate one ``<target|label>`` construct to plain text or markup."""
    target = match.group(1)
    label = match.group(2)
    if target.startswith("@"):
        shown = label or target.lstrip("@")
        return f"@{shown}"
    if target.startswith("#"):
        shown = label or target.lstrip("#")
        return f"#{shown}"
    if target.startswith("!"):
        if target.startswith("!date"):
            return label or target
        if target.startswith("!subteam"):
            return f"@{label}" if label else "@group"
        return f"@{target[1:]}"
    shown = escape(label) if label else escape(target)
    return f"[link={escape(target)}]{shown}[/link]"


def _render_line(line: str) -> str:
    """Convert one mrkdwn line (no fences) to a rich markup string."""
    fragments: list[str] = []

    def stash(rendered: str) -> str:
        """Set aside an already-rendered markup fragment, safe from escaping."""
        fragments.append(rendered)
        return _SENTINEL.format(len(fragments) - 1)

    line = _CODE_SPAN.sub(lambda m: stash(f"[dim]{escape(m.group(1))}[/dim]"), line)
    line = _TAG.sub(lambda m: stash(_replace_tag(m)), line)
    line = _BOLD.sub(lambda m: stash(f"[bold]{escape(m.group(1))}[/bold]"), line)
    line = _ITALIC.sub(lambda m: stash(f"[italic]{escape(m.group(1))}[/italic]"), line)
    line = _STRIKE.sub(lambda m: stash(f"[strike]{escape(m.group(1))}[/strike]"), line)

    parts = re.split("\x00(\\d+)\x00", line)
    rendered: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 0:
            rendered.append(escape(part))
        else:
            rendered.append(fragments[int(part)])
    return "".join(rendered)


def _mrkdwn_to_markup(text: str) -> str:
    """Convert Slack mrkdwn ``text`` to a rich markup string."""
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines() or [""]:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            lines.append(f"[dim]{escape(line)}[/dim]")
        elif in_fence:
            lines.append(f"[dim]{escape(line)}[/dim]")
        else:
            lines.append(_render_line(line))
    for entity, character in _ENTITIES.items():
        lines = [line.replace(entity, character) for line in lines]
    return "\n".join(lines)
