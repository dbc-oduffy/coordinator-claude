# Pre-Dispatch Verification


Plans drafted against unchecked substrate become dispatches that find a different reality on disk. Verify at plan-write time, not after the executor reports back.

---

## Plan-Time Verification Checklist


- **Investigate before planning.** Bug reports / consumer docs are framing, not ground truth — scout for producer/consumer/schema `file:line` evidence. "Fully independent files" still needs file-overlap analysis. Native-code plans require 2-3 in-tree `file:line` citations.
- **Premise-pass before regenerating torn-down structure** — reversing a prior decision → grep wiki+lessons for why.
- **Audit symptom is correct; locus may be wrong** — verify producer code before accepting the audit's fix-locus.
- **Survey plan-substrate before dispatching on a not-just-authored plan**; re-run mechanical pre-flights after material amendments.
- **7-dim confidence checklist** — no-duplicate / no-fabrication / architecture-compatible / official-docs-read / reference-impl-seen / root-cause-known / fix-locus discrimination. All green or stop.
- **Reviewer rationale must discriminate chosen shape from alternatives.** If "nothing would change", approval is non-load-bearing.

## Premise-Pass Discipline

- **Premise-pass extends to mechanical premises, not just architectural ones.** JSON field names, env-var presence, registry keys, frontmatter fields all count as premises. A plan citing a specific dotted config field (e.g. `install-status.json.deployment_state`) MUST grep the schema to confirm the field exists before the executor depends on it.

- **Plan-stub-vs-landed-disk drift is structural — research before re-author.** When a roadmap stub cites cross-repo deliverables ("PR-N landed in peer repo X"), the plan-author MUST cross-repo grep the landed code before re-authoring. Stub-vs-landed drift is a structural staleness mode — the stub is hypothesis, the landed code is ground truth.

- **Re-extraction as crash recovery is process theater when versioned artifacts already exist.** Across multi-repo splits (host + addon + plugin), a crash mid-extraction tempts the recovery EM to re-run the producer pipeline. Before doing so, survey peer-repo artifacts for the versioned output the producer would have written — if `peer-repo/dist/<artifact>-vN.json` exists with a matching schema/version, the producer succeeded and the crash was downstream. Re-running the producer wastes a session and risks overwriting good output with a fresh run that diverges from what consumers already pinned. 
- **A contract reversal must reconcile code + tripwire + doctrine-doc in ONE change, or the stale doc is a re-introduction vector.** When a plan flips a runtime contract (a bake→runtime invariant, an enum's allowed set, a producer's emit shape), enumerate every surface that *encodes* the old contract — the code, any static-grep tripwire that asserts it, AND the doctrine/wiki/CLAUDE.md prose that documents it — and amend all three atomically. A reversal that updates the code but leaves the doc asserting the old contract leaves a live re-introduction vector: the next planner reads the stale doc as ground truth and re-codifies the reversed-away shape. Grep the contract's central noun across the doctrine wiki and lessons file before declaring the reversal landed. 
- **A "consume/delegate a shared primitive and retire the duplicate" spec can be premised on a duplication that doesn't exist in the shape described — verify the SHAPE of the code you're retiring, not just that the target files exist.**  Rule: when a consume/delegate spec promises to retire duplication, read the target locus and confirm the duplicate is the shape claimed; the right consumption is often an *additive* verification guard over a primitive that single-sources the *definition*, not a deletion. 
- **Grep the data-SHAPE contract a mechanism asserts, not just that the cited field exists somewhere.** A plan can pass path-verification (files exist at cited paths) and still be wrong at its central *mechanism* because that mechanism assumes a data-shape contract the corpus does not honor. Premise-pass on a frontmatter/field premise is NOT satisfied by finding one record that carries the key — when a mechanism depends on a field contract (every record carries key K; K is spelled exactly so; the discriminating value lives in K), grep the VALUE distribution and the exact spelling across the whole corpus.  Grep is authoritative over the spec for the mechanism's own asserted field contract, not only for paths and constants. 
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

## Verify the Realistic Execution Path — Actual Input Shapes and Test Path-Resolution

