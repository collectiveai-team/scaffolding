"""Derive a proposal's review state from reviewer votes recorded as issue comments.

`state:approved` and `state:declined` are DERIVED: no human and no model writes them
(see the `PROTECTED` guards in `.github/workflows/proposal-update.yml`). They are the
output of this tally, whose only input is the comment ledger of the issue.

The tally is **stateless** — every run replays the whole ledger from the last reset
marker, so a missed webhook, a hand-edited label, or a re-run all converge on the same
answer. Labels are a derived mirror for the board, never the source of truth.

Ledger rules:

- A vote is a comment whose line starts with `/approve`, `/object`, `/decline` or
  `/withdraw`.
- **One vote per account.** Votes reduce to a map keyed by login and the account's
  LAST command wins, so re-voting replaces rather than accumulates.
- Only accounts with write access to the repo are counted, checked per-login and
  failing closed. The repo is public, so anyone can type `/approve`.
- Comments before the newest reset marker are ignored: revising the body dismisses
  approvals (they were cast against text that no longer exists).
- An objection is sticky — a revision does NOT clear it, only the objector's
  `/withdraw` does. Otherwise an author lifts objections by editing.
- Silence can approve (lazy consensus) but never decline.
- `state:declined` is terminal and `state:had-comments` survives an empty ledger:
  an approval must be earned, a block is preserved.

Run: uv run python scripts/proposal_vote.py tally --issue 147
     uv run python scripts/proposal_vote.py sweep
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, replace

import cyclopts

QUORUM = 2
LAZY_DAYS = 7
WARN_DAYS = 5

PROPOSAL = "state:proposal"
HAD_COMMENTS = "state:had-comments"
APPROVED = "state:approved"
DECLINED = "state:declined"
STATE_LABELS = frozenset({PROPOSAL, HAD_COMMENTS, APPROVED, DECLINED})
# Read an ambiguous board (an issue carrying two state labels, which hand-labelling
# has already produced) in the direction that blocks.
STATE_PRECEDENCE = (DECLINED, HAD_COMMENTS, APPROVED, PROPOSAL)

# How an approval was won. `state:approved` stays the single state so queries and
# downstream tooling don't fork, but the board must say which approvals nobody
# actually read: `label:approved:lazy` is the audit query for that.
BY_QUORUM = "approved:quorum"
BY_LAZY = "approved:lazy"
PROVENANCE_LABELS = frozenset({BY_QUORUM, BY_LAZY})

RESET_MARKER = "<!-- proposal-vote:reset -->"
TALLY_MARKER = "<!-- proposal-vote:tally -->"
WARN_MARKER = "<!-- proposal-vote:warn -->"
CALL_MARKER = "<!-- proposal-vote:review-call -->"

WRITE_ROLES = frozenset({"admin", "maintain", "write"})
COMMAND = re.compile(r"^[ \t]*/(approve|object|decline|withdraw)\b", re.MULTILINE)

app = cyclopts.App(name="proposal-vote", help=__doc__)


@dataclass(frozen=True)
class Comment:
    """A single issue comment from the gh payload."""

    login: str
    body: str
    at: dt.datetime
    is_bot: bool


@dataclass(frozen=True)
class Command:
    """One vote command parsed from a comment."""

    login: str
    verb: str
    at: dt.datetime


@dataclass(frozen=True)
class Tally:
    """Who currently stands where, after one-vote-per-account reduction."""

    approvals: tuple[str, ...] = ()
    objections: tuple[str, ...] = ()
    declines: tuple[str, ...] = ()
    since: dt.datetime | None = None
    # Every eligible account that issued any command, including a /withdraw that
    # left no standing vote. This is "has the ledger been touched", not "who agrees".
    spoke: tuple[str, ...] = ()

    def age_days(self, now: dt.datetime) -> float:
        if self.since is None:
            return 0.0
        return (now - self.since).total_seconds() / 86400.0


@dataclass(frozen=True)
class Decision:
    """The derived state plus the label writes that realise it."""

    state: str
    reason: str
    warn: bool = False
    votes: tuple[str, ...] = field(default_factory=tuple)
    provenance: str = ""


@dataclass(frozen=True)
class Audience:
    """Who may vote, and who to interrupt about it."""

    electorate: frozenset[str]
    team: str = ""
    team_members: tuple[str, ...] = ()


@dataclass(frozen=True)
class Outcome:
    """Everything one issue's run resolved to, for the notification pass."""

    decision: Decision
    tally: Tally
    comments: list[Comment]
    since: dt.datetime
    now: dt.datetime
    moved: bool


