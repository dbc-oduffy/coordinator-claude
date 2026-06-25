<!-- Pre-made template. The post-restart EM copies this to tasks/<feature>/install-chain.md and edits
     the leg table to match the install spinoffs (kind: spinoff + install_chain_order) present in
     state/handoffs/. Purpose:
     guarantee every install leg the operator queued is followed to conclusion before the workstream
     is completed — nothing silently dropped when context turns over. Referenced by
     templates/handoffs/continue-onboarding-and-installation.md Step 0. This is the spine; each
     queued install repo is a spinoff tracked under it — the same shape coordinator:roadmap-planning
     produces. -->
# Install-chain spine

> Lightweight, edit-in-place. NOT a design plan — it is the disk-resident spine that keeps a
> multi-repo install honest across compaction: one onboarding spine, N install **spinoffs** picked
> up in turn. Coordinator installs standalone; this spine only earns its keep when the operator
> queued *additional* legs (deep-research and/or downstream repos). If there is only the one leg
> (coordinator onboarding), this spine is trivially short — that is fine.

## How to fill this in

1. List coordinator onboarding (this handoff) as leg 0, then every install **spinoff** currently in
   `state/handoffs/` — they carry `kind: spinoff` + `install_chain_order:` (run the Step 0 sweep:
   `grep -l 'install_chain_order:' state/handoffs/*.md`).
2. Order the spinoffs by each one's `install_chain_order:` frontmatter if present; otherwise by
   discovered order. Lower order = installed earlier (closer to the trunk).
2a. **Discover orient legs and interleave them.** A repo may seed its orientation as a *separate*
   `kind: spinoff` baton that omits `install_chain_order:` (so the install-leg sweep misses it) — run
   the Step 0 orient-leg sweep (`orient-*.md` filename OR a word-boundary "orientation" in
   `summary:`/`title:`, gated by `kind: spinoff` AND no `install_chain_order:`). Pair each to an
   install leg by **longest-prefix stem** (if two install legs tie as equal-longest prefix, treat the
   orient leg as **ambiguous/unpaired** — never auto-pick). **Position each orient row by these rules
   (read the qualification — "immediately after" is NOT the unconditional default):**
   - `ready_to_fire` + no `orient_after:` → immediately after its paired install **ONLY if that install
     is the leaf** (highest `install_chain_order:`). Paired to a **non-leaf** install → **defers to the
     absolute tail** (safe — it may depend on a later install) and is labeled in the `repo / leg` cell
     `"[deferred to tail — seed orient_after: to interleave mid-chain]"` so the deferral is visible, not
     silent. Mid-chain interleave of a non-leaf orient leg is opt-in via `orient_after:` only.
   - `orient_after: <repo-id>` → immediately after the **named** install leg (mid-chain, not necessarily
     the tail). Edge: named leg **absent** from chain → falls back to absolute-tail AND label
     `"[orient_after: <repo-id> unmet — named leg not in chain]"`; named leg present but `awaiting_gate`
     → inherits the deferral.
   - `orient_after: "leaf"` → immediately after the highest-order install leg (an explicit anchor that
     resolves to the absolute tail).
   - `awaiting_gate` → **absolute tail** (deferred on gate status).
   - **unpaired / ambiguously-paired** → absolute tail; mark visibly (`unpaired` / `ambiguous`) so a
     mis-seeded baton is never silently dropped.
   - **BOTH `orient_after:` AND `awaiting_gate` on one leg** → resolve the `orient_after:` anchor
     position first, then apply the `awaiting_gate` tail-deferral relative to that anchor.

   Full rules: `docs/wiki/agent-install-contract.md § Orient-leg discovery` and
   `continue-onboarding-and-installation.md` Step 0.
