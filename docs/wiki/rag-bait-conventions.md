# RAG-Bait Conventions

> How to write code so the project-RAG index retrieves it well. Required patterns, vocabulary
> discipline, authorial latitude, and the trim+provenance contract for /distill.

---

## The Carveout — What This Rule Is Not

The global "no inline what-comments" rule targets line-level comments that explain what the
code does: `# increment counter`, `# call the helper`, `# this handles the edge case`. Those
comments shadow well-named identifiers without adding meaning and rot the moment the code
changes.

This guide operates at a different granularity: **purpose prose at structural boundaries** —
module tops, class docstrings, function headers. The rule is not a relaxation of the
no-comments norm; it is peer-level. Inline what-comments remain forbidden. Purpose prose at
boundaries is **required**.

The distinction: inline comments describe behaviour at a line or block level. RAG-bait prose
describes *purpose* at a chunk-boundary level, in domain vocabulary, oriented toward a reader
(or retriever) asking "what is this thing for?" rather than "what does this line do?".

---

## Four Required Patterns

### 1. Module / Class Purpose Docstring

**Where:** Top of every module file and every non-trivial class.

**What:** 1-3 sentences. Domain vocabulary. Should reference CONTEXT.md terms where applicable.
The goal is to orient the *containing chunk* for subsystem-level recall — when a retriever
processes this module, the docstring is the highest-weight signal about what the module does.

**Python example:**
```python
"""
Enricher dispatch hub for the coordinator pipeline.

Receives a stub document path, loads the active enricher agent definition, and
dispatches it with the plan context. Returns the enriched stub path for downstream
executor dispatch. Part of the enrich-and-review skill flow.
"""
```

**TypeScript example:**
```typescript
/**
 * Session-scoped task tracker for the coordinator flight recorder.
 *
 * Manages discrete steps, key decisions, and tried-and-abandoned metadata so
 * a post-compaction agent can reconstruct session state from disk alone.
 */
```

**Anti-example — do not write:**
```python
# This module handles enrichment.
# It was added as part of the coordinator refactor.
```
Why bad: "This module handles enrichment" is a what-comment at module scope. "Added as part
of the coordinator refactor" is task context that belongs in the PR description and will
mislead future readers.

---

### 2. Function / Method Purpose Line

**Where:** Every non-trivial public function and method. Trivial = pure pass-throughs,
getters/setters, dunder methods with no branching logic.

**What:** One sentence. Domain vocabulary. Explain what this function *is for*, not how it
works internally.

**Why this pattern has the highest retrieval-recall leverage (per Camelia F1):** Chunkers
split on function boundaries. Without a purpose line, the chunk that represents a function
embeds primarily on syntactic signal — variable names, control-flow keywords — and ranks
poorly against natural-language queries like "how does the enricher pick its agent?".
With a purpose line, the chunk embeds on purpose-shaped semantic signal and rises on the
right queries.

**Python example:**
```python
def select_enricher_agent(stub_path: Path, project_type: list[str]) -> Path:
    """Select the enricher agent definition matching this stub's project type."""
    ...
```

**TypeScript example:**
```typescript
/** Append a new step to the flight recorder, preserving existing entries. */
function appendFlightRecorderStep(goal: string, detail: string): void {
    ...
}
```

**Anti-example — do not write:**
```python
def select_enricher_agent(stub_path: Path, project_type: list[str]) -> Path:
    # Opens the stub, reads front matter, matches against loaded agent defs.
    ...
```
Why bad: Behaviour-level summary, not purpose. Will diverge from the implementation silently.

---

### 3. Spec Backlink

**Where:** One line near the top of the function, class, or module that implements a specific
spec requirement — particularly anything non-obvious or the result of a decision.

**Format:**
```python
# Implements archive/specs/2026-04-29-foo.md §3.2 — decompose_query semantics
```

