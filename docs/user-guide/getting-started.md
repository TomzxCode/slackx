# Getting started

slackx is a small CLI that caches Slack threads, channel messages, users, and
channels to a local SQLite database, so they can be read, searched, and served
locally.

## Installation

Clone the repository and install dependencies with uv:

```bash
git clone https://github.com/TomzxCode/slackx.git
cd slackx
uv sync
```

Python 3.13 or later is required. The examples below run the CLI through
`uv run`; once the project virtualenv is active
(`source .venv/bin/activate`), the plain `slackx` and `slack-fake-server`
commands work the same way.

## Slack credentials

slackx needs a Slack token to access the API. Two token types are supported:

**Bot token**

Set the `SLACK_TOKEN` environment variable to a bot token starting with `xoxb-`:

```bash
export SLACK_TOKEN=xoxb-your-bot-token
```

**Browser token**

Set both `SLACK_TOKEN` (starting with `xoxc-`) and `SLACK_COOKIE` (the `xoxd-` cookie from the same browser session):

```bash
export SLACK_TOKEN=xoxc-your-browser-token
export SLACK_COOKIE=xoxd-your-d-cookie
```

Alternatively, put the same keys in a config file at `~/.config/slackx/config`:

```
SLACK_TOKEN=xoxb-your-bot-token
SLACK_COOKIE=xoxd-your-d-cookie
```

Environment variables take precedence over the config file. See
[Configuration](configuration.md) for details.

## Quick start

Fetch a Slack thread by pasting its permalink URL:

```bash
uv run slackx conversations fetch "https://workspace.slack.com/archives/C01234/p1700000000123456"
```

Display the cached thread:

```bash
uv run slackx conversations show "https://workspace.slack.com/archives/C01234/p1700000000123456"
```

Fetch all workspace users and channels so messages render with real names:

```bash
uv run slackx users fetch
uv run slackx channels fetch
```

## Cache location

Each Slack workspace caches to its own SQLite database under the XDG cache
directory, e.g. `~/.cache/slackx/<workspace>/threads.db`. The workspace is
discovered with `auth.test` when credentials are configured and remembered on
disk, so later commands reuse the most recently used workspace, even offline.

Select a workspace explicitly, or override the path with `--db`:

```bash
uv run slackx conversations fetch <url> --workspace acme
uv run slackx conversations fetch <url> --db /path/to/custom.db
```

## Next steps

- Fetch [threads](fetching-threads.md) and
  [channel messages](fetching-channel-messages.md).
- [Search messages](searching.md) using Slack's search syntax.
- Browse the cache in a browser with [the web UI](serving.md).
- Track how far each consumer has read with
  [last-read pointers](tracking-last-read.md).
- Every command and flag is listed in the [CLI reference](cli-reference.md).
- No workspace at hand? Point slackx at the bundled
  [fake Slack server](../developer-guide/fake-slack-server.md) and try the CLI
  without credentials.