def parse_commands(comments: list[Comment], since: dt.datetime | None) -> list[Command]:
    """Extract vote commands from comments cast after `since`, in chronological order."""
    found: list[Command] = []
    for comment in sorted(comments, key=lambda c: c.at):
        if since is not None and comment.at <= since:
            continue
        if comment.is_bot:
            continue
        found.extend(
            Command(login=comment.login, verb=match.group(1), at=comment.at)
            for match in COMMAND.finditer(comment.body)
        )
    return found


def tally(commands: list[Command], eligible: frozenset[str]) -> Tally:
    """Reduce commands to at most one standing vote per account (last command wins)."""
    standing: dict[str, str] = {}
    for command in commands:
        if command.login not in eligible:
            continue
        if command.verb == "withdraw":
            standing.pop(command.login, None)
        else:
            standing[command.login] = command.verb

    def who(verb: str) -> tuple[str, ...]:
        return tuple(sorted(login for login, v in standing.items() if v == verb))

    return Tally(
        approvals=who("approve"),
        objections=who("object"),
        declines=who("decline"),
        spoke=tuple(sorted({c.login for c in commands if c.login in eligible})),
    )


def current_state(labels: set[str]) -> str:
    """Report the state an issue already carries, resolved blocking-first if it has two."""
    return next((state for state in STATE_PRECEDENCE if state in labels), "")


def decide(
    counted: Tally, now: dt.datetime, *, quorum: int = QUORUM, current: str = ""
) -> Decision:
    """Map a tally onto the derived review state.

    Asymmetric on purpose: an approval must be *earned* from the ledger, while a
    decline or an open objection is *preserved* when the ledger is silent. Being
    wrong towards "blocked" costs a re-vote; being wrong towards "approved" ships a
    standard nobody read.
    """
    # Terminal. A declined proposal's CES number is burned and never reused
    # (docs/engineering-standards.md:32), so no later vote may silently resurrect it
    # — reopening is a deliberate act: remove the label by hand.
    if current == DECLINED:
        return Decision(DECLINED, "declined (terminal — remove the label by hand to reopen)")
    # Silence is not consent, so it cannot clear an objection. Note this keys on
    # `spoke`, not on standing votes: a /withdraw leaves nothing standing but is an
    # explicit act, and must hand control back to the ledger.
    if current == HAD_COMMENTS and not counted.spoke:
        return Decision(HAD_COMMENTS, "untouched ledger — existing objection preserved")

    age = counted.age_days(now)
    if len(counted.declines) >= quorum:
        return Decision(
            DECLINED, f"declined by {len(counted.declines)} reviewers", votes=counted.declines
        )
    if counted.objections:
        return Decision(HAD_COMMENTS, f"objection open from {', '.join(counted.objections)}")
    if len(counted.approvals) >= quorum:
        return Decision(
            APPROVED,
            f"quorum {len(counted.approvals)}/{quorum}",
            votes=counted.approvals,
            provenance=BY_QUORUM,
        )
    if counted.approvals and age >= LAZY_DAYS:
        return Decision(
            APPROVED,
            f"lazy consensus: {age:.0f}d since last revision, no objection",
            votes=counted.approvals,
            provenance=BY_LAZY,
        )
    warn = bool(counted.approvals) and WARN_DAYS <= age < LAZY_DAYS
    return Decision(PROPOSAL, f"awaiting review ({len(counted.approvals)}/{quorum})", warn=warn)


