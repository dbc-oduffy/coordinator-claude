# Pre-Dispatch Verification

**System:** coordinator
**Provenance:** consolidated 2026-05-14 from `tasks/coordinator-improvement-queue.md` triage (E40, E51, E87, E88, E150, E156).

Plans drafted against unchecked substrate become dispatches that find a different reality on disk. Verify at plan-write time, not after the executor reports back. Companion to `coordinator/CLAUDE.md` § Pre-Dispatch Verification — this wiki carries the longer-form rules and refinements.

---

## Premise-Pass Discipline

- **Premise-pass extends to mechanical premises, not just architectural ones.** JSON field names, env-var presence, registry keys, frontmatter fields all count as premises. A plan citing `install-status.json.deployment_state` MUST grep the schema to confirm the field exists before the executor depends on it.

- **Plan-stub-vs-landed-disk drift is structural — research before re-author.** When a roadmap stub cites cross-repo deliverables ("PR-N landed in peer repo X"), the plan-author MUST cross-repo grep the landed code before re-authoring. Stub-vs-landed drift is a structural staleness mode — the stub is hypothesis, the landed code is ground truth.

- **Re-extraction as crash recovery is process theater when versioned artifacts already exist.** Across multi-repo splits (host + addon + plugin), a crash mid-extraction tempts the recovery EM to re-run the producer pipeline. Before doing so, survey peer-repo artifacts for the versioned output the producer would have written — if `peer-repo/dist/<artifact>-vN.json` exists with a matching schema/version, the producer succeeded and the crash was downstream. Re-running the producer wastes a session and risks overwriting good output with a fresh run that diverges from what consumers already pinned. Companion rule in CLAUDE.md § Verifying Executor Output. (2026-05-15, project-rag-ue-addon.)

- **A contract reversal must reconcile code + tripwire + doctrine-doc in ONE change, or the stale doc is a re-introduction vector.** When a plan flips a runtime contract (a bake→runtime invariant, an enum's allowed set, a producer's emit shape), enumerate every surface that *encodes* the old contract — the code, any static-grep tripwire that asserts it, AND the doctrine/wiki/CLAUDE.md prose that documents it — and amend all three atomically. A reversal that updates the code but leaves the doc asserting the old contract leaves a live re-introduction vector: the next planner reads the stale doc as ground truth and re-codifies the reversed-away shape. Grep the contract's central noun across `docs/wiki/`, `tasks/lessons.md`, and tripwire scripts before declaring the reversal landed. Source: 2026-05-30 project-rag.

- **A "consume/delegate a shared primitive and retire the duplicate" spec can be premised on a duplication that doesn't exist in the shape described — verify the SHAPE of the code you're retiring, not just that the target files exist.** 2026-05-27 host-resilience Q2: the spinoff said `capacity_budget.py` held a "duplicate inline inequality" to delete by delegating to the host primitive. On disk: `capacity_budget.py` was pure constants/floor-division accessors (no inequality to retire); the product invariant was enforced implicitly by floor-division; the plausibility clamps used fleet-specific thresholds the host's generic floor would have *loosened* — violating the spec's own "behaviour IDENTICAL" requirement. Rule: when a consume/delegate spec promises to retire duplication, read the target locus and confirm the duplicate is the shape claimed; the right consumption is often an *additive* verification guard over a primitive that single-sources the *definition*, not a deletion. Source: 2026-05-27 project-rag-ue-addon.

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

## Enumerate EVERY Writer of a Path Before Codifying Its Role

A filter, predicate, or invariant applied at *one* writer of a shared store silently re-leaks through the others. Before codifying any rule about what a table/path/collection contains, grep for **every** writer — not just the producer the bug surfaced through.

**Concrete failure (`graph.db.classes`, 2026-05-26 project-rag):** a Python/TS language-isolation filter was applied to the main `extract_cpp` INSERT and the `_legacy_sqlite_path` mirror, but a sibling writer `ingest_native_classes` (reached via `extract_cross_layer_edges`, a different call path) kept stamping `.py` rows as `language='cpp'`. The classes table has ≥4 independent writers; the fix covered two. Code-review caught the reintroduced leak.

