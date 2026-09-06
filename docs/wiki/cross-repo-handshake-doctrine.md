# Cross-Repo Handshake Doctrine

> Sentinel artifacts that cross a repo boundary must self-document their preconditions inline. The producer's plan is invisible at consumption time.

## Lesson surface

**example-game-workbench-repo.** A producer dropped a sentinel file (lockfile / manifest / handoff marker) into a downstream repo to assert "X is ready." The consumer read it without context — and without the producer's plan, could not validate preconditions still held. The contract lived in the producer's head, not on disk.

## Failure shape

Cross-repo sentinels degrade silently in three ways:

- **Bare-presence sentinels.** File exists; consumer infers readiness from existence alone. No way to detect the upstream world moved on (version bumped, fingerprint mismatched).
- **Producer-only documentation.** Semantics live in the producer's plan/wiki/commit message — invisible to a consumer-side reader walking the file cold.
- **Implicit co-state.** Sentinel asserts X, but X only holds when Y and Z also hold (build hash, schema version, freshness window). Co-state in producer's head.

When the consumer reads in a future session — or in a different repo's EM — none of that context survives the boundary.

## Rule

**Every sentinel written across a repo boundary must carry, in-band:**

- **(a) What does my presence assert?** One-line claim. "example-game-repo plugin build N installed, matches engine M."
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

Pair with `check-shipped-on-main.py` for the upstream check (producer on main); this section is the downstream check (consumer actually calling the producer). Both gates must pass before the handoff is stamped shipped.

## In-session verification beats cross-repo acceptance handoff

*project-rag.* When the host EM has the corpus and tool access to verify a cross-repo deliverable directly — RAG indices, build tooling, test runners — preferring an in-session verification step over a cross-repo acceptance handoff is cheaper and more reliable. Handoffs require the receiving EM to context-load before they can confirm; the producer EM already has context. Defer to a cross-repo acceptance handoff only when (a) verification requires tools or corpus the producer EM lacks, or (b) the consumer's domain expertise is load-bearing for the acceptance call. Stop playing memo pong — when a verification ask CAN be done locally, do it; don't relay the ask back as a return memo. Sender-side memo escalation for verification depth launders a workflow decision the EM owns into the receiver's inbox.

## Bilateral schema-bump sequencing — both repos widen readers before either flips the manifest

**2026-05-27.** When two repos share a serialized contract (NDJSON stream, manifest, on-disk record shape) and the schema gains a field, the bump is bilateral and **ordered**: **every reader in both repos must accept the wider shape *before* any writer flips its manifest/version to emit it.** Flip-writer-first strands the lagging reader on a shape it can't parse.

- **Schema-additive ≠ projection-additive.** A field added to the schema is not automatically emitted by every projection. Audit *every* NDJSON emitter / record writer on both sides — a new column in the schema that one emitter forgets to populate produces a half-populated stream that readers can't distinguish from corruption.
- **Sequencing:** (1) widen all readers in both repos to tolerate the new field (absent or present); (2) ship and confirm on both sides; (3) *then* flip the writer's manifest/version to emit it. Each step is a separate landing.
- **The reader-widening is the regression net** for the writer flip — land it first, same discipline as "land regression-net tests before the refactor" (CLAUDE.md § Implementation Standards). → `install-surface-completeness.md` for the install-surface half (a version gate added after consumers exist must be advisory `WARN`, not hard-fail, or it regresses pre-gate installs).

### Carve-out — `top-level-array-additive` bumps are non-holding against confirmed-tolerant consumers

**example-cockpit-repo per-repo-observation-model.** The bilateral sequencing rule above still governs the general case and, unchanged, governs **nested-field-additive** bumps (a new field on an existing entity object) — those break `.strict()` consumers (row quarantined) and remain **holding / bilateral-sequencing-required** until consumers adopt entity-level unknown-field tolerance. NOT free-emit.

But a **top-level-array-additive** bump — a wholly new top-level array added to the contract, not a field grafted onto an existing entity — is exempt from that ordering, under the following pinned predicate:

> A **top-level-array-additive** bump is non-holding IFF every registered consumer of that contract structurally ignores unknown top-level arrays — a capability each consumer must DECLARE, not one producers may assume. Absent a declared-tolerant consumer set, the bump reverts to bilateral-sequencing.
>
> Declared tolerance is **two-dimensional**: (1) STRUCTURAL — the consumer ignores/replayably-quarantines unknown top-level arrays rather than full-validating; AND (2) VERSION-ENVELOPE — the bump must land within the consumer's accepted `schema_version` range. The additive bump must therefore ship as a MINOR/patch widen (never rolled into a MAJOR increment — a major bump trips every consumer), and must stay at/above each consumer's minor-floor. A producer that couples an additive-array widen to a major bump, or emits below a consumer's floor, reverts to bilateral-sequencing for that consumer.
>
> A **nested-field-additive** bump — a new field on an existing entity object — breaks `.strict()` consumers (row quarantined). It is **holding / bilateral-sequencing-required** (widen consumers first) UNTIL consumers adopt entity-level unknown-field tolerance. NOT free-emit. (see § Acceptance-readiness vs. branch-position for the named exception, gated on the identity-free consumer-capability census of `cockpit-contract-entity-addition-protocol.md` Step (g) — NOT on siblinghood — with the lockstep-cadence fact explaining only why the quarantine window is transient)
>
> Binding fleet envelope: **major 2, minor ≥ 2.3.0** — binding because of rag's floor alone (cockpit imposes no floor).

**Mechanism, not version number.** The reason a top-level-array-additive bump is non-holding is structural, independent of the version bump itself: the consumer's ingest loop never reads unknown top-level arrays in the first place — it iterates the known, named top-level keys and is structurally blind to a new sibling array. The version bump is the *envelope* gate (dimension 2 above); the *structural* gate (dimension 1) is what actually makes the bump safe, and that gate is a property of the consumer's ingest-loop implementation, not of any version number the producer chooses. A producer must confirm the structural property is **declared** by each consumer, not infer it from the fact that the bump "looks additive."

**Retiring the sentinel-hold + ack-brigade for this case.** Against a consumer whose structural tolerance is confirmed (not merely assumed) and whose version-envelope covers the bump, the producer emits the new top-level array directly — no sentinel-hold, no cross-repo ack-brigade, no bilateral reader-widen-first sequencing. The confirmed-tolerant consumer set is the scope boundary: any consumer NOT in that confirmed set still gets full bilateral sequencing.

**Correcting the record — cockpit's residual holding surface.** example-cockpit-repo already moved its top-level envelope gate to major-only `checkSchemaVersion` (a minor/patch bump inside the accepted range is a structural no-op for the envelope check). The residual holding surface in cockpit is **per-entity `.strict()` validation** — i.e. nested-field-additive, not the top-level envelope. Citing cockpit's ingest behavior for either case should reference the capability/concept and `example-cockpit-repo/docs/decisions/2026-07-07-cockpit-live-remote-per-repo-observation-model.md`, not volatile `file:line` — cockpit's `ingest.ts` line numbers drift as its per-repo-ingest plan lands.

## Ship against best-current-state when the upstream contract is in-flight — defer is the deadlock