**Why this survives refactors:** The comment is purpose-shaped ("implements X"), not
behaviour-shaped ("calls Y then Z"). When the implementation changes, the spec reference
remains accurate unless the *purpose* of the code changes. Points at `archive/specs/` after
/distill runs (not `docs/plans/`) — /distill rewrites these during the link-heal pass.

**Python example:**
```python
def decompose_query(query: str) -> list[SubQuery]:
    # Implements archive/specs/2026-04-29-project-rag-readiness.md §3.2 — decompose_query semantics
    ...
```

**Anti-example — do not write:**
```python
def decompose_query(query: str) -> list[SubQuery]:
    # See the planning doc for context
    ...
```
Why bad: Non-retrievable. "The planning doc" could mean anything; after /distill moves the
plan to `archive/specs/`, the pointer is broken.

---

### 4. Negative-Spec Block

**Where:** At any hard-won correction site — a place where the natural implementation
instinct is wrong, a prior version was wrong, or the correct approach is non-obvious.

**What:** A `DO NOT` comment explaining what NOT to do and why. Surfaces the don't-do-this
signal that embedding models otherwise have to infer from absence.

**Why:** Future executors will read this code and may reach for the same wrong solution.
The negative-spec block stops them in place. It also indexes well on queries about the
problem — "asyncio.run" or "FastMCP await" will surface this chunk when someone hits the
same issue.

**Python example (from PORT-PATTERNS):**
```python
# DO NOT call asyncio.run() here — FastMCP awaits the handler naturally.
# Wrapping in asyncio.run() creates a nested event-loop error at runtime.
# The outer server loop already provides the event context.
async def handle_request(req: Request) -> Response:
    ...
```

**TypeScript example:**
```typescript
// DO NOT use Promise.all() for sequential enricher dispatch — enrichers
// share file-system state and must run in order. Race conditions corrupt the stub.
async function dispatchEnrichers(stubs: StubPath[]): Promise<void> {
    ...
}
```

**Anti-example — do not write:**
```python
# Note: use await here
async def handle_request(req: Request) -> Response:
    ...
```
Why bad: Positive instruction without the failure mode. A future executor who doesn't know
the failure context may not treat this as a hard constraint.

---

## Vocabulary Discipline — CONTEXT.md

If a project has a `CONTEXT.md` file (domain glossary in canonical vocabulary), identifiers,
docstrings, and comments MUST use the canonical terms. Terms in the `_Avoid_:` list must
not appear.

**Discipline is most load-bearing for project-coined and domain-specific terms** — `distill`,
`enricher`, `holodeck`, `RAG-bait`, `coordinator`, `spec backlink`. These are low-frequency
tokens where the embedding model has no prior; synonym fragmentation breaks retrieval.

**Latitude is fine for general engineering vocabulary** — `function`, `module`, `test`,
`class`, `interface`. These are high-frequency in open-domain corpora; the embedding model
handles synonyms well.

**Why this matters technically:**

- **BM25 (lexical retrieval):** exact-token matching. A query for "enricher" returns zero
  results for chunks that say "enrichment worker" or "agent runner". Synonym fragmentation
  directly destroys BM25 recall.
- **Embeddings (semantic retrieval):** more robust to synonyms *in open-domain corpora*.
  However, project-coined terms are low-frequency or absent from training data. The embedding
  model has no prior for "distill" meaning "extract wiki + archive spec + heal links"; it
  clusters these tokens on surface similarity. If some modules say "distill" and others say
  "summarize" or "compress", the clusters fragment relative to corpus size. Small repos feel
  this acutely — there isn't enough corpus mass to pull divergent synonyms into coherent
  clusters.

The `_Avoid_:` list in `CONTEXT.md` should target project-coined terms specifically. Don't
build a synonym-avoidance list for `function` — that's noise. Do build one for `enricher`
(avoid: "enrichment agent", "stub processor", "agent runner").

---

## Executor Authorial Latitude

The spec describes goal, constraints, and acceptance criteria. **The spec does NOT prescribe
exact comment text.** The executor writes RAG-bait prose as it implements, choosing wording
that fits the code in front of it.

