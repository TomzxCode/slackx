# Configuration

## Credentials

Slack credentials can be provided through environment variables or a config file.

### Environment variables

```bash
export SLACK_TOKEN=xoxb-your-bot-token
```

For browser tokens, also set the cookie:

```bash
export SLACK_TOKEN=xoxc-your-browser-token
export SLACK_COOKIE=xoxd-your-d-cookie
```

### Config file

Create `~/.config/slackx/config` (or `$XDG_CONFIG_HOME/slackx/config`):

```
SLACK_TOKEN=xoxb-your-bot-token
SLACK_COOKIE=xoxd-your-d-cookie
```

Environment variables take precedence over the config file.

### Token types

| Token type | Prefix | Cookie required |
|---|---|---|
| Bot token | `xoxb-` | No |
| Browser token | `xoxc-` | Yes (`xoxd-`) |

## API base URL

Override the Slack API base URL to point at a fake server or custom endpoint:

```bash
# Via CLI flag
slackx conversations fetch <url> --api-base-url http://localhost:8199/api

# Via environment variable
export SLACK_API_BASE_URL=http://localhost:8199/api

# Via config file
echo "SLACK_API_BASE_URL=http://localhost:8199/api" >> ~/.config/slackx/config
```

When `--api-base-url` points to a non-default server, credentials are optional.

## Database path

Each Slack workspace caches to its own database under the XDG cache
directory, so ids and timestamps from different workspaces never mix:

| Platform | Default path |
|---|---|
| Linux | `~/.cache/slackx/<workspace>/threads.db` |
| Linux (XDG) | `$XDG_CACHE_HOME/slackx/<workspace>/threads.db` |

The workspace name comes from `auth.test`: the URL subdomain (`acme` in
`https://acme.slack.com/`), falling back to the team id. The name is
remembered per credential set, so `auth.test` runs once; afterwards commands
reuse the most recently used workspace, including offline. When several
workspace caches exist and no last-used workspace is recorded, slackx asks
for `--workspace`.

Select a workspace explicitly, or place the database outside the
per-workspace layout with `--db`:

```bash
slackx conversations fetch <url> --workspace acme
slackx conversations fetch <url> --db /path/to/custom.db
```

`--db` takes precedence over the per-workspace layout. An existing
pre-workspace `~/.cache/slackx/threads.db` is left in place and used as an
offline fallback while no workspace cache exists yet.

## Log level

Control logging verbosity with `--log-level` (`debug`, `info`, `warning`,
`error`, or `critical`; default: `info`):

```bash
slackx conversations fetch --log-level debug <url>
```

At `debug`, this outputs SQL query timings, API request details, and other
diagnostic information to stderr.