**2026-05-27.** When a cross-repo dependency is mid-migration (the producer's contract is changing under you), the failure mode is mutual deferral — each side waits for the other to land first, and nothing ships. **Ship against the producer's best-current-state with a defensive `try/except` import + fallback**, not a hard dependency on the not-yet-landed shape:

- A defensive import (`try: from upstream import NewThing / except ImportError: NewThing = <fallback>`) lets the consumer land now and pick up the real shape when it arrives, with no deadlock and no synchronized-merge theater.
- Defer only when the fallback would ship something *wrong*, not merely *incomplete*. Incomplete-but-correct beats blocked.
- This is the runtime analogue of the bilateral-sequencing rule above: where sequencing applies (you control both readers), sequence; where the upstream is genuinely in-flight and out of your control, ship defensively against current state.

## Acceptance-readiness vs. branch-position — killing the mutual-deference standoff

**claude-klabauter↔DoE (memo: nix-mutual-deference-reach-main-first) + C7 origin_* emit.**

**The anti-pattern (name it): the mutual-deference standoff.** In a bilateral contract bump between co-developed repos, reader-first degrades into deadlock when each side defensively waits for the other to "land on `main` first." *"You go first" / "no, I insist you go first"* — it reads as safety; it is process theater. If both sides serialize on the other's main-position, nobody moves. <!-- Review: eng-director (the Director of Engineering) — the runtime/in-flight-upstream face of the same deadlock is § Ship against best-current-state; one-clause cross-ref, no restructure. --> (The runtime/in-flight-upstream face of the same deadlock is § "Ship against best-current-state when the upstream contract is in-flight" above — mutual deferral there, mutual deference-on-branch-position here, are two faces of one deadlock.)

**The root confusion: acceptance-readiness ≠ branch-position.** Reader-first governs **acceptance readiness** — *has the reader widened to accept (or gracefully degrade against) the new shape?* — NOT **branch position** — *has the reader's code reached `main`?* A reader that has widened on its work branch **is ready**; it does not need to be on `main` first. Conflating the two converts an answerable readiness question (non-blocking) into a deadlockable ordering question.

**Lockstep default: aligned-branch + coordinated-merge.** For **co-developed lockstep repos** — same operator, sibling `work/*` branches, shared cadence (the machine-b fleet: claude-klabauter / DoE / cockpit / rag) — a bilateral contract bump coordinates by: (a) **Align on branch** — vendor/integrate across each other's *current work branches*, not off `main`; the vendored pin may lead the release tag (reader-first-ahead-of-tag; `docs/decisions/DR-167-cockpit-contract-standing-owner.md` tolerates). (b) **Merge to main together** — coordinated merge so the bump lands atomically from the fleet's view; if a SHA moves on merge (rebase/squash), the pin **re-cuts at merge time** — provenance bookkeeping, not a gate. (c) **Key any residual hold on acceptance, never main-position** — "has the reader widened / does it degrade gracefully?" is the only legitimate gate, and even that is the *reader's* self-protection (loud hard-throw on MAJOR mismatch), not a producer-side wait.

**Reserve strict producer-holds-for-reader serialization for genuinely independent release trains** (different operators, async cadence) — and even there, gate on acceptance, not on `main`. <!-- Review: eng-director (the Director of Engineering) — named the main-tag-pinned consumer as the canonical example of the reserved carve-out, so a reader doesn't mistake "branch-position is theater" as universal. --> e.g. a consumer that vendors only from main-tagged releases — for it, reaching main and cutting the tag IS the legitimate gate, because the producer's work branch is not a vendoring source it consumes; such a consumer is an independent release train by construction and falls outside the lockstep default by design, not by exception.

**Runtime-emit altitude — the same confusion one level down, and a REFINEMENT (named exception) to the nested-field-additive carve-out above.** The § top-level-array carve-out correctly pins **nested-field-additive** bumps as holding / bilateral-sequencing-required by default ("NOT free-emit") because they quarantine rows on `.strict()` consumers. <!-- Review: eng-director (the Director of Engineering) — re-anchored the exception's trigger on the identity-free consumer-capability census (cockpit-contract-entity-addition-protocol.md Step g), not on siblinghood; a relationship predicate is neither necessary nor sufficient for emit-first safety. --> **Named exception:** emit-first is safe **IFF every registered consumer of the contract passes the consumer-capability census** — (a) replayable-quarantine (unknown/newer entity data is parked, retained, and replayed on re-vendor, never silently dropped and never a whole-envelope hard-throw) AND (b) observable-skip (the quarantine is visible on a query/health/doctor surface without depending on the producer to notify) — at the emitted bump class (minor/patch), per `cockpit-contract-entity-addition-protocol.md` Step (g) (`DECISIONS.md § D21`). That capability census — run per bump, identity-free, re-armed automatically the moment a new or non-conforming consumer joins the registered set — is what licenses emit-first, not any relationship between producer and consumer. The **lockstep sibling re-vendoring on the shared cadence** fact explains WHY the quarantine window is transient (the re-vendor that closes it is actually imminent) — it is the answer to the "does the re-vendor actually come" half of the discriminator below, not the safety gate itself. A future *strict* (non-quarantining) sibling would still fail the census and be denied emit-first; an independent, non-sibling consumer that DOES pass the census would still qualify. <!-- Review: eng-director (the Director of Engineering) — minor finding folded in: self-heal is conditional on the consumer ingesting a full-snapshot emission, not an unconditional property of quarantine-and-replay. --> **Self-heal precondition (folds into the census):** the self-heal holds because the emission is a full state snapshot re-ingested idempotently on natural keys — the re-vendored ingest re-presents the same rows, which now validate. A consumer ingesting a **delta/append stream** instead of a full snapshot does NOT self-heal this way (a quarantined row would never be re-presented) and fails census bar (a) on that basis — it stays on the default bilateral-sequencing hold. The default hold still governs when the quarantine would **persist**: an independent consumer with an indefinite re-vendor horizon means missing-data is real, and bilateral sequencing applies. **Discriminator:** does the consumer's quarantine self-heal (census bar (a), full-snapshot re-ingest) on a re-vendor that is actually coming (lockstep-sibling freshness)? Census-passing + imminent re-vendor → emit-first; census-failing or independent-with-indefinite-horizon → hold. <!-- Review: eng-director (the Director of Engineering) — softened the self-heal claim from certainty to a bounded-benign window; "actually coming" is a prediction, not a checkable state, and census bar (b) is the forcing function that bounds the downside if the re-vendor slips. --> The "actually coming" half of the discriminator is a prediction, not a checkable state — if a lockstep sibling's re-vendor slips (deprioritized, cadence changes, repo goes dormant), the window does not silently degrade to data loss: it is **bounded-benign**, closed whenever the re-vendor eventually lands, with the interim visible via the consumer's `malformed_ingest` surface (census bar (b) is precisely this forcing function). Only consumer-render freshness degrades in that slip case; integrity and observability hold throughout.

**Two concrete instances:**

- *claude-klabauter↔DoE cockpit-contract v2.8.0:* claude-klabauter nearly deferred its re-vendor "until DoE reaches main" — which DoE could mirror (deadlock) and which conflated readiness with branch-position. DoE's 2.8.0 was on its work branch, widened and ready; claude-klabauter vendored off the aligned branch and both merge together. No serialization needed.
- *C7 `origin_*` (this session, `4008f5e`):* DoE emitted `origin_*` on `HandoffSummary` — a nested-field-additive, same-major MINOR bump (2.8.0→2.9.0) on cockpit's `.strict()` entity — **emit-first**, because cockpit passes the consumer-capability census (its ingest parks unknown-key rows in `malformed_ingest`, replayable, and observable on a health surface) and is a lockstep sibling re-vendoring on the fleet cadence, so the transient quarantine window is closing imminently: a genuine self-heal, not data loss. Gating DoE's emit on cockpit's reader-ready *confirm* would have been the standoff. <!-- Review: eng-director (the Director of Engineering) — the minor-bump-ness (same major, 2.8.0→2.9.0) is what routes this instance to the census minor-bump path, not the sibling relationship per se. -->

**Cockpit Head-of-Product steer (memo: stop-emit-read-deference-theater).** **The courtesy-stall memo is the standoff wearing prose.** The mutual-deference standoff has a memo tell: authoring a memo whose subtext is "we held emit until you were ready to read." It reads as courtesy and functions as a stall — the code didn't wait, but the memo reintroduces the standoff in prose. Reader-widens-ahead is the standing default posture, not a per-bump negotiation to re-open each time a field lands. A producer that is census-clear to emit (per the runtime-emit exception above) owes no "ready to read?" handshake and should not author one; the emit itself, plus the consumer's own tolerant ingest, is the whole contract. Stop authoring emit memos whose real content is deference.

**Version-desync hops are producer-side hygiene, never consumer obligations.** When an additive field can only be reached by passing through an intermediate contract version — e.g. an owner-string reshape froze 2.8.0, forcing consumers through a two-hop re-vendor (2.8.0 owner-string, then 2.9.0 origin_*) to consume one field the reader already modelled — the producer must NOT hand the consumer an ordered "re-vendor twice, in this sequence" chore. Two correct producer-side resolutions: (a) land the coupled hops together as one consumable bump, or (b) absorb the intermediate internally so the consumer sees a single additive step. Surfacing the desync sequence to the consumer as coordination they must sequence around is the mutual-deference standoff in a version-desync costume: on a single-machine lockstep fleet the coordination cost of sequencing the hops exceeds the engineering cost of the change being coordinated — the definition of process theater. **Discriminator:** if a consumer must re-vendor N times in a prescribed order to reach one additive field, that ordering is producer-side hygiene the producer failed to absorb — fix it producer-side, do not document it as a consumer step — UNLESS neither producer-side resolution is reachable (the intermediate is a genuinely-breaking change that cannot be coupled into one landing (a) nor absorbed internally (b), e.g. an independent-release-train hop per § Acceptance-readiness vs. branch-position's own carve-out above), in which case the ordered multi-hop is not producer hygiene but a legitimate reversion to the § Bilateral schema-bump sequencing default. The hygiene finding applies only when (a) or (b) WAS available and the producer surfaced the sequence instead. <!-- Review: eng-director (the Director of Engineering) — qualified the discriminator so it doesn't presume absorption is always reachable; the memo's own (a)-OR-(b) disjunction has a residual case (genuinely-breaking, un-absorbable intermediate on an independent release train) that reverts to bilateral sequencing, not producer hygiene. -->

**"Live on the contract" ≠ "on the wire": a field is not live until its live emit path emits it.** Distinct from the § Half-shipped tripwire above (which checks the *consumer* call-site). This checks the *producer emit path*. A field can be live on the contract — schema and emitter code landed (e.g. C7 `origin_*` on cockpit-contract 2.9.0, `4008f5e`) — yet reach zero consumers because the *actual runtime emit path* that writes to the wire is pinned to an older contract version (the claude-klabauter daemon on 2.7.0 at the time of this steer). "Shipped on the contract" and "flowing on the wire" are two distinct events, and the gap between them is exactly where a consumer wastes cycles waiting for data that is not coming. **Rule:** couple every "shipped" announcement to the producer that actually emits the field on the wire, or state it plainly — "shipped on the contract, not yet on any wire (live emit path is `<producer>` at `<version>`)." Pair with the § Half-shipped tripwire: that gate is the consumer call-site, this gate is the producer emit-path — both must hold before "live" is a truthful claim.

## Resolver-callable over host-side path-derivation for cross-repo value-shape contracts

When a cross-repo contract involves a *value whose shape the producer owns* — a sub-path, a directory layout, a derived key — the producer supplies a `Callable[[], Path]` (a resolver) from day 1, rather than the consumer deriving the path host-side from an assumed layout. Host-side path-derivation bakes the producer's *current* internal layout into the consumer; when the producer reorganizes (e.g. per-band dirs become transient build intermediates discriminated by a metadata filter), every host-side derivation breaks silently. A resolver the producer exports moves the ownership of the shape to the side that owns the shape. *(Related: the per-band-corpus-dir memo — the producer's real model was one merged store discriminated by a metadata filter; a host that had derived per-band paths would have baked the wrong contract. See `cross-repo-communication.md` § Memo framing is hypothesis.)*

## Dated comments are expiration tags during cross-repo migration windows

Concurrent peer-repo migrations create **transitional-correct-then-stale windows**: code that is correct *today* against a half-migrated sibling becomes wrong once the sibling completes its half. A comment-dated line such as `# 2026-05-26: matches addon pre-v6 spec` is the signal — during a migration window, **treat dated comments as expiration tags**, not just provenance. At substrate-verification time within a migration window, re-confirm any dated-comment assumption against the sibling's current HEAD before building on it. → `writing-plans.md` § substrate verification.

## Preemptive reviewed-diff handoff for cross-repo protocol bumps

**2026-05-27.** When a protocol/contract bump must cross to a sibling repo and you have the diff in hand, a **preemptive reviewed-diff handoff** (the diff, already reviewed for *handoff-readiness* — not just correctness — packaged for the sibling EM to land) beats a prose memo describing the change. The review lens here is "can the receiving EM apply this without re-deriving my context?", a superset of "is it correct." Route the diff via the `cross-repo-memo` channel (the memo carries/points at the diff) + PM-relay; the sibling EM lands it with their own context. → `cross-repo-communication.md` § Doctrine seeding vs. code/install-surface change (this is a code-altitude change — memo + PM-relay, not a direct write).

## Carve-out — bare-SHA sentinels for content-equivalence (copy_install)

**2026-05-28.** The one-line 40-hex git SHA `version.txt` written by claude-klabauter `coordinator/bin/install-sentinel-write` and read by claude-klabauter `coordinator/bin/check-plugin-drift.py` + `coordinator/bin/check-install-divergence.py` is an **established exception** to the inline-assertion rule above. The sentinel is bare-data by design — three reasons it does not violate the doctrine:

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

## Shared versioned contract — `started_at` + `completeness-checklist-mirror`

**DoE↔claude-klabauter.** DoE (producer) emits two session-substrate signals that claude-klabauter (consumer) reads at its `/workstream-complete` X→D conversions. Claude-klabauter consumes both and now **asserts the mirror schema tag consumer-side**, so a future producer bump surfaces as memo-worthy evidence drift rather than silently degrading to `{0,0}`. This section canonicalizes both formats as the shared contract both repos cite — the reader/writer/format naming the carve-out below requires of any cross-repo bare-data or semi-structured signal.

### `started_at` — session-start timestamp (unversioned by design)

- **Path:** `<SESSION_DIR>/started_at`, where `SESSION_DIR` = `.git/coordinator-sessions/<sid>/`.
- **Format:** a single line, ISO-8601 UTC (`%Y-%m-%dT%H:%M:%SZ`). No trailing keys, no schema tag — the one-liner is **deliberately unversioned**; its shape cannot meaningfully bump without becoming a different file.
- **Write semantics:** write-once / idempotent — written only if absent (`[[ ! -f … ]]`), so a re-boot within the same session never rewrites it.
- **Writer-of-record:** `bin/sweep-boot.py` trampoline + `session.boot_sweep` claude-klabauter op, successor to the retired `coordinator/hooks/scripts/session-init.py` SessionStart hook, itself successor to `coordinator/lib/coordinator-session.sh`'s `cs_*` session bootstrap (native successor `coordinator_core.session`).
- **Consumer-of-record:** claude-klabauter `/workstream-complete`'s chain-slug ladder (case-a → D; formerly folded into the `ceremony.wsc_tail` op, removed by K-046) via `git log --diff-filter=A --since=<started_at>` over `docs/plans/*.md`. Also DoE-internal (formerly `coordinator-session.sh` MY_SCOPE mtime fallback).
- **Staleness rule:** the timestamp *is* the staleness rule — anything file-created after it is in-session. No separate check needed.

### `completeness-checklist-mirror-v1` — checklist disk mirror (versioned)

- **Path:** `state/tasks/<sid>/completeness-checklist.yaml` (protected `state/` substrate — never bare `tasks/` — `global-doctrine/CLAUDE.md` § Coordinator Operating Doctrine).
- **Format:** YAML. Top-level keys: `schema: completeness-checklist-mirror-v1`, `sid:`, `created_at:`, `updated_at:` (all ISO-8601 UTC), and `items:` — a list of `{ title, state, updated_at }` where `state` ∈ `{open, done}`. Values are single-quoted YAML scalars (`''`-escaped).
- **Writer-of-record:** claude-klabauter `coordinator/bin/coordinator-tasks-mirror.py` (`init` / `update` subcommands).
- **Consumer-of-record:** claude-klabauter `/workstream-complete`'s `gates.completeness_checklist` gate (checklist items → D) via a line-pattern count of `state: open` — no YAML parser, per claude-klabauter's prior-art finding.
- **Version seam:** the `schema:` tag is the bump surface. The consumer **asserts** the tag (`completeness-checklist-mirror-v1`); a producer bump to `-v2` must be a **coordinated bilateral change** per the § "Bilateral schema-bump sequencing" rule above — widen the consumer's reader to tolerate both tags *before* the producer flips the emitted tag.

### Producer-change protocol

Any DoE change to either format is a cross-repo contract change: bump the `completeness-checklist-mirror` schema tag (never mutate a shape under a fixed tag), and route a `cross-repo-memo` to claude-klabauter **before** the bump lands so the consumer reader widens first (bilateral sequencing). The `started_at` one-liner is exempt from the versioned-bump protocol only because it cannot bump without becoming a different file — a *new* semantic signal there is a new sentinel, documented here.

### What stayed producer-blind — 2.67a

Not every X→D conversion consumes a producer signal. Claude-klabauter's Step 2.67a (session-authored transient-scratch self-clean) correctly stays manual-**X**: its self-clean predicate is *filesystem mtime over uncommitted scratch* (`docs/plans/2026-06-15-workstream-complete-self-clean.md`), to which a committed / session-id-tagged git-log predicate is structurally blind. Converting 2.67a to D on a git-log signal would emit a false-negative D that silently disables self-clean. The `started_at` producer signal is correct and load-bearing; it is simply insufficient *alone* for a predicate over uncommitted residue. The mtime consumer design is claude-klabauter's follow-up, not a DoE producer change.

- [`agentic-install-integrity.md`](./agentic-install-integrity.md) — doctrine wiki for the lifted classifier + deferred extensions (semantic-vs-byte, plugin-spawned state, agent-readable boot sentinel).
- [`cross-repo-contract-test-discipline.md`](./cross-repo-contract-test-discipline.md) — roadmap-stub schemas speculative-until-grounded; byte-equal fixtures + `eol=lf` pinning as the executable contract oracle.
- [`cross-repo-citation-conventions.md`](./cross-repo-citation-conventions.md) — how to cite across repos in handoffs and plans
- [`cross-repo-communication.md`](./cross-repo-communication.md) — when to use a sentinel vs. PM-relay vs. archive link
- [`scoped-safety-commits.md`](./scoped-safety-commits.md) — staging discipline when sentinel updates ride alongside other work
