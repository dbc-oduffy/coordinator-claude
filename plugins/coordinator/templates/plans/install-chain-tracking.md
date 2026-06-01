<!-- Pre-made template. The post-restart EM copies this to tasks/<feature>/install-chain.md and edits
     the leg table to match the install spinoffs (kind: spinoff + install_chain_order) present in
     tasks/handoffs/. Purpose:
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
   `tasks/handoffs/` — they carry `kind: spinoff` + `install_chain_order:` (run the Step 0 sweep:
   `grep -l 'install_chain_order:' tasks/handoffs/*.md`).
2. Order the spinoffs by each one's `install_chain_order:` frontmatter if present; otherwise by
   discovered order. Lower order = installed earlier (closer to the trunk).
3. Work the legs top-to-bottom. Pick up each spinoff (`/pickup tasks/handoffs/<file>`), advance its
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

| order | repo / leg | spinoff file (tasks/handoffs/) | plan (if any) | installed | provisioned | oriented | status |
|-------|-----------|--------------------------------|---------------|-----------|-------------|----------|--------|
| 0 | coordinator onboarding | continue-onboarding-and-installation.md (this handoff) | — | yes | n/a | no | in_progress |
| <!-- 1 --> | <!-- deep-research --> | <!-- install-deep-research.md --> | <!-- — --> | <!-- yes --> | <!-- n/a --> | <!-- no --> | <!-- pending --> |
| <!-- 2 (example slow leg) --> | <!-- downstream repo w/ RAG index --> | <!-- install-<repo>.md --> | <!-- — --> | <!-- yes --> | <!-- provisioning (ETA ~1h) --> | <!-- no --> | <!-- in_progress --> |
| <!-- add one row per queued spinoff; delete the example rows if no others were queued --> | | | | | | | |

## Completion gate

- [ ] Every row above is `done` — meaning each leg is installed, provisioned (or `n/a`), and oriented.
- [ ] Each spinoff has been actioned/archived per its repo's convention.
- [ ] Only then: `/workstream-complete` (or `/workday-complete`) for the install workstream.
