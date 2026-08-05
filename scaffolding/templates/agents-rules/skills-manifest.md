# CES-107 · track the skills manifest

**Code:** `CES-107` &nbsp;·&nbsp; **Slug:** `skills-manifest` &nbsp;·&nbsp; **Enforced by:**
`scaffolding check` &nbsp;·&nbsp; **Tracker:**
[#107](https://github.com/collectiveai-team/scaffolding/issues/107)

## Directive

`skills-lock.json` is the repo's **skills manifest**: the declared set of agent skills and where
each comes from. **Commit it.** `.agents/skills/` is *derived* from it — gitignored, rebuilt on
install, never the source of truth.

Installing skills is part of setup: `scaffolding install` restores from the manifest rather than
re-running a hardcoded list of `skills add` commands.

## It is a manifest, not a lock

The filename comes from the third-party `skills` CLI that owns the schema. It is misleading:

- Entries carry `source`, `sourceType`, `skillPath`, `computedHash` — **no git ref, tag, or SHA**.
  Restore fetches whatever is at the source *now*.
- `computedHash` is **not verified**. An all-zeros hash is accepted and silently rewritten to the
  real value on restore.

So it buys **set-level** reproducibility — which skills, from where — and neither version-level
reproducibility nor integrity. Say "manifest". Do not promise pinning you do not have.

## Why

Without a tracked manifest a repo's skill set is unreproducible and its drift is invisible. A
fresh clone gets whatever the installer's hardcoded list happens to say that week, and nobody can
tell what the repo is supposed to have. Committing the declaration makes the skill set reviewable
in diffs like any other dependency.

## The four states

| Repo state | Install behaviour |
| --- | --- |
| Manifest tracked | restore, then offer to top up missing house-baseline skills |
| Manifest gitignored | offer to un-ignore, then as above |
| Skills installed, no manifest | offer to adopt them into a manifest, then restore |
| Nothing | seed the house baseline, which creates the manifest |

Each offer is a decision defaulting to **yes** — merging is the default, but consent is always
asked, so a skill you deliberately removed is never silently resurrected. `--yes` and
non-interactive runs take the defaults.

## Adoption cannot recover provenance

An installed skill directory holds only `SKILL.md`, and with no manifest `skills list --json`
reports `source: null`. Adoption therefore resolves installed **names** against the house
baseline. A skill outside the baseline — hand-added, private, or renamed upstream — is reported
as unresolvable and must have its entry added by hand. It is never guessed.

## Authored skills

A skill whose source of truth is this repo's own tree is declared `"sourceType": "local"` with
`"source": "."`, so restore reads the working copy. Without this, editing the skill and running
install would silently revert it to the published version.

## Seed ops must deliver

`skills add` is atomic: one unknown skill name exits non-zero and writes **no manifest at all** —
not "all but one". Seed ops therefore declare a post-condition, and the install fails loudly when
a command runs without delivering. A missing `npx` remains a non-fatal skip; offline installs are
legitimate, silently-empty ones are not.

## Suppression

There is none, and that is deliberate — a repo either declares its skills or it does not. To opt
out of a house-baseline skill, decline the top-up prompt; the manifest then records the repo's
actual set.
