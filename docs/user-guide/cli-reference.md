# CLI reference

## Global options

Every subcommand accepts these options after the command name (for example
`slackx cache status --workspace acme`):

| Option | Description |
|---|---|
| `--db PATH` | SQLite cache database path, outside the per-workspace layout (default: `~/.cache/slackx/<workspace>/threads.db`) |
| `--workspace NAME` | Workspace selecting the per-workspace cache database (`~/.cache/slackx/NAME/threads.db`). Discovered via `auth.test` when omitted |
| `--api-base-url URL` | Slack API base URL (default: `https://slack.com/api`) |
| `--log-level LEVEL` | Logging verbosity: `debug`, `info`, `warning`, `error`, or `critical` (default: `info`) |
| `--version` | Print the application version and exit |

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

### conversations get

Print a cached thread or channel to stdout. Alias: `conversations show`.

```bash
slackx conversations get [TARGET] [--ts TS] [--json | --jsonl] [--fetch | --no-fetch] [--last DURATION] [--with-thread-message] [--reader ID]
```

| Argument | Description |
|---|---|
| `TARGET` | Slack thread permalink, channel id (`C001`), bare name (`general`), `#`-prefixed name (`#general`), or DM target (user id or `@handle`). Names are resolved against the cached channels. Without `--ts`, shows the channel's top-level messages (thread replies are not shown unless `--with-thread-message`). |
| `--ts TS` | Thread root timestamp |
| `--json` | Output as pretty-printed JSON |
| `--jsonl` | Output as a single compact JSON line (mutually exclusive with `--json`) |
| `--no-fetch` | Do not fetch the target from Slack. Resolving a channel by name still reads the cached channels, fetching the channel list if empty |
| `--fetch` | Force a refresh from Slack even if the target is already cached |
| `--last DURATION` | Lookback period for channel display (default: `1d`) |
| `--with-thread-message` | Also include thread replies when showing a channel, each marked as belonging to its thread |
| `--reader ID` | Reader whose last-read pointer is advanced after printing (default: `default`) |

After printing, the pointer for the shown channel or thread is advanced to the
newest cached message, so showing is reading. Readers are independent, so
several consumers can read the same cache without affecting each other's
pointers. See [Tracking last read](tracking-last-read.md).

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
`(channel, thread_ts)` so it can be revisited later with `conversations get`.

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

Print every cached user.

```bash
slackx users list [--json | --jsonl] [--limit N] [--fields FIELDS] [--no-fetch]
```

| Argument | Description |
|---|---|
| `--limit N` | Maximum number of users to return (default: all; `0` for all) |
| `--fields FIELDS` | Comma-separated fields to include, in order: `id`, `name`, `real_name`, `fetched_at`, `payload` (default: `id,name,real_name`) |
| `--no-fetch` | Do not auto-fetch when the cache is empty (`--fetch` is on by default) |

### users get

Print a single cached user. Alias: `users show`.

```bash
slackx users get USER [--json | --jsonl] [--fields FIELDS] [--no-fetch]
```

| Argument | Description |
|---|---|
| `USER` | User id (`U001`). An uncached user is fetched via `users.info` unless `--no-fetch` is given. |
| `--fields FIELDS` | Comma-separated fields to include, in order: `id`, `name`, `real_name`, `fetched_at`, `payload` (default: `id,name,real_name`) |
| `--no-fetch` | Do not auto-fetch when the user is not cached (`--fetch` is on by default) |

### channels list

Print every cached channel.

```bash
slackx channels list [--json | --jsonl] [--limit N] [--fields FIELDS] [--no-fetch]
```

| Argument | Description |
|---|---|
| `--limit N` | Maximum number of channels to return (default: all; `0` for all) |
| `--fields FIELDS` | Comma-separated fields to include, in order: `id`, `name`, `is_private`, `display_name`, `fetched_at`, `payload` (default: `id,name,is_private`). `display_name` resolves direct messages to their peer's name. |
| `--no-fetch` | Do not auto-fetch when the cache is empty (`--fetch` is on by default) |

Listing every channel auto-fetches the full channel list when the cache is
empty.

### channels get

Print a single cached channel. Alias: `channels show`.

```bash
slackx channels get CHANNEL [--json | --jsonl] [--fields FIELDS] [--no-fetch]
```

