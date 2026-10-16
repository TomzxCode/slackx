<!-- session_link: http://localhost:10000/?session=ses_ecd146300ffene4fNEdCg3uMTJ -->
# Infrastructure

<!--
This file captures the project's technology stack, development tooling, CI/CD pipelines,
environments, and deployment procedures. It gives implementation, testing, and deployment
skills the commands and configuration they need without grepping the codebase each time.
Update this file when tooling, environments, or deployment procedures change.
-->

## Technology Stack

| Component | Technology | Version |
|---|---|---|
| Language | Python | 3.13 |
| Runtime | CPython | >=3.13 (`.python-version` pins 3.13) |
| Framework | cyclopts (CLI), FastAPI + uvicorn (web server) | cyclopts >=4.18.0, FastAPI >=0.141.1, uvicorn >=0.52.4 |
| Database | SQLite via the standard library `sqlite3` module | Python 3.13 bundled SQLite |
| Async HTTP | httpx | >=0.28.1 |
| Logging | structlog | >=24.4 |
| Terminal output | rich | >=15.0.0 |
| Config loading | python-dotenv | >=1.0 |

The package is named `slackx` and exposes two console scripts: `slackx` (the CLI and web server) and `slack-fake-server` (the fake Slack API used in tests).
The build backend is `uv_build`.

## Development Tooling

| Tool | Purpose | Command |
|---|---|---|
| uv | Package management | `uv add some-package`, `uv sync`, `uv sync --all-extras --dev` |
| ruff | Linting and formatting | `uv run ruff check` / `uv run ruff format --check` (apply with `uv run ruff format`) |
| pytest | Testing | `uv run pytest` |
| mkdocs | Documentation site build | `uv run mkdocs build`, preview with `uv run mkdocs serve` |

There is no type checker configured (no mypy or pyright dependency or configuration), so no type-check command exists.
There is no separate build step for the Python package beyond `uv build`, and the web SPA ships prebuilt under `src/slackx/web/dist`.

## Environments

| Environment | Branch | Purpose | URL |
|---|---|---|---|
| Developer machine | any | Local install and use of the CLI and web UI via uv | not applicable (local) |
| GitHub Pages (documentation) | main | Published documentation site | https://tomzxcode.github.io/slackx |

There is no staging or production application environment.
The CLI runs on the developer's own machine and the web UI is served locally by the `slackx serve` command.

## CI/CD Pipelines

| Workflow | Trigger | What it runs |
|---|---|---|
| `.github/workflows/ci.yml` | push and pull request to `main` or `master` | `uv sync --all-extras --dev`, `uv run ruff check`, `uv run ruff format --check`, `uv run pytest` |
| `.github/workflows/static-docs.yml` | push to `main` and manual `workflow_dispatch` | build docs with `uv run mkdocs build` and deploy the site to GitHub Pages |

Dependabot (`.github/dependabot.yml`) opens weekly update pull requests for both `github-actions` and `pip` dependencies.
Code ownership is declared in `.github/CODEOWNERS` as `* @tomzx`.

## Deployment

The documentation site is the only deployed artifact.
Pushing to `main` triggers `.github/workflows/static-docs.yml`, which builds the MkDocs site, moves it into `docs`, uploads it as a Pages artifact, and deploys it to GitHub Pages.
The workflow also supports manual runs through `workflow_dispatch`.
The CLI and web server are not deployed anywhere; they are installed and run locally with uv or as an installed console script.

### Rollback

There is no application deployment to roll back.
To revert the published documentation, check out a good commit on `main` and re-run the `static-docs.yml` workflow (`workflow_dispatch`) to rebuild and redeploy Pages from that revision, or push a revert commit so the workflow runs again.

## Health Checks

There is no health check endpoint.
The `slackx serve` web UI exposes no `/health` or `/ready` route, and nothing probes it.
The app runs as a local process, so there is no load balancer or orchestrator probe to satisfy.

## Smoke Tests

There is no separate smoke test suite.
`uv run pytest` (the suite under `tests/`) is the only automated test run, and it is also what CI executes.
The fake Slack server is exercised by that suite for integration-style coverage.

## Hosting

There is no cloud infrastructure and no infrastructure-as-code.
The CLI and web UI run on local developer machines.
Documentation is hosted on GitHub Pages at https://tomzxcode.github.io/slackx, published by the Pages workflow.

## Secrets Management

Slack credentials are never stored in the repository.
They are read at runtime from environment variables (`SLACK_TOKEN` and `SLACK_COOKIE`) or from a config file at `$XDG_CONFIG_HOME/slackx/config` or `~/.config/slackx/config` in `KEY=VALUE` format.
An optional `SLACK_API_BASE_URL` override is resolved the same way.
The `.env` file is gitignored and is not committed.
Credential resolution prefers environment variables over the config file, and an `xoxc-` token requires its matching `xoxd-` cookie from the same browser session.
No secret values are recorded in this file.
