# Project memory

## 2026-09-23
- CLI commands are grouped as noun-verb sub-apps (cyclopts): `channels fetch|list`, `users fetch|list`, `conversations fetch|show|search|poll`, `cache clear|status`. Group apps live in `src/slack_cached/cli/_internal/_shared.py`; command modules are named `<group>_<verb>.py` under `cli/commands/`. `serve` is the only top-level command left.
- Three tests fail on main regardless of this change (verified via git stash): `test_resolve_ref_requires_url_or_channel_ts` (references removed `_refs._resolve_ref`), `test_fetch_channel_via_url` and `test_show_channel_via_url` (use a removed `--url` flag, stale from the positional-TARGET conversion in commit a26dea0).
- `.sdlc/features/FEAT-0001/0002/0003` requirements/specs still reference old flat command names (fetch-users, show-channels, show --channel, etc.); historical artifacts, candidates for a propagate-changes pass if ever revisited.
