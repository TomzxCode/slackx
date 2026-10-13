---
title: "Message rendering"
status: done
session_link: http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ
---

# Requirements: Message rendering

## Overview

Render cached Slack data to stdout for both people and scripts.
Human-readable output is styled on a terminal and plain when piped.
Machine output is JSON or JSONL.
Rendering covers threads, channel message lists, users, channels, and search matches, and converts Slack markup, layout blocks, and attachments into readable text.

## Stakeholders

| Stakeholder | Interest |
|---|---|
| CLI user | Wants to read cached threads, channels, users, and channels lists without opening Slack |
| Script author | Needs stable JSON or JSONL output and unchanged text when output is piped |
| Developer | Wants renderers kept as pure functions that are easy to test |

## Functional Requirements

Order rows by priority: Must first, then Should, then May.

| ID | Priority | Requirement |
|---|---|---|
| FR-1 | Must | The system shall render a thread as human-readable text with a header, a message count, and one timestamp, author, and message body per message |
| FR-2 | Must | The system shall render a channel message list as human-readable text, marking thread replies with their thread root |
| FR-3 | Must | The system shall render users and channels lists as human-readable text with the selected fields |
| FR-4 | Must | The system shall render a thread, channel message list, search result set, users list, or channels list as pretty-printed JSON when `--json` is passed |
| FR-5 | Must | The system shall render the same data as a single compact JSON line when `--jsonl` is passed, and shall reject `--json` combined with `--jsonl` with exit code 2 |
| FR-6 | Must | The system shall render Slack mrkdwn (bold, italics, strikethrough, inline code, code fences, links, user, channel, and special mentions, HTML entities, and date fallbacks) when styling is enabled |
| FR-7 | Must | The system shall render message layout blocks (section, header, divider, context, actions) and attachments, preferring blocks over the plain `text` field and appending attachments below |
| FR-8 | Should | The system shall select and order rendered fields from `--fields` and shall reject an unknown field with a non-zero exit and a message naming the available fields |
| FR-9 | Should | The system shall render permalinks as OSC 8 hyperlinks and timestamps as ISO 8601 when styling is enabled |
| FR-10 | Must | The system shall disable styling when stdout is not a TTY, when `NO_COLOR` is set, or when `TERM` is unset or `dumb`, and shall force styling on when `FORCE_COLOR` is set to a non-zero value |
| FR-11 | Should | The system shall resolve cached user ids to display names in human output and add a `user_name` field to JSON message records when the name is known |

## Non-Functional Requirements

Order rows by priority: Must first, then Should, then May.

| ID | Priority | Category | Requirement |
|---|---|---|---|
| NFR-1 | Should | Performance | Rendering shall run in memory and scale linearly with the number of messages, with no I/O during rendering |
| NFR-2 | Must | Portability | Piped or redirected output shall be plain text with the raw message markup unchanged, so scripts see stable bytes |
| NFR-3 | Must | Maintainability | Human and JSON renderers shall be pure functions that take loaded data and return a string, independent of argument parsing and I/O |
| NFR-4 | Should | Usability | JSON and JSONL output shall always be parseable, with a trailing newline and `ensure_ascii=False` |
| NFR-5 | Should | Reliability | An unparseable `ts` value shall fall back to the raw string instead of raising |

## Constraints

- Renderers write to stdout only, they do not query the database or the network.
- Styling is delegated to `rich`, and ANSI codes are emitted only when styling is enabled.
- The mrkdwn conversion is best-effort and line-local, no construct spans a newline.
- JSON output is generated with `ensure_ascii=False` and a trailing newline.

## Acceptance Criteria

Every FR and NFR shall have at least one acceptance criterion.

Order criteria by FRs first (sorted by ID), then NFRs (sorted by ID).

Acceptance criteria verify how a requirement is proven done, they do not restate it.
Write concrete, scenario-based criteria (happy path, edge cases and error states where applicable).
Write each criterion as a fenced `gherkin` block with a tag matching its requirement ID, so the criteria are parseable and later executable via BDD tooling (pytest-bdd, cucumber).
Multiple scenarios per requirement are allowed; tag each with the requirement ID.

- [ ] **FR-1**

    ```gherkin
    @FR-1
    Scenario: Show a cached thread as human-readable text
      Given a cached thread with two messages
      When the user runs conversations show for that thread
      Then stdout starts with a "Thread CHANNEL/THREAD_TS" header line
      And stdout lists each message with its ISO timestamp and author
    ```