Substrate verification that confirms the code / test / artifact *exists* can still greenlight a dispatch that fails on the real execution path — because the inputs the flow actually feeds, or the path a test resolves the code under, differ from the idealized model the plan carried. Existence is necessary, not sufficient; verify the path the runtime actually takes.

- **Verification briefs must feed the actual on-disk value shapes, not clean synthetic placeholders.** An executor verified an arg-pass change with clean synthetic values and passed — but the real skill flow extracts pre-quoted, commented frontmatter values that double-quote and pollute when passed as args; the regression surfaced only under realistic inputs. Feed the actual quotes, comments, and null shapes the flow extracts, not idealized placeholders. 
- **Trace how the TESTS RESOLVE the code under test, not just that the code exists.** A plan to auth-adapt bash veneers verified the scripts and the auth pattern but missed that `conftest` resolved them via a path fixture nonexistent on the actual repo layout — so all of the bash-parity tests found no script (empty / exit-127) and never exercised the injection, greening vacuously. Pre-dispatch verification must follow the test's own path-resolution to the artifact (the `conftest` / fixture that computes the path), not merely confirm the artifact exists at its own path. A test that cannot locate the code under test is a green that proves nothing. 
## Enumerate EVERY Writer of a Path Before Codifying Its Role

A filter, predicate, or invariant applied at *one* writer of a shared store silently re-leaks through the others. Before codifying any rule about what a table/path/collection contains, grep for **every** writer — not just the producer the bug surfaced through.


**Rule:** before codifying a predicate on any shared store, `grep -rn "INTO <table>"` (or the write-API equivalent) across every producer/consumer/mirror module and fix **every** writer. Also: pre-delete import-graph verification catches inventory mis-classification that plan-review misses — grep every importer of a module before classifying it as "not used." Retiring an installed subsystem exposes orphaned tests, docs, and recovery-mappings that a `grep-zero + --collect-only` gate surfaces. This is a concrete instance of "grep every writer of a path before codifying its role" — off-the-main-wave writers (cross-layer passes, legacy mirrors, background ingest) are the ones a single-producer mental model misses.

## Enumerate the Full Caller Graph BEFORE Agreeing a Delete-Sweep Scope with a Peer EM

 When negotiating a delete-sweep scope with a peer EM (cross-repo cleanup, shared-surface removal), grep the full caller graph of every candidate **before** the scope is agreed, not after. An agreed-on "6-file scope" expanded to 22 files once the callers were actually enumerated — the agreement was struck against an un-grepped mental model, and the gap surfaced mid-execution as scope creep that had to be re-negotiated.

**Rule:** the caller-graph enumeration is a *pre-agreement* artifact. Grep every caller / referencer / dynamic-loader site of each delete candidate, write the real footprint, and bring *that* to the scope agreement. A scope agreed on intuition is a scope that re-opens at the first un-grepped caller. This composes with § Reference-Sweeps Must Enumerate ALL Context Shapes (below) — the same shape inventory that catches rename misses catches delete-sweep caller misses; run it before the handshake, not after.

## Reference-Sweeps Must Enumerate ALL Context Shapes and Runtime-Invocation Surfaces

A single-pattern grep catches **<80%** of a rename's references — recurring across at least three audits. The misses are the high-severity ones because they fail at *runtime in production*, not in CI.

**Two enumeration axes, both required before the first sweep wave:**

1. **Context shapes.** The same identifier hides across: `from`-imports · slash-strings · dot-strings · `pathlib` components · `os.path.join` / PowerShell `Join-Path` args · dynamic-loader call sites (`spec_from_file_location`, `import_module`, `__import__`, `exec(open())`, `require()`) · `@patch`/`monkeypatch.setattr` string targets · f-strings · word-boundary cases where the *new* namespace contains the *old* as a substring (naïve grep then false-positives on every new-namespace citation — anchor with `\b`). Enumerate the shape inventory and run a grep *per shape* before chunking; a single regex on the literal misses most of these.

2. **Runtime-invocation surfaces.** Substrate enumeration scoped to "where the code/tests/docs live" (`src/`, `tests/`, `docs/`) silently omits the dirs that *invoke* helpers by path: `commands/`, `plugin/`, hidden config dirs, skill dirs, config. Grep the **whole repo** for the literal before scoping chunks.

