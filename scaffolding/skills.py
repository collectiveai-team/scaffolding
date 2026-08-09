"""Skills manifest — CES-107.

``skills-lock.json`` is the tracked declaration of a repo's agent skills; the
``.agents/skills/`` tree is *derived* from it and is never the source of truth.

Naming, deliberately: the third-party ``skills`` CLI owns this file's schema and
calls it a lock, but it pins no version and verifies no hash — a bogus
``computedHash`` is accepted and silently rewritten. It is a **manifest**. It
buys set-level reproducibility (which skills, from where), not version-level
reproducibility and not integrity. Do not describe it as a lock.

This module holds the manifest logic and the op-building for the ``skills``
component. It takes primitives rather than a ``Context`` so that it stays below
``components`` in the import order and is testable through its own seam.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from scaffolding.plan import Disposition, Op

if TYPE_CHECKING:
    from pathlib import Path

MANIFEST_FILE = "skills-lock.json"
MANIFEST_VERSION = 1

# The engine may delete ONLY these literal lines from a .gitignore. Literals, never
# patterns — that is what keeps "clean-adds plus a whitelist" a checkable invariant.
UNIGNORE_WHITELIST = frozenset({MANIFEST_FILE})

MATTPOCOCK_SOURCE = "mattpocock/skills"
SCAFFOLDING_SOURCE = "collectiveai-team/scaffolding"
VARLOCK_SOURCE = "dmno-dev/varlock"

MATTPOCOCK_SKILLS = [
    "grill-with-docs",
    "triage",
    "improve-codebase-architecture",
    "setup-matt-pocock-skills",
    "to-spec",
    "to-tickets",
    "implement",
    "wayfinder",
    "prototype",
    "diagnosing-bugs",
    "research",
    "tdd",
    "domain-modeling",
    "codebase-design",
    "code-review",
    "resolving-merge-conflicts",
    "grill-me",
    "teach",
    "writing-great-skills",
    "grilling",
]
LOCAL_SKILLS = ["ask-user", "journalist", "handoff", "test-smell-review"]
VARLOCK_SKILLS = ["varlock"]


@dataclass(frozen=True)
class SkillEntry:
    """One declared skill: its name and where it comes from."""

    name: str
    source: str
    source_type: str = "github"


@dataclass(frozen=True)
class Manifest:
    """The declared skill set of a repo."""

    entries: list[SkillEntry]

    @property
    def names(self) -> set[str]:
        return {e.name for e in self.entries}

    def to_json(self) -> str:
        skills = {
            e.name: {"source": e.source, "sourceType": e.source_type}
            for e in sorted(self.entries, key=lambda e: e.name)
        }
        return json.dumps({"version": MANIFEST_VERSION, "skills": skills}, indent=2) + "\n"


@dataclass(frozen=True)
class Reconstruction:
    """A manifest rebuilt from the derived tree, plus what could not be resolved.

    Provenance is not recoverable from disk: an installed skill directory holds only
    ``SKILL.md``, and with no manifest ``skills list --json`` reports ``source: null``.
    So names are resolved against the house baseline and anything else is surfaced,
    never guessed.
    """

    entries: list[SkillEntry]
    unresolved: list[str]


@dataclass(frozen=True)
class AddCommand:
    """A single ``skills add`` invocation, grouped by source."""

    source: str
    names: list[str]
    argv: list[str]


@dataclass(frozen=True)
class SkillsPlanInput:
    """Everything the skills planner needs, decisions already resolved."""

    root: Path
    agent: str
    skills_dir: str
    manifest_ignored: bool
    top_up: bool = True
    unignore: bool = True
    adopt: bool = True


def house_baseline() -> list[SkillEntry]:
    """Return the skill set the scaffolder ships by default."""
    return [
        *(SkillEntry(n, MATTPOCOCK_SOURCE) for n in MATTPOCOCK_SKILLS),
        *(SkillEntry(n, SCAFFOLDING_SOURCE) for n in LOCAL_SKILLS),
        *(SkillEntry(n, VARLOCK_SOURCE) for n in VARLOCK_SKILLS),
    ]


def manifest_path(root: Path) -> Path:
    return root / MANIFEST_FILE


def read_manifest(root: Path) -> Manifest | None:
    """Parse the manifest, or None when absent/unreadable/malformed."""
    path = manifest_path(root)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    skills = raw.get("skills")
    if not isinstance(skills, dict):
        return None
    return Manifest(
        entries=[
            SkillEntry(
                name=name,
                source=str(body.get("source") or ""),
                source_type=str(body.get("sourceType") or "github"),
            )
            for name, body in skills.items()
            if isinstance(body, dict)
        ]
    )


def installed_names(root: Path, skills_dir: str) -> list[str]:
    """Names in the derived tree. Read from disk — no subprocess, no network."""
    tree = root / skills_dir
    if not tree.is_dir():
        return []
    return sorted(p.name for p in tree.iterdir() if (p / "SKILL.md").is_file())


def reconstruct(installed: list[str]) -> Reconstruction:
    """Case C: rebuild a manifest from installed names by resolving against the baseline."""
    known = {e.name: e for e in house_baseline()}
    return Reconstruction(
        entries=[known[n] for n in installed if n in known],
        unresolved=[n for n in installed if n not in known],
    )


def baseline_gap(manifest: Manifest) -> list[SkillEntry]:
    """Baseline skills the manifest does not declare."""
    have = manifest.names
    return [e for e in house_baseline() if e.name not in have]


def add_commands(entries: list[SkillEntry], agent: str) -> list[AddCommand]:
    """Group entries into one ``skills add`` per source.

    Locally-sourced entries are skipped: they are authored in the working tree and
    restore reads them from there, so there is nothing to fetch.
    """
    by_source: dict[str, list[str]] = {}
    for entry in entries:
        if entry.source_type == "local":
            continue
        by_source.setdefault(entry.source, []).append(entry.name)
    return [
        AddCommand(
            source=source,
            names=sorted(names),
            argv=[
                "npx",
                "skills",
                "add",
                source,
                "--agent",
                agent,
                "--yes",
                "--skill",
                *sorted(names),
            ],
        )
        for source, names in sorted(by_source.items())
    ]


def restore_argv() -> list[str]:
    return ["npx", "skills", "experimental_install"]


def _restore_op(label: str) -> Op:
    return Op(
        "skills",
        "run",
        label,
        Disposition.RUN,
        cmd=restore_argv(),
        detail=f"restore from {MANIFEST_FILE}",
    )


def _seed_ops(entries: list[SkillEntry], agent: str, skills_dir: str) -> list[Op]:
    """Fetch ops that must actually deliver — post-condition asserted by the engine."""
    return [
        Op(
            "skills",
            "run",
            f"{cmd.source} ({skills_dir})",
            Disposition.RUN,
            cmd=cmd.argv,
            detail=f"{len(cmd.names)} skill" + ("s" if len(cmd.names) != 1 else ""),
            expect_skills=cmd.names,
        )
        for cmd in add_commands(entries, agent)
    ]


def _adopt_ops(inp: SkillsPlanInput, installed: list[str]) -> list[Op]:
    """Case C: derived tree present, no manifest."""
    if not inp.adopt:
        return [
            Op(
                "skills",
                "noop",
                MANIFEST_FILE,
                Disposition.SKIP,
                detail=f"adoption declined — {len(installed)} installed skills stay undeclared",
            )
        ]
    rebuilt = reconstruct(installed)
    ops = [
        Op(
            "skills",
            "write",
            MANIFEST_FILE,
            Disposition.ADD,
            path=str(manifest_path(inp.root)),
            content=Manifest(entries=rebuilt.entries).to_json(),
            detail=f"adopt {len(rebuilt.entries)} installed skill"
            + ("s" if len(rebuilt.entries) != 1 else ""),
        )
    ]
    ops += [
        Op(
            "skills",
            "noop",
            f"{MANIFEST_FILE}: {name}",
            Disposition.WARN,
            detail="installed but its source is unknown — add the entry by hand",
        )
        for name in rebuilt.unresolved
    ]
    ops.append(_restore_op(f"restore adopted skills ({inp.skills_dir})"))
    return ops


def _unignore_ops(inp: SkillsPlanInput) -> list[Op]:
    """Case B: the manifest exists but git is told to ignore it."""
    if not inp.unignore:
        return [
            Op(
                "skills",
                "noop",
                ".gitignore",
                Disposition.WARN,
                detail=f"{MANIFEST_FILE} stays ignored — the manifest cannot be tracked",
            )
        ]
    return [
        Op(
            "skills",
            "unignore",
            ".gitignore",
            Disposition.ADD,
            path=str(inp.root / ".gitignore"),
            content=MANIFEST_FILE,
            detail=f"stop ignoring {MANIFEST_FILE} so the manifest can be tracked",
        )
    ]


def _top_up_ops(inp: SkillsPlanInput, gap: list[SkillEntry]) -> list[Op]:
    if not gap:
        return []
    if not inp.top_up:
        return [
            Op(
                "skills",
                "noop",
                "house baseline",
                Disposition.SKIP,
                detail="top-up declined — missing: " + ", ".join(e.name for e in gap),
            )
        ]
    return _seed_ops(gap, inp.agent, inp.skills_dir)


def plan_manifest_ops(inp: SkillsPlanInput) -> list[Op]:
    """Build the ops for whichever of the four CES-107 migration cases this repo is in."""
    manifest = read_manifest(inp.root)

    if manifest is None:
        installed = installed_names(inp.root, inp.skills_dir)
        if installed:
            return _adopt_ops(inp, installed)  # case C
        return _seed_ops(house_baseline(), inp.agent, inp.skills_dir)  # case D

    ops: list[Op] = []
    if inp.manifest_ignored:
        ops += _unignore_ops(inp)  # case B
    ops.append(_restore_op(f"restore declared skills ({inp.skills_dir})"))  # case A
    ops += _top_up_ops(inp, baseline_gap(manifest))
    return ops
