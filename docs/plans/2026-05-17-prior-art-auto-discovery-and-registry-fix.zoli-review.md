---
title: the Director of Engineering Standalone Review — Prior-Art Auto-Discovery + Registry Fix
created: 2026-05-17
reviewer: zoli
mode: standalone
plan: docs/plans/2026-05-17-prior-art-auto-discovery-and-registry-fix.md
verdict: APPROVE-WITH-REVISIONS
---

# the Director of Engineering Review — Prior-Art Auto-Discovery + Registry Fix

## Summary

The plan is structurally sound and architecturally correct on the load-bearing call: registry as single source of truth is the right cross-team boundary, and the Staff Engineer-altitude hedging on "what the other repos' EMs prefer" would be wrong here. Three cross-team repos consume coordinator doctrine; coordinator doctrine sets the contract; the registry shape is coordinator-owned. The plan asserts that correctly.

What needs revision is mostly mechanism, not direction: a few claims of atomicity and enforcement that don't have actual mechanisms behind them, an OS-aware path-matching rule that is one paragraph short of being implementable, a smoke-test plan that does not survive its own recursion meta-risk, and one genuine under-ambition call on the override semantics. None of these require a reshape. All are addressable in-place before Stage 1 dispatch.

**Verdict:** APPROVE-WITH-REVISIONS. Stage 1 may proceed once F1, F3, F4, F6, and F8 are addressed (these gate dispatch). F2, F5, F7, F9 are P2/P3 — fold during the stage that touches them.

---

## Findings

### F1 — P1 — "Atomic across 4 repos" is the wrong primitive (line 81, line 222)

**Disposition:** applied

**The claim:** "This must land in the same commit as the registry update (S1.B) — otherwise there's a window where the agent's auto-discovery has populated edges and the CLAUDE.md still has stale instructions for the EM. **Atomic.**"

**The problem:** S1.B touches `~/.claude/tasks/repo-registry.md` (claude-central repo). S1.C-pre touches three external repos' `CLAUDE.md` files (project-rag, project-rag-ue-addon, claude-unreal-holodeck). Cross-repo atomic commits do not exist in git. The word "atomic" promises something the mechanism cannot deliver, and the executor will either (a) interpret it literally and stall, or (b) interpret it loosely and ship inconsistent state across the four repos.

**What's actually true:** There is no window of corruption in either order, because the strip is *idempotent and additive in both directions*:
- If S1.B lands first: registry has edges, three CLAUDE.md files still carry stale `peer_repos:` hints. Agent in auto-discovery mode will find the right peers via the registry; the stale hints are vestigial and only fire if a human EM reads them and types `peer_repos:` manually — which is a no-op (the override produces the same set the registry would).
- If S1.C-pre lands first: three CLAUDE.md files stripped, registry still has empty edges. Agent has nothing to auto-discover. EM operates as today (manual `peer_repos:` from memory). No corruption, just no improvement until S1.B lands.

**Required edit:** Replace "Atomic" with a precise ordering+idempotency contract:

> S1.B and S1.C-pre may land in either order or as separate commits; neither produces incorrect prior-art output in isolation. Convention: land them in the same `/workday-complete` boundary (same logical session) so the registry-authority transition is observable in one changelog entry. Stage 2 does not start until both have landed.

This is honest about the mechanism and tightens the doctrine. The current language is a tripwire for future executors.

---

### F2 — P2 — Stage-gate enforcement is rhetorical, not mechanical (line 24, line 189)

**Disposition:** applied

**The claim:** "Stage 2 does not start until Stage 1 ships" + "Stage gates are real" in Hard Constraints.

**The problem:** There is no fail-loud mechanism. A future EM dispatching Stage 2 before Stage 1 lands gets silently incomplete auto-discovery (the registry has empty `relationships:` on triad entries). The plan itself names this exact failure mode ("running auto-discovery against a registry that's missing edges produces silently incomplete results") and then provides no detection for it.

**What to add — pick one (low cost, high yield):**

