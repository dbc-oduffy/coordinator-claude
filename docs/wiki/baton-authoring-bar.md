---
last-updated: 2026-07-23
---

# Baton-Authoring Bar

<!-- Spec backlink: docs/plans/2026-07-23-queue-triage-terminates-in-batons.md § C2 (AC2) -->

**What a themed baton owes its reader, beyond what any handoff owes.** A themed baton
(`coordinator/docs/wiki/queue-terminus-doctrine.md`'s outcome class 2 — N queue rows
clustered into one handoff carrying authored context) is still a handoff, and every base
handoff obligation applies unchanged. This wiki does not restate those; it names the
**multi-item delta** — the extra weight a bundle carries that a single-item baton does not.

## Bind, don't restate

Two obligations are already ratified elsewhere. A themed-baton author cites them; a themed
baton that violates either is non-compliant with existing doctrine, not merely with this
page.

- **The bundling threshold.** `spinoff-handoffs.md` § "Spinoff Granularity — Bundle by
  Doctrine Class" already sets the size discriminator (≤30-line authoring deliverables per
  item are bundling candidates), born from a real PM complaint about tiny-spinoff
  proliferation (*"so many unnecessary tiny spinoffs, so many of these could have been
  bundled"*). A themed baton is that ruling applied at the queue-triage seam. Do not invent
  a second line-count threshold here — there is exactly one, and it lives there.
- **What a pickup-able handoff owes its reader, at all.** `coordinator/snippets/em-operating-doctrine.md` §
  How to Plan and Hand Off, "Handoff Lineage" defines lineage,
  frontmatter status/deployment_state, and the base pickup contract for every handoff
  regardless of how many source items feed it. A themed baton satisfies all of that
  unchanged — clustering N rows into one file does not relax lineage discipline, frontmatter
  correctness, or any other base-handoff obligation.

## The multi-item delta — net-new content this wiki actually owns

A baton assembled from a cluster of queue rows owes its reader four things no single-item
baton needs to supply, because a single-item baton's "why" and "what next" already live in
the one row it came from. A cluster has no such single row to point at — the triaging agent
is the only place that context can come from, and it must be authored, not derived.

1. **The cluster's shared thesis — one sentence, EM-authored.** Name what these N items are
   collectively about. Not the clustering op's cluster label (a keyword like "Install" or
   "Schema") — a sentence a picker-up can act on without opening every constituent row. The
   detector proposes a grouping; only the triaging EM can state what the grouping *means*.
2. **Why these N belong together.** The justification for treating them as one unit of work,
   not the tool's grouping score. If two items only share a keyword and not a genuine
   concern, they don't belong in the same baton — see the negative-spec below.
3. **What a picker-up does first.** A concrete, ordered first move — not "read the rows and
   figure it out." A baton with no first move is not more actionable than the N rows it
   replaced; the whole point of spending triage-time context is that the picker-up doesn't
   have to re-derive a starting point.
4. **Constituent-row identity.** Every source row's id/path, so the bundle is traceable back
   to the queue entries it drains — this is also how `initiative` graduation stays
   bidirectional (`initiative-govern-discipline.md` § queue-triage carve-out): the theme
   value written on the baton must match the value written on each member row.

## Negative-spec (DEC-5) — a row list under a title is not a baton

<!-- Tripwire-shaped: check this before authoring any themed-baton body. -->

**A themed baton whose body is N queue rows pasted under one title heading is not a baton —
it is row-shuffling at larger granularity, which is the exact failure this terminus exists
to end.** If a themed-baton body would read as "here are the N rows the clusterer grouped,"
stop: the shared thesis, the why-these-belong-together, and the first move above have not
actually been authored, only implied by proximity. A reader who has to open every
constituent row to understand why they're bundled has received a filing cabinet, not a
baton.

This is the same failure DEC-1 names for parking (a named reason vs. a default sink) applied
to bundling: a cluster is not itself a justification, and a title is not itself a thesis.

## Where this bar is enforced (DEC-5, revised)

**Not at the scaffolder.** `coordinator-doc-new` is a scaffolder — every `_scaffold_*`
function emits frontmatter plus a placeholder body skeleton *before* any body exists
(`_scaffold_handoff`'s docstring: *"All required fields are present with placeholder values
the EM replaces via Edit"*). It runs before there is a body to refuse a row-list against, so
it is architecturally incapable of enforcing this bar.

**The enforcement point is the ceremony's existing PM gate (DEC-7).** `/debt-triage` and
`/bug-blitz` each already carry a PM-authorization gate before anything is written — the PM
sees the candidate baton list before scaffolding fires. The bar above is **EM discipline
held at that gate**: the EM authors the four delta items before presenting the candidate for
authorization, and the PM's authorization is itself a checkpoint against a row-list body
slipping through. This is not a mechanical refusal; it is a discipline the existing gate
gives a place to bite.

**A strengthening has been asked for, not depended on.** The C9 claude-klabauter memo additionally
requests a `nudge_baton_body_bar`-style write-guard over row-list-only baton bodies, on the
shipped `coordinator_core/write_guards/` precedent shape (`block_completion_monolith_write.py`,
`nudge_improvement_queue_write.py`, `block_subagent_plan_body_write.py`). This bar holds
without that guard — the guard, if it lands, adds a mechanical second line of defense; it is
not a prerequisite for this doctrine to be in force today.

## Worked shape — a themed-baton body skeleton

Illustrative outline, not a template to fill mechanically — the prose is the point, not the
headings.

```
---
(standard handoff frontmatter — kind, status, deployment_state, category, initiative: <graduated theme>, ...)
---

# <thesis, as a title — not the cluster keyword>

<One paragraph: the shared thesis, and why these N items are one unit of work rather than
N separate ones.>

## Constituent items

- state/improvement-queue/<id-1>.yaml — <one-line what it targets>
- state/improvement-queue/<id-2>.yaml — <one-line what it targets>
- state/improvement-queue/<id-3>.yaml — <one-line what it targets>

## What a picker-up does first

1. <concrete first move — a file to open, a grep to run, a decision to make first>
2. ...

## Anti-scope / risks specific to bundling these together

<Anything the picker-up should NOT assume just because these items were clustered — e.g.
where the cluster's false-positive risk (queue-terminus-doctrine.md) means one member may
turn out not to belong once work starts.>
```

A body that stops after "## Constituent items" — no thesis paragraph, no first-move list —
has failed the bar in this wiki regardless of how well-formed its frontmatter is.

## Cross-links

- `coordinator/docs/wiki/queue-terminus-doctrine.md` — the doctrine that produces batons in
  the first place: the four outcome classes, the clustering signal, and the discriminator
  between a themed baton and the other three classes. This wiki assumes that doctrine's
  vocabulary (baton, cluster, theme) without redefining it.
- `coordinator/docs/wiki/spinoff-handoffs.md` § "Spinoff Granularity" — the bundling
  threshold this page binds to rather than restates.
- `coordinator/skills/handoff/SKILL.md` § Handoff Lineage —
  the base handoff contract every baton, themed or solo, already owes.
- `coordinator/docs/wiki/initiative-govern-discipline.md` § queue-triage carve-out — how a
  graduated theme populates the shared `initiative` FK on both the baton and its member rows.
