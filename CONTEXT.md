# Scaffolding

The bootstrap CLI that installs house standards, agent config, and agent skills into a target
repo. It is deterministic and clean-adds-only: it decides what a repo needs, then adds what is
missing without editing what is already there.

## Language

### Install engine

**Component**:
A selectable unit of scaffolding (`gitignore`, `skills`, `standards`, …) that inspects a repo and
returns ops without performing them.
_Avoid_: module, plugin, step

**Op**:
One planned operation the engine will execute. Planning and execution are strictly separated —
a component never touches the filesystem.
_Avoid_: action, task, command

**Clean-add**:
Writing something that is absent. The engine's default and, aside from the unignore op, its only
mutation. An existing target is deferred, never overwritten.
_Avoid_: create, upsert

**Defer**:
Leaving an existing target untouched and handing the merge to the agentic guide.
_Avoid_: skip, conflict

**Unignore op**:
The engine's single destructive capability: removing one literal, whitelisted line from
`.gitignore`. Bounded by a literal whitelist rather than a pattern language, so "clean-adds plus
a known set of line removals" stays checkable. See `docs/adr/0001-scoped-unignore-op.md`.

**Decision**:
A choice the engine refuses to make silently, surfaced to the user with a default. Unanswered
decisions take their default.
_Avoid_: option, setting, flag

**Post-condition**:
An assertion attached to a run op declaring what must be true afterwards. Its absence is why
five weeks of installs silently installed no skills.

### Skills

**Skills manifest**:
`skills-lock.json` — the tracked declaration of which skills a repo uses and where they come
from. Despite the filename it pins no version and verifies no hash, so it buys set-level
reproducibility only.
_Avoid_: lockfile, skills lock, skill list

**Derived skills tree**:
`.agents/skills/` — the installed skill files. Rebuilt from the manifest, gitignored, and never
the source of truth.
_Avoid_: installed skills, skills directory

**House baseline**:
The skill set the scaffolder ships by default. What a repo's manifest is compared against.
_Avoid_: default skills, curated catalog

**Top-up**:
Adding house-baseline skills that a repo's manifest does not declare. Merges by default, always
asked.
_Avoid_: sync, update, upgrade

**Adoption**:
Building a manifest for a repo that has a derived skills tree but no manifest. Resolves names
against the house baseline; provenance is unrecoverable from disk, so anything else is surfaced
rather than guessed.
_Avoid_: import, migrate, reconstruct

**Authored skill**:
A skill whose source of truth is this repo's `skills/` tree. Declared with `sourceType: local` so
restore reads the working copy instead of clobbering it with the published one.
_Avoid_: local skill, own skill

### Standards

**CES**:
Collective Engineering Standard — one house rule the scaffolder ships, tracked by exactly one
issue. Cited as `CES-<issue#>`; its machine id is a kebab-case slug. See
`docs/engineering-standards.md`.
_Avoid_: rule, convention, lint rule