**Concrete failures:** (a) a helper-rename plan verified the source, test, and doc trees clean but missed a plugin command file that invokes the helper by absolute path — grep gates passed, a doctor step would have broken at runtime, only a test caught it. (b) A Python package rename has four import surfaces (from-imports + `os.path.join` string args + PowerShell `Join-Path` components + patch/monkeypatch string targets); a single-pattern audit captured <80%.

**Rule:** at plan-write time, write the shape inventory *and* the surface inventory into the plan body, grep each independently, and pair every static-grep tripwire with a runtime guard (a PreToolUse hook or an entrypoint test) — source-grep alone cannot see what agent-prompt instructions or command files write/invoke at runtime. Drive the **entrypoint**, not the module: a unit test that imports the module directly bypasses the loader and greens against a wrong path.

## Grep Is Authoritative Over the Spec — General Form

**Grep is authoritative over the spec, full stop — not only for the mechanism's own asserted field contract (§ above).** Paths, framework names, helper APIs, constants, schema fields, frontmatter keys, and env vars all get the same treatment: confirm each by grep from the asserting test/contract before it propagates into a plan or executor brief. The narrower field-contract statement above is the sharpest recurring instance of this rule, not a boundary on it — any claim citing an on-disk identifier is a hypothesis until grepped, regardless of which of these seven categories it falls into.

## Grep the LITERAL Identifier From the Asserting Line, Not a Paraphrase

Substrate-grep must check the **exact literal** as it appears on the asserting line — not a paraphrase, not the human-readable concept name. A false claim that grepped against a paraphrase sailed through three pre-flights and one staff reviewer because every check matched the *idea* and none matched the *string*.

**Substrate citations require direct file read, not scout characterization.** "Scaffolding is present" is not the same as "specific hookspec X is declared." Also: command-spec / doc markdown can be test-pinned SSOT — grep the tests before trimming any spec-shaped prose, gate on the contract suite after; MOVE-VERBATIM and DO-NOT-HAND-EDIT blocks are untouchable. Propagating scout-level framing ("the registration scaffold exists") into specific-name claims without grepping the cited file is the recurring failure — all such names were absent from their cited files, caught only at review rather than at plan-write. Rule: every hookspec name, constant name, and file:line citation in a plan gets `grep`-verified against the cited file before the plan ships to review.

**Corollaries:**

- **Deleting a shared constant** requires grepping re-export and back-compat-shim sites, not just direct importers — a shim re-exports under the old name and the direct-importer grep comes back clean.
- **A doc named as the edit-target for a concept rename/removal** needs a whole-file concept-grep, not a first-section patch — the concept recurs in later sections the patch never reached.
- **Impact-radius scouts must enumerate WRITE-direction patterns**, not just READ. A scan that finds `import X` / `$X` / `os.environ["X"]` silently misses `export X=`, `env[X] = …`, subprocess env injection, config writes. A retire/rename that audits only the read side leaves a writer setting the wrong name — a value nobody reads, no error.

## Closed-Enum Values Live in 3+ Mirror Sites — Grep the VALUE SET, Not the Name

A closed enum (a `deployment_state`, a `language` tag, a schema version, an emit-value set) typically lives in **three or more** mirror sites that must stay in lockstep: the typed source (dataclass / `Enum` / `const`), the JSON schema or DDL, and a test mirror — plus any consumer-side enumeration that switches on the value.

**Recurring failures:**

- **Static-dict observability schemas lag producer-side enum additions** (second-recurrence). When a producer gains a new emit-value, the consumer's static enumeration doesn't know about it and drops or mis-buckets the value silently. Grep the consumer enumerations on **every** new emit-value.
- **Same-named constants in adjacent namespaces silently mis-resolve at import.** Two modules each define the same-named constant (e.g. a schema-version constant); an import resolves to the wrong one and the mismatch is invisible until a version check fails downstream.
- **A mass-rename plan body may contradict the project's authoritative glossary.** Cross-check any planned X→Y substitution against the glossary *before* dispatching rename executors.

**Rule:** when extending or renaming a closed enum, grep the **value set** (every literal member), not just the type name — and enumerate the mirror sites (source / schema / test / consumer-switch) explicitly in the plan. Confirming the type name resolves proves nothing about whether all three+ mirrors carry the new member.

