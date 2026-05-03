# Documentation Index

Central entry point for all project documentation. Maintained by `/update-docs`.

---

## Architecture and Reference

| Doc | Purpose |
|-----|---------|
| [architecture.md](architecture.md) | Plugin system architecture, agent hierarchy, coordinator operating model |
| [getting-started.md](getting-started.md) | Setup and onboarding guide |
| [customization.md](customization.md) | How to customize plugins, extend commands, configure per-project settings |
| [ci-pipeline.md](ci-pipeline.md) | CI/CD infrastructure |
| [gitignore-policy.md](gitignore-policy.md) | What gets tracked vs ignored |

---

## Decision Records

Architectural decisions made during development. Embedded in guides or stored as standalone records.

→ [`docs/decisions/`](decisions/) — standalone decision records

---

## Research

Timestamped research outputs from `/deep-research` and `/notebooklm-research` pipelines. Source files are preserved permanently; key findings are extracted into the relevant documentation by `/distill`.

→ [`docs/research/`](research/) — all research outputs

---

## Design Specifications

Specs produced by planning/design sessions. After execution, key decisions are promoted into architecture docs as decision records.

→ [`docs/specs/`](specs/) — design specifications (if present)

---

## Historical Plans

Plans from design and implementation sessions are kept locally in `docs/plans/` (gitignored — author scratch).

---

*Last updated: 2026-04-10. Maintained by `/update-docs`.*
