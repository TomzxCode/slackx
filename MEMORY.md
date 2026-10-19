# Project memory

- 2026-10-19: `cli.main` configures structlog to write to the then-current `sys.stderr`. Pytest closes that capture file after the test, so a module that calls `cli.main` poisons later modules unless something reconfigures structlog in between. The symptom is `ValueError: I/O operation on closed file` in an unrelated server test. Reset structlog to a file-free configuration in an autouse fixture around such tests.
- 2026-10-13: The `.sdlc/` store is repo-local (no SDLC_DIR mirror). Existing feature directories use the legacy zero-padded `FEAT-000N-<slug>` naming that predates the current `N-<slug>` convention. Do not rename them casually: `mkdocs.yml` nav lists them and `docs/sdlc` is a symlink to `../.sdlc`.