### Extending a previously-binary assumption to a third value — grep EVERY site that branched on the old binary

When a value that was previously effectively binary gains a third state (a device flag that was yes/no becomes a three-way choice; a status that was ok/fail becomes ok/degraded/fail), the migration is complete only when EVERY site that branched on the old binary is updated — not just the producer. The dangerous misses are sibling *consumers* that still read the old boolean: a classifier reading an availability flag as a hard "wedge" verdict reports the degraded-but-fine third state as broken forever on every machine in that state.

**How to apply.** Grep every branch on the old binary predicate (`== false`, `if not X`, ternaries, and the negation forms) across producers AND consumers before declaring the ternary migration landed; each is a mirror site the way a closed-enum member is.

## Consumer Parsers Must Verify Producer's Actual Output Shape

When the plan adds a consumer (parser, importer, validator) for an existing producer's output, **grep the producer's emit-site to read the actual shape — do not infer the shape from the producer's spec or doc string.** Producer specs lag implementation; a spec that describes a JSON-blob output may correspond to a producer that emits NDJSON, or a wrapped envelope, or an empty `[]` on certain branches the spec didn't anticipate. Consumer code authored against the spec then fails on inputs the producer actually emits.

This is a strict extension of the no-fabrication-on-cited-fields rule above: the cited surface is the producer's *output shape* (top-level type, key names, optional-field nullability, error-branch shapes), and the canonical reference is the producer's code, not its docs. Grep the producer's serialization site (`return json.dumps(...)`, `yaml.safe_dump(...)`, the emit call) and read the actual structure before writing the consumer.

## A "Content-Agnostic / No-Extra-Work" Primitive Must Be Verified at the PRODUCER Surface, Not Just Read/Registration

When a plan or spinoff asserts a primitive is the "content-agnostic", "zero-code-change", or "no-chunker" fast path for a new case, verify that claim at the BUILD/producer surface — not only at the read/registration side that first suggested it. A capability can be genuinely generic on the read half (any pre-built artifact registers and is queryable) while the *build* half hard-rejects the new case: a primitive was asserted as the no-op fast path for a new content type, and the registration and read paths were truly generic, but the build tool hard-rejected every format except one — so onboarding the new case was impossible without exactly the host-side change the spinoff's "zero code change" claim promised to avoid.

**How to apply.** For any "no-extra-work / content-agnostic" claim, grep the producer/build entrypoint's accept-list (chunker allowlist, format switch, type guard) and confirm the new case is admitted there, not just at the consumer. The read/registration side passing is necessary, not sufficient.

## Cross-repo CLI delegation: verify the arg parser, not the plan's prose

**When delegating to a sibling repo's CLI, verify the actual input-injection mechanism (flag/env/stdin) against the producer's arg parser — prose "pass via --flag" is a guess until the parser confirms a flag of that shape exists.**

**Why:** A plan said a consumer would pass a resolved root path via a named flag to a sibling CLI. Reading the CLI's argparser showed it discovers roots autonomously and has no such flag; the named flag only pinned a version pointer. The real injection hook was an env var. Delegating just the wrong flag would have written a dangling pointer for non-canonical operator paths.

**How to apply:** before writing a cross-repo dispatch step, read the producer CLI's `argparse.add_argument` calls (or equivalent) and quote at least one matching `file:line` citation in the plan body. Flag names stated in prose are hypothesis until the parser source confirms them.

**A reviewed plan can cite a non-existent CLI flag, and an executor can leave a comment claiming a finding is done while not implementing it — verify tool interfaces and finding-completion against source/git, not the plan or executor narrative.** Full review chains do not catch tool-interface substrate-drift.  Rule: at execution, grep the literal tool interface; verify each load-bearing reviewer-finding by reading the code that claims to satisfy it.

## Index/Overview Docs Are Not Authoritative on a Target File's Internal Structure

**An overview or index document's enumeration of sub-parts is NOT authoritative on the target file's actual internal structure — grep the target's own headings at plan-time.**

