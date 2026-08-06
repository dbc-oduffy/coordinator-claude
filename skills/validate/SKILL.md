---
name: validate
description: "Run the project's fast test command at a cadence gate: merge, workday/workstream close, or ask."
version: 2.0.0
---

# Local CI Validation

Resolve and run the project's fast-tier validation command at cadence gates — merging, completing a workday/workstream, or an explicit 'does everything pass?' check.

## What It Does

Resolves the fast-test command via a three-step resolver (`cs_resolve_fast_test_cmd`), then executes the resolved command and captures its exit code into the `Validation:` enum.

### Resolution order (three steps — no conventional fallback)

1. **`COORDINATOR_FAST_TEST_CMD` env var** — if set and non-empty, use it verbatim. Escape hatch for one-off runs, CI overrides, and dogfood sessions.
2. **`coordinator.local.md` flat `fast_test_cmd:` key** — if `coordinator.local.md` exists at repo root and `fast_test_cmd:` is a non-empty string, use it.
3. **Skip-with-notice** — neither (1) nor (2) resolved. Emit a diagnostic to stderr naming both remediation paths (env var, local.md). Exit 2. Populate `Validation: skipped` and proceed to the next workday/workweek step.

There is no conventional fallback to `.github/scripts/run-all-checks.py`. The meta-repo (`~/.claude`) opts in explicitly by setting `fast_test_cmd: python .github/scripts/run-all-checks.py` in its own `coordinator.local.md`. Every repo must declare its fast-test or receive skip-with-notice.

<!-- negative-spec: do not restore the conventional fallback step as a fourth resolution step — that reintroduces scatter-by-implicit-convention -->

### Trust model

`COORDINATOR_FAST_TEST_CMD` is invoked verbatim with **no sanitization** — set it only from trusted contexts (local shell, CI-managed env, dogfood session). The `coordinator.local.md` `fast_test_cmd:` key is repo-local committed config and inherits whatever trust attaches to that file's review history (it ships through normal PR review). The resolver does NOT validate, escape, or filter either value — the assumption is that whoever set it is trusted to execute arbitrary commands in this repo. An agent or pipeline should NEVER set `COORDINATOR_FAST_TEST_CMD` from an untrusted source (a memo body, a webhook payload, a third-party file).

## How to Run

Run the claude-klabauter-resident `validate-fast-and-packageability` CLI's `fast` subcommand — a
naked-Python port of the resolver ladder (mktemp diagnostic capture + rc==2/126/other-nonzero/0
classification) this fence used to inline as bash. It resolves the fast-test command via
`coordinator_resolve_validation_cmd` in-process, executes it via `bash -c` when one resolves, and
prints exactly one `Validation: <value>` line to stdout matching the Exit Code → `Validation:`
Mapping table below:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/validate-fast-and-packageability" fast`

Run this using the Bash tool from the repo root. Read the full output — every script's pass/fail status and any error details.

### Packageability-contract check (DoE-local, opt-in-scoped)

DoE-claude additionally runs the engine-resident `validate-install-contract.py` (relocation
history: `CLAUDE.md § Build & Test`; resolution: `snippets/resolve-coordinator-bin.md`) against its own
`coordinator/docs/install/agent-install-manifest.json` as an extra fast-tier check —
this is DoE validating ITS OWN manifest, at DoE's own request, not a fleet-wide gate. The
validator is self-scoping: it SKIP-CLEANs (exit 0) on any repo whose manifest hasn't
opted in via `packageability_compliance.declared: true`, so this step is safe to run even
against a not-yet-compliant sibling clone — it never fails a repo out that hasn't asked
to be held to the contract. Run it after the resolved `fast_test_cmd` above, as an
independently-reported line — NOT folded into `VALIDATION_RESULT`:

Run the same CLI's `packageability` subcommand — it runs the co-located
`validate-install-contract.py` against this repo's own manifest, loud-skipping (WARN to stderr,
exit 0) when that script is absent from an otherwise-valid `coordinator/bin`, and prints exactly
one `Packageability: <exit-code>` line:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/validate-fast-and-packageability" packageability`

This reports as its own `Packageability: <exit-code>` line, distinct from `Validation:` above
— `VALIDATION_RESULT` is untouched by this check.

Do NOT wire `validate-install-contract.py` into any cross-repo/fleet-shared hook —
it is invoked only against a repo's own manifest, at that repo's own request. Each sibling repo that wants this check
adds its own equivalent line once it has brought its own manifest to compliance and
opted in.

### Tier classification is by shape, not by config key

The resolved command is Tier F only when it is itself path-scoped (names specific test files,
directories, or node-ids) — a repo that declares an unscoped `fast_test_cmd` (including the
common tie case where `fast_test_cmd` and `full_test_cmd` coincide, e.g. no `full_test_cmd` was
ever declared) is resolving Tier U, not Tier F, regardless of which key the command came from.
A marker filter (`-m '<expr>'`) is **not** scope — it is unverifiable without collecting, and
counting it would give every Tier-U gate a one-token bypass.
The test-breadth ladder has three tiers: Tier T (path-scoped, everyone including subagents,
ungated), Tier F (the repo's `fast_test_cmd`, when itself path-scoped — top-level EM only, and
only under a live grant — see § Grant-consuming below), and Tier U (the full suite, or any
unscoped runner regardless of which config key it came from — top-level EM only, and only under a
live grant). This shape classification is unchanged by grant-gating: the classifier still answers
only *what shape is this command*, never *is this caller authorized* — the grant check below is a
separate, authority-layer step, not a new input to classification, per the standing prohibition
against teaching the shape classifier about the grant. Expect this skill to classify the resolved
command and refuse to run an unscoped one absent a live Tier-U grant, naming the four honest
exits — scope `fast_test_cmd`; declare `fast_tier_unscoped_reason: "<why>"` in
`coordinator.local.md` when the repo's fast/full axis genuinely is not path-shaped (a declaration
covering only the literal resolved `fast_test_cmd` run by the top-level EM, not a grant, and
never read by the shape classifier); run the suite through a granted ceremony (§ The Three
Implicit-Grant
Ceremonies) — never silently writing a Tier-U grant itself; or, when the command's own shape gives
the classifier nothing to go on at all (an opaque wrapper or package-manager task alias that
carries no path, node-id, or marker token), declare `fast_tier_shape: scoped` or
`fast_tier_shape: unscoped` in `coordinator.local.md`. An unclassifiable command with no
`fast_tier_shape` declaration is refused rather than assumed safe — an ambiguous shape used to
fall through to "proceed" by default, which is the fail-open hole this fourth exit closes; an
absent or invalid `fast_tier_shape` value refuses the same way. The refusal is implemented
CLI-side in `validate-fast-and-packageability` (claude-klabauter), routed there by cross-repo memo;
an operator on an un-updated CLI may not see it yet.

### Grant-consuming: Tier F now needs a live session grant too

A scoped Tier F command is no longer ungated. Once the resolver classifies the resolved command as
Tier F (per § Tier classification above), this skill runs
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/tier-u-grant-cli" check`
before invoking it — the same session-scoped token Tier U already consumes, checked live, not
inferred from the conversation having discussed one. Exit 0 means granted — proceed to run the
resolved command. Exit 1 (ungranted) halts before invoking Tier F: a token absent or malformed
reads as ungranted, never granted (fail-closed). On a halt, name the honest exits rather than
fabricating a fallback run — ask the PM for a session grant (one ask lifts both Tier F and Tier U
for the rest of the session); run under a ceremony that already holds the implicit grant (§ The
Three Implicit-Grant Ceremonies: `/workday-complete`, `/workweek-complete`, `/merging-to-main`);
or defer the run and report `Validation: skipped` for this invocation.