**Rule:** before codifying a predicate on any shared store, `grep -rn "INTO <table>"` (or the write-API equivalent) across every producer/consumer/mirror module and fix **every** writer. This is the concrete instance of `coordinator/CLAUDE.md` § Codebase Investigation "grep every writer of a path before codifying its role." Off-the-main-wave writers (cross-layer passes, legacy mirrors, background ingest) are the ones a single-producer mental model misses.

## Enumerate the Full Caller Graph BEFORE Agreeing a Delete-Sweep Scope with a Peer EM

*2026-05-18 (claude-unreal-holodeck) + 2026-05-18 (project-rag-ue-addon) — same rule, two repos.* When negotiating a delete-sweep scope with a peer EM (cross-repo cleanup, shared-surface removal), grep the full caller graph of every candidate **before** the scope is agreed, not after. An agreed-on "6-file scope" expanded to 22 files once the callers were actually enumerated — the agreement was struck against an un-grepped mental model, and the gap surfaced mid-execution as scope creep that had to be re-negotiated.

**Rule:** the caller-graph enumeration is a *pre-agreement* artifact. Grep every caller / referencer / dynamic-loader site of each delete candidate, write the real footprint, and bring *that* to the scope agreement. A scope agreed on intuition is a scope that re-opens at the first un-grepped caller. This composes with § Reference-Sweeps Must Enumerate ALL Context Shapes (below) — the same shape inventory that catches rename misses catches delete-sweep caller misses; run it before the handshake, not after.

## Reference-Sweeps Must Enumerate ALL Context Shapes and Runtime-Invocation Surfaces

A single-pattern grep catches **<80%** of a rename's references — recurring across at least three audits. The misses are the high-severity ones because they fail at *runtime in production*, not in CI.

**Two enumeration axes, both required before the first sweep wave:**

1. **Context shapes.** The same identifier hides across: `from`-imports · slash-strings · dot-strings · `pathlib` components · `os.path.join` / PowerShell `Join-Path` args · dynamic-loader call sites (`spec_from_file_location`, `import_module`, `__import__`, `exec(open())`, `require()`) · `@patch`/`monkeypatch.setattr` string targets · f-strings · word-boundary cases where the *new* namespace contains the *old* as a substring (naïve grep then false-positives on every new-namespace citation — anchor with `\b`). Enumerate the shape inventory and run a grep *per shape* before chunking; a single regex on the literal misses most of these.

2. **Runtime-invocation surfaces.** Substrate enumeration scoped to "where the code/tests/docs live" (`src/`, `tests/`, `docs/`) silently omits the dirs that *invoke* helpers by path: `commands/`, `plugin/`, `.claude/`, skill dirs, config. Grep the **whole repo** for the literal before scoping chunks.

**Concrete failures:** (a) a helper-rename plan verified `project_rag_scripts/`, `tests/`, `docs/` clean but missed `plugin/commands/lib/doctor-1.5.1`, which invokes the helper by absolute path — grep gates passed, a doctor step would have broken at runtime, only a test caught it (2026-05-26). (b) A Python package rename has four import surfaces (from-imports + `os.path.join` string args + PowerShell `Join-Path` components + patch/monkeypatch string targets); a single-pattern audit captured <80%.

**Rule:** at plan-write time, write the shape inventory *and* the surface inventory into the plan body, grep each independently, and pair every static-grep tripwire with a runtime guard (a PreToolUse hook or an entrypoint test) — source-grep alone cannot see what agent-prompt instructions or command files write/invoke at runtime. Drive the **entrypoint**, not the module: a unit test that imports the module directly bypasses the loader and greens against a wrong path. Composes with `cleanup-sweep-hazards.md` §13/§21/§25.

## Grep the LITERAL Identifier From the Asserting Line, Not a Paraphrase

Substrate-grep must check the **exact literal** as it appears on the asserting line — not a paraphrase, not the human-readable concept name. A false claim that grepped against a paraphrase sailed through three pre-flights and one staff reviewer (2026-05-19) because every check matched the *idea* and none matched the *string*.

