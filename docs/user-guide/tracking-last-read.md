# Tracking last read

slackx can remember how far each consumer has read in a channel or a thread.
This is useful when several programs share one cache: a web UI, a poll watcher,
and an ad-hoc script can each keep their own position without overwriting each
other.

Each position is a **read marker**: a pointer from a reader to a timestamp for
one channel or thread.
Every reader has its own independent set of markers.

## Concepts

- **Reader** names the consumer that owns a set of markers (for example `web` or
  `poll`).
  Readers are free-form strings, so you can use one per tool, per user, or per
  device.
- **Channel marker** records that the reader has read a whole channel up to a
  timestamp.
- **Thread marker** records that the reader has read one thread up to a
  timestamp.
  A channel marker and a thread marker for the same channel are separate rows.

The marker's timestamp is the newest message the reader has seen.
When you do not pass an explicit value, slackx uses the newest cached message in
scope: the newest message of the thread for a thread marker, or the newest
message anywhere in the channel for a channel marker.

## Marking read

```bash
slackx conversations read mark C0123ABCDEF --reader web
slackx conversations read mark C0123ABCDEF --ts 1700000000.123456 --reader web
slackx conversations read mark C0123ABCDEF --reader poll --last-read 1700000000.000050
```

| Argument | Description |
|---|---|
| `TARGET` | Slack permalink, channel id (`C001`), bare name (`general`), `#`-prefixed name (`#general`), or DM target (user id or `@handle`). A permalink or `--ts` selects a thread. |
| `--ts TS` | Thread root timestamp. When given, the thread marker is advanced instead of the channel marker. |
| `--reader ID` | Reader owning the marker (default: `default`). |
| `--last-read TS` | Explicit timestamp to store. Defaults to the newest cached message in scope. |

Marking a target with no cached messages fails unless you pass `--last-read`.
Showing a channel or thread with `conversations show` does not need a separate
call: it advances the same pointer for the chosen `--reader` (default
`default`) after printing.

## Showing pointers

```bash
slackx conversations read show
slackx conversations read show --reader web
slackx conversations read show --channel C0123ABCDEF --json
```

With no `--reader`, every reader's pointers are listed.
`--channel` limits output to one channel.
Human-readable output is the default; `--json` and `--jsonl` emit structured
output.

## Clearing pointers

```bash
slackx conversations read clear --reader web --channel C0123ABCDEF
slackx conversations read clear --reader web --channel C0123ABCDEF --ts 1700000000.123456
slackx conversations read clear --reader web
```

Deleting is scoped: `--channel` (without `--ts`) removes every pointer for that
channel, `--channel` with `--ts` removes just that thread's pointer, and neither
removes every pointer owned by the reader.
To drop markers for every reader at once, use `slackx cache clear read`.

## HTTP API

The `serve` web server exposes the same pointers over JSON, so browser-based
consumers can read and write their own markers:

| Method and path | Purpose |
|---|---|
| `GET /api/read?reader=web&channel=C123` | List pointers, optionally filtered. |
| `PUT /api/read` | Create or advance a pointer. Body: `{"reader", "channel", "thread_ts"?, "last_read_ts"?}`; `last_read_ts` defaults to the newest cached message. |
| `DELETE /api/read/{reader}` | Delete all pointers for a reader (optional `?channel=`). |
| `DELETE /api/read/{reader}/{channel}` | Delete the channel-level pointer. |
| `DELETE /api/read/{reader}/{channel}/{thread_ts}` | Delete one thread pointer. |

Read markers are stored in the cache database, so they survive restarts and are
per workspace like the rest of the cache.
