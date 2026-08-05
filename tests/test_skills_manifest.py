"""CES-107 skills manifest: the four migration cases, consent, and the unignore op.

Exercised through the public seams — ``build_plan``/``apply`` for the component and
``plan_manifest_ops`` for the manifest logic — never through private helpers.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from scaffolding.checks import run_checks
from scaffolding.engine import apply, build_plan
from scaffolding.facts import detect
from scaffolding.plan import Decisions, Disposition, Op
from scaffolding.settings import Settings
from scaffolding.skills import (
    MANIFEST_FILE,
    Manifest,
    SkillEntry,
    SkillsPlanInput,
    baseline_gap,
    house_baseline,
    installed_names,
    plan_manifest_ops,
    read_manifest,
    reconstruct,
)

if TYPE_CHECKING:
    from pathlib import Path

SKILLS_DIR = ".agents/skills"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _install_skill(root: Path, name: str) -> None:
    d = root / SKILLS_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")


def _write_manifest(root: Path, entries: list[SkillEntry]) -> None:
    (root / MANIFEST_FILE).write_text(Manifest(entries=entries).to_json(), encoding="utf-8")


def _plan(root: Path, **kw) -> list[Op]:
    return plan_manifest_ops(
        SkillsPlanInput(
            root=root,
            agent="opencode",
            skills_dir=SKILLS_DIR,
            manifest_ignored=kw.pop("manifest_ignored", False),
            **kw,
        )
    )


def _kinds(ops: list[Op]) -> set[str]:
    return {op.kind for op in ops}


# --- case D: nothing present -------------------------------------------------
def test_case_d_seeds_the_house_baseline(repo: Path):
    ops = _plan(repo)
    assert all(op.disposition is Disposition.RUN for op in ops)
    promised = {name for op in ops for name in (op.expect_skills or [])}
    assert promised == {e.name for e in house_baseline()}


def test_seed_ops_declare_a_post_condition(repo: Path):
    # Without this the engine cannot tell "installed nothing" from "installed fine".
    assert all(op.expect_skills for op in _plan(repo))


# --- case A: manifest present ------------------------------------------------
def test_case_a_restores_and_does_not_reseed(repo: Path):
    _write_manifest(repo, house_baseline())
    ops = _plan(repo)
    assert [op.cmd for op in ops] == [["npx", "skills", "experimental_install"]]


def test_case_a_tops_up_only_the_gap(repo: Path):
    _write_manifest(repo, [SkillEntry("tdd", "mattpocock/skills")])
    ops = _plan(repo)
    promised = {name for op in ops for name in (op.expect_skills or [])}
    assert "tdd" not in promised
    assert "triage" in promised


def test_case_a_declined_top_up_reports_the_gap_and_adds_nothing(repo: Path):
    _write_manifest(repo, [SkillEntry("tdd", "mattpocock/skills")])
    ops = _plan(repo, top_up=False)
    assert not any(op.expect_skills for op in ops)
    skipped = [op for op in ops if op.disposition is Disposition.SKIP]
    assert len(skipped) == 1
    assert "triage" in skipped[0].detail


def test_declared_local_skills_are_never_refetched(repo: Path):
    """The dogfooding carve-out: a skill declared local must not be pulled from github.

    `handoff` is in the house baseline, so a naive top-up would refetch it from
    collectiveai-team/scaffolding and clobber the copy authored in this working tree.
    Declaring it satisfies the baseline by name, so the gap is empty.
    """
    _write_manifest(repo, [SkillEntry("handoff", ".", "local")])
    assert "handoff" in {e.name for e in house_baseline()}
    promised = {name for op in _plan(repo) for name in (op.expect_skills or [])}
    assert "handoff" not in promised


# --- case B: manifest ignored ------------------------------------------------
def test_case_b_emits_a_scoped_unignore_op(repo: Path):
    _write_manifest(repo, house_baseline())
    ops = _plan(repo, manifest_ignored=True)
    unignore = [op for op in ops if op.kind == "unignore"]
    assert len(unignore) == 1
    assert unignore[0].content == MANIFEST_FILE


def test_case_b_declined_warns_instead_of_editing(repo: Path):
    _write_manifest(repo, house_baseline())
    ops = _plan(repo, manifest_ignored=True, unignore=False)
    assert "unignore" not in _kinds(ops)
    assert any(op.disposition is Disposition.WARN for op in ops)


def test_unignore_removes_only_the_whitelisted_line(repo: Path):
    gi = repo / ".gitignore"
    gi.write_text(".env\nskills-lock.json\n.tmp/\n", encoding="utf-8")
    _write_manifest(repo, house_baseline())
    ops = [op for op in _plan(repo, manifest_ignored=True) if op.kind == "unignore"]
    apply(_as_plan(repo, ops), repo)
    assert gi.read_text(encoding="utf-8").splitlines() == [".env", ".tmp/"]


def test_unignore_refuses_a_line_outside_the_whitelist(repo: Path):
    gi = repo / ".gitignore"
    gi.write_text(".env\n", encoding="utf-8")
    rogue = Op("skills", "unignore", ".gitignore", Disposition.ADD, path=str(gi), content=".env")
    with pytest.raises(ValueError, match="non-whitelisted"):
        apply(_as_plan(repo, [rogue]), repo)


# --- case C: installed skills, no manifest -----------------------------------
def test_case_c_adopts_installed_skills_into_a_manifest(repo: Path):
    _install_skill(repo, "tdd")
    _install_skill(repo, "triage")
    ops = _plan(repo)
    write = [op for op in ops if op.kind == "write"]
    assert len(write) == 1
    declared = json.loads(write[0].content or "{}")["skills"]
    assert set(declared) == {"tdd", "triage"}
    assert declared["tdd"]["source"] == "mattpocock/skills"


def test_case_c_warns_about_skills_it_cannot_resolve(repo: Path):
    # Provenance is unrecoverable from disk, so a non-baseline skill must be surfaced.
    _install_skill(repo, "tdd")
    _install_skill(repo, "our-private-skill")
    ops = _plan(repo)
    warned = [op for op in ops if op.disposition is Disposition.WARN]
    assert len(warned) == 1
    assert "our-private-skill" in warned[0].target
    declared = json.loads(next(op for op in ops if op.kind == "write").content or "{}")["skills"]
    assert "our-private-skill" not in declared  # surfaced, never guessed


def test_case_c_declined_writes_nothing(repo: Path):
    _install_skill(repo, "tdd")
    ops = _plan(repo, adopt=False)
    assert "write" not in _kinds(ops)
    assert all(op.disposition is Disposition.SKIP for op in ops)


def test_reconstruction_splits_known_from_unknown():
    rebuilt = reconstruct(["tdd", "mystery"])
    assert [e.name for e in rebuilt.entries] == ["tdd"]
    assert rebuilt.unresolved == ["mystery"]


# --- manifest parsing --------------------------------------------------------
def test_malformed_manifest_reads_as_absent(repo: Path):
    (repo / MANIFEST_FILE).write_text("{not json", encoding="utf-8")
    assert read_manifest(repo) is None


def test_manifest_roundtrips(repo: Path):
    _write_manifest(repo, [SkillEntry("handoff", ".", "local")])
    manifest = read_manifest(repo)
    assert manifest is not None
    assert manifest.entries == [SkillEntry("handoff", ".", "local")]


def test_baseline_gap_is_empty_for_a_complete_manifest():
    assert baseline_gap(Manifest(entries=house_baseline())) == []


def test_installed_names_ignores_dirs_without_a_skill_file(repo: Path):
    _install_skill(repo, "tdd")
    (repo / SKILLS_DIR / "not-a-skill").mkdir(parents=True)
    assert installed_names(repo, SKILLS_DIR) == ["tdd"]


# --- component + check wiring ------------------------------------------------
def test_seeding_a_bare_repo_asks_nothing_about_skills(repo: Path):
    # Case D has nothing to consent to — no manifest to merge into, nothing installed.
    plan = build_plan(repo, detect(repo, probe_visibility=False), Settings(skip_varlock=True))
    assert not [d for d in plan.decisions if d.key.startswith("skills_")]


def test_adoption_is_only_asked_when_skills_are_installed(repo: Path):
    _install_skill(repo, "tdd")
    plan = build_plan(repo, detect(repo, probe_visibility=False), Settings(skip_varlock=True))
    assert "skills_adopt" in {d.key for d in plan.decisions}


def test_skills_component_asks_before_diverging(repo: Path):
    _write_manifest(repo, [SkillEntry("tdd", "mattpocock/skills")])
    plan = build_plan(repo, detect(repo, probe_visibility=False), Settings(skip_varlock=True))
    assert "skills_top_up" in {d.key for d in plan.decisions}


def test_declining_top_up_is_honoured_end_to_end(repo: Path):
    _write_manifest(repo, [SkillEntry("tdd", "mattpocock/skills")])
    plan = build_plan(
        repo,
        detect(repo, probe_visibility=False),
        Settings(skip_varlock=True),
        decisions=Decisions(skills_top_up=False),
    )
    assert not any(op.expect_skills for op in plan.ops if op.component == "skills")


def test_check_flags_an_ignored_manifest(repo: Path):
    (repo / ".gitignore").write_text(f"{MANIFEST_FILE}\n", encoding="utf-8")
    _write_manifest(repo, [SkillEntry("tdd", "mattpocock/skills")])
    _install_skill(repo, "tdd")
    failed = {r.name for r in run_checks(repo) if not r.ok}
    assert "skills manifest not ignored" in failed


def test_check_flags_a_declared_but_missing_skill(repo: Path):
    _write_manifest(repo, [SkillEntry("tdd", "mattpocock/skills")])
    results = {r.name: r for r in run_checks(repo)}
    assert not results["declared skills installed"].ok
    assert "tdd" in results["declared skills installed"].detail


def _as_plan(root: Path, ops: list[Op]):
    plan = build_plan(
        root, detect(root, probe_visibility=False), Settings(skip_skills=True, skip_varlock=True)
    )
    plan.ops = ops
    return plan
