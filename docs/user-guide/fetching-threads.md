# Fetching threads

## Basic usage

Fetch a Slack thread by providing its permalink URL:

```bash
slackx conversations fetch "https://workspace.slack.com/archives/C01234/p1700000000123456"
```

Or use an explicit channel target and `--ts`:

```bash
slackx conversations fetch C01234 --ts 1700000000.123456
```

The command prints a summary to stderr:

```
cached 8 messages (8 new, full) for C01234/1700000000.123456
```

## Incremental refresh

Running fetch again on the same thread only retrieves new or edited messages:

```bash
# First fetch
slackx conversations fetch "https://workspace.slack.com/archives/C01234/p1700000000123456"
# cached 8 messages (8 new, full)

# Second fetch (only new replies)
slackx conversations fetch "https://workspace.slack.com/archives/C01234/p1700000000123456"
# cached 10 messages (2 new, incremental)
```

## Showing cached threads

Display a thread in human-readable format:

```bash
slackx conversations show "https://workspace.slack.com/archives/C01234/p1700000000123456"
```

Output includes timestamps, author names (resolved from cached users), and message text.

Display as JSON:

```bash
slackx conversations show --json "https://workspace.slack.com/archives/C01234/p1700000000123456"
```

JSON output includes `channel_name` and resolves user IDs to display names when cached users are available.

## Auto-fetch

The `conversations show` command automatically fetches a thread if it is not yet cached. Disable this with `--no-fetch`:

```bash
slackx conversations show --no-fetch "https://workspace.slack.com/archives/C01234/p1700000000123456"
```
