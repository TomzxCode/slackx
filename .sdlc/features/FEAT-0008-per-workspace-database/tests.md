---
title: "Per-Workspace Cache Database"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Test Plan: Per-Workspace Cache Database

## Scope

Covers workspace name derivation, workspace database path selection, the on-disk credential-name cache, the last-used pointer, offline resolution, and the synchronous `serve` resolution path.
Unit tests exercise `slack_cached.workspace` directly in `tests/test_workspace.py`.
Integration tests drive the CLI resolution precedence through `slack_cached.cli._internal._client` in `tests/test_cli.py`.
End-to-end tests cover the `serve` sync path in `tests/test_cli.py` and the fake server auth.test endpoint in `tests/test_fake_slack.py`.
Out of scope: Slack network behavior, SQLite storage internals, and the web UI.

## Unit Tests

| ID | Description | Input | Expected Output | Real test |
|---|---|---|---|---|
| TC-1 | Sanitize replaces unsafe characters in a workspace name | `sanitize_workspace_name("acme corp!")` | `acme_corp_` | `TestWorkspaceName::test_sanitize_replaces_unsafe_characters` |
| TC-2 | Sanitize falls back when the result is empty | `sanitize_workspace_name("...")` and `sanitize_workspace_name("")` | `workspace` | `TestWorkspaceName::test_sanitize_falls_back_when_empty` |
| TC-3 | Name from auth prefers the URL subdomain | `{"url": "https://acme.slack.com/", "team_id": "T123"}` | `acme` | `TestWorkspaceName::test_name_from_auth_prefers_url_subdomain` |
| TC-4 | Name from auth falls back to the team id | `{"team_id": "T123"}` | `T123` | `TestWorkspaceName::test_name_from_auth_falls_back_to_team_id` |
| TC-5 | Name from auth has a generic fallback | `{}` | `workspace` | `TestWorkspaceName::test_name_from_auth_generic_fallback` |
| TC-6 | Workspace database path sits in a per-workspace directory | `workspace_db_path("acme")` | parent name `acme`, file name `DEFAULT_DB_NAME` | `TestWorkspaceDbPath::test_path_is_per_workspace_directory` |
| TC-7 | Remember then read the last-used workspace | `claim_workspace_db("acme")` | `last_workspace()` returns `acme` | `TestWorkspaceDbPath::test_remember_and_read_last_workspace` |
| TC-8 | Claim remembers the workspace and returns its path | `claim_workspace_db("acme")` | path equals `workspace_db_path("acme")` and `last_workspace()` returns `acme` | `TestClaimWorkspaceDb::test_remembers_workspace_and_returns_path` |
| TC-9 | Claim never migrates the legacy database | a pre-existing legacy database | the legacy database still exists and the workspace database does not | `TestClaimWorkspaceDb::test_does_not_migrate_legacy_db` |
| TC-10 | Offline resolution prefers the last-used workspace | alpha and beta databases, beta claimed | `offline_db_path()` returns `workspace_db_path("beta")` | `TestOfflineResolution::test_prefers_last_used_workspace` |
| TC-11 | Offline resolution uses the only existing workspace | only an alpha database | `offline_db_path()` returns `workspace_db_path("alpha")` | `TestOfflineResolution::test_uses_single_existing_workspace` |
| TC-12 | Offline resolution falls back to the legacy database | only a legacy database | `offline_db_path()` returns `legacy_db_path()` | `TestOfflineResolution::test_falls_back_to_legacy_db_path` |

## Integration Tests

