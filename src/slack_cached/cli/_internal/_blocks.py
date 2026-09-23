"""Render Slack message blocks and attachments for the CLI human renderers.

Bot messages often carry their links only inside layout blocks or
attachments; the ``text`` field is then just a plain fallback. This module
mirrors the web UI's rendering order: blocks when present, otherwise the
message text, then attachments appended below. Text objects go through the
mrkdwn converter so links become clickable when styling is enabled.
"""

from __future__ import annotations

from typing import Any

from slack_cached.cli._internal._style import _Styler


def _text_object(obj: Any, s: _Styler) -> str:
    """Render a block text object ({type, text}); plain_text stays verbatim."""
    if not isinstance(obj, dict) or obj.get("text") is None:
        return ""
    text = str(obj["text"])
    if obj.get("type") == "plain_text":
        return text
    return s.mrkdwn(text)


def _link_line(label: str, url: str, s: _Styler) -> str:
    """Render ``label`` pointing at ``url`` in both styling modes."""
    if s.enabled:
        return s.link(label, url)
    return f"{label} ({url})"


def _render_blocks(blocks: list[Any], s: _Styler) -> list[str]:
    """Render layout blocks into body lines, mirroring the web UI."""
    lines: list[str] = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "section":
            if block.get("text"):
                lines.append(_text_object(block["text"], s))
            for field in block.get("fields") or []:
                lines.append(_text_object(field, s))
        elif btype == "header":
            if block.get("text"):
                lines.append(_text_object(block["text"], s))
        elif btype == "divider":
            lines.append("---")
        elif btype == "context":
            parts = [
                _text_object(element, s)
                for element in block.get("elements") or []
                if isinstance(element, dict)
                and element.get("type") in ("plain_text", "mrkdwn")
            ]
            if any(parts):
                lines.append("  ".join(part for part in parts if part))
        elif btype == "actions":
            for element in block.get("elements") or []:
                if not isinstance(element, dict) or element.get("type") != "button":
                    continue
                url = element.get("url")
                if not url:
                    continue
                label = element.get("text")
                label_text = (
                    label.get("text") if isinstance(label, dict) else None
                ) or url
                lines.append(_link_line(label_text, str(url), s))
    return lines


def _render_attachments(attachments: list[Any], s: _Styler) -> list[str]:
    """Render legacy attachments: linked title plus mrkdwn text."""
    lines: list[str] = []
    for attachment in attachments or []:
        if not isinstance(attachment, dict):
            continue
        title = attachment.get("title")
        title_link = attachment.get("title_link")
        if title:
            if title_link:
                lines.append(_link_line(str(title), str(title_link), s))
            else:
                lines.append(str(title))
        if attachment.get("text"):
            lines.append(s.mrkdwn(str(attachment["text"])))
    return lines


def _message_body_lines(
    text: str | None, payload: dict[str, Any] | None, s: _Styler
) -> list[str]:
    """Return a message's body lines: blocks, else text, plus attachments."""
    payload = payload or {}
    body = _render_blocks(payload.get("blocks") or [], s)
    if not body and text:
        body = s.mrkdwn(text).splitlines() or [""]
    attachments = _render_attachments(payload.get("attachments") or [], s)
    combined = body + attachments
    return combined if combined else [""]
