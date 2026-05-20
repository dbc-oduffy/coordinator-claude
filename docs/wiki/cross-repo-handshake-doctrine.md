# Cross-Repo Handshake Doctrine

> Sentinel artifacts that cross a repo boundary must self-document their preconditions inline. The producer's plan is invisible at consumption time.

## Lesson surface

**2026-05-13, claude-unreal-holodeck.** A producer dropped a sentinel file (lockfile / manifest / handoff marker) into a downstream repo to assert "X is ready." The consumer read it without context — and without the producer's plan, could not validate preconditions still held. The contract lived in the producer's head, not on disk.

## Failure shape

Cross-repo sentinels degrade silently in three ways:

- **Bare-presence sentinels.** File exists; consumer infers readiness from existence alone. No way to detect the upstream world moved on (version bumped, fingerprint mismatched).
- **Producer-only documentation.** Semantics live in the producer's plan/wiki/commit message — invisible to a consumer-side reader walking the file cold.
- **Implicit co-state.** Sentinel asserts X, but X only holds when Y and Z also hold (build hash, schema version, freshness window). Co-state in producer's head.

When the consumer reads in a future session — or in a different repo's EM — none of that context survives the boundary.

## Rule

**Every sentinel written across a repo boundary must carry, in-band:**

- **(a) What does my presence assert?** One-line claim. "Holodeck plugin build N installed, matches engine M."
- **(b) What co-state must hold?** Preconditions named explicitly — version pins, fingerprints, sibling-file requirements, schema versions.
- **(c) How is staleness detected?** A concrete check the consumer can run from the sentinel alone — timestamp window, fingerprint to recompute, version compare, upstream SHA.

Producer-side documentation is necessary but not sufficient. **The consumer-side reader must validate the handshake from the sentinel alone**, without producer plan/code/wiki.

## Concrete sentinel formats that work

- **YAML/JSON body.** Required keys: `asserts:`, `requires:` (co-state with expected values), `staleness_check:` (command or rule), `produced_by:` (repo + SHA + ISO timestamp), `schema_version:`.
- **Fingerprint-bearing lockfiles.** Hash of the upstream artifact, not just `ready: true`. Consumer recomputes and compares.
- **Self-validating manifests.** Inline validation rule (`min_engine_version:`, `expected_plugin_sha:`) — consumer check is a pure function of sentinel + local state.
- **No bare-presence sentinels across repo boundaries.** Empty `.ready` markers belong only in a single repo where producer and consumer share a plan.

## Half-shipped tripwire: verify consumer wiring before stamping `consumed`

**Cross-repo halves both ship before stamping `consumed` + `shipped_in:`.** A one-half-shipped report (producer landed, consumer not yet wired) is inert as a contract claim — the metadata says shipped but the runtime says "the symbol exists, the consumer just never calls it." Per CLAUDE.md § Handoff Lineage the terminal frontmatter is `status: consumed` with a `shipped_in: <commit-SHA or PR ref>` — `shipped` as a status value is rejected.

Before flipping a cross-repo handoff to `status: consumed` / `deployment_state: shipped`, the producer-side EM must verify that the consumer-side wiring matches the contract metadata:

1. **Grep the consumer's source** for the producer's exported symbol, path, or route.
2. **Confirm at least one live call-site** — bare presence of the import is not enough; the import might exist with no caller.
3. **Confirm a test or runtime probe exercises the call-site** — a wired-but-untested path is still a half-shipped contract.

Pair with `bin/check-shipped-on-main.sh` for the upstream check (producer on main); this section is the downstream check (consumer actually calling the producer). Both gates must pass before the handoff is stamped shipped.

## In-session verification beats cross-repo acceptance handoff

*2026-05-17, project-rag.* When the host EM has the corpus and tool access to verify a cross-repo deliverable directly — RAG indices, build tooling, test runners — preferring an in-session verification step over a cross-repo acceptance handoff is cheaper and more reliable. Handoffs require the receiving EM to context-load before they can confirm; the producer EM already has context. Defer to a cross-repo acceptance handoff only when (a) verification requires tools or corpus the producer EM lacks, or (b) the consumer's domain expertise is load-bearing for the acceptance call.

## Cross-references

- [`cross-repo-citation-conventions.md`](./cross-repo-citation-conventions.md) — how to cite across repos in handoffs and plans
- [`cross-repo-communication.md`](./cross-repo-communication.md) — when to use a sentinel vs. PM-relay vs. archive link
- [`scoped-safety-commits.md`](./scoped-safety-commits.md) — staging discipline when sentinel updates ride alongside other work
