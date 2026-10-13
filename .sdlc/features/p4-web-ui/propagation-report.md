---
date: "2026-10-13"
scope: "p4-web-ui (dependent of the read-marker change)"
entry: "code"
flags: "fix: false, create-issues: false"
status: complete
---

# Propagation Report

**Date:** 2026-10-13
**Scope:** p4-web-ui
**Entry:** code (rename of the read-marker namespace from `identifier` to `reader`, commits `3bb244e`, `c49c5ab`, `d5cdf8b`)

## Change Set

The same change set as the batch report, restricted to what touches this feature:

- The `/api/read` request body field and response field are now `reader`, not `identifier`.
- The query filter is `?reader=`, and the delete routes are `/api/read/{reader}[...]`.
- The blank-namespace validation error now says `reader`.

## Consistency Status

| Feature | Downward updates | Upward drift | IDs | Review order | Status |
|---|---|---|---|---|---|
| p4-web-ui | 3 proposed (rename) | 2 findings | clean | no reviews (sync-generated) | drifted |

## Updates (downward)

| # | Artifact | Edge | Change | Resolution | Status |
|---|---|---|---|---|---|
| 1 | p4-web-ui/requirements.md | code -> requirements | FR-8, FR-9, and their ACs call the API field an `identifier` | Rename to `reader` | proposed |
| 2 | p4-web-ui/specification.md | code -> specification | `ReadMarkerInput.identifier`, `ReadMarker.identifier`, `?identifier=`, routes `{identifier}`, and "blank identifier" | Rename to `reader` | proposed |
| 3 | p4-web-ui/tests.md | code -> tests | TC-12, TC-13, TC-14, TC-23 use "identifier" | Rename to `reader` | proposed |

## Questions Raised

| # | Edge | Disagreement | Resolutions | Where recorded |
|---|---|---|---|---|
| 1 | requirements <-> needs-assessment | `p4-web-ui` has no `needs-assessment.md` (sync-generated) | Backfill one, or accept | report only |
| 2 | needs-assessment <-> issue | `p4-web-ui` has no originating issue | Create a placeholder issue, or accept | report only |
| 3 | tests <-> tasks | `p4-web-ui` has no `plan.md` or `tasks/` | Backfill, or accept | report only |

## Traceability Matrix (p4-web-ui)

| FR / NFR | Spec section | Task(s) | Test(s) | Code location | Docs | Issue AC |
|---|---|---|---|---|---|---|
| FR-8 | API Contracts / read endpoints | (none) | TC-12, TC-13 | `server/app.py:299` (GET), `server/app.py:309` (PUT) | serving.md | (none) |
| FR-9 | API Contracts / delete routes | (none) | TC-14, TC-23 | `server/app.py:333`, `:342`, `:351` | serving.md | (none) |

## Summary

| Class | Critical | High | Medium | Low | Total |
|---|---|---|---|---|---|
| Orphan upstream | 0 | 2 | 0 | 0 | 2 |
| Orphan downstream | 0 | 0 | 0 | 0 | 0 |
| Broken reference | 0 | 0 | 0 | 0 | 0 |
| Status inversion | 0 | 0 | 0 | 0 | 0 |
| Documentation drift | 0 | 0 | 1 | 0 | 1 |
| **Total** | **0** | **2** | **1** | **0** | **3** |

## Findings

### 1. The read API is documented as `identifier`, but the code uses `reader`

**Feature:** p4-web-ui
**Class:** Documentation drift
**Severity:** Medium
**Direction:** Downward
**Edge(s):** code -> requirements, code -> specification, code -> tests
**Location:** `p4-web-ui/requirements.md:36-37,139-151`, `p4-web-ui/specification.md:109-160`, `p4-web-ui/tests.md:37-39,58`
**Finding:** The requirements, specification, and test plan describe the read endpoint's field and path parameter as `identifier`, which the code renamed to `reader`.
**Impact:** The documented API contract no longer matches `server/app.py`, so a consumer following the docs would send the wrong body field.
**Recommendation:** Rename `identifier` to `reader` in all three artifacts.

### 2. `p4-web-ui` has no needs assessment or originating issue

**Feature:** p4-web-ui
**Class:** Orphan upstream
**Severity:** High
**Direction:** Upward
**Edge(s):** requirements <-> needs-assessment, needs-assessment <-> issue
**Location:** `.sdlc/features/p4-web-ui/` (no `needs-assessment.md`, no issue reference)
**Finding:** The feature was reverse-engineered by `/sync-sdlc`, so its requirements trace to neither a documented need nor an issue.
**Impact:** Nothing verifies the feature is needed rather than merely present.
**Recommendation:** Human decision: backfill a needs assessment and placeholder issue, or record acceptance.

## Fixes Applied

None during the pass (it ran without `--fix`).

Applied afterward by user direction: `identifier` -> `reader` in `p4-web-ui/requirements.md`, `specification.md`, and `tests.md`.

## Recommended Actions

| Priority | Action | Owner decision |
|---|---|---|
| High | Backfill a needs assessment and placeholder issue for `p4-web-ui`, or record acceptance | answer question |
| Medium | Rename `identifier` to `reader` in `p4-web-ui/requirements.md`, `specification.md`, and `tests.md` | implement |
| Medium | Backfill a plan and tasks, or accept the sync-generated shape | answer question |