When a plan asserts "edit file X, section Y", the authoritative source for X's sections is `grep -nE '^#+ ' X` (or the file's own headings), NOT a sibling overview/index/PIPELINE doc that enumerates the *concept* set. Overview docs describe the pipeline; they are not a manifest of any one file's internal headings. A concept set and a file's actual section set can diverge — the overview may list phases a file does not have sections for, and have no sections for phases the file does carry.

**How to apply:** before dispatching against a named section in a multi-file refactor keyed off an index doc, run `grep -nE '^#+ ' <target-file>` and confirm the section exists. Mismatch catches non-existent sections before an executor stubs against them mid-fan-out. Sharper instance of the "grep seams, don't invent them" rule — specifically for plans driven by index/pipeline overview documents.

## Cross-Repo Memo Attribution Is Hypothesis — Grep the Canonical Statement First

**A cross-repo memo attributing a doctrine to a specific source is a hypothesis, not ground truth — grep the canonical statement before planning to amend it.**

When a memo says "you established X in your repo," read the cited wiki/lesson/queue entry yourself before acting. The rule may be (a) already written and the memo is redundant, (b) unwritten and the memo is advocating for something new (in which case it needs authoring, not amendment), or (c) written but in a different form than the memo claims. A memo is the sender's interpretation; the canonical doctrine is what the receiving repo's artifacts actually say.

**How to apply:** for any cross-repo memo that attributes a doctrine to your repo, grep the key noun from the memo's claim against your own doctrine wiki and lessons file before planning a response. The grep result — present or absent — is the ground truth; the memo is framing.

## Verdict-Only Investigator Pass Before Fix-Dispatch on Multi-Cluster Borderline Severity

**On a multi-cluster borderline-severity inventory, dispatch ONE read-only verdict-only investigator pass BEFORE any fix-dispatch.** This reliably outperforms fanned-out per-cluster investigations and avoids the severity-paraphrase failure mode.

Why: per-cluster investigations in parallel each anchor on their own paraphrase of the evidence; the investigator arrives at a severity label without reading the actual code, then the EM acts on the label. A single read-only investigator pass reads code across all clusters before assigning verdicts, catches phantom high-severity items and suppressed lower ones, and produces a single coherent severity map the fix-wave can trust.

**When to apply:** any fix-dispatch where (a) two or more clusters each have ≥1 severity-borderline item, AND (b) the severity signals came from sweep agents rather than from direct code reads.

## Constant/Identity Bump Is a Multi-Writer Change

A constant rename or value bump (schema version, protocol version, magic number) is a multi-writer change even when the constant lives in a single source file. Vendored copies, in-tree mocks, and test fixtures that hard-code the old value must all be updated atomically with the producer, and the touched test surface must be RUN — not just grepped — before declaring the pin landed. A bump that greens CI but leaves a mock pinned to the old value breaks on clean installs or in test environments that don't vendor from the canonical source.

**How to apply:** at plan-write time, grep the constant's VALUE (not just its name) across the whole repo including `tests/`, `vendor/`, and any `*.json`/`*.yaml` fixture files. Write a grep gate in the plan asserting zero remaining old-value occurrences. The gate is the contract; prose "update all copies" is not.

## Plan-Write Must Verify Fixture Inventory Before Prescribing New Fixtures

Before a plan prescribes a new test fixture (`tests/_*_fixture.py`, `conftest.py`, shared helpers), the plan-author MUST `ls tests/_*_fixture.py` and grep the symptom symbol across existing fixtures. Canonical fixtures frequently ship before the plan that needs them — a plan that authors a duplicate fixture creates import confusion, diverging setups, and redundant maintenance surface. The existence check is cheap; the dedup is free at plan time and expensive after fan-out.

## Post-Heavy-Churn Bug-Sweeps Need a Verify-First Executor Contract

After a period of heavy commits on a shared surface, sweep agents anchor on historical code shapes that intervening commits have already fixed. The result: sweepers flag issues against lines that do not exist, then "fix" code by re-introducing the very shapes the churn removed. **Contract:** every bug-sweep executor dispatched post-heavy-churn must read the CURRENT line at the cited locus before taking any action. If the line already reflects the intended fix, the executor is a no-op for that item. Cite the read-back as evidence in the sweep report. (Complements § Verdict-Only Investigator Pass — that rule covers multi-cluster triage BEFORE fix-dispatch; this rule covers per-item verification DURING fix-dispatch.)