The convention specifies *where* (module top, function header, hard-won correction site) and
*what kind* (purpose docstring, purpose line, spec backlink, negative-spec block). **The
executor owns *what to say*.**

Net effects:
- Specs get lighter — no need to draft comment prose in the stub.
- Comments co-evolve with the code they describe: when code is touched, its purpose comment
  is touched in the same commit. This is the primary mechanism for reduced comment rot at
  structural boundaries.
- Executors can exercise judgment on phrasing without doubt-spirals ("did I say this right?")
  — authorial intent is theirs.

**Critical constraint:** Authorial latitude on *phrasing* does NOT extend to *vocabulary*.
Canonical `CONTEXT.md` terms are required; project-coined synonyms are forbidden. The
latitude is in *how you compose the sentence*, not *which words name the domain objects*.

Without this binding, executor prose freedom would fragment embedding clusters even when
comment structure is correct. Reduced rot only beats inconsistency-cost if vocabulary stays
disciplined across all executor sessions. The `_Avoid_:` list in `CONTEXT.md` is the
hard constraint; everything else is the executor's to write.

**Vocabulary discipline measurability:** During /distill manual-review, the log should flag
≥1 vocabulary-drift hit on a CONTEXT.md-bearing repo, or attest zero drift after sampling
N≥3 modules. This converts the convention from aspirational to validated — see W4 for the
/distill rubric that embeds this check.

---

## Trim + Provenance Contract for /distill

When /distill runs on a repo, RAG-bait and the distillation log interact as follows:

**Spec backlinks** point at `archive/specs/` paths (not `docs/plans/`). During the
link-heal pass (W4 sub-step d), /distill rewrites spec backlinks in source code from the
original `docs/plans/` path to the archived `archive/specs/` path. This keeps backlinks
accurate after the plan moves to the archive.

**Provenance frontmatter** on wiki entries carries `last_verbose_sha` — the git SHA of the
original verbose plan/spec before trimming. When a future EM needs the review history or
integrator thread from that spec, the retrieval recipe is:
1. Read the trimmed `archive/specs/` version (on disk, indexed by RAG).
2. For the verbose original: `git show <last_verbose_sha>:<original path>`.

**Distillation log** (`tasks/distillation-log.md`, append-only) carries domain prose in
`reason` fields. Because the log lives on disk, RAG indexes it. A log row reading "integrator
triage resolving async-run wrapper conflict in port-patterns FastMCP transport" surfaces on a
query about that conflict and surfaces the `last_sha` needed to retrieve the verbose original.
This makes the log a retrieval bridge across the /distill boundary — cheapest mitigation for
"git history is out-of-band for RAG".

Example provenance frontmatter on a wiki entry:
```yaml
provenance:
  - archived_spec: archive/specs/2026-04-29-port-patterns-implementation.md
    original_path: docs/plans/2026-04-29-port-patterns-implementation.md
    last_verbose_sha: acc49ed5
    distilled: 2026-04-29
```

---

## Anti-Patterns

| Anti-pattern | Why it fails |
|---|---|
| Inline what-comments (`# increment x`) | Describe behaviour, not purpose. Rot on refactor. Forbidden per global rule. |
| Behaviour-level docstrings | "Calls validate(), then store(), then return." — lies after the implementation changes. |
| Auto-generated boilerplate | "This class was auto-generated. Do not modify." — zero retrieval signal. |
| Copy-pasted purpose blocks | Module A and Module B share a name pattern; executor copies A's docstring to B. Different roles, same prose — wrong signal for both chunks. |
| Vocabulary drift | "enrichment worker" instead of "enricher", "compress" instead of "distill". Fragments BM25 recall on project-coined terms. |
| Task-context comments | "Added for the port-patterns flow", "handles issue #123" — belongs in PR description; misleads future readers. |
| Missing function purpose lines on non-trivial functions | Function chunks embed on syntactic signal only; rank poorly against natural-language queries. |
