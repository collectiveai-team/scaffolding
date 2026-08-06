# CES-119 · dependency vulnerability scanning (osv-scanner)

**Code:** `CES-119` &nbsp;·&nbsp; **Slug:** `osv-scanner-replace-pip-audit` &nbsp;·&nbsp;
**Enforced by:** CI workflow (`osv-scanner.yml`) &nbsp;·&nbsp; **Tracker:**
[#119](https://github.com/collectiveai-team/scaffolding/issues/119)

## Directive

Every push to `main` and every PR is scanned for known dependency vulnerabilities via
[`osv-scanner scan source`](https://github.com/google/osv-scanner) against `uv.lock` (and, once a
non-Python template exists, whatever lockfile that ecosystem produces — same tool, same workflow).
This **replaces** the previous `pip-audit.yml`, it does not supplement it.

## Why

`pip-audit` only understands Python. `osv-scanner` (Google, Apache-2.0) is built on the same
underlying OSV.dev vulnerability database but natively parses lockfiles across ~20 ecosystems —
including `uv.lock` directly, no `uv export` step required — alongside `poetry.lock`,
`Pipfile.lock`, `package-lock.json`, `Cargo.lock`, `go.mod`, and more. It scales to the rest of a
scaffolded repo's roadmap (a Next.js frontend, a Go service) without adding a second scanner.

## Configuration

Runs via the reusable workflow (`google/osv-scanner-action/.github/workflows/osv-scanner-reusable.yml@v2`)
with `scan-args: --lockfile=uv.lock` — `uv.lock` is natively recognized by filename, no
parser-forcing prefix needed.

## Migration (existing repos)

Delete the old `pip-audit.yml` when adopting this — do not run both; they cover the same finding
class from the same underlying database, and running both is redundant noise, not defense in
depth. New repos get `osv-scanner.yml` directly; existing repos with `pip-audit.yml` should
replace it in the same change.

## Suppression

Per-vulnerability ignores go in an `osv-scanner.toml` config file at the repo root (see
[osv-scanner's configuration docs](https://google.github.io/osv-scanner/configuration/)) — never
silence the whole workflow to unblock one known, accepted advisory.
