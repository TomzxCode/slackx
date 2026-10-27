<!-- session_link: http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ -->
# Conventions

## Naming

- **Files:** snake_case for Python modules.
  - Modules ending in `_fetch`, `_get`, `_list`, `_show`, `_search`, `_poll`, `_mark`, `_clear`, `_status`, `_call`, `_exec`, `_methods`, or `_serve` name one CLI command each.
  - Modules starting with `_` are package-private helpers.
  - Test files are `test_<module>.py` matching the module under test.
- **Variables:** snake_case (e.g. `thread_ts`, `latest_reply`, `user_names`).
- **Functions / Methods:** snake_case (e.g. `fetch_thread`, `load_thread_messages`, `fetch_search`).
- **Classes:** PascalCase, value objects as frozen dataclasses (e.g. `SlackClient`, `CachedMessage`, `ThreadRef`, `FetchResult`, `Credentials`).
- **Constants:** UPPER_SNAKE_CASE (e.g. `SCHEMA`, `SEARCH_SCHEMA`, `DEFAULT_LIMIT`, `MAX_RETRIES`, `CHANNEL_PREFIXES`).
- **Private helpers:** prefixed with an underscore (e.g. `_build_client`, `_format_ts`, `_latest_ts`, `_log_sql`).
- **CLI subcommands:** noun-verb groups built with cyclopts (e.g. `conversations fetch`, `channels list`, `users fetch`, `conversations read mark`).
- **RPC methods:** dot-namespaced `group.verb` names mirroring the CLI groups (e.g. `cache.status`, `conversations.get`, `read.mark`, `cli.run`).

## Directory Structure

The package is `slackx`, exposed through two console scripts: `slackx` and `slack-fake-server`.

```
slackx/
  src/
    slackx/
      __init__.py
      _log.py                # Lazy structlog logger (no import cost until first log call)
      cache.py               # Async fetch orchestration and result dataclasses
      config.py              # Credentials, XDG paths, credential resolution
      defaults.py            # Default values shared by the API client and the CLI
      slack_api.py           # Async Slack Web API client (httpx)
      storage.py             # SQLite schema, CRUD, FTS5 search, read markers
      urls.py                # Permalink parsing into ThreadRef
      workspace.py           # Per-workspace cache database resolution
      __main__.py            # python -m slackx entry point
      rpc/
        __init__.py
        client.py            # RpcClient: async JSON-RPC client over httpx
        methods.py           # RPC method registry, parameter validation, handlers
        protocol.py          # JSON-RPC 2.0 error codes and RpcError
        server.py            # POST /rpc routes mounted on the FastAPI app
      cli/
        __init__.py          # main entry point, registers command modules
        commands/            # One module per command (cache_clear, channels_fetch, ...)
        _internal/           # Shared app, args, client, rendering helpers (_render, _blocks, _mrkdwn, _style, _format, _fields, _refs, _poll, _duration, _channels, _client, _remote, _shared)
      server/
        app.py               # FastAPI JSON API and static SPA serving
        static/              # Served SPA assets
      fake_slack/
        __init__.py          # slack-fake-server entry point
        commands/            # run command
        _internal/           # Fake Slack API internals (_config, _constants, _cursor, _data_pools, _generate, _handler, _rate_limiter, _server, _workspace)
  tests/
    test_blocks.py           # Tests for rich block rendering
    test_cache.py            # Tests for cache orchestration
    test_cli.py              # Tests for CLI surface
    test_config.py           # Tests for config resolution
    test_fake_slack.py       # Tests for fake Slack server
    test_mrkdwn.py           # Tests for mrkdwn rendering
    test_rpc.py              # Tests for the JSON-RPC endpoint, methods, and CLI surfaces
    test_server.py           # Tests for FastAPI JSON API
    test_slack_api.py        # Tests for Slack API client
    test_storage.py          # Tests for SQLite storage
    test_style.py            # Tests for terminal style rendering
    test_urls.py             # Tests for URL parsing
    test_workspace.py        # Tests for per-workspace database resolution
  docs/                      # mkdocs user guide, developer guide, and SDLC feature docs
  web/dist/                  # Built SPA served by the serve command
  .sdlc/                     # SDLC context, features, and templates
  pyproject.toml             # Project metadata, deps, tool config
  README.md                  # User-facing documentation
```

## Coding Standards

- Use frozen dataclasses for value objects (ThreadRef, Credentials, FetchResult, and similar).
- Use structlog for all logging; never use the stdlib logging module directly.
- Get module loggers from `slackx._log.get_logger`, not `structlog.get_logger`: the returned logger imports structlog on first use, so importing a module (and rendering CLI help) stays cheap.
- Use `from __future__ import annotations` in modules that use modern type syntax.
- Import the Slack client and cache functions lazily in CLI commands to avoid loading httpx when it is not needed.
- Use cyclopts for the CLI, with shared `Annotated` argument types in `cli/_internal/_shared.py`.
- Write CLI help text without markdown: help renders through cyclopts' `plaintext` format, so backticks and asterisks would print literally instead of formatting.
- Use context managers for database connections and transactions.
- Give public functions docstrings, and add brief docstrings to private helpers with non-obvious behavior.
- Use a TYPE_CHECKING guard for type-only imports.
- Keep `__init__.py` files minimal, for package initialization and entry points.
- Test with pytest; use the `tmp_path` fixture for temporary databases and `monkeypatch` for environment and dependency injection.
- Run `ruff check` and `ruff format` before committing; line length is 100 and lint selects E, F, I, B, UP, SIM.

## Commit Messages

- Most commits use a short, imperative description without a prefix (e.g. "Move read tracking under conversations and mark read on show", "Group CLI commands into noun-verb subcommands").
- Some commits use a Conventional Commits prefix with an optional scope (e.g. `feat(web): ...`, `feat(cli): ...`, `chore: ...`).
- No prefix style is enforced; the repository mixes both forms.

## Branching

- `main` is the default branch and what remote tracking points to.
- Work happens on named branches merged back into `main`, for example `sdlc`, `rich-output`, `serve-render-links`, and `spa`.
- Dependabot opens branches under `dependabot/...`.
- No branch name prefix convention is enforced.

## SDLC Documentation Style

- One sentence per line in markdown files for easier diff and review.
- Use sentence case for headings, not title case.
- Prefer bullet lists over prose paragraphs.
- Use tables for structured data (requirements, specifications, and similar).
- Keep overview paragraphs to one or two sentences.
