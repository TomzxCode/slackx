# slackx

A small Python CLI that caches Slack threads, channel messages, users, and
channels to a local SQLite database.

Given a Slack thread URL (or an explicit channel id and root timestamp), it
fetches the thread via `conversations.replies` and stores every message in a
SQLite cache.
On subsequent runs it only fetches new replies (and detects edits) by passing
`oldest` to the API based on the highest cached `ts`.

It can also cache every workspace user and visible channel, so that threads can
be rendered with human-readable author names.

## Install

```bash
uv sync
```

Run it:

```bash
uv run slackx --help
```

## Authentication

Credentials are loaded in this order:

1. Environment variables: `SLACK_TOKEN` (and optional `SLACK_COOKIE` for
   xoxc/web-client tokens).
2. A config file at `$XDG_CONFIG_HOME/slackx/config`
   (defaults to `~/.config/slackx/config`).
   It uses a simple `KEY=VALUE` format:
   ```
   SLACK_TOKEN=xoxb-...
   SLACK_COOKIE=...
   SLACK_API_BASE_URL=https://slack.com/api
   ```

## Cache location

Each Slack workspace gets its own cache database at
`$XDG_CACHE_HOME/slackx/<workspace>/threads.db`
(e.g. `~/.cache/slackx/acme/threads.db`). The workspace is determined from
the configured token/cookie via `auth.test` on first use, then cached on disk
so later commands need no extra API call; the most recently used workspace is
also remembered so read-only commands (e.g. `conversations get --no-fetch`) work offline.

Override with `--workspace <name>` to pick a workspace explicitly, or
`--db /path/to/file.db` for a database path outside the per-workspace layout.
An existing pre-workspace `~/.cache/slackx/threads.db` is left in place;
offline reads fall back to it only while no workspace cache exists yet.

## Usage

All commands accept `--log-level` (`debug`, `info`, `warning`, `error`, or
`critical`; default `info`) for logging on stderr, `--db` to
override the cache location, `--workspace` to select the per-workspace cache
explicitly, and `--api-base-url` to override the Slack API
base URL (defaults to `https://slack.com/api`; also settable via
`SLACK_API_BASE_URL`).

Human-readable output is styled when stdout is a terminal: bold headers and
author names, italic timestamps, clickable permalinks, and Slack message
formatting rendered visually (bold, italics, strikethrough, code, links, and
mentions). Message layout blocks and attachments are rendered in both modes,
so bot-post buttons and links show up like in the web UI. Piped or redirected
output is plain text with the raw message markup left untouched. Styling
respects `NO_COLOR` and `TERM=dumb` (both disable it) and `FORCE_COLOR=1`
(forces it on even when piped).

### Threads

Cache or refresh a thread (no thread output, only a summary on stderr):

```bash
slackx conversations fetch https://acme.slack.com/archives/C0123ABCDEF/p1700000000123456
```

Or with explicit channel/ts:

```bash
slackx conversations fetch C0123ABCDEF --ts 1700000000.123456
```

Show a cached thread (human-readable by default; use `--json` for JSON, or
`--jsonl` for the whole payload as a single compact JSON line). It auto-fetches
if the thread is missing; pass `--no-fetch` to disable that, or `--fetch` to
refresh the cached thread before printing. The command is also available as
`conversations show`:

```bash
slackx conversations get https://acme.slack.com/archives/C0123ABCDEF/p1700000000123456
slackx conversations get --json https://acme.slack.com/archives/C0123ABCDEF/p1700000000123456
slackx conversations get C0123ABCDEF --ts 1700000000.123456 --jsonl >> threads.jsonl
```

### Channel messages

Fetch all top-level messages in a channel via `conversations.history`:

```bash
slackx conversations fetch C0123ABCDEF
```

Add `--full-threads` to also fetch every reply thread for messages that have
replies:

```bash
slackx conversations fetch C0123ABCDEF --full-threads
```

### Search

Search the workspace with the same query syntax as the Slack search box. Every
matched message is cached under its `(channel, thread_ts)` so it can be revisited
later with `conversations get`. Search is always a live API call:

```bash
slackx conversations search "deploy failed"
slackx conversations search "from:@alice after:2024-01-01" --json
slackx conversations search "incident" --jsonl   # one JSON line per run, easy to append
```

