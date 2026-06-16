---
name: doctor
description: "coordinator-claude doctor (stub — install-chain contract conformance; full doctor skill is follow-on work per docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §13)"
allowed-tools:
  - Read
---

## Status: Stub

This skill exists to satisfy the `doctor_skill` field requirement in
`docs/install/agent-install-manifest.json`. The install-chain contract schema
(v2) requires `doctor_skill` to be a non-null skill path; this stub provides
that conforming target.

Full `/coordinator:doctor` implementation — including install-chain conformance
probes, dependency-state verification, and health reporting — is deferred to the
follow-on workstream tracked in `state/improvement-queue/` (see the plan that
introduced this stub: `docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §13`).

<!-- Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §C4b (the Staff Engineer 2026-06-15 F1 finding — doctor_skill nullability resolved via stub) -->