def _ts(raw: str) -> dt.datetime:
    return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _gh(args: list[str]) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def _load_comments(payload: list[dict]) -> list[Comment]:
    return [
        Comment(
            login=(c.get("author") or {}).get("login", ""),
            body=c.get("body") or "",
            at=_ts(c["createdAt"]),
            is_bot=(c.get("author") or {}).get("login", "").endswith("[bot]"),
        )
        for c in payload
    ]


def last_reset(comments: list[Comment], fallback: dt.datetime) -> dt.datetime:
    """Timestamp of the newest reset marker, i.e. the revision votes are cast against."""
    resets = [c.at for c in comments if c.is_bot and RESET_MARKER in c.body]
    return max(resets) if resets else fallback


def writers(repo: str) -> frozenset[str]:
    """Every human account with write access — the electorate and the notify list.

    One call, and it fails closed: if it raises, the run aborts before writing any
    label rather than tallying against an empty or partial electorate. This repo is
    public, so an unfiltered ledger would let a stranger cast `/approve`.
    """
    raw = json.loads(_gh(["api", f"repos/{repo}/collaborators", "--paginate"]))
    return frozenset(
        person["login"]
        for person in raw
        if person.get("type") == "User"
        and not person["login"].endswith("[bot]")
        and (person.get("role_name") or "").lower() in WRITE_ROLES
    )


def _apply(repo: str, number: int, decision: Decision, current: set[str]) -> bool:
    """Write the derived labels. Returns True when the state label actually moved.

    Any other `state:*` label is dropped, so an issue carrying two of them (which
    hand-labelling has already produced) is healed rather than left ambiguous.
    """
    keep = {f"vote:{login}" for login in decision.votes}
    want = keep | {decision.state} | ({decision.provenance} if decision.provenance else set())
    add = want - current
    remove = (
        ({lab for lab in current if lab.startswith("vote:")} - keep)
        | ((STATE_LABELS - {decision.state}) & current)
        | ((PROVENANCE_LABELS - want) & current)
    )
    for label in sorted(add):
        _gh(["label", "create", label, "--repo", repo, "--force"])
    args = [a for label in sorted(add) for a in ("--add-label", label)]
    args += [a for label in sorted(remove) for a in ("--remove-label", label)]
    if args:
        _gh(["issue", "edit", str(number), "--repo", repo, *args])
    return decision.state not in current


def _comment(repo: str, number: int, marker: str, body: str) -> None:
    _gh(["issue", "comment", str(number), "--repo", repo, "--body", f"{marker}\n{body}"])


def _posted_since(comments: list[Comment], marker: str, since: dt.datetime) -> bool:
    return any(c.is_bot and marker in c.body and c.at > since for c in comments)


def resolve_team(team: str) -> tuple[str, ...]:
    """Members of `org/slug`, or `()` when this token cannot see the org.

    A misspelled slug renders as plain text and notifies **nobody**, so a definitive
    404 is fatal — silent non-delivery is the worst outcome for a review gate. A 403
    is merely unverifiable: GITHUB_TOKEN is repo-scoped and cannot read org teams, so
    we fall back to a raw team mention there.
    """
    if "/" not in team:
        raise SystemExit(f"--team must be 'org/slug', got {team!r}")
    org, slug = team.split("/", 1)
    try:
        raw = _gh(["api", f"orgs/{org}/teams/{slug}/members", "--paginate"])
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "") + (exc.stdout or "")
        if "Not Found" in detail or "404" in detail:
            raise SystemExit(
                f"team {team!r} does not exist — a bad slug notifies nobody, silently"
            ) from exc
        print(f"  cannot read {team} members ({detail.strip()[:80]}) — mentioning the team")
        return ()
    return tuple(sorted(p["login"] for p in json.loads(raw)))


