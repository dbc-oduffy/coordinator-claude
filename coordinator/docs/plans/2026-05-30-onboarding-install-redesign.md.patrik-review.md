---
title: the Staff Engineer Review — 2026-05-30-onboarding-install-redesign
reviewer: patrik
created: 2026-05-30
verdict: REQUIRES_CHANGES
plan: plugins/coordinator/docs/plans/2026-05-30-onboarding-install-redesign.md
---

```json
{
  "reviewer": "patrik",
  "verdict": "REQUIRES_CHANGES",
  "summary": "Strong SDD half — the file-coherent chunk cut is correct, the three-layer bootstrap is sound, and the AGENTS.md front-door split is the right structure (not over-engineered). But the C5/AC12 percolation mechanism is factually inverted against disk: coordinator-claude ships via mirror mode governed by a .percolate-ignore exclude-list, NOT a publish.sh manifest include-list. AC12 tests a file (publish-manifest.txt) that does not exist for this target, so the install-surface-completeness gate is untestable as written and points the executor at the wrong remedy. Two further AC rows are non-binding as written, and one fix-locus question (session-start branch reachability) needs sharpening.",
  "premise_review": "clean",
  "alternatives_considered": [],
  "planning_quality": "",
  "findings": [
    {
      "file": "docs/plans/2026-05-30-onboarding-install-redesign.md",
      "line_start": 49,
      "line_end": 49,
      "severity": "major",
      "category": "correctness",
      "finding": "C5/AC12 percolation mechanism is inverted against disk. The plan (pinned-interface line 49, C5 line 88, AC12 line 143) asserts the continue-onboarding template 'must be in the publish.sh manifest include-list or it never ships.' Verified against disk: the coordinator-claude publish target is registered as MIRROR mode (setup/publish-targets.sh line 6: `coordinator-claude|mirror|...`), not manifest mode. Mirror mode is an 'everything-minus-excludes' model driven by `.percolate-ignore`, not an include-list manifest. There is no `publish-manifest.txt` for this target (manifest mode is only used for deep-research-claude and holodeck per the registry). The prior-art-checker Conflict #6 cited the wiki's 'anchor to deliberate include-list' guidance, but that guidance describes the MANIFEST surface — it does not apply to the mirror-mode coordinator-claude target. The plan adopted the wrong remedy. ACTUAL state: `templates/handoffs/` is NOT excluded by `.percolate-ignore` (the only `templates`-adjacent exclusion is `coordinator/tasks/` at line 60, and the template lives at `coordinator/templates/handoffs/`, not `tasks/`), so it WILL ship automatically under mirror. The real verification is a NEGATIVE one: confirm no `.percolate-ignore` pattern catches `templates/handoffs/`.",
      "suggested_fix": "Rewrite C5's percolation-include bullet and AC12 to target the correct mechanism: (1) replace 'manifest include-list' with 'mirror-mode `.percolate-ignore` exclude-list'; (2) AC12 test becomes `grep:` `.percolate-ignore` does NOT contain a pattern matching `templates/` or `templates/handoffs/` (negative assertion), plus a `bash:` `publish.sh --dry-run` confirming the template appears in the NEW/UPDATE audit lines for the coordinator-claude target. Drop the 'add to include-list' language entirely. Also amend the prior-art sidecar disposition: Conflict #6's `update-plan` direction was right that the question is real, but the cited wiki rule (include-list anchoring) does not govern this target — recommend `update-prior-art` to note the wiki's include-list guidance is manifest-mode-specific and does not cover mirror-mode targets like coordinator-claude.",
      "disposition": "applied"
    },
    {
      "file": "docs/plans/2026-05-30-onboarding-install-redesign.md",
      "line_start": 143,
      "line_end": 143,
      "severity": "major",
      "category": "testing",
      "finding": "AC12 is untestable as written. The test column reads `grep:` the publish manifest include-list contains the templates path. No such file exists for the coordinator-claude target (mirror mode, no `publish-manifest.txt`). A grep against a nonexistent file either errors or returns empty — in both cases the AC cannot pass, and the binding-class 'gate' is non-binding. This is the install-surface-completeness gate (the entire P-set is about install correctness), so a hollow gate here is the highest-leverage place for a silent clean-install failure to slip through — exactly the 2026-05-20/21 failure-shape the plan invokes as its justification.",
      "suggested_fix": "See finding 0's suggested AC12 rewrite (negative `.percolate-ignore` assertion + `publish.sh --dry-run` audit-line confirmation). The dry-run assertion is the one that actually proves the template ships — a grep on an exclude-list only proves it is not blocked, which is necessary but not sufficient.",
      "disposition": "applied"
    },
    {
      "file": "docs/plans/2026-05-30-onboarding-install-redesign.md",
      "line_start": 132,
      "line_end": 132,
      "severity": "minor",
      "category": "testing",
      "finding": "AC1 binding test is weak. The criterion 'a cold Claude can route from README -> agent-install.md in one hop' is gated by `cited:` C2 read-through — i.e. the test is 'a human read C2 and agrees.' That is not a binding test; it is reviewer attestation. The actual behavior under test (does a cold, doctrine-less agent discover and follow the path?) is precisely what C8 dogfoods. As written AC1 can be marked green by inspection without the discovery behavior ever being exercised.",
      "suggested_fix": "Either (a) downgrade AC1's binding-class from 'gate' to 'inspection' and let AC10 (the dogfood) carry the binding discovery assertion, or (b) make AC1's test the concrete artifact check it actually is — `grep:` README contains the AGENTS.md pointer line AND `grep:` agent-install.md is reachable by a relative link from both README and AGENTS.md — and move the behavioral 'one hop for a cold agent' claim under AC10's dogfood evidence. Right now AC1 and AC11 overlap on the same artifact assertions while AC1 also smuggles in an unfalsifiable behavioral claim.",
      "disposition": "applied"
    },
    {
      "file": "docs/plans/2026-05-30-onboarding-install-redesign.md",
      "line_start": 91,
      "line_end": 95,
      "severity": "minor",
      "category": "correctness",
      "finding": "C6 fix-locus / reachability is under-specified relative to the substrate. Substrate-notes (Scout 3) established that when a handoff is loaded, `/pickup` PRE-EMPTS the session-start work menu (pickup owns the flow). So the session-start fresh-install branch only fires on the NO-handoff path. But the primary install flow STAGES the continue-onboarding handoff (Layer 0) and resumes via `/pickup` (Layer 2) — meaning in the happy path the session-start branch is never reached. The plan acknowledges this ('no-handoff case') but does not specify what triggers the no-handoff path on a fresh install: if the install always stages the handoff, when is the session-start branch actually exercised? If the answer is 'only when the user starts a fresh session WITHOUT pasting the /pickup command,' then C6's branch is a fallback for a user who diverged from the instructions — legitimate, but the detection condition ('a just-installed ~/.claude with no loaded handoff') needs to be precise enough to not false-positive on every subsequent normal session the user ever runs.",
      "suggested_fix": "C6 must specify the detection predicate concretely and make it self-limiting: e.g. fire the fresh-install branch only when (a) no handoff is loaded AND (b) a fresh-install sentinel exists AND (c) that sentinel is consumed/cleared on first fire — otherwise every no-handoff session-start for the life of the install re-offers 'co-write your CLAUDE.md.' Name the sentinel and its lifecycle in C6, and add a test-surface assertion that the branch does NOT fire on a second clean session. (This is the detect-then-fail-loud / guards-match-conditions-not-containers discipline from CLAUDE.md § Implementation Standards.)",
      "disposition": "applied"
    },
    {
      "file": "docs/plans/2026-05-30-onboarding-install-redesign.md",
      "line_start": 96,
      "line_end": 96,
      "severity": "minor",
      "category": "correctness",
      "finding": "C5 frontmatter set may be missing a load-bearing field. The plan specifies `title, created, branch, status: active, predecessor: null, deployment_state: ready_to_fire, pickup_ready: true`. The prior-art sidecar Claim #4 flagged (correctly) that `scope:` — not `branch:` — is the field load-bearing for pickup's `git add` step. A static install-time handoff that omits `scope:` may trip the pickup commit step, or pickup may fall back to a broad add. Since this template ships to every OSS user and is the FIRST thing a freshly-installed coordinator does, a malformed-but-not-rejected handoff is a high-blast-radius first impression.",
      "suggested_fix": "Before finalizing C5, read `skills/pickup/SKILL.md` lines 181-207 (the commit step) and confirm exactly which frontmatter fields the `git add` / scoped-commit step consumes. Add `scope:` to the template if pickup's commit path reads it. C5's test-surface should assert the frontmatter passes the ACTUAL pickup classification + commit-step field requirements, not just the classification table (the sidecar already noted the classification table and the commit step read different fields).",
      "disposition": "applied"
    },
    {
      "file": "docs/plans/2026-05-30-onboarding-install-redesign.md",
      "line_start": 61,
      "line_end": 62,
      "severity": "minor",
      "category": "architecture",
      "finding": "Layer 0 'maximally frontloaded' claim is sound but one item on the frontload list is questionable. Layer 0 proposes to 'register plugin/marketplace' from the vanilla session. Verify this is actually vanilla-runnable: plugin/marketplace registration writes `extraKnownMarketplaces` to `~/.claude/settings.json` and seeds `known_marketplaces.json` (per plugin-extraction-and-distribution.md item 13). That is a file-write a vanilla session CAN do — but only if the bootstrap script that performs it is itself discoverable and runnable pre-plugin-load. The plan assumes `register-claude-plugin` (or equivalent) is reachable by a doctrine-less agent from the cloned repo. Everything else on the frontload list (stage handoff, pre-write todo/mini-plan, drop files, capture decisions) is genuinely vanilla-safe. This one is the seam where 'looks frontloadable' could meet 'needs the thing it is registering.' It is almost certainly fine (settings.json is plain JSON), but the plan should name the concrete script C1 instructs the cold agent to run, so the executor does not invent a registration path.",
      "suggested_fix": "C1 should cite the concrete registration entrypoint (the bootstrap/register script the README order already names — plugin-extraction-and-distribution.md item 13 gives the canonical `clone -> register-claude-plugin -> /reload-plugins -> /<plugin>:setup` order). Pin that script name as a frozen reference in C1 so the Layer 0 frontload list is verifiable, not aspirational. No other Layer 0 item needs the plugin loaded — the layering is otherwise sound.",
      "disposition": "applied"
    },
    {
      "file": "docs/plans/2026-05-30-onboarding-install-redesign.md",
      "line_start": 105,
      "line_end": 105,
      "severity": "nitpick",
      "category": "documentation",
      "finding": "C8 conditionally schedules doc-link-checker only if a chunk performs a git mv / path rename, and asserts 'none currently planned — C1/C2 edit in place, C5/C7 add new files.' This is correct per the chunk scopes. But C2 ADDS a new top-level AGENTS.md that introduces NEW inbound links (README -> AGENTS.md -> agent-install.md), and C1 may re-target existing relative links inside agent-install.md during the rewrite. New/retargeted links are exactly what doc-link-checker validates — the 'only on rename' trigger misses link-introduction and link-retargeting, which this plan does.",
      "suggested_fix": "Broaden C8's doc-link-checker trigger from 'git mv / rename only' to 'rename OR introduction of new cross-doc relative links OR retargeting of existing links.' C2 (new AGENTS.md routing) and C1 (playbook rewrite touching links) both qualify. A link-integrity pass on the README -> AGENTS.md -> agent-install.md chain is cheap insurance on the exact discovery path P1 is about.",
      "disposition": "applied"
    }
  ]
}
```

