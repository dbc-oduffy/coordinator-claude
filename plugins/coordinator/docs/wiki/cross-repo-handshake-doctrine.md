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

Pair with `check-shipped-on-main.sh` for the upstream check (producer on main); this section is the downstream check (consumer actually calling the producer). Both gates must pass before the handoff is stamped shipped.

## In-session verification beats cross-repo acceptance handoff

*2026-05-17, project-rag.* When the host EM has the corpus and tool access to verify a cross-repo deliverable directly — RAG indices, build tooling, test runners — preferring an in-session verification step over a cross-repo acceptance handoff is cheaper and more reliable. Handoffs require the receiving EM to context-load before they can confirm; the producer EM already has context. Defer to a cross-repo acceptance handoff only when (a) verification requires tools or corpus the producer EM lacks, or (b) the consumer's domain expertise is load-bearing for the acceptance call. Stop playing memo pong — when a verification ask CAN be done locally, do it; don't relay the ask back as a return memo. Sender-side memo escalation for verification depth launders a workflow decision the EM owns into the receiver's inbox.

## Bilateral schema-bump sequencing — both repos widen readers before either flips the manifest

**2026-05-27.** When two repos share a serialized contract (NDJSON stream, manifest, on-disk record shape) and the schema gains a field, the bump is bilateral and **ordered**: **every reader in both repos must accept the wider shape *before* any writer flips its manifest/version to emit it.** Flip-writer-first strands the lagging reader on a shape it can't parse.

- **Schema-additive ≠ projection-additive.** A field added to the schema is not automatically emitted by every projection. Audit *every* NDJSON emitter / record writer on both sides — a new column in the schema that one emitter forgets to populate produces a half-populated stream that readers can't distinguish from corruption.
- **Sequencing:** (1) widen all readers in both repos to tolerate the new field (absent or present); (2) ship and confirm on both sides; (3) *then* flip the writer's manifest/version to emit it. Each step is a separate landing.
- **The reader-widening is the regression net** for the writer flip — land it first, same discipline as "land regression-net tests before the refactor" (CLAUDE.md § Implementation Standards). → `install-surface-completeness.md` for the install-surface half (a version gate added after consumers exist must be advisory `WARN`, not hard-fail, or it regresses pre-gate installs).

## Ship against best-current-state when the upstream contract is in-flight — defer is the deadlock

**2026-05-27.** When a cross-repo dependency is mid-migration (the producer's contract is changing under you), the failure mode is mutual deferral — each side waits for the other to land first, and nothing ships. **Ship against the producer's best-current-state with a defensive `try/except` import + fallback**, not a hard dependency on the not-yet-landed shape:

- A defensive import (`try: from upstream import NewThing / except ImportError: NewThing = <fallback>`) lets the consumer land now and pick up the real shape when it arrives, with no deadlock and no synchronized-merge theater.
- Defer only when the fallback would ship something *wrong*, not merely *incomplete*. Incomplete-but-correct beats blocked.
- This is the runtime analogue of the bilateral-sequencing rule above: where sequencing applies (you control both readers), sequence; where the upstream is genuinely in-flight and out of your control, ship defensively against current state.

## Resolver-callable over host-side path-derivation for cross-repo value-shape contracts

**2026-05-27.** When a cross-repo contract involves a *value whose shape the producer owns* — a sub-path, a directory layout, a derived key — the producer supplies a `Callable[[], Path]` (a resolver) from day 1, rather than the consumer deriving the path host-side from an assumed layout. Host-side path-derivation bakes the producer's *current* internal layout into the consumer; when the producer reorganizes (e.g. per-band dirs become transient build intermediates discriminated by a metadata filter), every host-side derivation breaks silently. A resolver the producer exports moves the ownership of the shape to the side that owns the shape. *(Related: the 2026-05-26 per-band-corpus-dir memo — the producer's real model was one merged store discriminated by a metadata filter; a host that had derived per-band paths would have baked the wrong contract. See `cross-repo-communication.md` § Memo framing is hypothesis.)*

## Dated comments are expiration tags during cross-repo migration windows

**2026-05-27.** Concurrent peer-repo migrations create **transitional-correct-then-stale windows** on a 24–72h timescale: code that is correct *today* against a half-migrated sibling becomes wrong once the sibling completes its half. A comment-dated line (`# 2026-05-26: matches addon pre-v6 spec`) is the signal — during a migration window, **treat dated comments as expiration tags**, not just provenance. At substrate-verification time within a migration window, re-confirm any dated-comment assumption against the sibling's current HEAD before building on it. → `writing-plans.md` § substrate verification.

## Preemptive reviewed-diff handoff for cross-repo protocol bumps

**2026-05-27.** When a protocol/contract bump must cross to a sibling repo and you have the diff in hand, a **preemptive reviewed-diff handoff** (the diff, already reviewed for *handoff-readiness* — not just correctness — packaged for the sibling EM to land) beats a prose memo describing the change. The review lens here is "can the receiving EM apply this without re-deriving my context?", a superset of "is it correct." Route the diff via the `cross-repo-memo` channel (the memo carries/points at the diff) + PM-relay; the sibling EM lands it with their own context. → `cross-repo-communication.md` § Doctrine seeding vs. code/install-surface change (this is a code-altitude change — memo + PM-relay, not a direct write).

## Carve-out — bare-SHA sentinels for content-equivalence (copy_install)