| Argument | Description |
|---|---|
| `CHANNEL` | Channel id (`C001`), bare name (`general`), or `#`-prefixed name (`#general`). An uncached channel is fetched via `conversations.info` unless `--no-fetch` is given. Resolving a name still fetches the channel list if the cache is empty. |
| `--fields FIELDS` | Comma-separated fields to include, in order: `id`, `name`, `is_private`, `display_name`, `fetched_at`, `payload` (default: `id,name,is_private`). `display_name` resolves direct messages to their peer's name. |
| `--no-fetch` | Do not auto-fetch when the channel is not cached (`--fetch` is on by default) |

A cache miss fetches only that channel via `conversations.info`; an unknown
channel exits non-zero with an error.

### cache status

Print cache database status: the workspace and database in use, plus counts and
last update time per entity.

```bash
slackx cache status [--json | --jsonl]
```

| Option | Description |
|---|---|
| `--json` | Output as pretty-printed JSON |
| `--jsonl` | Output as a single compact JSON line (mutually exclusive with `--json`) |

Reports the resolved workspace name and database path, then the number of
cached channels, users, threads, and messages, plus the most recent update time
for channels, users, and threads (threads carry the message-cache update time).
The workspace line is omitted when the database lives outside the per-workspace
layout (a custom `--db`, or the legacy single `threads.db`); the JSON output
carries `workspace` (null in that case) and `db_path`. Never fetches from
Slack.

### cache clear

Delete cached data: everything, messages, channels, or users.

```bash
slackx cache clear [TARGET] [--yes]
```

| Argument | Description |
|---|---|
| `TARGET` | What to clear: `all` (default), `messages`, `channels`, `users`, or `read` |
| `--yes`, `-y` | Skip the confirmation prompt |

Reads and clears the cache database directly; never calls Slack. `cache clear messages`
also clears the thread metadata (the rows `conversations get` uses to decide a
thread is cached), so those threads are refetched on next use. Without `--yes`
the command asks for confirmation on an interactive terminal and refuses to run
otherwise.

```bash
slackx cache clear messages       # drop all cached messages and threads
slackx cache clear users          # drop the cached user list
slackx cache clear read           # drop every last-read pointer
slackx cache clear all --yes      # wipe every cached entity
```

### conversations read mark

Record that a reader has read a channel or a thread up to a message.

```bash
slackx conversations read mark TARGET [--ts THREAD_TS] [--reader ID] [--last-read TS]
```

| Argument | Description |
|---|---|
| `TARGET` | Slack permalink, channel id (`C001`), bare name (`general`), `#`-prefixed name (`#general`), or DM target (user id or `@handle`). |
| `--ts TS` | Thread root timestamp. When given, the thread marker is advanced instead of the channel marker. |
| `--reader ID` | Reader owning the marker, so several consumers can each track their own (default: `default`) |
| `--last-read TS` | Explicit timestamp to store; defaults to the newest cached message in scope |

Each reader keeps its own independent set of markers. Marking a target with
no cached messages fails unless `--last-read` is given. `conversations get`
advances the same pointers automatically.

### conversations read show

Print stored last-read pointers (human-readable by default).

```bash
slackx conversations read show [--reader ID] [--channel CHANNEL] [--json | --jsonl]
```

| Argument | Description |
|---|---|
| `--reader ID` | Restrict to one reader's pointers (default: every reader) |
| `--channel CHANNEL` | Restrict to one channel (id, name, or `#name`) |
| `--json` | Output as pretty-printed JSON |
| `--jsonl` | Output as a single compact JSON line (mutually exclusive with `--json`) |

Never calls Slack.

### conversations read clear

Delete stored last-read pointers for one reader.

```bash
slackx conversations read clear --reader ID [--channel CHANNEL] [--ts THREAD_TS]
```

| Argument | Description |
|---|---|
| `--reader ID` | Reader whose pointers are deleted (required) |
| `--channel CHANNEL` | Restrict deletion to one channel (id, name, or `#name`) |
| `--ts TS` | Delete just this thread's pointer (requires `--channel`) |

With `--channel` (and no `--ts`) every pointer for that channel is removed; with
neither option every pointer owned by the reader is removed. Never calls
Slack.

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

Without `--db` or `--workspace`, the workspace is resolved from the configured
credentials (one `auth.test`, then remembered), falling back to the last-used
workspace offline.

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
| `Ns` | `30s` | N seconds |
| Combined | `2d5h30m` | 2 days, 5 hours, 30 minutes |
| `all` | `all` | No time limit |
