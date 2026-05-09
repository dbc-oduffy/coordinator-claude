---
system: implementation-standards-by-domain
last_updated: 2026-05-07
status: living
provenance: extracted from coordinator/CLAUDE.md § Implementation Standards Cluster 3 sub-headings (2026-05-07)
---

# Implementation Standards by Domain

> **The rule.** Domain-specific implementation standards live here. The flat-bullet rules in coordinator/CLAUDE.md § Implementation Standards cover cross-cutting standards every session should grep on boot. Domain-specific rules (observability contracts, database/indexer correctness, dependency management, engine plugin packaging) live in this wiki — they're high-value when you hit the failure mode in that domain, but pay no boot tax.

## Why this exists

Coordinator CLAUDE.md is read at every session boot. Domain-specific standards (observability, DB/indexer, dependency, engine plugin) apply only when working in that domain — the other 95% of sessions don't need them in context. Promoting them to a wiki keeps the doctrine intact, greppable when relevant, and out of the boot path.

See `docs/wiki/document-bloat-trim.md` for the general extraction rule.

## Observability contracts

- **Log field names are contracts, not labels.** A field must measure exactly one fact, named for that fact. `cuda_available` reporting NVML probe state (not device availability) misled reviewers for an entire release cycle — the name promised a different fact than the value delivered.
- **Silent absence is indistinguishable from success.** Fail-open paths and gate-skipped phases must both emit structured events; default-on-with-opt-out beats default-off-with-opt-in for load-bearing phases.

## Database / indexer correctness

- **Authority follows definition site, not invocation site, in any structural indexer.** Resolving a symbol at the call site produces the wrong canonical when the definition lives elsewhere — index at the definition, resolve outward.
- **When normalizing one path column, inventory ALL path-typed columns across ALL tables before declaring done.** A single-column patch leaves sibling columns broken; LIKE predicates let ACs pass clean while sibling queries silently return wrong data.
- **`INSERT OR REPLACE` + post-COUNT reports table residue, not insert delta.** Take a pre/post diff of row counts (or use `changes()`) when the goal is "how many rows were written this call."
- **Multi-root callers with an unscoped known-set wipe each other.** Scope the known-set query to the call's input boundary; a shared global set causes one caller's inserts to be invisible to a sibling caller's seen-check.

## Dependency management

- **Vendor with a mechanical SHA pin, not a doc-only policy.** A pinned SHA is machine-verifiable and survives doc drift; a policy note in a README is not enforceable at build time.

## Engine plugin packaging

- **UE plugin distribution mode determines DLL load location.** `AdditionalPluginDirectories` (engine-managed) and project-local plugin paths load from different directories; conflating the two produces inverted directional rules. Verify distribution mode before writing any DLL-path logic.

## Related

- `coordinator/CLAUDE.md` § Implementation Standards — the cross-cutting flat-bullet rules
- `docs/wiki/test-design-discipline.md`
- `docs/wiki/cleanup-sweep-hazards.md`
- `docs/wiki/oom-reproducer-strategy.md`
- `docs/wiki/document-bloat-trim.md` — extraction doctrine
