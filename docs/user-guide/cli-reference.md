# CLI reference

## Global options

| Option | Description |
|---|---|
| `--db PATH` | SQLite cache database path (default: `~/.cache/slackx/threads.db`) |
| `--api-base-url URL` | Slack API base URL (default: `https://slack.com/api`) |
| `--log-level LEVEL` | Logging verbosity: `debug`, `info`, `warning`, `error`, or `critical` (default: `info`) |

## Subcommands

### conversations fetch

Cache or refresh a Slack thread, or fetch messages from a channel.

```bash
slackx conversations fetch [TARGET] [--ts TS] [--full-threads] [--last DURATION]
```

| Argument | Description |
|---|---|
| `TARGET` | Slack thread permalink, channel id (`C001`), bare name (`general`), `#`-prefixed name (`#general`), or DM target (user id or `@handle`). Names are resolved against the cached channels. With `--ts`, a channel or DM target reads the given thread. |
| `--ts TS` | Thread root timestamp |
| `--full-threads` | Also fetch all thread replies (channel fetch only) |
| `--last DURATION` | Lookback period for channel fetch (default: `1d`) |

### conversations show

Print a cached thread or channel to stdout.

```bash
slackx conversations show [TARGET] [--ts TS] [--json | --jsonl] [--fetch | --no-fetch] [--last DURATION] [--with-thread-message]
```

| Argument | Description |
|---|---|
| `TARGET` | Slack thread permalink, channel id (`C001`), bare name (`general`), `#`-prefixed name (`#general`), or DM target (user id or `@handle`). Names are resolved against the cached channels. Without `--ts`, shows the channel's top-level messages (thread replies are not shown unless `--with-thread-message`). |
| `--ts TS` | Thread root timestamp |
| `--json` | Output as pretty-printed JSON |
| `--jsonl` | Output as a single compact JSON line (mutually exclusive with `--json`) |
| `--no-fetch` | Do not auto-fetch if not cached (`--fetch` is on by default) |
| `--last DURATION` | Lookback period for channel display (default: `1d`) |
| `--with-thread-message` | Also include thread replies when showing a channel, each marked as belonging to its thread |

### conversations search

Search Slack via `search.messages` and cache every matched message/thread.

```bash
slackx conversations search QUERY [--count N] [--limit N] [--sort score|timestamp] [--sort-dir asc|desc] [--full-threads] [--fields FIELDS] [--json | --jsonl]
```

| Argument | Description |
|---|---|
| `QUERY` | Slack search query (same syntax as the Slack search box, required) |
| `--count N` | Maximum results per page (default: `20`) |
| `--limit N` | Maximum total matches to fetch (default: `200`; `0` for no limit) |
| `--sort` | Sort by `score` or `timestamp` (default: `timestamp`) |
| `--sort-dir` | Sort direction, `asc` or `desc` (default: `desc`) |
| `--full-threads` | Also fetch all replies for every thread a match belongs to |
| `--fields FIELDS` | Comma-separated fields to include, in order: `channel`, `channel_name`, `ts`, `thread_ts`, `user`, `user_name`, `text`, `permalink`, `payload` (default: all but `payload`) |
| `--json` | Output as pretty-printed JSON |
| `--jsonl` | Output as a single compact JSON line (mutually exclusive with `--json`) |

Search is always a live API call. Every matched message is cached under its
`(channel, thread_ts)` so it can be revisited later with `conversations show`.

### users fetch

Cache all workspace users, or a single user when an id is given.

```bash
slackx users fetch [USER]
```

| Argument | Description |
|---|---|
| `USER` | Optional user id (`U001`). When given, fetch only that user via `users.info` instead of enumerating every workspace member. |

### channels fetch

Cache all visible channels, or a single channel when an id is given.

```bash
slackx channels fetch [CHANNEL]
```

| Argument | Description |
|---|---|
| `CHANNEL` | Optional channel id (`C001`), bare name (`general`), or `#`-prefixed name (`#general`). When given, fetch only that channel via `conversations.info` instead of enumerating every visible channel. |

### users list

Print cached users, or a single user when an id is given.

```bash
slackx users list [USER] [--json | --jsonl] [--limit N] [--fields FIELDS] [--no-fetch]
```

| Argument | Description |
|---|---|
| `USER` | Optional user id (`U001`). When given, show only that user instead of listing every cached user. An uncached user is fetched via `users.info` unless `--no-fetch` is given. |
| `--limit N` | Maximum number of users to return (default: all; `0` for all; ignored when `USER` is given) |
| `--fields FIELDS` | Comma-separated fields to include, in order: `id`, `name`, `real_name`, `fetched_at`, `payload` (default: `id,name,real_name`) |
| `--no-fetch` | Do not auto-fetch when the cache is empty (`--fetch` is on by default) |

