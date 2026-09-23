# Caching channels

## Fetching channels

Download all visible conversations (public channels, private channels, MPIMs, and DMs) to the local cache:

```bash
slackx channels fetch
```

The command prints a summary to stderr:

```
processed 45 channels (45 added, 45 total in db)
```

Running it again updates existing records without duplication.

Pass a channel id (or a cached name) to fetch just that channel with a single
`conversations.info` call:

```bash
slackx channels fetch C001
```

## Showing cached channels

Display all cached channels in human-readable format:

```bash
slackx channels list
```

Output shows channel ID, name, and visibility (public/private).

Display as JSON:

```bash
slackx channels list --json
```

Channels are auto-fetched if the cache is empty (unless `--no-fetch` is given).

## Showing a single channel

Pass a channel id (or a cached name) to show just that channel:

```bash
slackx channels list C001
slackx channels list C001 --json --fields id,name,is_private
```

When the channel is not cached, it is fetched from Slack with a single
`conversations.info` call (unless `--no-fetch` is given). An unknown channel
exits non-zero with an error.
