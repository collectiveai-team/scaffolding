---
name: test-smell-review
description: Review pytest/unittest tests for false-green smells — tests that pass without protecting anything (empty, assertion-free, tautological, mocking the unit under test, echoing a mock back to itself). Use after writing or editing test files, and when the user asks to review test quality, find weak tests, or check whether tests actually catch bugs.
---

# Test Smell Review

A test suite that is 100% green is not proof the code is correct — it is only
proof that no test failed. Apply this judgment whenever tests are written,
edited, or explicitly reviewed: **a test is useful only if some incorrect
implementation would make it fail.** If no such implementation exists, the
test is structurally green regardless of whether the code is right.

This skill exists because the obvious approach — installing `falsegreen-skill`
(the upstream npm package this is adapted from) and shelling out to it — is a
poor fit for an agentic coding session: it makes a second, separate LLM API
call (its own API key, its own cost, non-deterministic on top of the
in-context judgment the current agent can already make), and it installs as a
Node CLI in a Python-only repo. This skill instead teaches the current agent
session to apply the same judgment framework **directly, in-context, with no
subprocess call** — zero extra cost, zero extra runtime, works identically
across every agent host this repo already targets.

## Step 0: run the deterministic scanner first, if installed

If `falsegreen` (`pip install falsegreen`) is available in the project, run it
on the changed test files before applying any judgment below — it proves the
purely structural cases (empty test, no assertion, tautological assert,
swallowed exception, sleep-in-test, and 40+ more) deterministically, for free,
with no LLM involved:

```bash
falsegreen tests/test_changed_file.py
```

Everything it flags is already proven by a parser; do not re-derive those
findings by hand. Apply the judgment protocol below only to what a parser
cannot prove — that is what it is for.

## The six judgments (J1–J6)

For each test, ask these in order and stop at the first one that fails:

| # | Question | Catches |
|---|---|---|
| J1 | Does the assertion actually run? | Dead code after `return`, a loop over an empty collection, an exception swallowed before the assert |
| J2 | Is the expected value from an independent source, not the code's own output? | Asserting a mock's `return_value` back at itself (an echo), re-deriving the production formula as the "expected" value |
| J3 | Is the real unit under test — not a mock standing in for it? | Patching the function being tested instead of one of its dependencies |
| J4 | Does the assertion verify enough? | Truthiness-only checks, `len(x) > 0`, a `str()`/`repr()` comparison that checks formatting instead of the value |
| J5 | Is the test coupled to implementation internals rather than behavior? | Asserting on a mock's positional call args by a computed index, testing a private method directly |
| J6 | Does the test pass in isolation, independent of run order? | Shared mutable module-level state, a test that only passes because an earlier test happened to run first |

Flag **HIGH** only when the failed judgment has no plausible legitimate
interpretation (a mock echoing itself is never a real check). Flag **LOW**
when the smell is likely but a legitimate reading exists. Everything else is
**PASS** — say nothing about it.

## Precision rules (do not over-flag)

- Case 18 ("the expected value contradicts the spec") requires an actual cited
  spec, docstring, or API contract. Without a citation, do not report it —
  that is a judgment call for a human, not something to assert from thin air.
- A characterization test — one deliberately freezing today's behavior during
  a refactor — is not a false positive. Ask before flagging one if the intent
  isn't stated in the test name/docstring.
- Boolean predicates (`isinstance(...)`, `.exists()`, `.is_dir()`) are real
  assertions, not weak truthiness checks.
- At the integration/API/E2E level, a truthiness check on a response or a
  rendered element often *is* the real check (the response existing is the
  point) — do not apply unit-level strictness to a test that is deliberately
  crossing an I/O boundary.

## Reporting a finding

For each real finding, give: the file and line, which judgment failed (J1–J6),
a one-line reason, and a concrete fix — an independent expected value or a
narrower assertion, not just "add more asserts":

```
tests/test_discount.py:14  [J2] HIGH
  Asserts mock_rate.return_value back at itself — passes for any return
  value, including a wrong one.
  Fix: assert the real computed result, e.g. `assert result == 90` (10% off
  100, from the spec), not `assert result == mock_rate.return_value`.
```

## Credit

This skill's protocol is adapted from
[`falsegreen-skill`](https://github.com/vinicq/falsegreen-skill)'s J1–J6
framework and case catalog (itself building on Soares 2023's "rotten green
test" thesis and Delplanque et al., ICSE 2019) — reimplemented here as
native, in-context agent instructions instead of an external Node CLI that
calls a second LLM. The companion deterministic scanner referenced in Step 0
is [`falsegreen`](https://github.com/vinicq/falsegreen) (unrelated adaptation
concern — it's a real static AST pass, not an LLM call, and is proposed as a
house prek hook separately). Full case catalog, if a finding needs more
detail than this condensed version covers:
https://github.com/vinicq/falsegreen-skill/blob/master/reference.md.
