# Tracking last read

slackx can remember how far each consumer has read in a channel or a thread.
This is useful when several programs share one cache: a web UI, a poll watcher,
and an ad-hoc script can each keep their own position without overwriting each
other.

Each position is a **read marker**: a pointer from a consumer identifier to a
timestamp for one channel or thread.
Every identifier has its own independent set of markers.

## Concepts

- **Identifier** names the consumer that owns a set of markers (for example
  `web` or `poll`).
  Identifiers are free-form strings, so you can use one per tool, per user, or
  per device.
- **Channel marker** records that the consumer has read a whole channel up to a
  timestamp.
- **Thread marker** records that the consumer has read one thread up to a
  timestamp.
  A channel marker and a thread marker for the same channel are separate rows.

The marker's timestamp is the newest message the consumer has seen.
When you do not pass an explicit value, slackx uses the newest cached message in
scope: the newest message of the thread for a thread marker, or the newest
message anywhere in the channel for a channel marker.

## Marking read

```bash
slackx read mark C0123ABCDEF --identifier web
slackx read mark C0123ABCDEF --ts 1700000000.123456 --identifier web
slackx read mark C0123ABCDEF --identifier poll --last-read 1700000000.000050
```

| Argument | Description |
|---|---|
| `TARGET` | Slack permalink, channel id (`C001`), bare name (`general`), `#`-prefixed name (`#general`), or DM target (user id or `@handle`). A permalink or `--ts` selects a thread. |
| `--ts TS` | Thread root timestamp. When given, the thread marker is advanced instead of the channel marker. |
| `--identifier ID` | Consumer owning the marker (default: `default`). |
| `--last-read TS` | Explicit timestamp to store. Defaults to the newest cached message in scope. |

Marking a target with no cached messages fails unless you pass `--last-read`.

## Showing pointers

```bash
slackx read show
slackx read show --identifier web
slackx read show --channel C0123ABCDEF --json
```

With no `--identifier`, every consumer's pointers are listed.
`--channel` limits output to one channel.
Human-readable output is the default; `--json` and `--jsonl` emit structured
output.

## Clearing pointers

```bash
slackx read clear --identifier web --channel C0123ABCDEF
slackx read clear --identifier web --channel C0123ABCDEF --ts 1700000000.123456
slackx read clear --identifier web
```

Deleting is scoped: `--channel` (without `--ts`) removes every pointer for that
channel, `--channel` with `--ts` removes just that thread's pointer, and neither
removes every pointer owned by the identifier.
To drop markers for every identifier at once, use `slackx cache clear read`.

## HTTP API

The `serve` web server exposes the same pointers over JSON, so browser-based
consumers can read and write their own markers:

| Method and path | Purpose |
|---|---|
| `GET /api/read?identifier=web&channel=C123` | List pointers, optionally filtered. |
| `PUT /api/read` | Create or advance a pointer. Body: `{"identifier", "channel", "thread_ts"?, "last_read_ts"?}`; `last_read_ts` defaults to the newest cached message. |
| `DELETE /api/read/{identifier}` | Delete all pointers for an identifier (optional `?channel=`). |
| `DELETE /api/read/{identifier}/{channel}` | Delete the channel-level pointer. |
| `DELETE /api/read/{identifier}/{channel}/{thread_ts}` | Delete one thread pointer. |

Read markers are stored in the cache database, so they survive restarts and are
per workspace like the rest of the cache.
