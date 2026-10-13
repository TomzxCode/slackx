---
date: "2026-10-13"
scope: "all (change set belongs to p3-read-markers; p4-web-ui is a dependent)"
entry: "code"
flags: "fix: false, create-issues: false"
status: complete
---

# Propagation Report

**Date:** 2026-10-13
**Scope:** all features; the change set belongs to `p3-read-markers`
**Entry:** code (commits `3bb244e`, `c49c5ab`, `d5cdf8b`)

## Change Set

The downstream-observable changes this pass compares against:

- A new `read_markers` table and its storage functions (`set_last_read`, `get_read_marker`, `get_last_read`, `load_read_markers`, `delete_read_marker`, `delete_read_markers`, `count_read_markers`, `latest_message_ts`) in `src/slack_cached/storage.py`.
- A new CLI group `slackx conversations read mark|show|clear`, plus `slackx cache clear read`.
- `slackx conversations show` now advances the pointer for `--reader` after printing.
- An HTTP surface `GET|PUT|DELETE /api/read...` in `src/slack_cached/server/app.py`.
- A rename of the namespace from `identifier` to `reader` across the CLI flag, the API body field and path parameters, the `read_markers` column, the index `idx_read_markers_reader`, and the `ReadMarker` field.
- `cache status` now reports `read_marker_count`.
- Documentation: `README.md`, `docs/user-guide/cli-reference.md`, `docs/user-guide/serving.md`, and the new `docs/user-guide/tracking-last-read.md`.

## Consistency Status

| Feature | Downward updates | Upward drift | IDs | Review order | Status |
|---|---|---|---|---|---|
| p3-read-markers | 3 proposed (rename) | 2 findings | clean | no reviews (sync-generated) | drifted |
| p4-web-ui | 3 proposed (rename) | 0 | clean | no reviews | drifted |
| FEAT-0001..0008, p1, p2, p5, p6 | 0 | 0 | clean | n/a | outside change set |
| `.sdlc/context/*` (architecture, vocabulary, schema.dbml) | 3 proposed (rename) | n/a | clean | n/a | drifted (sync-owned) |

## Updates (downward)

| # | Artifact | Edge | Change | Resolution | Status |
|---|---|---|---|---|---|
| 1 | p3-read-markers/requirements.md | code -> requirements | The stored namespace and flag were renamed `identifier` -> `reader` (FR-1, FR-3, FR-7, FR-8, FR-12, and the ACs that run `--identifier`) | Rename the flag, the field, and the wording to `reader` | proposed |
| 2 | p3-read-markers/specification.md | code -> specification | `ReadMarker.identifier`, `read_markers.identifier`, `idx_read_markers_identifier`, `--identifier`, `PUT` body `identifier`, and routes `/api/read/{identifier}` no longer match the code | Rename all occurrences to `reader`, including `idx_read_markers_reader` | proposed |
| 3 | p3-read-markers/tests.md | code -> tests | Renamed test functions and `--identifier` references: TC-3 (`test_read_markers_are_per_identifier` -> `_per_reader`), TC-9 (`test_read_mark_default_identifier` -> `_default_reader`), TC-16 (`test_read_clear_all_for_identifier` -> `_for_reader`), TC-21 (`test_read_marker_put_blank_identifier_is_422` -> `_blank_reader_`), TC-30 (`test_show_uses_default_identifier` -> `_default_reader`) | Update the test names and the `identifier` wording | proposed |
| 4 | p4-web-ui/requirements.md | code -> requirements | FR-8, FR-9, and their ACs describe the API field as an `identifier` | Rename to `reader` | proposed |
| 5 | p4-web-ui/specification.md | code -> specification | `ReadMarkerInput.identifier`, `ReadMarker.identifier`, `?identifier=`, routes `{identifier}`, and "blank identifier" | Rename to `reader` | proposed |
| 6 | p4-web-ui/tests.md | code -> tests | TC-12..TC-14, TC-23 use "identifier" | Rename to `reader` | proposed |
| 7 | `.sdlc/context/architecture.md` | code -> documentation | The read-markers section and ER diagram key pointers by `identifier` | Rename to `reader`; context files are sync-owned, so prefer a `/sync-sdlc` re-run | proposed |
| 8 | `.sdlc/context/vocabulary.md` | code -> documentation | The `identifier (consumer)` term and the `ReadMarker` field list use `identifier` | Rename to `reader`; prefer a `/sync-sdlc` re-run | proposed |
| 9 | `.sdlc/context/schema.dbml` | code -> documentation | `read_markers.identifier` and `idx_read_markers_identifier` | Rename to `reader`; prefer a `/sync-sdlc` re-run | proposed |

## Questions Raised

