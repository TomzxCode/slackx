# Fetching channel messages

## Basic usage

Fetch all top-level messages from a channel:

```bash
slackx fetch --channel C01234
```

This uses the Slack `conversations.history` API to retrieve top-level messages (standalone messages and thread parents). Thread replies are not included unless you use `--full-threads`.

## Full thread expansion

Add `--full-threads` to also fetch all replies for every threaded conversation found in the channel:

```bash
slackx fetch --channel C01234 --full-threads
```

The summary includes thread expansion stats:

```
cached 42 messages for C01234 (42 fetched, 8 threads with replies fetched)
```

## Time-bounded fetch

Use `--last` to limit the lookback period. Accepts duration strings like `24h`, `2d5h30m`, `90m`, or `all` for full history:

```bash
# Last 3 days
slackx fetch --channel C01234 --last 3d

# Last 2 hours
slackx fetch --channel C01234 --last 2h

# Full history
slackx fetch --channel C01234 --last all
```

The default lookback is `1d` (one day).

## Showing cached channel messages

Display a channel's cached top-level messages:

```bash
slackx show --channel C01234
```

Thread replies are not shown; `show --channel` mirrors the channel as it appears
in Slack. Use `show --channel C01234 --ts <thread_ts>` to read a specific thread.

To include thread replies, pass `--with-thread-message`. Replies are rendered
indented and tagged with the thread they belong to:

```bash
slackx show --channel C01234 --with-thread-message
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
slackx show --channel C01234 --last 7d
```

Display as JSON:

```bash
slackx show --channel C01234 --json
```

Channel messages are auto-fetched if the cache is empty (unless `--no-fetch` is given).
