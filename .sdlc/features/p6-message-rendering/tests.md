---
title: "Message rendering"
status: done
session_link: http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ
---

# Test Plan: Message rendering

## Scope

This plan covers the rendering pipeline: Slack mrkdwn conversion, block and attachment rendering, terminal style detection, and the human and JSON renderers for threads, channels, users, channels lists, search, and status.
Unit cases exercise the converter and renderer helpers with constructed data.
Integration cases call the renderers directly.
End-to-end cases invoke the CLI with `cli.main` against a temporary database and capture stdout.
Out of scope are fetching and storage, the web UI, and any test of a terminal emulator's rendering of ANSI codes.

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Bold conversion | `*bold* text` | `[bold]bold[/bold] text` |
| TC-2 | Italic does not match snake_case | `snake_case_word`, `_italic_ text` | snake_case unchanged, italic tagged |
| TC-3 | Strikethrough conversion | `~gone~ text` | `[strike]gone[/strike] text` |
| TC-4 | Inline code is stashed from emphasis | ``use `x_y *z*` here`` | code dim, no bold or italic tags |
| TC-5 | Code fence styles each line | fenced `a*b` block | every line dim, fence markers included |
| TC-6 | Labeled and bare links | `<https://example.com\|the site>`, `<https://example.com>` | `[link=...]` markup |
| TC-7 | User and channel mentions | `<@U123\|alice>`, `<@U123>`, `<#C1\|dev>` | `@alice`, `@U123`, `#dev` |
| TC-8 | Special mentions and date fallback | `<!here>`, `<!channel>`, `<!subteam^S1\|ops>`, `<!date^...\|Feb 18>` | `@here`, `@channel`, `@ops`, `Feb 18` |
| TC-9 | HTML entities decoded | `a &amp; b &lt;c&gt;` | `a & b <c>` |
| TC-10 | Literal brackets and backslash escaped | `array[0]`, `[red]fake[/red]`, `C:\\ *bold*` | brackets escaped, bold still works |
| TC-11 | Styler behavior | disabled, enabled, empty text | unchanged when disabled, ANSI and OSC 8 when enabled, empty stays empty |
| TC-12 | Style detection | TTY, pipe, `NO_COLOR`, `TERM=dumb`, `FORCE_COLOR` values, no stream arg | styled only for a TTY with a color terminal, forced by `FORCE_COLOR` |
| TC-13 | Section block | mrkdwn text, plain text, fields | links clickable when styled, verbatim when plain, one line per field |
| TC-14 | Header, divider, context | header plain text, divider, context elements | `Build`, `---`, elements joined by two spaces |
| TC-15 | Actions block | button with label and url, styled and plain | OSC 8 link when styled, `label (url)` when plain |
| TC-16 | Attachments | title with link, title without link, mrkdwn text | linked title, plain title, mrkdwn body |
| TC-17 | Non-dict entries | `None`, `3`, `"x"` in blocks or attachments | skipped without error |
| TC-18 | Message body assembly | blocks plus text, text only, blocks plus attachments, empty | blocks win, else text, attachments appended, empty yields a blank line |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome |
|---|---|---|---|
| TC-19 | Styled thread render | One message, `styled=True` | Header, author, and timestamp carry ANSI codes |
| TC-20 | Plain thread render | One message, default `styled` | No escape codes, header text present |
| TC-21 | Styled thread renders mrkdwn | Message with bold text and a link | Bold ANSI and OSC 8 link on an indented line |
| TC-22 | Plain thread keeps verbatim text | Message with mrkdwn | Raw `*bold*` and `<url\|link>` present |
| TC-23 | Styled channel render marks replies | Leading message plus a reply | Dim arrow and dim thread root ts present |
| TC-24 | Styled search links the permalink | One match with a permalink | OSC 8 sequence and the permalink url present |
| TC-25 | Styled status render | A `DbStatus` | Counts bold, timestamps italic |
| TC-26 | Thread render shows bot links | Message whose payload holds a section block | Link line indented four spaces |
| TC-27 | Channel render shows bot links plain | Message payload with an attachment title link | `PR #7 (https://git.dev/pr/7)` present |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome |
|---|---|---|---|
| TC-28 | Show a thread human-readable | Populate a temp DB, run `conversations show` | Exit 0, header and messages on stdout |
| TC-29 | Show a thread as JSON | Run `conversations show --json` | Exit 0, valid JSON with the thread keys |
| TC-30 | Show a thread as JSONL | Run `conversations show --jsonl` | Exit 0, one compact JSON line |
| TC-31 | Reject conflicting flags | Run `conversations show --json --jsonl` | Exit 2, error on stderr |
| TC-32 | List users with selected fields | Run `users list --fields id,name` and `--json --fields id,real_name` | Human columns in order, JSON keys in order |
| TC-33 | List channels with visibility | Run `channels list --fields id,is_private` | `(private)` shown for a private channel |
| TC-34 | Show a channel with thread replies | Run `conversations show <channel> --with-thread-message` | Reply marked with its thread root |
| TC-35 | Search output formats | Run `conversations search` human, `--json`, `--jsonl`, and `--fields` | Human lines, valid JSON, one JSONL line, selected fields |
| TC-36 | Resolve author and channel names | Populate users and channels, run show and search | Display names shown instead of ids |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-37 | stdout is not a TTY | Styling disabled, output plain and free of escape codes |
| TC-38 | `NO_COLOR` or `TERM=dumb` on a TTY | Styling disabled |
| TC-39 | `FORCE_COLOR=1` on a non-TTY | Styling enabled |
| TC-40 | Unsupported or literal markup such as `[red]fake[/red]` | Rendered as literal text, no ANSI red, brackets escaped |
| TC-41 | Message with no text and no blocks | Body renders as a single blank line |
| TC-42 | Unknown `--fields` value | Exit code 2, stderr names the unknown field and the available fields |
| TC-43 | Message `ts` that cannot be parsed as a float | Raw `ts` string returned, no exception |
| TC-44 | Malformed block or attachment entry | Entry skipped, remaining entries still render |

