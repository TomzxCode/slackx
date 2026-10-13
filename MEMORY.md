# Project memory

- 2026-10-13: The `.sdlc/` store is repo-local (no SDLC_DIR mirror). Existing feature directories use the legacy zero-padded `FEAT-000N-<slug>` naming that predates the current `N-<slug>` convention. Do not rename them casually: `mkdocs.yml` nav lists them and `docs/sdlc` is a symlink to `../.sdlc`.
