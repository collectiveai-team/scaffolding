"""`check` — completeness verification from the guide Verify checklist."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scaffolding.agent_config import AGENTS_SKILLS_DIR
from scaffolding.components import AGENTS_MARKER, GITIGNORE_ENTRIES
from scaffolding.skills import MANIFEST_FILE, installed_names, read_manifest


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _strip_jsonc(text: str) -> str:
    # remove // line comments and /* */ block comments, then trailing commas
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"(^|\s)//[^\n]*", r"\1", text)
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _git_tracked(root: Path, rel: str) -> bool:
    try:
        out = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return out.returncode == 0
    except Exception:
        return False


def _gitignored(root: Path, rel: str) -> bool:
    try:
        out = subprocess.run(
            ["git", "check-ignore", "-q", rel],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return out.returncode == 0
    except Exception:
        return False


def _check_opencode(root: Path) -> list[CheckResult]:
    oc = root / "opencode.jsonc"
    if not oc.exists():
        return []
    try:
        data = json.loads(_strip_jsonc(oc.read_text(encoding="utf-8")))
        need = [k for k in ("$schema", "plugin", "permission") if k not in data]
        ok = not need
        detail = "ok" if ok else f"missing keys: {', '.join(need)}"
        return [CheckResult("opencode.jsonc valid", ok, detail)]
    except (ValueError, OSError) as exc:
        return [CheckResult("opencode.jsonc valid", False, f"parse error: {exc}")]


def _check_claude(root: Path) -> list[CheckResult]:
    out: list[CheckResult] = []
    settings = root / ".claude" / "settings.json"
    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
            deny = data.get("permissions", {}).get("deny", [])
            ok = any(".env" in str(rule) for rule in deny)
            out.append(
                CheckResult(
                    ".claude/settings.json valid",
                    ok,
                    "ok" if ok else "permissions.deny missing .env rules",
                )
            )
        except (ValueError, OSError) as exc:
            out.append(CheckResult(".claude/settings.json valid", False, f"parse error: {exc}"))

    claude_md = root / "CLAUDE.md"
    if claude_md.is_symlink() or claude_md.exists():
        bridged = (claude_md.is_symlink() and "AGENTS.md" in str(claude_md.readlink())) or (
            claude_md.is_file() and "AGENTS.md" in claude_md.read_text(encoding="utf-8")
        )
        out.append(
            CheckResult(
                "CLAUDE.md -> AGENTS.md",
                bridged,
                "bridged" if bridged else "CLAUDE.md does not reference AGENTS.md",
            )
        )
    return out


def _agent_config_checks(root: Path) -> list[CheckResult]:
    return _check_opencode(root) + _check_claude(root)


def _check_skills_manifest(root: Path) -> list[CheckResult]:
    """CES-107: the manifest is tracked, and the derived tree matches what it declares."""
    manifest = read_manifest(root)
    if manifest is None:
        return [
            CheckResult(
                "skills manifest",
                False,
                f"{MANIFEST_FILE} missing or unreadable — run `scaffolding install skills`",
            )
        ]

    out: list[CheckResult] = []
    ignored = _gitignored(root, MANIFEST_FILE)
    out.append(
        CheckResult(
            "skills manifest not ignored",
            not ignored,
            "ok" if not ignored else f"remove {MANIFEST_FILE} from .gitignore — it must be tracked",
        )
    )
    # Tracking is checked separately from ignoring: the engine never touches the git
    # index, so `git add` stays a human act that this check enforces.
    tracked = _git_tracked(root, MANIFEST_FILE)
    out.append(
        CheckResult(
            "skills manifest tracked",
            tracked,
            "tracked" if tracked else f"exists but untracked — run `git add {MANIFEST_FILE}`",
        )
    )

    installed = set(installed_names(root, AGENTS_SKILLS_DIR))
    missing = sorted(manifest.names - installed)
    out.append(
        CheckResult(
            "declared skills installed",
            not missing,
            "ok"
            if not missing
            else f"declared but not in {AGENTS_SKILLS_DIR}: {', '.join(missing)}",
        )
    )
    return out


def run_checks(root: Path | None = None) -> list[CheckResult]:
    root = root or Path.cwd()
    results: list[CheckResult] = []

    gi = root / ".gitignore"
    if gi.exists():
        present = {ln.rstrip() for ln in gi.read_text(encoding="utf-8").splitlines()}
        missing = [e for e in GITIGNORE_ENTRIES if e not in present]
        results.append(
            CheckResult(
                ".gitignore entries",
                not missing,
                "all present" if not missing else f"missing: {', '.join(missing)}",
            )
        )
    else:
        results.append(CheckResult(".gitignore entries", False, ".gitignore missing"))

    prek = root / "prek.toml"
    if prek.exists():
        body = prek.read_text(encoding="utf-8")
        results.append(
            CheckResult(
                "prek betterleaks hook",
                "betterleaks" in body,
                "present" if "betterleaks" in body else "betterleaks hook missing",
            )
        )
    else:
        results.append(CheckResult("prek.toml", False, "prek.toml missing"))

    # Agent config is per-agent and optional: validate whatever is present rather than
    # requiring opencode.jsonc. AGENTS.md (checked below) is the only universal requirement.
    results += _agent_config_checks(root)

    schema = root / ".env.schema"
    if schema.exists():
        tracked = _git_tracked(root, ".env.schema")
        results.append(
            CheckResult(
                ".env.schema tracked",
                tracked,
                "tracked" if tracked else "exists but not tracked by git",
            )
        )
    else:
        results.append(CheckResult(".env.schema", False, "missing (run varlock)"))

    env_ignored = _gitignored(root, ".env")
    results.append(
        CheckResult(
            ".env ignored", env_ignored, "ignored" if env_ignored else ".env is not gitignored"
        )
    )

    sg = root / "sgconfig.yml"
    prek_has_astgrep = prek.exists() and "ast-grep" in prek.read_text(encoding="utf-8")
    if prek_has_astgrep:
        rules = (
            list((root / "ast-grep" / "rules").glob("*.yml"))
            if (root / "ast-grep" / "rules").exists()
            else []
        )
        ok = sg.exists() and bool(rules)
        results.append(
            CheckResult(
                "ast-grep config",
                ok,
                "ok" if ok else "ast-grep hook present but sgconfig.yml/rules missing",
            )
        )

    results += _check_skills_manifest(root)

    am = root / "AGENTS.md"
    if am.exists():
        has = AGENTS_MARKER in am.read_text(encoding="utf-8")
        results.append(
            CheckResult("AGENTS.md section", has, "present" if has else f"{AGENTS_MARKER} missing")
        )
    else:
        results.append(CheckResult("AGENTS.md", False, "missing"))

    return results
