---
title: Parallel Enrichment — Unified Seam Review
description: When N enrichers work on chunked content in parallel, per-chunk review misses cross-chunk seam violations. This guide explains the seam-review requirement and when it applies.
---

# Parallel Enrichment — Unified Seam Review

> When N enrichers work on chunked content in parallel, each chunk gets reviewed independently — but
> structural errors only appear across chunk boundaries. This guide explains the seam-review requirement
> and when it applies.

## The Rule

After any parallel fan-out enrichment wave completes, dispatch **one reviewer over all chunks together**
before integrating. Per-chunk review misses cross-chunk seam violations.

## Why Per-Chunk Review Fails

Each enricher sees its slice of the artifact. The reviewer dispatched for Chunk 3 cannot see whether
Chunk 3's opening sentence correctly continues the thought from Chunk 2's closing sentence, or whether
Chunk 4 introduces a conflicting definition. Seam errors are invisible to per-chunk review by construction.

**Concrete example:** Three enrichers each expand a different section of a CLAUDE.md file. Enricher A
adds a rule about scout dispatches in § Subagent Dispatch. Enricher B adds a related rule in § Plan-First
Workflow. Enricher C adds a tripwire in § Adding a Convention. Per-chunk review approves each section
independently. The seam reviewer reads the assembled file and catches: Enricher A's wording contradicts
Enricher B's (both say "always do X" but define X differently), and Enricher C's tripwire references a
section name that Enricher A renamed. Neither conflict was visible within any single chunk.

## What Seam Review Covers

A seam reviewer reads the full assembled artifact and checks:

1. **Narrative continuity** — does each chunk's opening connect to the prior chunk's close?
2. **Terminology consistency** — does the same concept use the same word across all chunks?
3. **Structural coherence** — are section levels, list styles, and heading hierarchies consistent?
4. **No duplicate content** — did two enrichers independently add the same information?
5. **No orphaned references** — does every cross-reference ("see above", "as noted in Section 2") resolve?

## When This Applies

Any fan-out pattern where N subagents write to different sections of the same artifact:

- Parallel enrichers processing chunks of a long document
- Parallel reviewers writing findings into different sections of a review report
- Parallel executors writing to different sections of a CLAUDE.md or wiki file

It does NOT apply when subagents write to entirely separate files with no inter-file narrative dependency.

## Pin the Schema as a Hard Contract in Every Brief, Not an Example

*2026-05-20, self.* Parallel fan-out scouts (especially Haiku) drift YAML/structured-output schemas silently when the brief shows the schema as an *example* rather than stating it as a *contract*. Each scout reads the example, infers "something roughly like this," and emits a near-but-not-identical shape — different key casing, an extra wrapper level, a list where a peer emitted a scalar. The seam reviewer then catches N divergent schemas instead of one, and the assembly step has to normalize them post-hoc.

**Rule:** when fanning out N scouts that all emit a structured artifact (YAML frontmatter, JSON record, a fixed-field table), the brief must state the schema as a **hard contract** — exact key names, types, nesting, and required-vs-optional — not "here's an example of the output." An example invites interpolation; a contract forbids it. Pair with the precision floor from `dispatching-parallel-agents.md` § Brief Shape Determines Finding Shape: the precision of the schema spec is the floor on the uniformity of the emitted shapes. This is the schema-uniformity analog of the seam-review rule below — pinning the contract up front reduces the seam violations the reviewer has to catch after.

## Implementation

1. Fan out N enrichers over N chunks (parallel).
2. Wait for all N to complete.
3. Assemble the full artifact (or confirm it is already assembled in one file).
4. Dispatch a single seam reviewer with the full artifact as input. Brief: "Check cross-chunk seam
   coherence — narrative continuity, terminology consistency, structural coherence, no duplicates,
   no orphaned references."
5. Integrate seam reviewer's findings before shipping.

## Multiple parallel integrators on different file-chunks — file-scope hard-fences required

Multiple parallel review-integrators on different file-chunks work cleanly IF integrator briefs name explicit file ownership AND forward overlapping findings rather than touching out-of-scope files. File-scope hard-fences in each integrator brief eliminate cross-integrator stomp; overlapping findings (a finding in chunk A that also affects chunk B) must escalate to EM-side fold rather than the integrator writing out-of-scope files. Apply: for any parallel integrator dispatch, include a "Files this integrator owns: ..." block and a "Forward out-of-scope overlapping findings to EM" instruction.

## Related

- `coordinator/CLAUDE.md` § Review Sequencing — pointer to this wiki
- `docs/wiki/round-trip-contract-tests.md` — broader integration-test doctrine