### channels list

Print cached channels, or a single channel when an id is given.

```bash
slackx channels list [CHANNEL] [--json | --jsonl] [--limit N] [--fields FIELDS] [--no-fetch]
```

| Argument | Description |
|---|---|
| `CHANNEL` | Optional channel id (`C001`), bare name (`general`), or `#`-prefixed name (`#general`). When given, show only that channel instead of listing every cached channel. |
| `--limit N` | Maximum number of channels to return (default: all; `0` for all; ignored when `CHANNEL` is given) |
| `--fields FIELDS` | Comma-separated fields to include, in order: `id`, `name`, `is_private`, `display_name`, `fetched_at`, `payload` (default: `id,name,is_private`). `display_name` resolves direct messages to their peer's name. |
| `--no-fetch` | Do not auto-fetch when the cache is empty (`--fetch` is on by default) |

Listing every channel auto-fetches the full channel list when the cache is
empty. When `CHANNEL` is given, a cache miss fetches only that channel via
`conversations.info`; an unknown channel exits non-zero with an error.

### cache status

Print cache database status: counts and last update time per entity.

```bash
slackx cache status [--json | --jsonl]
```

Reports the number of cached channels, users, threads, and messages, plus the
most recent update time for channels, users, and threads (threads carry the
message-cache update time). Never fetches from Slack.

### cache clear

Delete cached data: everything, messages, channels, or users.

```bash
slackx cache clear [TARGET] [--yes]
```

| Argument | Description |
|---|---|
| `TARGET` | What to clear: `all` (default), `messages`, `channels`, or `users` |
| `--yes`, `-y` | Skip the confirmation prompt |

Reads and clears the cache database directly; never calls Slack. `cache clear messages`
also clears the thread metadata (the rows `conversations show` uses to decide a
thread is cached), so those threads are refetched on next use. Without `--yes`
the command asks for confirmation on an interactive terminal and refuses to run
otherwise.

```bash
slackx cache clear messages       # drop all cached messages and threads
slackx cache clear users          # drop the cached user list
slackx cache clear all --yes      # wipe every cached entity
```

### conversations poll

Poll channels concurrently in a loop for new messages.

```bash
slackx conversations poll --channels CHANNELS [--interval DURATION] [--last DURATION] [--full-threads] [--concurrency N] [--json]
```

| Argument | Description |
|---|---|
| `--channels CHANNELS` | Comma-separated list of channels (required). Each entry may be a channel id (`C001`), a bare name (`general`), or a `#`-prefixed name (`#general`). Names are resolved against the cached channels. |
| `--interval DURATION` | Time between poll cycles (default: `5m`) |
| `--last DURATION` | Lookback period per cycle (default: `5m`, use `all` for full history) |
| `--full-threads` | Also fetch all thread replies for every threaded message |
| `--concurrency N` | Maximum number of channels fetched concurrently (default: `3`) |
| `--json` | Emit per-cycle JSON summaries to stdout |

Uses `httpx.AsyncClient` for non-blocking concurrent HTTP requests. An
`asyncio.Semaphore` caps concurrent in-flight requests to avoid overwhelming
Slack's rate limit. The client also reads `X-RateLimit-Remaining` headers from
every response and proactively waits for the rate limit window to reset when
nearly exhausted.

Stops gracefully on `Ctrl+C`.

### serve

Serve the cached database through a local web UI.

```bash
slackx serve [--host HOST] [--port PORT]
```

| Argument | Description |
|---|---|
| `--host HOST` | Interface to bind to (default: `127.0.0.1`) |
| `--port PORT` | Port to bind to (default: `8280`) |

Opens a Slack-like interface to browse cached users, channels, messages and
threads, with a `Ctrl+P` palette for searching conversations and jumping to
them. Refresh buttons trigger live Slack fetches when credentials are
configured; browsing the cache itself needs none. See
[Serving the web UI](serving.md).

## Duration format

The `--last` flag accepts duration strings:

| Format | Example | Meaning |
|---|---|---|
| `Nh` | `3h` | N hours |
| `Nd` | `7d` | N days |
| `Nm` | `90m` | N minutes |
| Combined | `2d5h30m` | 2 days, 5 hours, 30 minutes |
| `all` | `all` | No time limit |