| # | Edge | Disagreement | Resolutions | Where recorded |
|---|---|---|---|---|
| 1 | requirements <-> needs-assessment | `p3-read-markers` has no `needs-assessment.md` because the feature was reverse-engineered by `/sync-sdlc` | Backfill a needs assessment, or accept a sync-generated feature without one | report only |
| 2 | needs-assessment <-> issue | `p3-read-markers` has no originating GitHub issue | Create a placeholder issue and promote the feature, or accept a p-prefixed feature | report only |
| 3 | tests <-> tasks | `p3-read-markers` and `p4-web-ui` have no `plan.md` or `tasks/`, so tests have no task home | Backfill a plan and tasks, or accept the sync-generated shape | report only |

## Traceability Matrix (p3-read-markers)

| FR / NFR | Spec section | Task(s) | Test(s) | Code location | Docs | Issue AC |
|---|---|---|---|---|---|---|
| FR-1 | Data Models / read_markers | (none) | TC-1, TC-3, TC-8 | `storage.py:1347` `set_last_read` | tracking-last-read.md | (none) |
| FR-2 | Technical Decisions / sentinel | (none) | TC-1, TC-10, TC-19 | `storage.py` `_marker_scope`, `_row_to_read_marker` | tracking-last-read.md | (none) |
| FR-3 | Traceability (independent rows) | (none) | TC-3, TC-9, TC-16 | `storage.py:1409` `load_read_markers` | tracking-last-read.md | (none) |
| FR-4 | Data Models / `latest_message_ts` | (none) | TC-6, TC-8, TC-18 | `storage.py:1475` `latest_message_ts` | tracking-last-read.md | (none) |
| FR-5 | API Contracts | (none) | TC-11, TC-19 | `storage.py:1347` `set_last_read` | cli-reference.md | (none) |
| FR-6 | Sequences / CLI mark | (none) | TC-12, TC-20 | `cli/commands/read_mark.py` | cli-reference.md | (none) |
| FR-7 | Error codes (422) | (none) | TC-24 | `cli/commands/read_mark.py` | cli-reference.md | (none) |
| FR-8 | API Contracts / `read show` | (none) | TC-13, TC-14 | `cli/commands/read_show.py` | cli-reference.md | (none) |
| FR-9 | API Contracts / `read clear` | (none) | TC-15, TC-16, TC-22 | `cli/commands/read_clear.py` | cli-reference.md | (none) |
| FR-10 | Error codes (exit 2) | (none) | TC-25 | `cli/commands/read_clear.py` | cli-reference.md | (none) |
| FR-11 | API Contracts | (none) | TC-18, TC-19, TC-22 | `server/app.py:299` | serving.md | (none) |
| FR-12 | Error codes (404, 422) | (none) | TC-20, TC-21, TC-26 | `server/app.py:309` | serving.md | (none) |
| FR-13 | Architecture (`cache clear read`) | (none) | TC-7, TC-17 | `cli/commands/cache_clear.py`, `storage.py` `clear_cache` | cli-reference.md | (none) |
| FR-14 | Sequences / Show advancing | (none) | TC-29, TC-30, TC-31 | `cli/commands/conversations_show.py:158` `_mark_read` | cli-reference.md | (none) |
| NFR-1 | Technical Decisions / upsert | (none) | TC-2 | `storage.py:1347` | (n/a) | (none) |
| NFR-2 | Technical Decisions / sentinel | (none) | TC-1, TC-18 | `storage.py` `_row_to_read_marker` | (n/a) | (none) |
| NFR-3 | (implicit) output modes | (none) | TC-13, TC-14 | `cli/_internal/_render.py` `_render_read_markers_human` | cli-reference.md | (none) |
| NFR-4 | (index) `idx_read_markers_reader` | (none) | TC-4, TC-6 | `storage.py:128` | (n/a) | (none) |

Bold note: the Task(s) column is empty for every requirement because `p3-read-markers` has no `tasks/` directory, which is the `tests -> tasks` finding below rather than a per-requirement defect.

## Summary

| Class | Critical | High | Medium | Low | Total |
|---|---|---|---|---|---|
| Orphan upstream | 0 | 2 | 0 | 0 | 2 |
| Orphan downstream | 0 | 0 | 0 | 1 | 1 |
| Broken reference | 0 | 0 | 0 | 0 | 0 |
| Status inversion | 0 | 0 | 0 | 0 | 0 |
| Documentation drift | 0 | 0 | 5 | 0 | 5 |
| **Total** | **0** | **2** | **5** | **1** | **8** |

## Findings

### 1. Read-marker artifacts still use the `identifier` name removed by the rename

