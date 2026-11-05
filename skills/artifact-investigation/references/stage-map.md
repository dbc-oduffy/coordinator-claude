# Artifact-investigation stage map

Read only when a stage blocks. Owners follow roadmap COORDINATOR-RESOLUTIONS (Resolutions 1 and 2);
a peer answer re-opens a row by being recorded in the primitive register, not here.

| Stage | Cluster | Owning plane | Phase 1 state | Phase 2 state |
|-------|---------|--------------|---------------|---------------|
| Parse PE and .NET artifacts by script | C16 | project-rag (host capability over caller-held bytes) | `coverage: unknown` until landed | `coverage: unknown` until landed |
| Ghidra program-facts ingest by script | C5 | engine (engine script, records through C3) | `coverage: unknown` until landed | live: `scripts/ghidra_ingest.py` |
| Structural index query | C4 | project-rag (query capability) | `coverage: unknown` until landed | `coverage: unknown` until landed |
| Record claims and unknowns | C3 | engine (the one writer) | `coverage: unknown` until landed | live: `rea_ledger.write` |
| Claim provenance fields | C2 | doctrine repo (deep-research claim fields) | names frozen in `evidence-unknowns-ledger-schema.md` | names frozen in `evidence-unknowns-ledger-schema.md` |
| Agent judgment | none | this session | always available | gated by the claim filter and sweep gate |

The record shape for claims and unknowns is owned by project-rag; this skill names none.
