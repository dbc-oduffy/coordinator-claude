# Pre-Dispatch Verification

**System:** coordinator
**Provenance:** consolidated 2026-05-14 from `tasks/coordinator-improvement-queue.md` triage (E40, E51, E87, E88, E150, E156).

Plans drafted against unchecked substrate become dispatches that find a different reality on disk. Verify at plan-write time, not after the executor reports back. Companion to `coordinator/CLAUDE.md` § Pre-Dispatch Verification — this wiki carries the longer-form rules and refinements.

---

## Premise-Pass Discipline

- **Premise-pass extends to mechanical premises, not just architectural ones.** JSON field names, env-var presence, registry keys, frontmatter fields all count as premises. A plan citing `install-status.json.deployment_state` MUST grep the schema to confirm the field exists before the executor depends on it.

- **Plan-stub-vs-landed-disk drift is structural — research before re-author.** When a roadmap stub cites cross-repo deliverables ("PR-N landed in peer repo X"), the plan-author MUST cross-repo grep the landed code before re-authoring. Stub-vs-landed drift is a structural staleness mode — the stub is hypothesis, the landed code is ground truth.

- **Re-extraction as crash recovery is process theater when versioned artifacts already exist.** Across multi-repo splits (host + addon + plugin), a crash mid-extraction tempts the recovery EM to re-run the producer pipeline. Before doing so, survey peer-repo artifacts for the versioned output the producer would have written — if `peer-repo/dist/<artifact>-vN.json` exists with a matching schema/version, the producer succeeded and the crash was downstream. Re-running the producer wastes a session and risks overwriting good output with a fresh run that diverges from what consumers already pinned. Companion rule in CLAUDE.md § Verifying Executor Output. (2026-05-15, project-rag-ue-addon.)

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

## Consumer Parsers Must Verify Producer's Actual Output Shape

When the plan adds a consumer (parser, importer, validator) for an existing producer's output, **grep the producer's emit-site to read the actual shape — do not infer the shape from the producer's spec or doc string.** Producer specs lag implementation; a spec that describes a JSON-blob output may correspond to a producer that emits NDJSON, or a wrapped envelope, or an empty `[]` on certain branches the spec didn't anticipate. Consumer code authored against the spec then fails on inputs the producer actually emits.

This is a strict extension of the no-fabrication-on-cited-fields rule above: the cited surface is the producer's *output shape* (top-level type, key names, optional-field nullability, error-branch shapes), and the canonical reference is the producer's code, not its docs. Grep the producer's serialization site (`return json.dumps(...)`, `yaml.safe_dump(...)`, the emit call) and read the actual structure before writing the consumer.

## Related

- `coordinator/CLAUDE.md` § Pre-Dispatch Verification — the canonical bullet list.
- `docs/wiki/tiered-context-loading.md` — what to read before dispatching.
- `docs/wiki/prior-art-checker.md` — automated pre-flight against accumulated prior art.
- `docs/wiki/docs-checker-pre-review.md` — automated pre-flight on external API claims.