| ID | Description | Preconditions | Expected Outcome | Real test |
|---|---|---|---|---|
| TC-13 | Fetch lands in the workspace directory | `XDG_CACHE_HOME` points at a temp dir and a stubbed client returns `url: https://acme.slack.com/` | `slackx/acme/threads.db` exists and `last_workspace` holds `acme` | `test_fetch_targets_workspace_directory` |
| TC-14 | Offline show reads the last-used workspace | a prior fetch, then `_build_client` is replaced with a failing stub | `conversations show --no-fetch` exits 0 and prints `hello` without building a client | `test_show_reads_last_workspace_offline` |
| TC-15 | `--workspace` selects the database without auth.test | a stubbed client whose `auth_test` raises | `slackx/beta/threads.db` exists and `last_workspace` holds `beta` | `test_workspace_flag_selects_database` |
| TC-16 | auth.test runs once per credential set | a counting client driven over two fetches | auth.test runs once and `workspace_names.json` holds one entry whose value is `acme` | `test_auth_test_runs_once_per_credentials` |
| TC-17 | Ambiguous workspaces make the CLI fail | alpha and beta databases exist and no pointer is recorded | `conversations show --no-fetch` raises `SystemExit` matching `alpha, beta` | `test_show_requires_workspace_when_ambiguous` |

## End-to-End Tests

| ID | Description | Steps | Expected Outcome | Real test |
|---|---|---|---|---|
| TC-18 | serve sync resolution uses credentials | set token and cookie, call `_resolve_db_path_sync` on a cache miss, then again on a cache hit | both calls return `workspace_db_path("acme")`, and the cache hit builds no client | `test_serve_sync_resolution_uses_credentials` |
| TC-19 | serve sync resolution falls back offline without credentials | clear the token and call `_resolve_db_path_sync` | it returns `offline_db_path()` | `test_serve_sync_resolution_without_credentials_falls_back_offline` |
| TC-20 | Fake server exposes auth.test | GET `/api/auth.test` | `ok` is true, `team_id` is `T01FAKEWK`, and `url` is `https://fake.slack.com/` | `TestAuthTest::test_returns_workspace_identity` |
| TC-21 | Fake server user matches the generated workspace | GET `/api/auth.test` and `/api/users.list` | the auth user id equals the first listed member id | `TestAuthTest::test_user_matches_generated_workspace` |

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior | Real test |
|---|---|---|---|
| TC-22 | Multiple workspace databases and no last-used pointer at the module level | `offline_db_path()` raises `SystemExit` listing `alpha, beta` | `TestOfflineResolution::test_ambiguous_workspaces_require_explicit_choice` |
| TC-23 | Multiple workspace databases and no last-used pointer through the CLI | `conversations show --no-fetch` raises `SystemExit` listing `alpha, beta` | `test_show_requires_workspace_when_ambiguous` |
| TC-24 | Empty cache directory | `offline_db_path()` returns the legacy default path | `TestOfflineResolution::test_defaults_to_legacy_db_path_when_empty` |
| TC-25 | Unsafe or empty workspace name | the name is sanitized to a safe directory name, falling back to `workspace` | `TestWorkspaceName::test_sanitize_replaces_unsafe_characters`, `TestWorkspaceName::test_sanitize_falls_back_when_empty` |

## Test Infrastructure

- A `tmp_path` cache root with an autouse `_cache_dir` fixture that sets `XDG_CACHE_HOME` in `tests/test_workspace.py`.
- `monkeypatch.setenv` for `XDG_CACHE_HOME`, `XDG_CONFIG_HOME`, `SLACK_TOKEN`, and `SLACK_COOKIE` in `tests/test_cli.py`.
- Stubbed Slack clients injected with `monkeypatch.setattr(cli._internal._client, "_build_client", ...)`, including the `_stub_workspace_client` helper.
- `slack_cached.storage.connect` creates the workspace and legacy databases the resolution tests need to exist.
- The `fake_server` fixture in `tests/test_fake_slack.py` serves the auth.test endpoint.
- `pytest.raises(SystemExit, match=...)` asserts the ambiguity failure message.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-01 | TC-6, TC-8, TC-13 |
| FR-02 | TC-3, TC-4, TC-5, TC-13 |
| FR-03 | TC-7, TC-10, TC-14 |
| FR-04 | TC-15 |
| FR-05 | No dedicated test; `--db` is exercised throughout `tests/test_cli.py` |
| FR-06 | TC-22, TC-23 |
| FR-07 | TC-9 |
| FR-08 | TC-12, TC-24 |
| FR-09 | TC-20, TC-21 |
| NFR-01 | TC-6, TC-9, TC-13 |
| NFR-02 | TC-14 |
| NFR-03 | TC-16, TC-18 |
