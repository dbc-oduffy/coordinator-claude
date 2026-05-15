# Pre-Dispatch Verification

**System:** coordinator
**Provenance:** consolidated 2026-05-14 from `tasks/coordinator-improvement-queue.md` triage (E40, E51, E87, E88, E150, E156).

Plans drafted against unchecked substrate become dispatches that find a different reality on disk. Verify at plan-write time, not after the executor reports back. Companion to `coordinator/CLAUDE.md` § Pre-Dispatch Verification — this wiki carries the longer-form rules and refinements.

---

## Premise-Pass Discipline

- **Premise-pass extends to mechanical premises, not just architectural ones.** JSON field names, env-var presence, registry keys, frontmatter fields all count as premises. A plan citing `install-status.json.deployment_state` MUST grep the schema to confirm the field exists before the executor depends on it.

- **Plan-stub-vs-landed-disk drift is structural — research before re-author.** When a roadmap stub cites cross-repo deliverables ("PR-N landed in peer repo X"), the plan-author MUST cross-repo grep the landed code before re-authoring. Stub-vs-landed drift is a structural staleness mode — the stub is hypothesis, the landed code is ground truth.

---

## Surfacing Probes

- **Probe-without-surface is an invisible probe.** When an enumeration check runs but its output isn't surfaced to the EM or to logs (e.g. a hook that lints but suppresses stderr), the check effectively doesn't exist. Wrap enumeration outputs in sentinel comments and add a parity test that fails when the sentinel is missing.
  - **Snippet-sync tripwires specifically:** the tripwire's consumer list MUST enumerate every consuming agent prompt by path; an unlisted consumer drifts silently. Verify the list against grep before considering the snippet-sync tripwire complete.

---

## Sibling-Surface Capability Parity

- **Sibling surfaces implementing a shared contract MUST receive the same fix when the contract changes.** Setup script + recovery script, install + uninstall, install + doctor — capability divergence is a silent regression. Single-entry-point doctrine extends to capability-divergence checks — grep for sibling implementations of any contract you're about to extend.

---

## Gate-Verification Mechanics

- **Verifying an import gate (`from foo import bar`) requires the actual runtime's `sys.path`, not a bare `python -c 'import foo'` at the shell.** The hook/script's invocation context determines path resolution; bare-interpreter probes pass while real dispatch fails (and vice versa). Run the probe IN the dispatch's interpreter context.

---

## Related

- `coordinator/CLAUDE.md` § Pre-Dispatch Verification — the canonical bullet list.
- `docs/wiki/tiered-context-loading.md` — what to read before dispatching.
- `docs/wiki/prior-art-checker.md` — automated pre-flight against accumulated prior art.
- `docs/wiki/docs-checker-pre-review.md` — automated pre-flight on external API claims.