## Narrative — four-pass review

### Pass 0 — Premise & alternatives

`premise_review: clean`. I greped the substrate and prior-art surfaces for prohibition vocabulary against the central nouns this plan introduces (AGENTS.md front door, three-layer bootstrap, Track A/B detection, refinement-target). Nothing in the prior-art sidecar, the substrate notes, or the percolation doctrine prohibits this shape — the one Conflict (#6) is a mechanism question, not a prior decision being reversed. The architecture is frozen in a PM-ratified problem-set and converged through `/shape`; I did not re-litigate it, and per your framing the SDD half is my remit. No alternatives surfaced that would gate the verdict. `planning_quality` empty — the planning is thorough (two pre-flights, substrate scouts, file-overlap table, cross-plan coordination).

### Pass 1 — Structure

The file-coherent chunk cut is **correct** and answers your question 1 directly. One executor per hot file (agent-install.md = C1, setup.md = C3) is the right discriminator because those two files carry the most decision-density and the highest merge-conflict risk if split. The pinned-interface block is the right instrument to let C1–C7 fan out: handoff path, detection-helper contract, verbatim tier labels, and unchanged command names are all named as frozen contracts, and the file-overlap table is disjoint. The seam-verification-at-merge step (C1 references the handoff path / helper / tiers / command names — confirm consistency) is the correct gate. **With one exception**: the pinned interface at line 49 freezes a contract (manifest include-list) that does not match disk — see finding 0. A pinned interface that is factually wrong propagates the error into every chunk that treats it as frozen. That is why finding 0 is `major` and not `minor`: it is in the pinned-interface block, which is load-bearing for the whole fan-out.

Your question 3 — AGENTS.md as front door vs. a single file: the two-file split (AGENTS.md = thin front door, agent-install.md = detailed playbook) is the **right** structure, not over-engineered. The justification is concrete and verified: AGENTS.md is the emerging cross-tool convention filename a cold agent looks for unprompted, which is the precise graceful-degradation P1 needs when the human never pastes the one-liner. Collapsing into one file would either bloat the convention-named entrypoint or lose the unprompted-discovery property. Keep the split.

### Pass 2 — Implementation / fix-locus

Your question 5 (fix-locus): mostly right. setup.md Phase 1.d as the locus for the deep-research remedial offer is **correct** — that is where the presence-check already lives (observational), so making it remedial is a same-locus upgrade, not a new surface. The refinement-target close in Phase 7 and the AGENTS.md/README discovery surface are all at the right altitude.

Two fix-locus concerns: (a) the C6 session-start fresh-install branch reachability (finding 3) — the happy path resumes via `/pickup`, which pre-empts the menu, so the branch only fires on a no-handoff divergence and needs a self-limiting detection predicate or it re-nags forever; (b) the C5 frontmatter field set (finding 4) may omit `scope:`, which the pickup commit step (not the classification table) reads.

Your question 2 (three-layer bootstrap soundness): **sound.** Layer 0 vanilla-runnable / Layer 1 kernel-as-flow-concept / Layer 2 post-restart-pickup is correct, and the corrected restart reason (Agent Teams env var, not plugin registration, since `/reload-plugins` hot-activates) is accurately encoded. The one item I would have C1 pin concretely is the registration entrypoint script (finding 5) — everything else on the Layer 0 frontload list is genuinely doctrine-free; plugin registration is the single item that sits near the 'needs-what-it-registers' seam, and naming the script removes the ambiguity for the executor.

### Pass 3 — Documentation / completeness

Your question 4 (are any of the 3 OOS items incomplete-work-in-disguise?): **No — all three are genuine architectural boundaries.** (1) Cherry-pick/merge engine for Track B — the OOS reason is unbounded judgment scope, a hard constraint, not appetite. The minimal-honest Track B path (detect, tell the user plainly, offer the kernel) is real shipped work, not a deferral. (2) Kernel standalone mini-install — the reason is that registration requires the restart, so a separable install duplicates substrate for zero capability gain; that is an irreducible architectural fact, not a 'later.' (3) UE/holodeck/project-rag for OSS — a hard policy boundary (percolation polarity, CLAUDE.local.md editorial principle). The plan-coverage-checker independently verified all three as OOS-JUSTIFIED; I concur. The PM-gated percolation (line 150) is a PM-authorization gate on an externally-visible action, not an OOS scope-cut — also correct.

### Pass 4 — Edge cases / AC binding

Your question 6 (non-binding/untestable ACs): three issues.
- **AC12** is untestable as written (finding 1) — it greps a manifest file that does not exist for this target. Highest-severity AC problem because it is the install-surface-completeness gate.
- **AC1** is non-binding as written (finding 2) — `cited:` C2 read-through is reviewer attestation, and it smuggles an unfalsifiable 'one hop for a cold agent' behavioral claim that overlaps AC11's artifact checks. Route the behavioral claim to AC10's dogfood.
- The remaining ACs (AC2–AC11) are binding and testable: AC3 (`bash:` test green), AC9 (regression `grep:` for capture-fan-out-threshold), AC6/AC7/AC8 (`grep:` for verbatim strings) are all concrete and falsifiable. AC9 in particular is a well-formed cross-plan regression guard.

### Self-check

Am I over-engineering the findings? Finding 0/1 (percolation mechanism) is not polish — it is a factual inversion in a pinned interface and a hollow gate on the install-completeness surface, which is the plan's entire raison d'être. Findings 3–5 are the simplest sufficient fixes (specify a predicate, confirm a field, pin a script name), not refactors. I held the rest to nitpick. The verdict is REQUIRES_CHANGES on the strength of findings 0+1 alone — the rest are minor and would ride along.

## Coverage
- **Reviewed:** chunk decomposition & file-overlap (Q1), three-layer bootstrap soundness (Q2), AGENTS.md front-door structure (Q3), OOS architectural-boundary validity (Q4), fix-locus per chunk (Q5), AC binding/testability (Q6), percolation mechanism against disk, pickup frontmatter contract, prior-art Conflict #6 disposition.
- **Not reviewed:** the actual prose/copy quality of agent-install.md (does not exist yet — C1 authors it); UX flow of the install dialogue (the UX Reviewer's lens); the organic-ramp sibling plan's internals (only the shared-file seam).
- **Confidence:** HIGH on findings 0, 1 (verified against disk: publish-targets.sh mirror-mode registration, absence of publish-manifest.txt, .percolate-ignore exclude patterns). HIGH on findings 2, 6 (artifact-level reasoning). MEDIUM on findings 3, 4, 5 (reasoning from substrate notes + sidecar; would be HIGH after reading pickup/SKILL.md commit step and session-start branch condition directly, which I scoped to the executor per the suggested fixes).
- **Gaps:** I did not read `skills/pickup/SKILL.md` lines 181-207 (commit step) by line — finding 4 routes that read to C5 execution. I did not run `publish.sh --dry-run` to positively confirm the template ships (finding 1's suggested test) — that is the executor's verification, and I confirmed the necessary precondition (no exclude pattern catches it).

## Worker Dispatch Recommendations

- **doc-link-checker** — after C1/C2 land, validate the README -> AGENTS.md -> agent-install.md relative-link chain. Rationale: C2 introduces a new top-level file with new inbound links and C1 may retarget links during the playbook rewrite; the 'rename-only' trigger in C8 (finding 6) misses link-introduction, which is exactly the P1 discovery path. Substrate precondition: these are in-repo relative links, not private-repo absolute self-URLs, so the doc-link-checker substrate precondition is satisfied.