**Substrate citations require direct file read, not scout characterization.** "Scaffolding is present" is not the same as "specific hookspec X is declared." Propagating scout-level framing ("the registration scaffold exists") into specific-name claims (`project_rag_register_schema`, `CorpusProvider`, `SCHEMA_VERSION`) without grepping the cited file is the recurring failure: all three of those names were absent from their cited files, caught by Patrik at review rather than at plan-write. Rule: every hookspec name, constant name, and file:line citation in a plan gets `grep`-verified against the cited file before the plan ships to review. Source: 2026-05-27 project-rag-ue-addon.

**Corollaries:**

- **Deleting a shared constant** requires grepping re-export and back-compat-shim sites, not just direct importers — a shim re-exports under the old name and the direct-importer grep comes back clean.
- **A doc named as the edit-target for a concept rename/removal** needs a whole-file concept-grep, not a first-section patch — the concept recurs in later sections the patch never reached.
- **Impact-radius scouts must enumerate WRITE-direction patterns**, not just READ. A scan that finds `import X` / `$X` / `os.environ["X"]` silently misses `export X=`, `env[X] = …`, subprocess env injection, config writes. A retire/rename that audits only the read side leaves a writer setting the wrong name — a value nobody reads, no error. (Mirrored in `cleanup-sweep-hazards.md` §26.)

## Closed-Enum Values Live in 3+ Mirror Sites — Grep the VALUE SET, Not the Name

A closed enum (a `deployment_state`, a `language` tag, a schema version, an emit-value set) typically lives in **three or more** mirror sites that must stay in lockstep: the typed source (dataclass / `Enum` / `const`), the JSON schema or DDL, and a test mirror — plus any consumer-side enumeration that switches on the value.

**Recurring failures:**

- **Static-dict observability schemas lag producer-side enum additions** (second-recurrence). When a producer gains a new emit-value, the consumer's static enumeration doesn't know about it and drops or mis-buckets the value silently. Grep the consumer enumerations on **every** new emit-value.
- **Same-named constants in adjacent namespaces silently mis-resolve at import** (the `SCHEMA_VERSION` case). Two modules each define `SCHEMA_VERSION`; an import resolves to the wrong one and the mismatch is invisible until a version check fails downstream.
- **A mass-rename plan body may contradict the project's authoritative glossary** (`CLAUDE.md` Version Glossary). Cross-check the X→Y substitution against the glossary *before* dispatching rename executors.

**Rule:** when extending or renaming a closed enum, grep the **value set** (every literal member), not just the type name — and enumerate the mirror sites (source / schema / test / consumer-switch) explicitly in the plan. Confirming the type name resolves proves nothing about whether all three+ mirrors carry the new member. → also `cleanup-sweep-hazards.md` §17 (inventory all path-typed columns) for the same multi-mirror discipline on schemas.

## Consumer Parsers Must Verify Producer's Actual Output Shape

When the plan adds a consumer (parser, importer, validator) for an existing producer's output, **grep the producer's emit-site to read the actual shape — do not infer the shape from the producer's spec or doc string.** Producer specs lag implementation; a spec that describes a JSON-blob output may correspond to a producer that emits NDJSON, or a wrapped envelope, or an empty `[]` on certain branches the spec didn't anticipate. Consumer code authored against the spec then fails on inputs the producer actually emits.

This is a strict extension of the no-fabrication-on-cited-fields rule above: the cited surface is the producer's *output shape* (top-level type, key names, optional-field nullability, error-branch shapes), and the canonical reference is the producer's code, not its docs. Grep the producer's serialization site (`return json.dumps(...)`, `yaml.safe_dump(...)`, the emit call) and read the actual structure before writing the consumer.

## Cross-repo CLI delegation: verify the arg parser, not the plan's prose