## `git log --name-only` Lists Adds AND Deletes — Verify Against HEAD Before Declaring Uncatalogued

`git log --name-only` (and `--diff-filter` without explicit `A` / `M`) includes deleted files in its output alongside additions. When using git log to enumerate "emergent" or "uncatalogued" files that need architecture-survey treatment, verify each candidate against `HEAD` state before declaring it uncatalogued — a file appearing in `git log --name-only` may have been deleted and absent at HEAD, making it spurious drift inventory. Run `git ls-files -- <path>` or `ls <path>` to confirm HEAD presence before actioning.

## Measure Blast Radius Before Framing the Fix Shape

Before offering a fix shape for any sweep/citation/rename task, grep the full corpus + classify before estimating. A confident "small, mechanical" estimate stated pre-measurement can collapse to "an order of magnitude larger, heterogeneous classes, mostly NOT uniformly convertible" on a real grep. Corpus-grep + class-classify BEFORE framing the fix shape to the PM; a fix-shape offered pre-measurement is a hypothesis wearing a recommendation's costume.

## A Cited Identifier From a Trusted Internal Source Is Still a Hypothesis — Disk-Verify Before Folding Into a Plan

Prior-art-checker conflicts, wiki citations, and peer-reviewer findings are framing — they may prescribe a fix for the wrong target, cite a script that doesn't exist for this repo, or reference an older shape. A cited claim folded unverified was wrong twice in one session: a prior-art-checker finding prescribed a fix for the wrong deployment mode of the target (mode matters); a wiki-cited script name pinned into an executor brief doesn't exist in this repo's install layout at all (phantom — a differently-named script does the registration). Both reached plan/brief and were caught only downstream.

**Rule.** Grep the literal identifier/mechanism against disk before it propagates into a plan or executor brief. This extends no-fabrication-on-cited-fields to internal-source citations — prior reviewers, wikis, and pre-flight checkers are framing, not ground truth.

## Re-verify negation premises at EACH pipeline stage — intra-session concurrent-EM drift

**Re-verify "X absent / broken / not yet landed" at every pipeline stage (plan-write, review dispatch, execute dispatch) — a concurrent EM can flip the premise between stages within a single session.**

A premise of the form "X is not yet present" or "this bug has not been fixed" is point-in-time. When the plan-write, review, and execute dispatch happen across a session that includes concurrent EM activity on the shared branch, a sibling executor may have landed the exact thing you're planning to build (or fixed the bug you're working around) between the plan-write and the execute dispatch. Acting on the stale premise means double-work at best and a conflicting landing at worst.

Apply: before each phase boundary (plan → review; review → execute), run `git fetch && git log origin/main..HEAD` and check whether the "absent/broken/not-landed" premise still holds. One-liner: `git log --oneline --since=<plan-write-timestamp> -- <cited-paths>`. If the premise has flipped, stop — re-plan from the updated state rather than proceeding into a stale phase.

## Re-verify Mechanism and Sibling-Repo Liveness at the Dispatch/Destructive Instant

Companion to § Re-verify negation premises at EACH pipeline stage: that rule covers a *premise* flipping across a session; these two cover a *mechanism* or a *sibling repo's state* that was true at plan-review or pickup but is stale by the time you reach the irreversible step. Plan-review approval and pickup-time investigation both freeze in time; the destructive step does not.

- **Re-confirm an install-topology mechanism on disk at the destructive step, not just at plan-review.** A plan reviewed *twice* proposed relocating a component's load mechanism to a different repo. Execution revealed the actual load mechanism was bespoke to the current install (config hooks + a root-pointer file; a marketplace-style source path was vestigial residue) — leaving the carrier in place was cleaner. A reviewed plan step that assumes an install-topology mechanism must re-confirm that mechanism exists on disk *in the shape assumed* before the irreversible move; review approval does not freeze the topology.