- [ ] **FR-2**

    ```gherkin
    @FR-2
    Scenario: Show a channel with a thread reply
      Given a cached channel with one top-level message and one thread reply
      When the user runs conversations show for that channel with --with-thread-message
      Then the top-level message is indented as a normal message
      And the reply is marked with an arrow and its thread root ts
    ```

- [ ] **FR-3**

    ```gherkin
    @FR-3
    Scenario: List cached users and channels
      Given cached users and channels
      When the user runs users list and channels list
      Then each user is printed as id, name, and real_name joined by two spaces
      And each channel is printed as id, name, and visibility
    ```

- [ ] **FR-4**

    ```gherkin
    @FR-4
    Scenario: Emit pretty-printed JSON
      Given a cached thread
      When the user runs conversations show --json
      Then stdout is valid JSON with channel, channel_name, thread_ts, message_count, and messages keys
      And the JSON is indented by two spaces
    ```

- [ ] **FR-5**

    ```gherkin
    @FR-5
    Scenario: Emit JSONL and reject conflicting flags
      Given a cached users list
      When the user runs users list --jsonl
      Then stdout is a single JSON line with no newline inside the payload
      When the user runs users list --json --jsonl
      Then the command exits with code 2 and prints an error to stderr
    ```

- [ ] **FR-6**

    ```gherkin
    @FR-6
    Scenario: Render Slack markup with styling enabled
      Given a message with the text "*bold* _italic_ ~strike~ `code` <https://x.com|link> <@U1>"
      When the styled thread renderer runs
      Then bold, italic, and strikethrough fragments carry the matching ANSI codes
      And the link becomes an OSC 8 hyperlink
      And the mention renders as "@U1"
    ```

- [ ] **FR-7**

    ```gherkin
    @FR-7
    Scenario: Prefer blocks and append attachments
      Given a message with blocks and an attachment and a plain text fallback
      When the message body is rendered
      Then the blocks are rendered instead of the text
      And the attachment title or text appears after the blocks
    ```

- [ ] **FR-8**

    ```gherkin
    @FR-8
    Scenario: Select and reject fields
      Given a cached users list
      When the user runs users list --fields id,name
      Then only the id and name columns are printed in that order
      When the user runs users list --fields bogus
      Then the command exits with code 2 and stderr names the unknown field
    ```

- [ ] **FR-9**

    ```gherkin
    @FR-9
    Scenario: Styled permalink and timestamp
      Given a search match with a permalink
      When the styled search renderer runs
      Then the permalink is wrapped in an OSC 8 sequence
      And the timestamp is rendered as an ISO 8601 string
    ```

- [ ] **FR-10**

    ```gherkin
    @FR-10
    Scenario: Detect when styling applies
      Given a stream that is not a TTY and no color environment variables
      When style support is checked
      Then styling is disabled
      Given `NO_COLOR` or `TERM=dumb` is set on a TTY
      Then styling is disabled
      Given `FORCE_COLOR=1` is set on a non-TTY
      Then styling is enabled
    ```

- [ ] **FR-11**

    ```gherkin
    @FR-11
    Scenario: Resolve author display names
      Given a cached message whose author id has a cached display name
      When the thread is rendered as human text and as JSON
      Then the human output shows the display name instead of the id
      And each JSON message carries a user_name field
    ```

- [ ] **NFR-1**

    ```gherkin
    @NFR-1
    Scenario: Render without I/O
      Given a list of already-loaded messages
      When a renderer is called
      Then it returns a string without opening a database or network connection
    ```

- [ ] **NFR-2**

    ```gherkin
    @NFR-2
    Scenario: Keep piped output plain
      Given stdout is not a TTY
      When a thread is rendered with styling disabled
      Then the output contains no ANSI escape codes
      And the raw mrkdwn text is unchanged
    ```

- [ ] **NFR-3**

    ```gherkin
    @NFR-3
    Scenario: Keep renderers pure
      Given the same input data and styling flag
      When a renderer is called twice
      Then it returns the same string both times
    ```

- [ ] **NFR-4**

    ```gherkin
    @NFR-4
    Scenario: Emit parseable JSON
      Given any rendered JSON or JSONL output
      When the output is parsed with a JSON parser
      Then parsing succeeds
      And non-ASCII characters are preserved rather than escaped
    ```

- [ ] **NFR-5**

    ```gherkin
    @NFR-5
    Scenario: Fall back on an unparseable timestamp
      Given a message whose ts is not a number
      When the timestamp is formatted
      Then the raw ts string is returned
    ```

## Conflicts

None identified yet.

## Open Questions

1. Should a `--color` flag force styling independently of the environment variables?
2. Should additional block types (for example image, rich_text, or file) render beyond the supported set?