def _ping(audience: Audience, heard: set[str]) -> str:
    """Who still owes a vote.

    Individual mentions are used whenever the team roster is knowable, because a
    team mention authored by github-actions[bot] is not reliably delivered.
    """
    roster = frozenset(audience.team_members) if audience.team_members else audience.electorate
    outstanding = sorted(roster - heard)
    if not outstanding:
        return "_everyone has voted_"
    if audience.team and not audience.team_members:
        return f"@{audience.team}"
    return " ".join(f"@{login}" for login in outstanding)


def _announce(repo: str, issue: int, ctx: Outcome, audience: Audience) -> None:
    """Post at most the two notifications worth interrupting people for.

    Deliberately NOT one per vote: a repo that pings on every event gets muted, and a
    muted repo has no reviewers.
    """
    decision, counted, comments, since = ctx.decision, ctx.tally, ctx.comments, ctx.since
    heard = set(counted.approvals) | set(counted.objections) | set(counted.declines)

    if ctx.moved and decision.state in {APPROVED, DECLINED}:
        roll = ", ".join(f"@{login}" for login in decision.votes)
        _comment(
            repo, issue, TALLY_MARKER, f"**{decision.state}** — {decision.reason}.\nVotes: {roll}."
        )
    # First approval on this revision = "ready for review". That is the moment a
    # second pair of eyes is actually needed, so that is when we interrupt people.
    if (
        decision.state == PROPOSAL
        and counted.approvals
        and not _posted_since(comments, CALL_MARKER, since)
    ):
        _comment(
            repo,
            issue,
            CALL_MARKER,
            f"Ready for review — {_ping(audience, heard)}\n\n"
            f"`/approve` to support, `/object <reason>` to block, `/withdraw` to retract. "
            f"Needs {QUORUM} approvals; auto-approves after {LAZY_DAYS}d without objection.",
        )
    # Announce before the clock runs out; a silent auto-approval is just a
    # rubber stamp with extra steps. Once per revision, hence the marker check.
    if decision.warn and not _posted_since(comments, WARN_MARKER, since):
        _comment(
            repo,
            issue,
            WARN_MARKER,
            f"{_ping(audience, heard)} — auto-approves under lazy consensus in "
            f"{LAZY_DAYS - counted.age_days(ctx.now):.0f} day(s) "
            f"({len(counted.approvals)} approval, no objection). `/object` to stop the clock.",
        )


@app.command
def tally_issue(issue: int, *, repo: str = "", now: str = "", team: str = "") -> None:
    """Re-tally one proposal issue and write its derived state.

    `--team` mentions a GitHub team (`org/slug`) instead of naming individuals.
    """
    repo = repo or _gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]).strip()
    raw = json.loads(
        _gh(["issue", "view", str(issue), "--repo", repo, "--json", "comments,labels,createdAt"])
    )
    comments = _load_comments(raw["comments"])
    since = last_reset(comments, _ts(raw["createdAt"]))
    audience = Audience(
        electorate=writers(repo),
        team=team,
        team_members=resolve_team(team) if team else (),
    )
    counted = replace(tally(parse_commands(comments, since), audience.electorate), since=since)
    moment = _ts(now) if now else dt.datetime.now(dt.UTC)
    labels = {lab["name"] for lab in raw["labels"]}
    decision = decide(counted, moment, current=current_state(labels))
    moved = _apply(repo, issue, decision, labels)
    print(f"#{issue}: {decision.state} — {decision.reason}")
    _announce(repo, issue, Outcome(decision, counted, comments, since, moment, moved), audience)


@app.command
def sweep(*, repo: str = "", team: str = "") -> None:
    """Re-tally every open proposal — the cron arm that lets the lazy-consensus clock fire."""
    repo = repo or _gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]).strip()
    listing = _gh(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--label",
            "type:proposal",
            "--state",
            "open",
            "--limit",
            "200",
            "--json",
            "number",
            "-q",
            ".[].number",
        ]
    )
    for line in listing.split():
        tally_issue(int(line), repo=repo, team=team)


if __name__ == "__main__":
    sys.exit(app())