- **Re-check sibling-repo liveness immediately before dispatch, not just at pickup.** *[universal]* A read-only scout's map of a sibling repo goes stale within *minutes* when a live sibling session is actively committing the same work. A scout reported a set of files as "uncommitted / stranded"; two minutes later a live session had committed the equivalent chunk of that exact plan. The pre-dispatch commit-freshness / liveness recheck (`git log` timestamps + live-session tracking) caught what would have been a double-spend collision. Treat any commit within the last few minutes on the target files as a stand-down signal — investigation freshness decays against a live peer, so recheck at the dispatch *instant*, not the plan-write instant.

## Handoff Quantitative-Trend Claims Are True Numbers With a Guessed Cause — git-log Verify Before Designing a Fix

A handoff citing a numerical trend ("+2.4 errors/day for 13 days", "the count has doubled since Tuesday") can be *arithmetically correct* while its stated cause is wrong: a single re-platform / bulk-rename / dependency-bump commit can masquerade as organic day-over-day drift. Designing a fix against the assumed organic cause spends the session on the wrong mechanism.

**How to apply.** As the FIRST pickup-verification step, run `git log --since=<window> -- <cited-substrate>` against the paths the trend is measured over. If the commit count and shape don't match the trend's implied gradual accumulation — e.g. one large commit accounts for the whole delta — redo the framing before authoring the plan. The trend is a symptom; the git history is the cause oracle. "Broken today" claims need HEAD verification, not trust in a handoff's stated cause.

## Handoff/Stub-Cited Loci Diverge From Disk — Trace to the Production Writer, Correct in the Plan, Don't False-Block

A handoff or roadmap stub citing `file:line` fix-loci is hypothesis about where the work lives; disk is ground truth. Two divergence modes recur, with opposite failure shapes — one *over-trusts* the citation, one *over-rejects* it.

- **A strangler migration relocates the PRODUCTION writer the audit cited — trace fix-loci to their live writer before planning.** A spinoff handoff cited `file:line` loci in one repo for silent-overwrite fixes in several append/promote operations. At plan-write, disk showed a strangler migration had relocated the PRIMARY production writers into a sibling repo's engine layer — the originally-cited code was only the seam-absent legacy fallback. Naïvely "fixing" the cited legacy write ships a fix that never touches the production silent-loss path. The right move split scope: fix the legacy fallbacks defensively AND route the relocated loci via the proper cross-repo channel. Composes with § Enumerate EVERY Writer of a Path — a strangler migration is exactly the off-the-main-wave writer a single-locus mental model misses.

- **A wrong PATH with a right SUBSTRATE is a premise fix, not a blocker — repo-search before declaring absence.** A stub cited a skill-directory path that turned out nonexistent; the real surface was a differently-named command file. A single failed `ls` is NOT "substrate absent" — repo-search for the concept first, and carry the path correction into the plan as a premise fix rather than surfacing a false blocker to the PM. The citation was stale on path but the work was real; the plan-author's job is to correct it, not bounce it.

## Never Brief a Role for a Capability Its Definition Withholds

**Check the brief's asks against the target's `tools:` line and Tools Policy before dispatching. A brief requesting a withheld capability is malformed at authoring time — nothing refuses it, so the agent declines at runtime, already spawned and paid for.**

The role's own declaration does not prevent this: the pull to brief past it comes from the task genuinely needing the capability, and reads as stronger than the boundary.

**How to apply.** Name the role holding each capability the brief asks for. If the target withholds it, dispatch a second role that has it — not a louder brief, and never a widened tool grant on the role whose boundary is the point. Canonical instance: `reviewer-routed-workers.md` § Execution rides alongside the reviewer, never inside it.

**Corollary.** A runtime decline is evidence about the brief, not the agent. Static-only findings from a static-only reviewer are the expected shape; filing that as a capability gap in the *role* misfiles the defect.

## Related

## vendored-fork line refs are not upstream line refs

Vendored-fork line refs are not upstream line refs — grep HEAD by symbol before dispatching the executor. When a memo or plan cites `path/to/file.py:123`, that line number may belong to a vendored or forked copy whose line numbers diverged from upstream. Grep by symbol name (function, class, constant) against the repo's actual HEAD to find the real location before writing the executor brief.

## coverage-gate tests must be named in every executor brief that adds the gated artifact