**When delegating to a sibling repo's CLI, verify the actual input-injection mechanism (flag/env/stdin) against the producer's arg parser — prose "pass via --flag" is a guess until the parser confirms a flag of that shape exists.**
**Why:** A plan said the consumer would "pass the resolved engine root using the dotted `--ue-version`" to a seeder CLI. Reading the seeder's argparser showed it discovers roots autonomously and has NO `--engine-root` flag; `--ue-version` only pins a pointer. The real injection hook was an env var. Delegating just `--ue-version` would have written a dangling pointer for non-canonical operator paths.
**How to apply:** before writing a cross-repo dispatch step, read the producer CLI's `argparse.add_argument` calls (or equivalent) and quote at least one matching `file:line` citation in the plan body. Flag names stated in prose are hypothesis until the parser source confirms them.

*Source: holodeck `tasks/lessons.md` (holodeck-L219, central-promoted 2026-05-28).*

**A reviewed plan can cite a non-existent CLI flag, and an executor can leave a comment claiming a finding is done while not implementing it — verify tool interfaces and finding-completion against source/git, not the plan or executor narrative.** Full review chains do not catch tool-interface substrate-drift. 2026-05-27 samples-extraction: a Sid-F6 note cited `synthesize_engine_compile_commands.py --project-root` (no such flag; real tool is `synthesize_project_compile_commands.py`), and the first executor wired samples to the shared engine cc while leaving a comment asserting "per-sample cc synthesized in the loop below" — false. Both caught only by reading the script's argparse and the actual orchestrator block. Rule: at execution, grep the literal tool interface; verify each load-bearing reviewer-finding by reading the code that claims to satisfy it. Source: 2026-05-27 project-rag-ue-addon.

## Index/Overview Docs Are Not Authoritative on a Target File's Internal Structure

**An overview or index document's enumeration of sub-parts is NOT authoritative on the target file's actual internal structure — grep the target's own headings at plan-time.**

When a plan asserts "edit file X, section Y", the authoritative source for X's sections is `grep -nE '^#+ ' X` (or the file's own headings), NOT a sibling overview/index/PIPELINE doc that enumerates the *concept* set. Overview docs describe the pipeline; they are not a manifest of any one file's internal headings. A concept set and a file's actual section set can diverge — the PIPELINE overview may list phases a file does not have sections for, and have no sections for phases the file does carry.

**How to apply:** before dispatching against a named section in a multi-file refactor keyed off an index doc, run `grep -nE '^#+ ' <target-file>` and confirm the section exists. Mismatch catches non-existent sections before an executor stubs against them mid-fan-out. Sharper instance of the "grep seams, don't invent them" rule — specifically for plans driven by index/pipeline overview documents.

*Source: 2026-05-28 distill-manifests fan-out; plan modelled sections from PIPELINE.md phase-overview table; actual `agent-prompts.md` had a different section set.*

## Cross-Repo Memo Attribution Is Hypothesis — Grep the Canonical Statement First

**A cross-repo memo attributing a doctrine to a specific source is a hypothesis, not ground truth — grep the canonical statement before planning to amend it.**

When a memo says "you established X in your repo," read the cited wiki/lesson/queue entry yourself before acting. The rule may be (a) already written and the memo is redundant, (b) unwritten and the memo is advocating for something new (in which case it needs authoring, not amendment), or (c) written but in a different form than the memo claims. A memo is the sender's interpretation; the canonical doctrine is what the receiving repo's artifacts actually say.

**How to apply:** for any cross-repo memo that attributes a doctrine to your repo, run `grep -rn "<key noun from memo claim>" docs/wiki/ tasks/lessons.md` before planning a response. The grep result — present or absent — is the ground truth; the memo is framing.

*Source: 2026-05-27 self (central tasks/lessons.md:571).*

## Verdict-Only Investigator Pass Before Fix-Dispatch on Multi-Cluster Borderline Severity

**On a multi-cluster borderline-severity inventory, dispatch ONE read-only verdict-only investigator pass BEFORE any fix-dispatch.** This reliably outperforms fanned-out per-cluster investigations and avoids the P0/P1-paraphrase failure mode.

