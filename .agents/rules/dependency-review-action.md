# CES-113 · dependency-review-action

**Code:** `CES-113` &nbsp;·&nbsp; **Slug:** `dependency-review-action` &nbsp;·&nbsp; **Enforced
by:** CI workflow (`dependency-review.yml`) &nbsp;·&nbsp; **Tracker:**
[#113](https://github.com/collectiveai-team/scaffolding/issues/113)

## Directive

Every PR that changes the dependency graph gets an automatic, PR-visible summary of what was
added/removed/changed, via
[`actions/dependency-review-action`](https://github.com/actions/dependency-review-action).

## Why

`pip-audit`/`osv-scanner` scan the *final resolved* dependency set for known CVEs — neither
highlights *what changed in this PR* versus the base branch, so a reviewer has to notice a new
dependency by reading `uv.lock`'s diff line by line. `dependency-review-action` is a direct,
GitHub-native fix for the "dependency creep" failure mode: an agent reaching for a new library to
make one HTTP call where the stdlib or an existing transitive dep would do.

## Enforcement posture

Ships **summary-only**: `comment-summary-in-pr: always`, no `fail-on-severity` or
`deny-licenses`. It cannot block a merge in this configuration — promote to a hard gate only after
a burn-in period, as a separate, explicit decision.

## Requirements

GitHub-hosted repos only. Private repos need "Dependency graph" enabled in repo settings (free
tier, not a paid Advanced Security feature) — without it, the action silently has nothing to
report.

## Suppression

There is nothing to suppress in the summary-only default — it only comments, never fails a check.
Once (and if) a repo promotes this to a hard gate, per-advisory allow-listing is the
`allow-ghsas`/`allow-licenses` inputs on the action itself, not a house-side mechanism.
