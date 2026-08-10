"""Behaviour of the proposal vote tally.

Asserted through the public seam (`parse_commands` -> `tally` -> `decide`), the same
pipeline the workflow runs, rather than through internals (CES-65).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "proposal_vote", Path(__file__).resolve().parents[1] / "scripts" / "proposal_vote.py"
)
assert _SPEC is not None
assert _SPEC.loader is not None
pv = importlib.util.module_from_spec(_SPEC)
sys.modules["proposal_vote"] = pv
_SPEC.loader.exec_module(pv)

T0 = dt.datetime(2026, 8, 1, tzinfo=dt.UTC)
REVIEWERS = frozenset({"jedzill4", "dmazzini", "ahaimo"})


def comment(login: str, body: str, *, day: int = 1, bot: bool = False) -> object:
    return pv.Comment(
        login=login,
        body=body,
        at=T0 + dt.timedelta(days=day),
        is_bot=bot,
    )


def run(comments: list, *, eligible=REVIEWERS, since=T0, at_day: int = 2, current: str = ""):
    commands = pv.parse_commands(comments, since)
    counted = dataclasses.replace(pv.tally(commands, eligible), since=since)
    return pv.decide(counted, T0 + dt.timedelta(days=at_day), current=current)


def test_two_distinct_accounts_reach_quorum():
    decision = run([comment("jedzill4", "/approve"), comment("dmazzini", "/approve")])
    assert decision.state == pv.APPROVED
    assert decision.votes == ("dmazzini", "jedzill4")


def test_one_account_cannot_vote_twice():
    """The whole gate collapses if repeated /approve accumulates."""
    decision = run(
        [
            comment("jedzill4", "/approve", day=1),
            comment("jedzill4", "/approve", day=1),
            comment("jedzill4", "/approve\n/approve", day=1),
        ]
    )
    assert decision.state == pv.PROPOSAL
    assert "1/2" in decision.reason


def test_stranger_without_write_access_is_ignored():
    """Public repo: anyone can type /approve."""
    decision = run([comment("jedzill4", "/approve"), comment("drive-by", "/approve")])
    assert decision.state == pv.PROPOSAL


def test_bot_comments_never_vote():
    decision = run(
        [comment("jedzill4", "/approve"), comment("github-actions[bot]", "/approve", bot=True)]
    )
    assert decision.state == pv.PROPOSAL


def test_last_command_wins():
    decision = run(
        [
            comment("jedzill4", "/approve", day=1),
            comment("dmazzini", "/approve", day=1),
            comment("dmazzini", "/object on reflection, no", day=2),
        ],
        at_day=3,
    )
    assert decision.state == pv.HAD_COMMENTS


def test_withdraw_retracts_a_standing_vote():
    decision = run(
        [
            comment("jedzill4", "/approve", day=1),
            comment("dmazzini", "/approve", day=1),
            comment("dmazzini", "/withdraw", day=2),
        ],
        at_day=3,
    )
    assert decision.state == pv.PROPOSAL


def test_objection_vetoes_even_at_quorum():
    decision = run(
        [
            comment("jedzill4", "/approve"),
            comment("dmazzini", "/approve"),
            comment("ahaimo", "/object the pattern misses decorated defs"),
        ]
    )
    assert decision.state == pv.HAD_COMMENTS


def test_votes_before_the_reset_marker_are_dismissed():
    decision = run(
        [comment("jedzill4", "/approve", day=1), comment("dmazzini", "/approve", day=1)],
        since=T0 + dt.timedelta(days=2),
        at_day=3,
    )
    assert decision.state == pv.PROPOSAL


def test_lazy_consensus_needs_an_approval_and_time():
    votes = [comment("jedzill4", "/approve", day=1)]
    assert run(votes, at_day=3).state == pv.PROPOSAL
    assert run(votes, at_day=9).state == pv.APPROVED
    assert "lazy consensus" in run(votes, at_day=9).reason


def test_silence_alone_never_approves():
    """Zero approvals plus elapsed time must stay put.

    This is what makes the migration safe: no existing proposal has a vote, so
    switching on the cron cannot mass-approve anything.
    """
    assert run([], at_day=99).state == pv.PROPOSAL


def test_objection_stops_the_lazy_clock():
    decision = run(
        [comment("jedzill4", "/approve", day=1), comment("ahaimo", "/object", day=1)],
        at_day=99,
    )
    assert decision.state == pv.HAD_COMMENTS


def test_warning_fires_before_auto_approval():
    votes = [comment("jedzill4", "/approve", day=1)]
    assert run(votes, at_day=3).warn is False
    assert run(votes, at_day=6).warn is True
    # Past the deadline it has already auto-approved, so there is nothing to warn about.
    assert run(votes, at_day=9).warn is False
    assert run(votes, at_day=9).state == pv.APPROVED


def test_decline_requires_quorum_and_is_never_implicit():
    one = [comment("jedzill4", "/decline")]
    assert run(one, at_day=99).state == pv.PROPOSAL
    two = [*one, comment("dmazzini", "/decline")]
    assert run(two).state == pv.DECLINED


def test_approval_records_how_it_was_won():
    """Provenance must be queryable.

    `label:approved:lazy` is the audit of what got in without a second reader.
    """
    quorum = run([comment("jedzill4", "/approve"), comment("dmazzini", "/approve")])
    assert (quorum.state, quorum.provenance) == (pv.APPROVED, pv.BY_QUORUM)

    lazy = run([comment("jedzill4", "/approve", day=1)], at_day=9)
    assert (lazy.state, lazy.provenance) == (pv.APPROVED, pv.BY_LAZY)

    assert run([]).provenance == ""
    assert pv.BY_QUORUM != pv.BY_LAZY


def test_lazy_approval_is_reversible_by_a_late_objection():
    """Statelessness earns this: nothing is latched, so a late reader still wins."""
    votes = [comment("jedzill4", "/approve", day=1)]
    assert run(votes, at_day=9).state == pv.APPROVED
    late = [*votes, comment("ahaimo", "/object hold on", day=10)]
    assert run(late, at_day=11).state == pv.HAD_COMMENTS


def test_ping_targets_only_those_who_have_not_voted():
    room = pv.Audience(electorate=frozenset({"jedzill4", "dmazzini", "ahaimo"}))
    assert pv._ping(room, {"jedzill4"}) == "@ahaimo @dmazzini"
    assert pv._ping(room, set(room.electorate)) == "_everyone has voted_"


def test_a_resolved_team_narrows_the_ping_to_its_members():
    """The team defines who to ask; the electorate defines who may vote."""
    room = pv.Audience(
        electorate=frozenset({"jedzill4", "dmazzini", "ahaimo", "jansaldo"}),
        team="collectiveai-team/botique",
        team_members=("jedzill4", "lionelchamorro"),
    )
    assert pv._ping(room, set()) == "@jedzill4 @lionelchamorro"
    assert pv._ping(room, {"jedzill4"}) == "@lionelchamorro"


def test_unresolvable_team_falls_back_to_a_team_mention():
    """GITHUB_TOKEN cannot read org teams, so CI lands here."""
    room = pv.Audience(
        electorate=frozenset({"jedzill4", "dmazzini"}),
        team="collectiveai-team/botique",
        team_members=(),
    )
    assert pv._ping(room, set()) == "@collectiveai-team/botique"


def test_team_slug_must_be_qualified():
    with pytest.raises(SystemExit, match="org/slug"):
        pv.resolve_team("botique")


@pytest.mark.parametrize(
    ("body", "counts"),
    [
        ("/approve", True),
        ("  /approve  ", True),
        ("/approve looks good to me", True),
        ("sounds good, /approve", False),
        ("> /approve", False),
        ("`/approve`", False),
        ("/approved", False),
        ("/approvex", False),
    ],
)
def test_only_a_leading_command_counts(body: str, counts: bool):
    """Quoting someone else's vote must not cast one."""
    found = pv.parse_commands([comment("jedzill4", body)], T0)
    assert bool(found) is counts


