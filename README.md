<p align="center">
  <img src="assets/logo.png" alt="scaffolding — agent-driven repo bootstrap + recurring skills" style="width:600px; max-width:100%; height:auto;" />
</p>

<p align="center">
  <em>Clean-adds-only repo bootstrap CLI — plus a couple of recurring agent skills.</em>
</p>

<p align="center">
  <a href="https://github.com/collectiveai-team/scaffolding/releases"><img alt="Release" src="https://img.shields.io/github/v/release/collectiveai-team/scaffolding?logo=github" /></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://opencode.ai/"><img src="https://img.shields.io/badge/Agents-opencode%20%C2%B7%20claude--code%20%C2%B7%20codex-1d1d1d?logo=anthropic&logoColor=white" alt="opencode · claude-code · codex"></a>
  <a href="https://docs.astral.sh/uv/"><img src="https://img.shields.io/badge/Install-uvx%20%C2%B7%20curl-261230?logo=astral&logoColor=white" alt="Install via uvx or curl" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

---

**Source Code**: [https://github.com/collectiveai-team/scaffolding](https://github.com/collectiveai-team/scaffolding)

---

Personal repo bootstrap + agent skills for opencode / claude-code / codex.

This repo does two things:

1. **Bootstrap a repo** with my workspace defaults (gitignore, per-agent config,
   `AGENTS.md` guidance, optional prek hooks, ast-grep, CI, Varlock secrets) via a
   small Python CLI. This is a one-time-per-repo operation, run as an *agentic
   install* or directly — not an installed skill. Target one or more agents with
   `--agent` (repeatable / comma-separated; default `opencode`).
2. **Ship a couple of recurring skills** (`journalist`, `handoff`) that you
   install once and use repeatedly.

Most engineering workflow skills I use come from Matt Pocock's
[`skills`](https://github.com/mattpocock/skills). This repo intentionally does
not vendor those; it only contains my own additions.

## Bootstrap a repo

Run this from the root of the repo you want to set up.

**Existing working repo (recommended): let an agent do it.** The bootstrap needs
judgment — new-vs-existing detection, additive JSONC/`AGENTS.md` merges, Python
detection, and per-item conflict resolution. The CLI does the deterministic
clean-adds; the agent drives it and handles merges. Point your agent at the guide:

> Set up this repo by following the instructions here:
> `https://raw.githubusercontent.com/collectiveai-team/scaffolding/main/guide.md`
> Don't summarize it — follow every step.

**New / empty repo (fast path): run the CLI directly.** It does clean adds only
and refuses to touch existing files, deferring any merge to the agent.

Straight from git via `uvx` (no PyPI):

```bash
uvx --from git+https://github.com/collectiveai-team/scaffolding scaffolding install
```

Or via the bootstrap shim (also installs `uv` if missing — preserves the classic
one-liner):

```bash
curl -fsSL https://raw.githubusercontent.com/collectiveai-team/scaffolding/main/install.sh | bash
```

The installer is idempotent — safe to re-run. Existing files are never edited or
overwritten; they are reported as `[defer]` for the agent to merge.

### Commands

```
scaffolding install [components…]   # clean-adds (all default-on, or just the named ones)
scaffolding install --yes           # non-interactive / CI (conservative defaults)
scaffolding install --dry-run       # render the plan, write nothing
scaffolding plan --json             # machine-readable plan for the agent path
scaffolding list                    # available components (gate / default / what they add)
scaffolding check                   # verify bootstrap completeness (nonzero exit on failure)
scaffolding doctor                  # diagnose environment + tools
```

Components: `gitignore agent-config prek ast-grep pyproject ci agents standards
skills varlock` (all default-on except `ci`, which is opt-in). Scope with
positional names or `--skip a,b`. Useful flags: `--agent` (repeatable:
`opencode`/`claude-code`/`codex`), `--ci/--no-ci`, `--ci-parts`,
`--name`, `--description`, `--varlock/--no-varlock`, `--no-deps`. Legacy env vars
(`AGENT`, `SKIP_SKILLS`, `SKIP_VARLOCK`, `WITH_CI`/`SKIP_CI`, `ASSUME_YES`) are
honored.

There is no `uninstall`: the installer requires a git repo, so `git status` /
`git checkout` / `git clean` are the undo mechanism.

## Installed skills

These are real skills you install once and use repeatedly. They land in the
shared `.agents/skills` standard (read by opencode + codex); selecting
`claude-code` bridges them via the `.claude/skills` → `.agents/skills` symlink.

Install selected upstream skills from Matt Pocock:

```bash
npx skills add mattpocock/skills --agent opencode --yes --skill grill-with-docs triage improve-codebase-architecture setup-matt-pocock-skills to-spec to-tickets implement wayfinder prototype diagnosing-bugs research tdd domain-modeling codebase-design code-review resolving-merge-conflicts grill-me teach writing-great-skills grilling
```

Then install my local skills from this repo:

```bash
npx skills add collectiveai-team/scaffolding --agent opencode --yes --skill ask-user journalist handoff
```

If installing from a checkout, run from this repo:

```bash
npx skills add . --agent opencode --yes --skill ask-user journalist handoff --full-depth
```

Skills install once into `.agents/skills`; claude-code reaches them via the
`.claude/skills` symlink created by the bootstrap, so there is no need to re-run
the installer with `--agent claude-code` / `--agent codex`.

## Upstream skills from Matt Pocock

User-invoked engineering workflows:

- `grill-with-docs`, `triage`, `improve-codebase-architecture`, `setup-matt-pocock-skills`.
- `to-spec`, `to-tickets`, `implement`, `wayfinder`.

Model-invoked engineering workflows:

- `prototype`, `diagnosing-bugs`, `research`, `tdd`.
- `domain-modeling`, `codebase-design`, `code-review`, `resolving-merge-conflicts`.

Productivity workflows:

- User-invoked: `grill-me`, `teach`, `writing-great-skills`.
- Model-invoked: `grilling`.

## What's in this repo

- `scaffolding/` — the bootstrap CLI (Cyclopts + Questionary + pydantic-settings
  + Rich). `cli.py`, `engine.py`/`plan.py`, `components.py`, and `templates/`
  (per-agent config — opencode.jsonc / .claude settings, prek hooks, pyproject,
  ast-grep rules, CI workflows, AGENTS.md section).
- `install.sh` — thin bootstrap shim (ensure `uv`, then run the CLI from git).
- `guide.md` — the agentic-install guide (judgment layer).
- `skills/productivity/journalist` — local daily session journals under `.journals/`.
- `skills/productivity/handoff` — compact the current session into a temp-dir handoff for another agent.
- `skills/productivity/ask-user` — route a situation to the smallest suitable installed workflow.
- `skills/quality/test-smell-review` — review tests for false-green smells (pass without
  protecting anything) using an in-context judgment protocol, adapted from
  `falsegreen-skill` without its external LLM-CLI dependency.
- `docs/engineering-standards.md` — **CES (Collective Engineering Standard)**: how house
  rules are coded, cited (`CES-<issue#>` + slug), and shipped. Single source of truth,
  referenced by `AGENTS.md`.