Add `--full-threads` to also fetch every reply for each thread a match belongs to:

```bash
slackx conversations search "incident" --full-threads
```

Tune result paging and ordering with `--count`, `--sort` (`score` or `timestamp`,
default `timestamp`), and `--sort-dir` (`asc` or `desc`, default `desc`).

```bash
slackx conversations search "RFC" --count 5 --sort score --sort-dir asc
```

`--limit` caps the total number of matches fetched (default `200`), so broad
queries do not page through every result and stall under Slack's rate limits.
Pass `--limit 0` for no cap.

```bash
slackx conversations search "from:@alice" --limit 500
```

Use `--fields` to choose which fields are returned, in order:

```bash
slackx conversations search "incident" --json --fields channel,ts,user,text
```

### Polling channels

Poll multiple channels concurrently for new messages:

```bash
slackx conversations poll --channels C001,#general,random --interval 5m --last 5m --concurrency 3
```

Uses `httpx.AsyncClient` with an `asyncio.Semaphore` for concurrent, non-blocking
HTTP requests. Reads `X-RateLimit-Remaining` headers to proactively throttle
before hitting 429s. Add `--full-threads` to expand threads, and `--json` to get
per-cycle JSON summaries on stdout. Stops gracefully with `Ctrl+C`.

### Web UI

Browse the cache in a browser with a Slack-like interface:

```bash
slackx serve          # then open http://127.0.0.1:8280
```

Shows a small initial list of users and channels rather than loading the whole
workspace. Use `Ctrl+P` to search all cached users and channels and full-text
search conversations (SQLite FTS5), then jump straight to a match. Channel
messages and threads render with readable author names even before the sidebar
has loaded.
Opening a channel or thread resumes at the message you last viewed, because the
UI stores its viewed position as a read marker under the `web-ui` reader.
Refresh buttons can trigger live Slack fetches when credentials are
configured; browsing the cache itself needs none.

### JSON-RPC API

Clients can call a running server instead of spawning a CLI command per
operation. The `serve` app exposes a JSON-RPC 2.0 endpoint at `POST /rpc`, and
`rpc serve` starts the same app when only the API is needed:

```bash
slackx rpc serve --db ~/.cache/slackx/acme/threads.db --port 8280
slackx rpc methods
slackx rpc call users.list '{"limit": 20}'
slackx rpc call conversations.get '{"target": "#general", "fetch": false}'
```

The default endpoint is `http://127.0.0.1:8280/rpc`; override it with `--url`
or `SLACKX_RPC_URL`. Results match the CLI's `--json` payloads. The methods
cover cache status and clearing, users, channels, conversations (fetch, get,
search), and read markers. `cli.run` reaches every other command, and
`rpc exec` and `--remote` wrap it:

```bash
slackx rpc exec -- conversations search "deploy" --json
slackx --remote http://127.0.0.1:8280 conversations get C1 --json
```

Set `SLACKX_RPC_TOKEN` and `--token` to require a bearer token. Binding a
non-loopback host without a token is refused. A Python client is available at
`slackx.rpc.client.RpcClient`. See the
[JSON-RPC API guide](docs/user-guide/json-rpc.md) for the method table and
protocol details.

### Tracking last read

Record how far each consumer has read in a channel or a thread, so several
programs can share one cache without overwriting each other's position:

```bash
slackx conversations read mark C0123ABCDEF --reader web
slackx conversations read mark C0123ABCDEF --ts 1700000000.123456 --reader web
slackx conversations read show --reader web
slackx conversations read clear --reader web --channel C0123ABCDEF
```

Each `--reader` (default `default`) owns an independent set of pointers: a
channel-level pointer plus one per thread. The value defaults to the newest
cached message in scope; pass `--last-read TS` to set it explicitly. Showing a
channel or thread with `conversations get --reader ID` advances the same
pointer automatically, so showing is reading. The `serve` web API exposes the
pointers under `/api/read`, and the web UI stores the message at the top of its
viewport under the `web-ui` reader so it can resume there. Use
`slackx cache clear read` to drop every pointer.

### Users and channels

Cache or refresh every workspace user or visible channel:

```bash
slackx users fetch
slackx channels fetch
```

Pass a user id to `users fetch`, or a channel id to `channels fetch`, to refresh
just that one entity with a single `users.info`/`conversations.info` call:

```bash
slackx users fetch U001
slackx channels fetch C001
```

Show cached users or channels (human-readable by default, `--json` for pretty
JSON, `--jsonl` for a single compact JSON line; both auto-fetch when empty
unless `--no-fetch` is given). Use `--limit N` to cap how many are returned and
`--fields` to choose which fields are returned and rendered:

```bash
slackx users list
slackx channels list --json
slackx channels list --jsonl
slackx users list --limit 20 --fields id,name
slackx channels list --json --fields id,display_name,is_private
```

Pass an id to `users get` or `channels get` to retrieve just that user or
channel; a cache miss fetches it with a single `users.info`/`conversations.info`
call. Both accept `show` as an alias (`users show`, `channels show`):

```bash
slackx users get U001
slackx channels get C001
```

When a thread's authors are present in the cached users, `conversations get` renders their
real name and handle (e.g. `Alice Smith (alice)`) instead of raw user ids.

Inspect the cache itself with `cache status`, which reports the workspace in use,
the database path, the number of cached channels, users, threads, messages, and
read markers, along with the last update time for each (`--json`/`--jsonl` for
machine-readable output):

```bash
slackx cache status
```

Clear cached data with `cache clear`, scoped to `messages`, `channels`, `users`,
`read`, or `all` (the default). Clearing messages also drops the thread metadata
so those threads are refetched next time:

```bash
slackx cache clear messages
slackx cache clear read
slackx cache clear all --yes
```

Without `--yes` the command asks for confirmation on an interactive terminal.

## Refresh behavior

`conversations fetch` always reaches out to Slack.
If the thread is already cached, it requests `conversations.replies` with
`oldest=<latest_cached_ts>` so the API returns only new replies (and any
recent edits at that boundary).
Messages are upserted by `ts`, so edits replace the older version in place.

HTTP 429 / `ratelimited` responses are retried automatically with exponential
backoff (up to 5 attempts), respecting the `Retry-After` header.

## Fake Slack server

A built-in fake Slack API server for testing and development:

```bash
uv run slack-fake-server --help
uv run slack-fake-server --port 8199 --num-threads 50
```

It serves deterministic workspace data across the endpoints slackx uses
(`auth.test`, `conversations.list`, `conversations.info`,
`conversations.history`, `conversations.replies`, `users.list`, `users.info`,
`search.messages`, and `chat.postMessage`) and can simulate Slack-tier rate
limiting with `--rate-limits`.

Point `slackx` at it with:

```bash
slackx conversations fetch C0001 --last all --api-base-url http://localhost:8199/api
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
```

## Related projects

Tools that also pull Slack history into a local database, each aimed at a
somewhat different job:

- [slacrawl](https://github.com/openclaw/slacrawl) is a Go terminal app that
  mirrors a workspace into local SQLite for full-text search, terminal
  browsing, reporting, and read-only SQL. It syncs from the API, imports Slack
  exports, and ships a TUI. Closest match to slackx, but TUI-first and
  archive-wide rather than thread-first.
- [slackdump](https://github.com/rusq/slackdump) is a Go archiver that dumps
  channels, threads, users, and files without admin rights, either as a Slack
  Export folder or as a resumable SQLite archive. It is the mature heavyweight
  option, with conversion, search, a viewer, and an MCP server.
- [slackcache](https://github.com/rogerchappel/slackcache) is a small
  local-first CLI that imports Slack export JSON, redacts risky text by
  default, then supports search and thread viewing from files instead of the
  live API.
- [slackslaw](https://github.com/salam/slackslaw-cli) is a bash and sqlite
  wrapper around slackdump that adds multi-workspace sync, search, stats,
  LLM context dumps, and a live tail.
- [traul](https://github.com/dandaka/traul) syncs Slack along with Discord,
  Telegram, and other sources into one local SQLite database with FTS5 and
  optional vector search, in a form an agent can query.

For a live terminal client rather than a cache, [slack-term](https://github.com/jpbruinsslot/slack-term)
is a well-known choice.
