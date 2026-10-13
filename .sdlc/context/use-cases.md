<!-- session_link: http://localhost:10000/?session=ses_ecc525c60ffe8kz2Dfu8Dom3Pz -->
# Use Cases

<!--
This file records what people and systems do with the project, so requirements,
specifications, and prioritization can reason about the actors and goals behind
a change. Each entry names the actor, the goal, and how the project serves it
today. Keep IDs stable: reuse an existing UC-N for the same use case, and only
add a new one for a genuinely new use case. Put not-yet-built use cases under
"Wanted", each with a signal (an issue, feature, or roadmap item). Record
deliberate non-goals under "Out of scope".
-->

Actors are the developer or researcher who runs the CLI (the primary user), other local programs that share one cache (cache consumers), and contributors who build and test the tool.
Each entry is a goal an actor has for using the tool, not an operation the tool exposes.

## Supported

| ID | Use case | Actor | Description |
|---|---|---|---|
| UC-1 | Keep a local, offline copy of Slack conversations | Developer / researcher | Cache threads (by permalink or channel id and timestamp), a channel's message history, and the workspace's users and channels into a per-workspace SQLite database, refreshing incrementally so only new replies and edits are fetched. |
| UC-2 | Read a Slack conversation without Slack | Developer / researcher | Read a cached thread or channel offline, with replies, rendered blocks and attachments, and author names resolved from the cached user directory. |
| UC-3 | Find messages across the workspace | Developer / researcher | Search with the Slack search syntax and cache each match so it can be revisited offline. |
| UC-4 | Watch channels for new messages | Developer / researcher | Poll several channels concurrently and surface new messages as they arrive. |
| UC-5 | Browse the whole cached workspace in a UI | Developer / researcher | Serve a local Slack-like web UI to read channels and threads and full-text search every cached message. |
| UC-6 | Share one cache across programs | Cache consumer (other local program) | Keep an independent read position per consumer, so several local programs read the same cache without overwriting each other's place. |
| UC-7 | Develop and test without a live workspace | Contributor | Run the built-in fake Slack server with deterministic data and point the CLI at it. |

Operational capabilities the tool also offers (credential setup, `cache status`, `cache clear`, and direct listing of cached users and channels) are recorded in `project-overview.md` scope.
They support the goals above rather than being goals themselves.

## Wanted

None recorded.
No goals, roadmap, or open issues currently capture an unbuilt use case.

## Out of scope

- Writing or sending messages to Slack
- Real-time event streaming (Socket Mode, Events API)
- Simultaneous multi-token management (one set of credentials is configured at a time)
- A hosted or multi-user production web service
- Caching files, attachments, or reactions
- Analytics, telemetry, metrics, tracing, or dashboards