This skill still never writes a grant itself — that prohibition survives this change unmodified:
it stops a skill from minting authority nobody granted it, which is a different failure than the
one grant-gating addresses here. Do not "helpfully" add a token write to this skill; a grant is
written only by a ceremony on the ratified implicit-grant list, for its own ceremony, never by
`/validate`.

## Exit Code → `Validation:` Mapping

| Condition | `Validation:` value |
|---|---|
| Resolver exit 2 (skip-with-notice) | `skipped` |
| Resolver exit 126 (configured value carries an un-interpretable escaped quote) | `config-malformed` (blocking — a config defect, not a test failure) |
| Resolver exit 127 (bare `python` token, no python3/python on PATH) | `interp-missing` (blocking — NOT a skip) |
| Resolver exit 0, configured command exits 0 | `0` |
| Resolver exit 0, configured command exits non-zero | `<exit-code>` (the non-zero integer) |

The resolver does not pre-parse or probe the command string before execution. A configured command that fails to invoke (missing script, missing binary, syntax error) returns non-zero from the shell and surfaces as a normal `Validation: <exit-code>` — same as a test failure. Exit-code semantics are the contract; no heuristic on the command string.

## When to Use

- At cadence gates: /workstream-complete, /merge-to-main, /workday-complete, /workweek-complete
- NOT a per-commit reflex — commits are quick-saves; mid-work iteration uses the targeted subset.
- After modifying CI scripts, plugin manifests, settings, or memory files
- When the user asks "does everything pass?" or "validate"

## Interpreting Results

- **`Validation: 0`** — all checks passed. Safe to proceed with commit/merge.
- **`Validation: <non-zero>`** — configured command reported failure. Fix the failing check before proceeding. The command's own output includes the script name and error details.
- **`Validation: skipped`** — resolver found no configured command. Proceed to the next step; fast-tier validation was not run. To enable: set `fast_test_cmd:` in `coordinator.local.md`, or set `$COORDINATOR_FAST_TEST_CMD`. This is distinct from a PM-authorized skip (which is recorded as `N/A`).

## Integration

This skill complements `verification-before-completion`. That skill requires evidence before claims; this skill provides the evidence for repo-level validation claims.

`/workday-complete` Step 1 and `/workweek-complete` Step 2 both delegate to this skill. They do not inline their own resolution logic — this is the single owner.

Caveat: `/workweek-complete` Step 2's delegation is fully covered by § Grant-consuming above — it
runs as a normal `PreToolUse(Bash)`-observable invocation. `/workday-complete` Step 1's delegation
is not: `d_step1_validate` fires as a `directives[]` entry inside the control-plane engine's
`workday_complete` assembler, a process boundary the Bash-level grant check above never observes,
so no Tier-F grant check fires on that path yet either (mirrors
`coordinator/docs/wiki/test-design-discipline.md` § The Three Implicit-Grant Ceremonies). Do not
read "both delegate to this skill" as implying both runs are grant-checked equally.

## Common Mistakes

- **Forgetting to stage files before validating.** Unstaged changes won't be caught by some checks — ensure your working tree reflects intent before running.
- **Committing secrets or credentials.** Check for `.env` files, API keys, and private tokens before staging. CI may catch these, but prevention is better.
- **Skipping JSON and YAML validity checks.** Malformed frontmatter or settings JSON silently breaks plugin loading. Run the validator even for "small" config edits.
- **Leaving empty chunk or stub files.** Empty files in `docs/plans/` or `tasks/` directories can confuse downstream pipeline tools — delete or populate before committing.
- **Not reading the full output.** Skimming past FAIL lines or truncated error details means fixing the wrong thing. Read every script's result completely.
- **Assuming `skipped` means passing.** `Validation: skipped` means no command was configured, not that checks passed. Configure `fast_test_cmd:` to get an actionable signal.