Why: per-cluster investigations in parallel each anchor on their own paraphrase of the evidence; the investigator arrives at a severity label without reading the actual code, then the EM acts on the label. A single read-only investigator pass reads code across all clusters before assigning verdicts, catches phantom P0s and suppressed P1s, and produces a single coherent severity map the fix-wave can trust. Known as the "wave-3d-triage shape."

**When to apply:** any fix-dispatch where (a) two or more clusters each have ≥1 severity-borderline item, AND (b) the P0/P1 signals came from sweep agents rather than from direct code reads.

*Source: 2026-05-28 project-rag (tasks/lessons.md:15); companion to `coordinator/CLAUDE.md` § P0/P1 Verification Gate.*

## Constant/Identity Bump Is a Multi-Writer Change

A constant rename or value bump (schema version, protocol version, magic number) is a multi-writer change even when the constant lives in a single source file. Vendored copies, in-tree mocks, and test fixtures that hard-code the old value must all be updated atomically with the producer, and the touched test surface must be RUN — not just grepped — before declaring the pin landed. A bump that greens CI but leaves a mock pinned to the old value breaks on clean installs or in test environments that don't vendor from the canonical source.

**How to apply:** at plan-write time, grep the constant's VALUE (not just its name) across the whole repo including `tests/`, `vendor/`, and any `*.json`/`*.yaml` fixture files. Write a grep gate in the plan asserting zero remaining old-value occurrences. The gate is the contract; prose "update all copies" is not.

*Source: project-rag `tasks/lessons.md` (central-promoted 2026-05-29).*

## Plan-Write Must Verify Fixture Inventory Before Prescribing New Fixtures

Before a plan prescribes a new test fixture (`tests/_*_fixture.py`, `conftest.py`, shared helpers), the plan-author MUST `ls tests/_*_fixture.py` and grep the symptom symbol across existing fixtures. Canonical fixtures frequently ship before the plan that needs them — a plan that authors a duplicate fixture creates import confusion, diverging setups, and redundant maintenance surface. The existence check is cheap; the dedup is free at plan time and expensive after fan-out.

*Source: project-rag `tasks/lessons.md` (central-promoted 2026-05-29).*

## Post-Heavy-Churn Bug-Sweeps Need a Verify-First Executor Contract

After a period of heavy commits on a shared surface, Sonnet sweep agents anchor on historical code shapes that intervening commits have already fixed. The result: sweepers flag P0/P1 issues against lines that no longer exist, then "fix" code by re-introducing the very shapes the churn removed. **Contract:** every bug-sweep executor dispatched post-heavy-churn must read the CURRENT line at the cited locus before taking any action. If the line already reflects the intended fix, the executor is a no-op for that item. Cite the read-back as evidence in the sweep report. (Complements § Verdict-Only Investigator Pass — that rule covers multi-cluster triage BEFORE fix-dispatch; this rule covers per-item verification DURING fix-dispatch.)

*Source: project-rag `tasks/lessons.md` (central-promoted 2026-05-29).*

## `git log --name-only` Lists Adds AND Deletes — Verify Against HEAD Before Declaring Uncatalogued

`git log --name-only` (and `--diff-filter` without explicit `A` / `M`) includes deleted files in its output alongside additions. When using git log to enumerate "emergent" or "uncatalogued" files that need architecture-survey treatment, verify each candidate against `HEAD` state before declaring it uncatalogued — a file appearing in `git log --name-only` may have been deleted and no longer exist at HEAD, making it spurious drift inventory. Run `git ls-files -- <path>` or `ls <path>` to confirm HEAD presence before actioning.

*Source: holodeck `tasks/lessons.md` (central-promoted 2026-05-29).*

## Related

- `coordinator/CLAUDE.md` § Pre-Dispatch Verification — the canonical bullet list.
- `docs/wiki/tiered-context-loading.md` — what to read before dispatching.
- `docs/wiki/prior-art-checker.md` — automated pre-flight against accumulated prior art.
- `docs/wiki/docs-checker-pre-review.md` — automated pre-flight on external API claims.
