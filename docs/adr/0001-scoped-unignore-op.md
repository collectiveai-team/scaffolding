# Scoped unignore op: bounded destructive editing in a clean-adds-only engine

**Status:** accepted (CES-107)

The engine is clean-adds-only — it must never edit, merge, or overwrite an existing target file.
That invariant is what makes it safe to point at someone else's repo, and CES-30 depends on it.
CES-107 makes `skills-lock.json` a tracked manifest, which breaks on any repo that already
gitignores it: the scaffolder would restore skills happily while the manifest stayed untracked
forever, and would report success. Un-ignoring requires deleting a line from a file the repo
already owns.

We added an `unignore` op that removes **one literal line drawn from an enumerated whitelist**
(`UNIGNORE_WHITELIST` in `scaffolding/skills.py`) from `.gitignore`, gated behind a `Decision`
that defaults to yes. It refuses any line outside the whitelist by raising.

## Considered options

- **Check and instruct instead.** `scaffolding check` fails with the exact remedy and a human
  makes the one-line edit. Preserves the invariant perfectly. Rejected because the same run that
  detects the problem can fix it, and every legacy repo would otherwise carry a manual step.
- **General `edit` / `remove-line` capability.** Rejected: clean-adds-only would stop being a
  property of the engine and become a convention nobody can verify.
- **Do nothing; grandfather affected repos.** Rejected: the repos that most need the standard are
  exactly the ones that already ignore the file.

## Consequences

"Clean-adds-only" is now precisely "clean-adds, plus removal of literal lines on an explicit
whitelist." This remains checkable because the whitelist is a literal frozenset in code, not a
pattern language — you can read it and enumerate every destructive edit the engine can perform.

Future components will cite this precedent. The line to hold is the *literal whitelist*, not the
op: adding a new literal is a reviewable one-line change, whereas accepting a regex, a glob, or a
caller-supplied string would give the capability away entirely.

Note the asymmetry this preserves. The manifest top-up is also a merge, but the third-party
`skills` CLI performs that write as a side effect of a run op — the engine itself never touches
the file. The unignore op is the only place the engine edits an existing target.
