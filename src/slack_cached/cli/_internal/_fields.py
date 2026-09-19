"""Field selection shared by the user/channel listing commands."""

from collections.abc import Sequence

USER_FIELDS = ("id", "name", "real_name", "fetched_at", "payload")
USER_DEFAULT_FIELDS = ("id", "name", "real_name")
CHANNEL_FIELDS = ("id", "name", "is_private", "display_name", "fetched_at", "payload")
CHANNEL_DEFAULT_FIELDS = ("id", "name", "is_private")


def parse_fields(raw: str | None, allowed: Sequence[str], default: Sequence[str]) -> list[str]:
    """Parse a comma-separated ``--fields`` value into an ordered, validated list.

    Falls back to ``default`` when ``raw`` is empty. Duplicates are dropped while
    preserving order. Raises ``ValueError`` naming the unknown field(s) so the
    calling command can exit non-zero with a clear message.
    """
    if raw is None or not raw.strip():
        return list(default)
    fields: list[str] = []
    unknown: list[str] = []
    for part in raw.split(","):
        field = part.strip()
        if not field:
            continue
        if field not in allowed:
            unknown.append(field)
        elif field not in fields:
            fields.append(field)
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(unknown)}; available: {', '.join(allowed)}")
    return fields or list(default)