Option A (cheap, mechanical): Stage 2 agent-prompt edit adds a startup precondition check — *"Read the active project's entry in the registry. If its `relationships:` array is empty AND the project's `path` is one of the known-interwoven set [project-rag, project-rag-ue-addon, claude-unreal-holodeck], emit DEGRADED with reason 'registry interwoven-set entry has empty relationships — Stage 1 may not have landed.'"* The hardcoded set is ugly but specific; if it's wrong, the cure is one-line.

Option B (cleaner): Add an explicit `registry_schema_version` field to the registry frontmatter, bumped by S1.A. Stage 2 agent prompt asserts minimum version. Out of scope for this plan if the registry frontmatter doesn't already have a version field — check during S1 stub authoring.

**My call:** Option A. It's a 4-line addition to S2.A and it costs nothing if Stage 1 landed correctly.

---

### F3 — P1 — OS-aware path matching is one paragraph short of being implementable (line 111)

**Disposition:** applied

**The claim:** "Path matching is OS-aware: case-insensitive on Windows (NTFS default), case-sensitive on Linux and macOS (POSIX default)."

**The problem:** Case sensitivity is *one* axis. The agent will fail on these others before it ever sees a case-sensitivity issue:

1. **Separator normalization.** Registry entries written on Windows carry `x:/coordinator-claude` (forward slashes — POSIX-style). `pwd` on Windows in a PowerShell session may return `X:\coordinator-claude` (backslashes, uppercase drive). The agent prompt must normalize: lowercase drive letter, forward-slash separators, no trailing slash.
2. **Drive letter case.** `x:` vs `X:` — Windows treats these identically; the agent must too.
3. **`~/` expansion.** `~/.claude` in a registry path field vs an absolute home path returned by `pwd`. The agent must resolve `~` against `$HOME` / `$env:USERPROFILE` before comparing.
4. **Symlinks / realpath.** Multiple machines have `~/.claude` symlinked into a worktree. `pwd -P` vs `pwd -L` produces different results. The agent prompt must pick one and state it.
5. **UNC and WSL paths** — out of scope (no current consumer); document as explicitly unsupported so a future bug report has a written reason.

**Required edit:** Replace the OS-aware paragraph with a normalization recipe the agent can execute:

> Before comparison, normalize both `pwd` and the registry `path` field via: (a) expand `~/` against $HOME / $env:USERPROFILE, (b) resolve symlinks via realpath / Resolve-Path, (c) convert separators to forward slashes, (d) lowercase drive letters on Windows, (e) strip trailing slash. After normalization, compare case-insensitively on Windows, case-sensitively on Linux/macOS. UNC and WSL paths are explicitly unsupported; agent emits DEGRADED with reason "unsupported path shape" rather than guessing.

This is verbose but it's what the agent needs to do. Without it, the first cross-machine handoff will produce a false "project not registered" sidecar and a confused EM.

**Cross-team directive:** This finding stands as a constraint on Stage 2 dispatch. Plan currently has authority to set this — I'm exercising it.

---

### F4 — P1 — Override semantics: `replaces` as default is the wrong call (line 118)

**Disposition:** applied (PM-ruled: flip to augment-default, 2026-05-17)

**The claim:** "if dispatch brief includes `peer_repos: [...]`, that list **replaces** auto-discovery by default. If the dispatch brief also includes `peer_repos_mode: augment`, the manual list is **added to** auto-discovered peers."

**The under-ambition:** This is a legacy-calibrated choice. The conservative shape is "preserve today's behavior, where `peer_repos:` is the only signal" → replaces is closest to today. But today's behavior is *exactly the bug this plan exists to fix*. The EM has been manually carrying registry information into dispatch briefs because the agent didn't read the registry. Now the agent reads the registry; the *natural* shape is that manual `peer_repos:` *adds* to the auto-discovered set (the EM is contributing additional knowledge), and replacement is the override path.