3. Work the legs top-to-bottom. Pick up each spinoff (`/pickup state/handoffs/<file>`), advance its
   three sub-axes (installed → provisioned → oriented) as each completes, and flip the roll-up
   `status` to `done` only when all three are satisfied (a leg with no separate provision step uses
   `n/a` there). A leg may sit at `installed=yes, provisioned=provisioning(...)` for a while —
   that is expected for slow background steps and does not block the rest of the chain; return to it
   to finish provisioning + orienting. Do **not** run `/workstream-complete` while any row is
   `pending` / `in_progress`.

## Legs

Each leg carries three sub-axis columns — **installed / provisioned / oriented** — because a leg
is not "done" the moment its files land. A downstream repo can be *installed* yet still
*provisioning* (e.g. a first RAG index that runs for the better part of an hour, in the background,
not blocking this chain) and not yet *oriented* (the operator has not co-shaped it). Track all three
so the spine shows where every leg actually stands at a glance. Marks: `yes` / `no` / `n/a`
(coordinator onboarding has no separate provision step), or `provisioning (ETA …)` while a slow
background step runs. `status` is the roll-up (`pending` / `in_progress` / `done`).

Orient legs (separate `orient-*` batons) are interleaved: a `ready_to_fire` orient row sits
**immediately after its paired install leg** only when that install is the **leaf** (else it defers to
the **absolute tail** — a non-leaf orient leg may depend on a later install; seed `orient_after:` to
interleave mid-chain), or at the chain **absolute tail** when `awaiting_gate` / `orient_after: "leaf"` /
unpaired / ambiguous. Give an interleaved orient leg its own row with `installed`/`provisioned` = `n/a`
(it carries only the orient sub-axis). **Label every tail-deferred row in the `repo / leg` cell with
the reason** (`[deferred to tail — seed orient_after: …]`, `[orient_after: "leaf"]`, `[awaiting_gate]`,
`unpaired`, `ambiguous`) so the deferral is visible, never silent.

| order | repo / leg | spinoff file (state/handoffs/) | plan (if any) | installed | provisioned | oriented | status |
|-------|-----------|--------------------------------|---------------|-----------|-------------|----------|--------|
| 0 | coordinator onboarding | continue-onboarding-and-installation.md (this handoff) | — | yes | n/a | no | in_progress |
| <!-- 1 --> | <!-- deep-research --> | <!-- install-deep-research.md --> | <!-- — --> | <!-- yes --> | <!-- n/a --> | <!-- no --> | <!-- pending --> |
| <!-- 2 (example slow leg, NON-leaf — leg 3 installs after it) --> | <!-- downstream repo w/ RAG index --> | <!-- install-<repo>.md --> | <!-- — --> | <!-- yes --> | <!-- provisioning (ETA ~1h) --> | <!-- no --> | <!-- in_progress --> |
| <!-- 3 (leaf install — highest install_chain_order) --> | <!-- <repo-addon> --> | <!-- install-<repo-addon>.md --> | <!-- — --> | <!-- yes --> | <!-- n/a --> | <!-- no --> | <!-- pending --> |
| <!-- 3.1 (paired orient, ready_to_fire + leaf → interleaved right after the leaf install — the ONLY safe mid-leg interleave) --> | <!-- <repo-addon> orientation --> | <!-- orient-<repo-addon>.md --> | <!-- — --> | <!-- n/a --> | <!-- n/a --> | <!-- no --> | <!-- pending --> |
| <!-- tail (leg-2 orient: ready_to_fire but paired to NON-leaf install + no orient_after → deferred to absolute tail) --> | <!-- <repo> orientation [deferred to tail — seed orient_after: to interleave mid-chain] --> | <!-- orient-<repo>.md --> | <!-- n/a --> | <!-- n/a --> | <!-- no --> | <!-- pending --> |
| <!-- add one row per queued spinoff (install + paired orient); delete the example rows if no others were queued --> | | | | | | | |

## Completion gate

- [ ] Every row above is `done` — meaning each leg is installed, provisioned (or `n/a`), and oriented.
- [ ] Each spinoff has been actioned/archived per its repo's convention.
- [ ] Only then: `/workstream-complete` (or `/workday-complete`) for the install workstream.