def test_a_decline_is_terminal():
    """The CES number is burned, so nothing may silently resurrect it."""
    assert run([], current=pv.DECLINED).state == pv.DECLINED
    revival = [comment("jedzill4", "/approve"), comment("dmazzini", "/approve")]
    assert run(revival, current=pv.DECLINED).state == pv.DECLINED


def test_an_open_objection_survives_an_empty_ledger():
    """#69 has sat in had-comments for weeks with no ledger — keep it there."""
    assert run([], current=pv.HAD_COMMENTS).state == pv.HAD_COMMENTS
    assert run([], at_day=99, current=pv.HAD_COMMENTS).state == pv.HAD_COMMENTS


def test_a_ledger_still_overrides_had_comments():
    """Preserved only while silent: once someone votes, derivation takes over."""
    withdrawn = [comment("ahaimo", "/object", day=1), comment("ahaimo", "/withdraw", day=2)]
    assert run(withdrawn, at_day=3, current=pv.HAD_COMMENTS).state == pv.PROPOSAL


def test_an_unearned_approval_is_revoked():
    """The other half of the asymmetry: approvals must be earned from the ledger."""
    assert run([], current=pv.APPROVED).state == pv.PROPOSAL
    assert run([], at_day=99, current=pv.APPROVED).state == pv.PROPOSAL


def test_a_double_labelled_issue_reads_as_the_blocking_state():
    assert pv.current_state({pv.APPROVED, pv.PROPOSAL}) == pv.APPROVED
    assert pv.current_state({pv.DECLINED, pv.APPROVED}) == pv.DECLINED
    assert pv.current_state({pv.HAD_COMMENTS, pv.PROPOSAL}) == pv.HAD_COMMENTS
    assert pv.current_state(set()) == ""
