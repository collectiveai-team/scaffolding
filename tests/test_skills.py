"""Skill registry tests: the shipped `skills/` tree must match what the CLI installs."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from scaffolding.components import DATASCIENCE_SKILLS, LOCAL_SKILLS
from scaffolding.engine import build_plan
from scaffolding.facts import detect
from scaffolding.plan import Disposition
from scaffolding.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"

# `tessl skill lint` enforces this, but it needs an authenticated CLI. The pattern is
# cheap to check here so a malformed skill fails in CI rather than at publish time.
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ShippedSkill:
    """A SKILL.md in the tree, with the ``name:`` npx resolves it by."""

    name: str
    path: Path

    @property
    def directory(self) -> str:
        return self.path.parent.name


def _frontmatter(skill_md: Path) -> dict[str, object]:  # ast-grep-ignore: no-dict-return-annotation
    """Parse the YAML frontmatter block.

    Deliberately a real YAML parse, not a line scan: an unquoted scalar containing
    ``": "`` parses as a nested mapping and makes the whole skill unloadable, which a
    ``startswith("name:")`` check happily walks straight past.
    """
    body = skill_md.read_text(encoding="utf-8")
    assert body.startswith("---\n"), f"{skill_md}: missing frontmatter block"
    _, raw, _ = body.split("---\n", 2)
    loaded = yaml.safe_load(raw)
    assert isinstance(loaded, dict), f"{skill_md}: frontmatter is not a mapping"
    return loaded


def _declared_name(skill_md: Path) -> str:
    name = _frontmatter(skill_md).get("name")
    assert isinstance(name, str), f"{skill_md}: frontmatter `name:` missing or not a string"
    return name


def _shipped_skills() -> list[ShippedSkill]:
    """Every SKILL.md under `skills/<category>/<skill>/`, in stable order."""
    paths = sorted(SKILLS_ROOT.glob("*/*/SKILL.md"))
    return [ShippedSkill(name=_declared_name(p), path=p) for p in paths]


def _skill_ops(settings: Settings, repo: Path):
    plan = build_plan(repo, detect(repo, probe_visibility=False), settings, requested=["skills"])
    return [op for op in plan.by(Disposition.RUN) if op.component == "skills"]


# The skills component no-ops without npx, so the behavioural tests below need it.
needs_npx = pytest.mark.skipif(
    shutil.which("npx") is None, reason="skills component is a no-op without npx"
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


# --- the tree and the registry agree -----------------------------------------
@pytest.mark.parametrize("skill", [*LOCAL_SKILLS, *DATASCIENCE_SKILLS])
def test_registered_skill_is_shipped(skill: str):
    """Every name the CLI passes to `npx skills --skill` must exist in `skills/`."""
    names = {s.name for s in _shipped_skills()}
    assert skill in names, f"{skill} is registered but has no skills/*/{skill}/SKILL.md"


def test_shipped_skill_directory_matches_frontmatter_name():
    """`npx skills` resolves by name; a mismatched directory makes the skill unreachable."""
    for skill in _shipped_skills():
        assert skill.directory == skill.name


def test_skill_names_are_globally_unique():
    """`.agents/skills` is flat, so a name collision across categories silently clobbers."""
    names = [s.name for s in _shipped_skills()]
    assert len(names) == len(set(names))


def test_every_shipped_skill_is_registered():
    """A skill in the tree that no command installs is dead weight."""
    assert {s.name for s in _shipped_skills()} == {*LOCAL_SKILLS, *DATASCIENCE_SKILLS}


# --- frontmatter is well-formed ----------------------------------------------
def test_skill_name_is_lowercase_kebab_case():
    """Skill registries reject anything else, and the name is the install key."""
    for skill in _shipped_skills():
        assert SKILL_NAME_RE.match(skill.name), f"{skill.path}: bad name {skill.name!r}"


def test_skill_frontmatter_is_valid_yaml_with_a_description():
    """The description is the only thing an agent sees when deciding to load a skill.

    Regression guard: three skills once shipped a description containing an unquoted
    ``": "``, which YAML reads as a nested mapping. The skill silently fails to load.
    """
    for skill in _shipped_skills():
        description = _frontmatter(skill.path).get("description")
        assert isinstance(description, str), f"{skill.path}: description missing or not a string"
        assert description.strip(), f"{skill.path}: empty description"


# --- the datascience family is opt-in ----------------------------------------
@needs_npx
def test_datascience_skills_absent_by_default(repo: Path):
    ops = _skill_ops(Settings(), repo)
    assert ops, "expected the default skills ops"
    assert "datascience" not in " ".join(op.target for op in ops)


@needs_npx
def test_datascience_skills_added_when_opted_in(repo: Path):
    ops = _skill_ops(Settings(with_datascience_skills=True), repo)
    requested = [arg for op in ops for arg in (op.cmd or [])]
    for skill in DATASCIENCE_SKILLS:
        assert skill in requested


def test_skip_skills_wins_over_datascience_optin(repo: Path):
    settings = Settings(skip_skills=True, with_datascience_skills=True)
    assert _skill_ops(settings, repo) == []