## Test Infrastructure

- `tests/test_mrkdwn.py` covers the mrkdwn converter and the styled thread renderer.
- `tests/test_blocks.py` covers block, attachment, and message body rendering.
- `tests/test_style.py` covers `_supports_styles`, `_Styler`, and the styled renderers, using `monkeypatch` for environment variables and a `StringIO` stream with a stubbed `isatty`.
- `tests/test_cli.py` covers the CLI surface with `cli.main`, `tmp_path` databases, and the `capsys` fixture.
- No network is required, the fake Slack API is not used by these tests.
- Styled assertions match ANSI sequences directly (for example `\x1b[1m`, `\x1b]8;`).

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-1 | TC-19, TC-20, TC-21, TC-22, TC-28 |
| FR-2 | TC-23, TC-27, TC-34 |
| FR-3 | TC-32, TC-33 |
| FR-4 | TC-29, TC-35 |
| FR-5 | TC-30, TC-31, TC-35 |
| FR-6 | TC-1, TC-2, TC-3, TC-4, TC-5, TC-6, TC-7, TC-8, TC-9, TC-10, TC-21 |
| FR-7 | TC-13, TC-14, TC-15, TC-16, TC-17, TC-18, TC-26, TC-27 |
| FR-8 | TC-32, TC-33, TC-35, TC-42 |
| FR-9 | TC-24, TC-25 |
| FR-10 | TC-12, TC-37, TC-38, TC-39 |
| FR-11 | TC-36 |
| NFR-1 | TC-19, TC-26, TC-27 (renderers run without a database) |
| NFR-2 | TC-20, TC-22, TC-37 |
| NFR-3 | TC-19, TC-20 (repeated calls on constructed data) |
| NFR-4 | TC-29, TC-30, TC-35 |
| NFR-5 | None, `_format_ts` fallback has no dedicated test (gap) |