**Feature:** p3-read-markers (primary), p4-web-ui
**Class:** Documentation drift
**Severity:** Medium
**Direction:** Downward
**Edge(s):** code -> requirements, code -> specification, code -> tests
**Location:** `p3-read-markers/requirements.md`, `specification.md`, `tests.md`; `p4-web-ui/requirements.md`, `specification.md`, `tests.md`
**Finding:** The code renamed the read-marker namespace from `identifier` to `reader` (CLI flag, API field and paths, the `read_markers` column, the index, and the `ReadMarker` field), but the requirements, specification, and test plans still describe `identifier`.
**Impact:** The artifacts no longer match the code, and the renamed test functions referenced in the test plans cannot be resolved by ID.
**Recommendation:** Rename `identifier` to `reader` in these artifacts, and update the test function names in `p3-read-markers/tests.md`.

### 2. `p3-read-markers` has no needs assessment or originating issue

**Feature:** p3-read-markers
**Class:** Orphan upstream
**Severity:** High
**Direction:** Upward
**Edge(s):** requirements <-> needs-assessment, needs-assessment <-> issue
**Location:** `.sdlc/features/p3-read-markers/` (no `needs-assessment.md`, no issue reference)
**Finding:** The feature was reverse-engineered from the already-implemented code by `/sync-sdlc`, so the requirements have no upstream needs assessment and no GitHub issue.
**Impact:** The requirements cannot be traced to a documented need, so nothing verifies that the feature is the right product rather than merely present.
**Recommendation:** Human decision: backfill a `needs-assessment.md` and a placeholder issue (see `/create-placeholder-issue`), or record that this feature is accepted as sync-generated.

### 3. `p3-read-markers` and `p4-web-ui` have no plan or tasks

**Feature:** p3-read-markers, p4-web-ui
**Class:** Orphan downstream / structural gap
**Severity:** Medium
**Direction:** Upward
**Edge(s):** tests <-> tasks, tasks <-> plan
**Location:** `.sdlc/features/p3-read-markers/`, `.sdlc/features/p4-web-ui/` (no `plan.md`, no `tasks/`)
**Finding:** Both features have no `plan.md` and no `tasks/`, so every test has no task home and every task-to-test edge is unsatisfiable.
**Impact:** Work decomposition and effort tracking are absent; the `tests <-> tasks` and `tasks <-> plan` checks cannot pass.
**Recommendation:** Human decision: backfill a plan and tasks, or accept the sync-generated shape and record it.

### 4. `.sdlc/context/` files still describe the `identifier` name

**Feature:** project context (not a feature)
**Class:** Documentation drift
**Severity:** Medium
**Direction:** Downward
**Edge(s):** code -> documentation
**Location:** `.sdlc/context/architecture.md`, `vocabulary.md`, `schema.dbml`
**Finding:** The read-markers section of `architecture.md`, the `identifier (consumer)` vocabulary term, and the `read_markers` table in `schema.dbml` all use `identifier`.
**Impact:** Context files are what implementation, testing, and audit skills read first, so they would mislead the next skill about the schema and flag.
**Recommendation:** Prefer a `/sync-sdlc` re-run, since these files are sync-owned and were generated in the same session as the feature.

### 5. Read-marker tests are filed under the URL-parsing feature

**Feature:** FEAT-0005-url-parsing
**Class:** Orphan downstream
**Severity:** Low
**Direction:** Upward
**Edge(s):** tests <-> tasks (attribution)
**Location:** `.sdlc/features/FEAT-0005-url-parsing/tests.md:54-55` (TC-17, TC-18)
**Finding:** `FEAT-0005-url-parsing/tests.md` lists two read-marker integration tests, which belong to `p3-read-markers`.
**Impact:** Test-to-feature attribution is wrong, so coverage for one feature is counted under another.
**Recommendation:** Repair by moving TC-17 and TC-18 into `p3-read-markers/tests.md` (or renumber); the test functions themselves still exist.

## Fixes Applied

None during the pass (it ran without `--fix`).

Applied afterward by user direction (rename only):

- `identifier` -> `reader` in `p3-read-markers/requirements.md`, `specification.md`, and `tests.md` (including the renamed test-function references).
- `identifier` -> `reader` in `.sdlc/context/architecture.md`, `vocabulary.md`, and `schema.dbml` through a scoped `/sync-sdlc`, plus a commit-message example in `conventions.md`.

## Recommended Actions

| Priority | Action | Owner decision |
|---|---|---|
| High | Backfill a needs assessment and placeholder issue for `p3-read-markers`, or record acceptance of a sync-generated feature | answer question |
| Medium | Rename `identifier` to `reader` in `p3-read-markers` and `p4-web-ui` (run this pass again with `--fix`, or edit directly) | implement |
| Medium | Re-run `/sync-sdlc` so `.sdlc/context/architecture.md`, `vocabulary.md`, and `schema.dbml` pick up the `reader` name | implement |
| Medium | Backfill a plan and tasks for `p3-read-markers` and `p4-web-ui`, or accept the current shape | answer question |
| Low | Move TC-17 and TC-18 out of `FEAT-0005-url-parsing/tests.md` into `p3-read-markers/tests.md` | repair |
