# Fetching channel messages

## Basic usage

Fetch all top-level messages from a channel:

```bash
slackx conversations fetch C01234
```

This uses the Slack `conversations.history` API to retrieve top-level messages (standalone messages and thread parents). Thread replies are not included unless you use `--full-threads`.

## Full thread expansion

Add `--full-threads` to also fetch all replies for every threaded conversation found in the channel:

```bash
slackx conversations fetch C01234 --full-threads
```

The summary includes thread expansion stats:

```
cached 42 messages for C01234 (42 fetched, 8 threads with replies fetched)
```

## Time-bounded fetch

Use `--last` to limit the lookback period. Accepts duration strings like `24h`, `2d5h30m`, `90m`, or `all` for full history:

```bash
# Last 3 days
slackx conversations fetch C01234 --last 3d

# Last 2 hours
slackx conversations fetch C01234 --last 2h

# Full history
slackx conversations fetch C01234 --last all
```

The default lookback is `1d` (one day).

## Showing cached channel messages

Display a channel's cached top-level messages:

```bash
slackx conversations get C01234
```

Thread replies are not shown; `conversations get` mirrors the channel as it appears
in Slack. Use `conversations get C01234 --ts <thread_ts>` to read a specific thread.

To include thread replies, pass `--with-thread-message`. Replies are rendered
indented and tagged with the thread they belong to:

```bash
slackx conversations get C01234 --with-thread-message
```

```
Channel general
3 message(s) (1 thread replie(s))

[2023-11-14T22:13:20+00:00] Alice
    parent

    ↳ [2023-11-14T22:15:00+00:00] Bob (thread 1700000000.000100)
        reply

[2023-11-14T22:16:40+00:00] Carol
    standalone
```

In JSON output each message carries `thread_ts` and an `is_thread_reply` flag.

Filter by time with `--last`:

```bash
slackx conversations get C01234 --last 7d
```

`--last` bounds both the Slack fetch and what is printed: a message cached by an
earlier wider fetch (for example `conversations fetch --last all`, a search, or a
previous `--last 30d`) is hidden when it falls outside the window. The default is
`1d`, so pass `--last all` to see everything in the cache. When the window is empty
but older messages are cached, `slackx` logs `channel_window_empty` to stderr; use
`--fetch` to load the window from Slack.

Display as JSON:

```bash
slackx conversations get C01234 --json
```

Channel messages are auto-fetched if the cache is empty (unless `--no-fetch` is given). `--fetch` refreshes an already-cached channel before printing. With `--no-fetch` the channel itself is never fetched, but resolving a channel by name still fetches the channel list when the channel cache is empty; use a channel id to guarantee no Slack calls.
