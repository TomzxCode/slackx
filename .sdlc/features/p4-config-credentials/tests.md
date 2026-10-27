---
title: "Configuration and Credential Management"
status: done
session_link: "http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ"
---

# Test Plan: Configuration and Credential Management

## Scope

This plan covers the credential and path helpers in `src/slackx/config.py`: environment and config file resolution, environment precedence, the missing-token failure, and the XDG cache path default.
The tests live in `tests/test_config.py` and call the `config` functions directly.
It does not cover the API base URL override (FR-08), the `require=False` path (FR-09), the xoxc- without cookie error (FR-05), the `--db` and `--api-base-url` CLI wiring in `cli/_internal/_client.py`, or the per-workspace database path resolution (FEAT-p8, covered by `tests/test_workspace.py`).

## Unit Tests

| ID | Description | Input | Expected Output |
|---|---|---|---|
| TC-1 | Environment credentials resolve (`test_load_credentials_from_env`) | `SLACK_TOKEN=xoxb-test`, `SLACK_COOKIE=cookie-value` | `load_credentials()` returns `Credentials(token="xoxb-test", cookie="cookie-value")` |
| TC-2 | Token without a cookie is allowed (`test_load_credentials_token_only`) | `SLACK_TOKEN=xoxb-test`, `SLACK_COOKIE` unset, `XDG_CONFIG_HOME=/nonexistent` | `Credentials(token="xoxb-test", cookie=None)` |
| TC-3 | Config file credentials resolve when env is absent (`test_load_credentials_from_config_file`) | Env unset, `$XDG_CONFIG_HOME/slackx/config` holds `SLACK_TOKEN=xoxc-file` and `SLACK_COOKIE=cookie-file` | `Credentials(token="xoxc-file", cookie="cookie-file")` |
| TC-4 | Environment variables override the config file (`test_load_credentials_env_overrides_file`) | `SLACK_TOKEN=xoxb-env` set, config file holds `xoxc-file` and `cookie-file` | `Credentials(token="xoxb-env", cookie="cookie-file")` (token from env, cookie from file) |
| TC-5 | Default database path follows XDG cache (`test_default_db_path_uses_xdg_cache`) | `XDG_CACHE_HOME=<tmp>` | `default_db_path()` equals `<tmp>/slackx/threads.db` |

## Integration Tests

No integration tests.
The feature touches no external system and the tests call the pure helper functions directly.

## End-to-End Tests

No end-to-end tests.
The CLI consumption surface (`--db`, `--api-base-url`, credential loading through `cli/_internal/_client.py`) is exercised elsewhere in `tests/test_cli.py` and is out of scope here.

## Edge Cases and Failure Scenarios

| ID | Scenario | Expected Behavior |
|---|---|---|
| TC-6 | No token in env or config file while `require` defaults to True (`test_load_credentials_missing_raises`) | `load_credentials()` raises `SystemExit` |
| TC-7 | An `xoxc-` token with no cookie | `load_credentials()` raises `SystemExit` with the message naming the required matching d cookie; no dedicated test today |
| TC-8 | `load_credentials(require=False)` with no token | Returns `Credentials(token="", cookie=None)` instead of exiting; no dedicated test today |
| TC-9 | Config file present but without a cookie value | The cookie stays `None` and a non-`xoxc-` token still resolves; covered indirectly by TC-2 |

## Test Infrastructure

- `pytest` with `monkeypatch` to set and unset `SLACK_TOKEN`, `SLACK_COOKIE`, `XDG_CONFIG_HOME`, and `XDG_CACHE_HOME`.
- `tmp_path` provides the isolated config file location and XDG path roots.
- No network access, mocks, or fixtures beyond `monkeypatch` and `tmp_path`.
- `tests/test_config.py` imports the module as `from slackx import config`.

## Coverage Matrix

| Requirement | Test Cases |
|---|---|
| FR-01 | TC-1 |
| FR-02 | TC-3 |
| FR-03 | TC-4 |
| FR-04 | TC-6 |
| FR-05 | None (edge case TC-7 has no dedicated test) |
| FR-06 | TC-5 |
| FR-07 | None (CLI `--db` wiring, tested outside `test_config.py`) |
| FR-08 | None (no dedicated test) |
| FR-09 | None (edge case TC-8 has no dedicated test) |
| NFR-01 | None (no dedicated test) |
| NFR-02 | TC-6 (indirectly) |