**2026-05-28.** The one-line 40-hex git SHA `version.txt` written by `coordinator/bin/install-sentinel-write` and read by `coordinator/bin/check-plugin-drift.sh` + `coordinator/bin/check-install-divergence.py` is an **established exception** to the inline-assertion rule above. The sentinel is bare-data by design — three reasons it does not violate the doctrine:

1. **The reader carries the interpretation.** The drift probe and the classifier are the canonical readers; both know what a bare 40-hex SHA means in `<live>/version.txt` (the source HEAD at install time, used as the three-way classifier's baseline). The format does not need to self-document because reader-of-record is named in code.

2. **The format itself is the staleness-detection rule.** A 40-hex string that does not match the reader's current source HEAD is the staleness signal — no separate timestamp, fingerprint, or version-compare field is needed. Either it matches (clean), it differs but content matches (`[ok-via-git-propagation]` — see `live-install-drift-audit.md` content-equivalence fallback), or it differs and content differs (genuine drift). The single 40-hex SHA encodes all three outcomes when paired with the source HEAD and the content fallback.

3. **The cross-repo contract is canonicalized in one wiki.** [`live-install-drift-audit.md`](./live-install-drift-audit.md) documents the `version.txt` shape, the `[info] no sentinel` output, the content-equivalence fallback, and the named writer-of-record (`install-sentinel-write` + downstream install ceremonies). Any consumer in any sibling repo can read that wiki to bind to the contract without reading classifier source. **This is the falsifiable boundary: a future bare-data cross-repo sentinel is permitted ONLY when it has its own canonicalization wiki naming reader + writer + format, the way `live-install-drift-audit.md` does for this case.** No canonicalization wiki → no exception → the inline-assertion rule applies.

Net: new cross-repo sentinels must still meet the inline-assertion rule above. The bare-SHA copy_install case is an established exception, not a license to ship bare-data sentinels generally.

## Cross-references

- [`live-install-drift-audit.md`](./live-install-drift-audit.md) — canonical convention authority for `version.txt` shape (referenced by the carve-out above).
## land host-side compute with guarded no-op ahead of sibling DDL

Land host-side compute ahead of a sibling-repo's schema/DDL by gating the write on sibling artifact presence. A guarded no-op (e.g., `if not schema_exists: return`) lets the work ship without blocking on cross-repo sequencing. The sibling lands the DDL on their own timeline; the host code auto-activates on next run. Apply: whenever host code depends on a sibling-owned schema object, add a guard that returns a benign no-op if the schema object is absent.

## Mechanism Verification on Sibling-Pattern Adoption

When mirroring a sibling-repo pattern, verify the mechanism transfers — not just the shape. Pattern shape can transfer; the mechanism (e.g., where a version constant is sourced, how a health-check wire is wired) may be repo-specific. Also verify that the path you are replacing actually worked in the first place. Apply: for each sibling pattern you adopt, (1) confirm the reason it works for the sibling holds in your substrate, (2) confirm the path you're replacing was actually functioning.

## Incoming `kind: fyi` Is "Accept-With-Amend Invited" — Not "Trust the Diff"

Incoming cross-repo `kind: fyi` memos mean no action is requested — NOT that the content is integrated correctly. Coordinated triples (code/schema/fixture) arriving via fyi must still get a code-reviewer pass and a targeted test-run before consumption. Apply: treat every inbound fyi as "accept with permission to amend" and run `code-reviewer` before adopting the content.

## Cross-Repo Migration Memo Is a Hypothesis — Scout Before Adopting

A cross-repo "take everything" migration memo over-claims scope. Scout provenance, byte-identity, regenerability, policy bans, and rename collisions before adopting. Thorough investigation routinely inverts the framing ("we already own this"). Apply: for any migration memo, dispatch a scout that checks: `git log -- <path>` on the sibling, `grep` for your own holding, DR classification of each artifact, and rename collision with your existing tree.

## Direct-Commit Doctrine Has a Sibling-Own-Tree Carve-Out

The triad-roles-doctrine direct-commit rule governs authoring work in a peer tree. A signal-back memo about a sibling's OWN-tree action (their prune timing, decline decision, cleanup scheduling) is legitimately a record-keeping memo — it does not constitute cross-repo code writing. Apply: a memo that records "we are declining / deferring X on our own timeline" is a record-keeping memo, not a violation of the direct-commit doctrine.

## Stop playing memo pong — when a verification ask can be done locally, do it

When a verification ask in a memo CAN be done locally in-session, do it rather than relaying the ask back as a return memo. Sender-side memo ladder for verification depth launders a workflow decision the EM owns into the receiver's inbox. Apply: before sending a return memo asking the sender to verify something, ask "can I grep/read/run this locally?" If yes, do it.

- [`agentic-install-integrity.md`](./agentic-install-integrity.md) — doctrine wiki for the lifted classifier + deferred extensions (semantic-vs-byte, plugin-spawned state, agent-readable boot sentinel).
- [`cross-repo-contract-test-discipline.md`](./cross-repo-contract-test-discipline.md) — roadmap-stub schemas speculative-until-grounded; byte-equal fixtures + `eol=lf` pinning as the executable contract oracle.
- [`cross-repo-citation-conventions.md`](./cross-repo-citation-conventions.md) — how to cite across repos in handoffs and plans
- [`cross-repo-communication.md`](./cross-repo-communication.md) — when to use a sentinel vs. PM-relay vs. archive link
- [`scoped-safety-commits.md`](./scoped-safety-commits.md) — staging discipline when sentinel updates ride alongside other work