**The cost of getting this wrong:** Every EM that types `peer_repos: [X]` after this ships expects X to be *included*, not to *silently exclude* the two peers auto-discovery would have found. The replaces-by-default semantic is a silent-data-loss surface — exactly the class of bug the plan otherwise works hard to avoid (cf. "No fallback escape hatches" in Hard Constraints).

**Recommendation:** Flip the default. `peer_repos: [...]` augments by default. `peer_repos_mode: replace` is the override flag for "I want precise control, drop auto-discovery." Rename the augment-mode flag to `replace` so the unmarked path is the safer one.

**Backward-compat check:** F8 below — verify the existing dispatch surface against this flip.

**Counter-argument (and why I'm not buying it):** "EM precision when they need it" is the stated motivation for replaces-by-default. But the EM has the override flag in either direction. The question is which default produces the less-surprising failure mode. Augment-by-default fails by consulting one extra peer (cheap, observable in sidecar). Replace-by-default fails by silently *missing* a peer (expensive, invisible until a finding is missed).

This is the one place I'd push hardest on revision. Single-character flip in the default; significant safety improvement.

---

### F5 — P2 — Edges-no-cap is correct, but document the escape valve (line 95)

**Disposition:** applied

**The claim:** Channel 1 (edges) has no cap. Combined ceiling of 5 catches runaway.

**The assessment:** The shape is right. Edges are EM-authored ground truth; capping them silently defeats the purpose. The combined ceiling of 5 is the cost discipline. This is genuine engineering, not under-ambition.

**The one gap:** What happens when a repo legitimately has 6+ edges to consult? Today there are no such repos. In two quarters, there might be (the triad could grow; cross-domain repos might accumulate). The plan's answer is "DEGRADED with rationale." That's fine, but the EM remediation is unstated — does the EM bump the ceiling? Pass `peer_repos:` to subset? Add `peer_repos_mode: replace` (per F4)?

**Required edit:** Add one sentence to the Discovery channels and caps section (after line 97):

> When the combined ceiling is hit, the EM's remediation surface is `peer_repos: [...]` with `peer_repos_mode: replace` to consult a deliberately chosen subset. The ceiling itself does not get bumped silently — that's a doctrine change requiring PM authorization.

---

### F6 — P1 — Smoke-test plan does not survive its own recursion meta-risk (lines 182, AC5-AC8)

**Disposition:** applied

**The claim:** "Stage 2: End-to-end smoke — dispatch prior-art-checker against a known small plan from each of three repos."

**The recursion problem (which the dispatch prompt flagged, correctly):** prior-art-checker is the agent being modified. The first run after the change has corrupted output as its *signal* — but corrupted output is also what the EM is using to detect the bug. The smoke test as written ("verify sidecar headers match expected discovery channels") presumes the EM can read the sidecar to know whether the agent is working — but the sidecar is the artifact-under-test.

**The fix:** Test against a *known oracle* rather than against expected behavior. Three concrete oracle-shaped checks:

1. **Oracle 1 — registry pure-read smoke (no agent needed):** Before dispatching the agent at all, run `bin/verify-registry-schema.sh` (mentioned at line 181 as optional — promote to required). This validates the registry can be parsed and the edges are well-formed. Pure mechanical check, no agent involvement.
2. **Oracle 2 — dry-run dispatch from coordinator-claude itself:** The active project for the smoke test is `coordinator-claude`. Expected auto-discovery: claude-central via `dev-publish` edge. Single edge, single expected peer. If the agent returns anything other than `peer-wikis: claude-central (edge:dev-publish)`, the agent is broken. This is a 1-edge oracle — minimum complexity, maximum signal.
3. **Oracle 3 — triad cross-check:** Dispatch from each triad member; verify the other two appear. Pairwise symmetric — if A→B works and B→A doesn't, edge symmetry is broken in the registry, not the agent.

**Required edit:** Replace the current Stage 2 Test Surface bullet with the three-oracle structure above. Promote `bin/verify-registry-schema.sh` from "optional, gated on S1.A outcome" to required Stage 1 acceptance criterion.

---

### F7 — P2 — Registry-entry-time opt-out is the right cross-team escape hatch (line 73, F4-adjacent)

**Disposition:** applied

**The dispatch question:** "Are there cases where a repo SHOULD be able to override registry-driven discovery from inside its own CLAUDE.md (e.g., a security-sensitive repo opting OUT of being consulted as a peer)?"

**My answer:** Yes, and the right shape is registry-side, not CLAUDE.md-side. Adding a `consult: false` field (or equivalent — `consultable: false`, `prior_art_eligible: false`) to a registry entry's frontmatter is the clean expression. CLAUDE.md remains human-readable narrative; the registry carries machine-actionable opt-out. This is symmetric with the rest of the design.

**Not blocking:** No current consumer needs this. But the plan should explicitly document that the registry — not CLAUDE.md — is the future home for opt-out signals, so a future PM who needs the feature does not re-introduce CLAUDE.md dispatch hints to get there.

**Required edit:** Add to § "What This Plan Does NOT Do":

> Does not add a per-entry opt-out field (`consult: false` or similar). When a future need arises (e.g., a security-sensitive repo declining to be consulted), the addition lives in the registry schema, not in CLAUDE.md — the single-source-of-truth principle established here makes registry the canonical surface for both inclusion and exclusion signals.

---

### F8 — P1 — Backward-compat claim needs a verification surface (line 134)

**Disposition:** applied

**The claim:** "Existing dispatches that pass `peer_repos: [...]` continue to work — that path becomes 'override mode.'"

**The problem:** This claim is asserted but not verified. If F4 (flip the default to augment) lands, the claim *changes* — existing dispatches that pass `peer_repos: [...]` *do not* produce identical behavior; they now also consult auto-discovered peers. This may or may not be a breaking change for existing tooling.

**Required edit (regardless of F4 resolution):** Add to AC list:

> AC11: For each of the last 5 prior-art-checker dispatches in coordinator-claude `git log` (if findable via the sidecar archive), the new agent prompt produces equivalent or strictly-greater peer coverage. If any prior dispatch's behavior would diverge, flag in the Stage 2 stub PR description.

If F4 is adopted: this AC catches the "I used to pass `peer_repos: [X]` and got only X; now I get X plus auto-discovery" surprise *before* it ships rather than at the first user-facing sidecar.

If F4 is rejected (replaces stays default): this AC is trivially satisfied but free insurance.

---

### F9 — P2 — Enum extension under-ambition check (lines 38-43)

**Disposition:** applied

**The dispatch question:** Are three new `relationship.kind` values right, or symptoms of premature taxonomy?

**My assessment:** Three is right; two would be wrong. Here's why:

- `schema-lockstep` is a genuinely different concept from `peer`. Two repos sharing a *test-enforced* schema constraint is a relationship with concrete operational consequences (a change in one *must* trigger consultation of the other). Collapsing it into `peer` loses that signal.
- `ancestor` carries historical weight (lessons learned during the carve-out live in the ancestor's wiki). Distinct from `peer`.
- `depends-on` is the most general; this is the one where I'd most expect future refactor. But naming it now is cheap and the alternative (collapsing into `consumes-from` and broadening that kind's meaning) muddles the existing data-flow-specific shape. Keep it.

The plan resists the "two-kinds-cover-this" collapse correctly. PM call was right; closed-enum discipline is load-bearing here. No revision needed.

**One micro-note:** The wiki update at S1.C step 1 should also clarify that `peer` after this change means *"siblings without one of the more-specific relationships"* — i.e., `peer` is the residual kind. Otherwise a future EM will hesitate between `peer` and `depends-on` and choose `peer` for safety, eroding the new precision.

**Required edit:** Add to S1.C step 1 (or the wiki update body):

> `peer` is the residual kind: use it only when none of `schema-lockstep`, `ancestor`, `depends-on`, `dev-publish`, `consumes-from` apply. The more-specific kind always wins.

---

### F10 — P3 — Phase 14 sibling-mention hint will produce noisy candidates (line 149)

**Disposition:** applied

**The concern:** The Phase 14 trigger ("CLAUDE.md references other registry shortnames by sibling-path or quoted shortname") will fire on any candidate repo whose CLAUDE.md mentions, say, `coordinator-claude` in prose — including transient references like "we use the coordinator pipeline." Expected false-positive rate: high.

**Severity is low** because the output is a *notice to PM*, not auto-action. But the notice's signal-to-noise ratio matters for whether PM trusts it.

**Suggestion (not required):** Constrain the match to (a) sibling-path mentions of the form `../<shortname>/` or `x:/<shortname>/` (filesystem-shaped), or (b) shortnames appearing in a CLAUDE.md frontmatter or in a heading. Drop bare-prose mentions. This trades some recall for considerably better precision.

Not a gate. Flag for the Stage 3 stub to consider during implementation.

---

## Cross-team authority calls (DoE altitude)

The plan asserts cross-repo doctrine in three places. I'm confirming each:

1. **Stripping `peer_repos:` hints from three external CLAUDE.md files (S1.C-pre).** This is coordinator's call to make, not the external repos' EMs'. Coordinator owns the prior-art-checker contract; the registry is coordinator-owned; the dispatch surface is coordinator-defined. External repos do not get a vote on whether their CLAUDE.md carries this hint, because the hint is not *for* them — it's for an agent coordinator dispatches. **Authority confirmed.** External repo teams are notified, not consulted.

2. **Adding closed-enum values that ripple across all consumers.** Same authority shape. The registry schema is coordinator-owned. Extending the closed enum is coordinator's call. **Authority confirmed.**

3. **The single-source-of-truth claim.** This is the load-bearing one and the plan asserts it correctly. The right cross-team posture is "the registry is the contract; CLAUDE.md is human-readable narrative." External EMs that disagree should surface to PM; the default is not negotiable per-repo. **Authority confirmed.**

If a the Staff Engineer-altitude review hedges any of these as "ask the external EMs whether they're open to this," that hedging should be overridden. The plan has it right.

---

## Coverage

- **Reviewed:** plan correctness, cross-team boundary authority, override semantics, OS-aware path matching, atomicity claim, stage-gate enforcement, smoke-test recursion risk, enum extension granularity, backward-compat claim, Phase 14 trigger precision, registry opt-out future-surface.
- **Not reviewed:** the actual agent-prompt diff (out of scope — Stage 2 not yet authored), registry YAML shape (pending S1 stub), `bin/verify-registry-schema.sh` (not yet written).
- **Confidence:** HIGH on F1, F3, F4, F6, F8 (mechanism gaps and override-default safety). MEDIUM on F2, F5 (Stage-gate, escape valve — judgment calls, defensible either way). MEDIUM on F7, F9, F10 (forward-looking shape calls).
- **Gaps:** I have not seen the agent prompt edit. F3 and F4 will need re-verification once Stage 2 stub lands.
- **Cross-team scope:** This review issues directives effective on project-rag, project-rag-ue-addon, and claude-unreal-holodeck via the registry-as-source-of-truth boundary. Those teams are on the receiving end of the doctrine, not voting members on it.

---

## Verdict

**APPROVE-WITH-REVISIONS.**

Stage 1 dispatch is gated on resolving F1 (atomicity language), F3 (path normalization recipe), F4 (override default flip — strongest recommendation), F6 (oracle-shaped smoke tests), F8 (backward-compat AC).

F2, F5, F7, F9, F10 can be folded during the stage that touches them — flag in stub dispatch but not blocking for Stage 1.

The plan's load-bearing architectural choice — registry as single source of truth, with coordinator owning the contract — is correct, and the cross-team authority to make that call sits at this altitude. No reshape needed.

---

## Worker Dispatch Recommendations

- **doc-link-checker** — verify the plan's path citations (registry path field formats, three external CLAUDE.md paths, wiki paths) all resolve before Stage 1 dispatch. Cheap, mechanical, catches the kind of citation-rot that aged plans accumulate.
