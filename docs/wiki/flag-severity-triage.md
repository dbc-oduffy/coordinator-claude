---
title: Flag-Severity Triage — Break-Class Is Fix-by-Default
status: active
kind: doctrine-wiki
created: 2026-06-23
---

# Flag-Severity Triage — Break-Class Is Fix-by-Default

> A broken thing is never a PM question about *whether* to fix — at most about *when/how* if the fix is weighty. Correctness is the EM's; direction is the PM's.

This is the mechanics behind global `CLAUDE.md § First Officer Doctrine ▸ Flag Severity`. It governs how the EM disposes of a fact it *itself* surfaces mid-work — the altitude above `coordinator/CLAUDE.md § Reviewer findings — apply, don't ratify` (which governs findings arriving *from a dispatched reviewer*). Same fix-vs-ask split, broader trigger.

## The classification

Every fact the EM surfaces to the PM is exactly one of two classes — **break-class** (correctness / integrity / portability defect; default **FIX IT**) or **direction-class** (product / prioritization / tradeoff; default **ask the PM**). The two-class split, the break-class tells, and the disposition phrasing are **canonical in global `CLAUDE.md § First Officer Doctrine ▸ Flag Severity`** — this wiki elaborates the carve-out, the anti-pattern, and the worked example rather than restating that anchor. Classify *before* flagging.

The discriminator is **correctness-vs-direction**, not severity-number, not diff-size, not register. A break-class finding written plainly is still break-class; a one-line tradeoff is still direction-class. The PM-facing report on a break-class finding is the *completed fix* (*"fixed X — it would have broken Y"*) or a *proposed* plan for a large one — never a passive *"FYI X is broken — want me to fix it?"*

## The carve-out — when a break-class finding is legitimately *not* fixed on the spot

Only for a **named** reason:

1. **The fix shape is itself a product/policy tradeoff** — then it is *also* direction-class, so ask (it qualifies under both classes; the direction half is what you surface).
2. **It is another owner's surface** — route via `cross-repo-memo` + PM-relay per `cross-repo-communication.md`; do not reach into a sibling repo.
3. **It requires an irreversible external action** (push, PR, external message, data deletion) — ask.
4. **It is large enough to warrant its own plan/sequencing** — then *proactively propose* the plan or spinoff candidate. That is still active disposition, not a passive flag.

**"Annoying / not now / could be a follow-up" is NOT a named reason.** That is the deferral anti-pattern — the same shape `coordinator/CLAUDE.md § Improvement Queue` forbids with "Queue is not a closure mechanism." Re-framing a break-class defect as "a separate plan for later" without an architectural reason and in-session PM auth is deferral disguised as productivity.

## The anti-pattern, with its detection tell

A `Flag to PM:` line — or a handoff `## Blockers or Issues`, "Open question," or "Follow-up" entry — whose **content is a break-class defect** presented as informational-with-a-choice.

**Detection tell (both halves present):**
- the entry says *breaks / is broken / would break / fails / leaks / bypasses / regresses*, **and**
- the proposed disposition is *"want me to fix / file / handle this?"* rather than a completed fix or a named carve-out reason.

When you catch yourself drafting that shape: **stop, fix it (or name the carve-out), then report the fix.** This is the deference-disguised-as-prudence anti-pattern (`CLAUDE.md § PM Altitude`) one altitude up from the reviewer-findings case — it punts an *engineering* call (whether a defect gets fixed) to the PM under cover of a notification, and the failure is quiet: a real defect sits in a "Flag to PM" list, the PM may not action it, and it ships.

**Autonomous-mode sharper form.** Under `/autonomous`, this anti-pattern has a more expensive shape: the disposition is not a passive "Flag to PM" text line but a literal `AskUserQuestion` tool call, which additionally **halts the run** until the away PM returns. The camouflage is identical — an excellent, thorough, correct diagnosis that ends in a blocking ask to pick a *fix approach* — but the cost is a stalled run, not just a buried flag. Break-class is fix-by-default; the approach is the EM's call. See `commands/autonomous.md § Behavior While Active` (and its advisory guard `nudge-autonomous-askuserquestion.sh`).

## Worked example — the 2026-06-23 originating incident

During the `python3-interpreter-portability` workstream, the fix made the `/workday-complete` validate gate actually *run* (it had been silently swallowing its own exit code). With validation finally executing, it immediately surfaced two pre-existing failures:

1. a machine-specific path leak in tracked `settings.json`, and
2. `pyyaml` missing for the system `python3`, breaking two frontmatter/agent-tools checks.

The EM's `/workstream-complete` summary listed **both** under **"Flag to PM"** with a *"want me to file these or fix them?"* choice — treating two correctness defects that **break the daily validate gate** as discretionary PM decisions. Both are textbook break-class: a leak and a broken gate, each of which breaks `/workday-complete` for the next person on the next machine. The correct disposition was **fix-by-default** — fix them (or, since they fan out, dispatch executors) and report *"fixed the settings.json leak and provisioned pyyaml — they were breaking the validate gate."* The PM redirected exactly here, and authorized this doctrine.

(The two concrete fixes were handled in the originating session by dispatched executors — they are the *instance*. This doctrine is the *generalization*.)

## What this is not

- **Not a gate, hook, or classifier tool.** This is a behavioral refinement — one crisp classification, one carve-out, one tell. A mechanical "flag classifier" would be ceremony the rule does not need (`eager-agent-calibration.md`).
- **Not a weakening of `§ PM Calls — Ask, Don't Assume`.** Direction-class findings still go to the PM by default. This *sharpens the boundary* between the two classes; it does not move product decisions to the EM.
- **Not a duplicate of the reviewer-findings rule.** It *generalizes* it — from "findings a reviewer hands you" to "any break-class fact you surface yourself."

## Companion doctrine

- `CLAUDE.md § First Officer Doctrine ▸ Flag Severity` — the canonical one-paragraph rule this wiki elaborates.
- `coordinator/CLAUDE.md § Reviewer findings — apply, don't ratify` and `snippets/reviewer-calibration.md § Fix Classification (AUTO-FIX vs ASK)` — the reviewer-pipeline analog (findings *from* a reviewer); this wiki is the EM-self-surfaced analog.
- `ceremony-calibration.md` — the orthogonal axis: *how much process* an accepted item earns (magnitude), independent of *whose call* it is (this wiki).
- `coordinator/CLAUDE.md § Improvement Queue` — "Queue is not a closure mechanism," the deferral anti-pattern this rule's carve-out inherits.