Coverage-gate tests (ALLOW_LIST checks, registry-sync tests, count-parity tests) must be explicitly named in every executor brief that adds the gated artifact. If the brief doesn't name the coverage gate, the executor may satisfy its local done-criteria while leaving the coverage test red. Apply: before dispatching, grep for `ALLOW_LIST`, `registry_sync`, and count-constant tests; list any that gate the artifact being added in the `done-criteria` block of the brief.

## Bundle plans at high-concurrency moments get pre-empted — verify before dispatching

Bundle plans authored during high-concurrency moments (multiple concurrent EMs on the shared bus) can be organically pre-empted by concurrent landings before the bundle is dispatched. At execute-plan time, `git log` recent commits against the bundle's named items and remove already-completed items before dispatching. Apply: always run `git log --oneline -20` and check for any plans dated today before dispatching an execute-plan wave.

## fix-spec's "preferred mechanism" is hypothesis — verify on disk before coding

A fix-spec's "preferred mechanism" is a hypothesis about the fix shape — verify it against the actual on-disk code before coding. The real cause may reshape the fix significantly. When a synthetic fixture cannot reproduce the real trigger, extract the logic into a testable helper that accepts the real-world input. Apply: grep the cited fix locus and read 30 lines of context before treating the spec's fix shape as authoritative.

- `docs/wiki/tiered-context-loading.md` — what to read before dispatching.
- `docs/wiki/prior-art-checker.md` — automated pre-flight against accumulated prior art.
- `docs/wiki/docs-checker-pre-review.md` — automated pre-flight on external API claims.

## Enumerate before the sweep

Bug-class sweeps that enumerate a fixed list of sites close the surfaced member but miss the class. Class-catching AST / structural lints with explicit allowlists are the canonical shape — enumerated-site-list lint → class lint with allowlist. Two silent-fail classes ride together (heredoc-in-Python, BSD-vs-GNU sed). `.gitignore` naming-SHAPE drift gets a suffix-general glob + check-ignore regression test, not a per-pattern allowlist.

Pre-dispatch verification flags any sweep plan whose acceptance-criteria table references only enumerated sites without naming the class.

## Literal-identifier grep + CLI-flag + consume/delegate spec checks

Pre-dispatch verification on plans that name a CLI flag or a consumer/delegate API runs three additional greps:

1. **Literal-identifier grep** — confirm the symbol exists on disk under the claimed name. Large match sets truncate; use `grep -c` (count-mode) first.
2. **CLI-flag check** — confirm the flag is in `--help` output or the parser source. Plan-author memory of flag names ages poorly across renames.
3. **Consume/delegate spec verification** — when the plan says "X consumes Y" or "delegate to Z", grep both the producer and consumer to confirm the contract shape (output_consumption / contract-change is a verification gate, not an authoring gate; the plan must name the file the consumer reads).

## Enumeration Greps Locate-Then-Read, Not `-rn`-Dump

When a grep is enumerating (counting instances, confirming presence/absence, scoping a sweep), use `-l`/`-c` to locate the matching files, then `Read` each one — don't `-rn`-dump the whole match set. An `-rn` dump over an enumeration is both noisy (buries the signal the enumeration was after) and truncation-prone (large match counts overflow the shell's captured output and silently under-report). Locate first, read the file for the actual content once you know which file matters.

## Single-Mode Only — Never Mix `-r`/`--include` With Explicit File Paths in One Grep Call

Mixing a recursive/`--include` mode with explicit file-path arguments in the same grep invocation exits 2 and emits **partial matches that read as complete** — the call doesn't fail loud, it fails quiet: the truncated result looks like a clean, exhaustive match set. This is a silent under-report with the same hazard profile as unpaginated truncation, and it's easy to trigger by accident when refining a grep mid-investigation (adding one explicit path to an already-recursive call). Run one mode or the other, never both in a single invocation.

## Duplicate-Detection Requires Body Comparison, Not Metadata

Deciding two files (or two records) are duplicates on filename, size, or frontmatter alone is unsound — matching metadata is consistent with genuinely different content, and non-matching metadata is consistent with a near-identical body under a renamed field. Confirm duplication by comparing bodies before merging, deleting, or treating one as canonical over the other.
