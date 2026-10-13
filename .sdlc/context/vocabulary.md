<!-- session_link: http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ -->
# Vocabulary

<!--
This file defines domain-specific terms, acronyms, and abbreviations used across
the project. Keeping definitions here avoids ambiguity in requirements, specs,
and discussions. Add new terms as they are introduced.

Terms within each table are sorted alphabetically by the first column.
-->

## Domain Terms

| Term | Definition |
|---|---|
| channel | A Slack conversation (public channel, private channel, MPIM, or DM) |
| channel type (im/mpim) | Slack's classification of a conversation surfaced in API payloads as is_im or is_mpim, used to tell DMs and group DMs apart from channels |
| conversation | Slack's unified term for channels, DMs, and group messages (used in API endpoint names) |
| deleted-message marking | Setting deleted: true in a cached message's payload when Slack omits it from a history response, rather than removing the row, so the UI can flag it |
| fake server | Local HTTP server (the fake_slack package, also run as the slack-fake-server console script) that mimics the Slack Web API for testing |
| incremental fetch | A refresh that passes `oldest` to the API to only get new/edited messages |
| permalink | A Slack URL in the form https://workspace.slack.com/archives/CHANNEL/pXXXXXXXXXXXXXXXX |
| poll cycle | One pass of conversations poll that fetches new messages for every listed channel, then waits for the interval before the next pass |
| read marker / last-read pointer | A stored position marking how far a consumer has read in a channel or thread |
| reader (consumer) | A label (default "default", for example "web") naming the consumer that owns an independent set of read markers |
| thread | A Slack conversation thread, identified by a channel id and root message timestamp |
| upsert | INSERT OR REPLACE SQLite operation that inserts new rows or replaces existing ones |
| workspace | A Slack workspace containing users, channels, and messages |

## Technical Terms

| Term | Definition |
|---|---|
| `--full-threads` | CLI flag on conversations fetch, search, and poll (and the web API) that also fetches every reply thread for each message with replies, not only top-level messages |
| `--jsonl` | CLI flag that writes one compact JSON object per line for appending to a .jsonl file or piping, mutually exclusive with `--json` |
| `--reader` | CLI flag on conversations show and conversations read mark that names the read pointer's owner, so several consumers can track their own last-read position |
| `--with-thread-message` | CLI flag on conversations show that includes thread replies in the rendered output, not only top-level messages |
| auth.test | Slack API endpoint that returns the caller's identity: team id, team name, user id, and workspace URL |
| CachedChannel | Dataclass representing a stored channel with id, name, is_private, fetched_at, and payload fields |
| CachedMessage | Dataclass representing a stored message with ts, user, text, and payload fields |
| CachedUser | Dataclass representing a stored user with id, name, real_name, fetched_at, and payload fields |
| ChannelFetchResult | Frozen dataclass holding channel fetch statistics (channel, fetched_messages, total_messages, threads_with_replies_fetched, deleted_messages) |
| ChannelMessage | Dataclass representing a channel message row with ts, user, text, payload, reply_count, and latest_reply_ts |
| ChannelSummary | Dataclass holding per-channel aggregate counts (id, name, is_private, message_count, thread_count, latest_ts) for listing |
| chat.postMessage | Slack API endpoint that sends a message to a channel or thread |
| cli/_internal | Package of shared CLI plumbing: command app and groups, DB and client resolution, rendering, and field helpers |
| cli/commands | Package holding one module per CLI command, for example conversations_fetch, users_list, read_mark |
| conversations.history | Slack API endpoint that returns top-level messages in a channel |
| conversations.info | Slack API endpoint that returns a single conversation's metadata |
| conversations.list | Slack API endpoint that returns all visible conversations/channels |
| conversations.replies | Slack API endpoint that returns all replies in a thread |
| Credentials | Frozen dataclass holding a Slack token and optional d cookie |
| cursor | Opaque pagination token returned by Slack APIs for fetching the next page of results |
| d cookie | The xoxd- cookie value paired with an xoxc- token for browser-style authentication |
| DbStatus | Dataclass reporting cache totals and last-update times (channel, user, thread, message, and read marker counts) |
| fake_slack | Package implementing the standalone fake Slack Web API server for testing |
| FetchResult | Frozen dataclass holding thread fetch statistics (channel, thread_ts, fetched_messages, total_messages, incremental) |
| FTS5 | SQLite full-text search extension backing the messages_fts virtual table over messages.text |
| last-workspace pointer | File at `~/.cache/slackx/last_workspace` recording the most recently used workspace so read-only commands can resolve their database offline |
| ListFetchResult | Dataclass holding list fetch statistics (processed, added, total) for user and channel list fetches |
| RateLimitState / rate limit bucket | Shared tracker of Slack rate limit headers per endpoint, used to throttle proactively when a bucket is nearly exhausted instead of waiting for HTTP 429 responses |
| ReadMarker | Dataclass holding a consumer's read position (reader, channel, thread_ts, last_read_ts, updated_at) |
| search.messages | Slack API endpoint that searches messages matching a query |
| SearchFetchResult | Dataclass holding search fetch statistics (query, matches, threads_seen, threads_new, messages_seen, messages_new) |
| SearchHit | Dataclass holding a search match with channel, thread_ts, ts, user, text, and snippet |
| server | FastAPI package exposing the cache as a JSON API (for example /api/channels, /api/search, /api/read) and static web UI, served by the serve command |
| ThreadRef | Internal dataclass holding a channel id and thread_ts pair |
| ThreadState | Dataclass tracking the fetch state of a thread (latest_reply, last_fetched) |
| ts | Slack timestamp string in epoch seconds with microseconds, e.g. "1700000000.123456" |
| users.info | Slack API endpoint that returns a single user's profile |
| users.list | Slack API endpoint that returns all workspace members |
| workspace database | The per-workspace SQLite cache under `~/.cache/slackx`, one `threads.db` per workspace name |
| workspace name | Identifier for a workspace's cache directory: the URL subdomain from auth.test (e.g. `acme` from `acme.slack.com`), falling back to the team id |
| workspace name cache | File at `~/.cache/slackx/workspace_names.json` mapping hashed credentials (token plus API base URL) to workspace names, avoiding repeated auth.test calls |
| XDG base directory | freedesktop.org specification for config, cache, and data file locations |
| xoxb token | A Slack bot token starting with "xoxb-", requiring only an Authorization header |
| xoxc token | A Slack browser/web-client token starting with "xoxc-", also requiring its matching xoxd d cookie |

## Acronyms and Abbreviations

| Abbreviation | Expansion |
|---|---|
| API | Application Programming Interface |
| CLI | Command Line Interface |
| DM | Direct Message (Slack 1:1 conversation) |
| FR | Functional Requirement |
| FTS5 | Full Text Search version 5 (SQLite extension) |
| HTTP | Hypertext Transfer Protocol |
| JSON | JavaScript Object Notation |
| JSONL | JSON Lines (one JSON value per line) |
| MPIM | Multi-Party Instant Message (Slack group DM) |
| NFR | Non-Functional Requirement |
| RNG | Random Number Generator |
| SQL | Structured Query Language |
| XDG | X Desktop Group (the freedesktop.org base directory spec) |
