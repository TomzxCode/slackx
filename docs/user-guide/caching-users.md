# Caching users

## Fetching users

Download all workspace members to the local cache:

```bash
slackx users fetch
```

The command prints a summary to stderr:

```
processed 150 users (150 added, 150 total in db)
```

Running it again updates existing records without duplication (upsert by user ID).

Pass a user id to fetch just that user with a single `users.info` call:

```bash
slackx users fetch U001
```

## Showing cached users

Display all cached users in human-readable format:

```bash
slackx users list
```

Display as JSON:

```bash
slackx users list --json
```

Users are auto-fetched if the cache is empty (unless `--no-fetch` is given).

Pass a user id to show just that user; a cache miss fetches it with a single
`users.info` call:

```bash
slackx users list U001 --json
```

## Display name resolution

When users are cached, thread and channel output resolves user IDs to display names in the format "Real Name (handle)". For example, a message from user `U123` appears as:

```
[2024-01-15 10:30:00] Alice Smith (alice)
  Hey, I've reviewed the PR.
```

Without cached users, the raw user ID is shown instead.
