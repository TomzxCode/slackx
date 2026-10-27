# Project memory

- 2026-10-19: `cli.main` configures structlog to write to the then-current `sys.stderr`. Pytest closes that capture file after the test, so a module that calls `cli.main` poisons later modules unless something reconfigures structlog in between. The symptom is `ValueError: I/O operation on closed file` in an unrelated server test. Reset structlog to a file-free configuration in an autouse fixture around such tests.
- 2026-10-13: The `.sdlc/` store is repo-local (no SDLC_DIR mirror). `mkdocs.yml` nav lists the feature pages through the `docs/sdlc` symlink to `../.sdlc`, so any feature directory rename must update the nav.
- 2026-10-27: Feature directories follow the pending `pN-<slug>` scheme, `p1`-`p15`; the legacy zero-padded `FEAT-000N-<slug>` directories were renamed (`FEAT-0001-thread-caching` became `p1-thread-caching`, former `p1`-`p7` shifted to `p9`-`p15`) and their `FEAT-000N` IDs rewritten to `FEAT-pN` across `.sdlc/`, `mkdocs.yml`, and docs.
