# RAG-Bait Conventions

Sets what a source file's own comments should say about itself versus what belongs in the commit and the plan.

> What a source file says about itself, and what it leaves to the commit and the plan. Short
> purpose prose where retrieval needs it; nothing that re-argues the code's existence.

---

## The Rule

Source carries **what the code is for** and **what would break if you changed it wrongly**.
It does not carry **why it was written, how it got here, or which plan asked for it** — every
commit traces to a plan, a review sidecar, or a decision record, and that trail is the durable
home for rationale. A comment that duplicates it rots the moment the code moves and buries the
code under its own justification.

This is the long form of the global "Comments: purpose, invariants, traps" rule. Never narrate
what a line does.

---

## What Belongs in Source

### 1. Module Purpose Docstring

**Where:** top of every module. **What:** 1–3 sentences in domain vocabulary saying what the
module is for. `test_module_docstring_convention.py` holds the floor for hook and template Python.

```python
"""Enricher dispatch hub: loads the matching enricher agent for a stub and dispatches it."""
```

Not: a history of the module, the commits that shaped it, dated measurements, or a table of
contents for the file below.

#### 1a. Owner-File Invariant

A module that **owns** a system-level guarantee ("at most one resident embed model per host",
"two concurrent indexing runs cannot corrupt the database") states that invariant in its
docstring, in the vocabulary a person asking about the guarantee would use — not the file's
surface vocabulary (routes, class names). This is the one place a docstring runs longer than
three sentences, and it earns it: a single invariant paragraph moved a canonical chunk from
rank 874 to rank 2 on the intent query. State the invariant and its mechanism; leave out how it
was discovered.

**Owner test:** if someone asked how the system guarantees X, is this the file you'd open?
Helpers, tests, and configs inherit the invariant; they don't restate it.

#### 1b. Parity Pairs

Cross-platform siblings implementing the same invariant (`install.{ps1,sh}`) carry equivalent
§1a paragraphs, updated in the same commit. Tuning one alone produced asymmetric retrieval
across platforms.

### 2. Function Purpose Line — Only When the Name Doesn't Say It

A function whose name and signature already state its purpose gets no docstring. Add one line
when the purpose is not recoverable from the name — a non-obvious contract, a return value with
meaning beyond its type, a precondition the caller must hold. One line, purpose not mechanism.

### 3. Spec Backlink — Commit Message, Not Source

Cite the plan in the **commit message**, as its minted id (`pln-<slug>-<6hex> § <section>`,
never a path — see `cross-repo-citation-conventions.md` for the foreign form). Do not write
`# Implements pln-…` into source: `git log` / `git blame` reach the plan from any line, and the
comment adds nothing the trail lacks. Existing in-source backlinks are debt, not precedent.

### 4. Negative-Spec Block — At a Real Trap Only

Where the natural implementation is wrong and a future editor would reach for it, a short
`DO NOT` states the wrong move and the failure it causes:

```python
# DO NOT wrap in asyncio.run() — FastMCP already awaits the handler; nesting raises at runtime.
async def handle_request(req: Request) -> Response:
```

One to three lines. The trap, not the story of who fell into it. A module that is merely
unusual is not a trap; a negative-spec is not a place to list everything the module doesn't do.

### 5. Skill Trigger-Boundary Block

A SKILL.md whose `description:` auto-routes and could match tangential prompts carries a
`## Do not use for` section bounding the trigger. Prompt surface, not source — the source rules
above don't apply to it.

---

## Vocabulary Discipline — CONTEXT.md

Where a repo has a `CONTEXT.md` glossary, identifiers, docstrings, and comments use its
canonical terms and avoid its `_Avoid_:` list. This matters for project-coined, low-frequency
terms (`distill`, `enricher`) where synonym drift fragments both BM25 and embedding recall;
general engineering vocabulary (`function`, `module`) needs no policing.

---

## Anti-Patterns

| Anti-pattern | Why it fails |
|---|---|
| Inline what-comments (`# increment x`) | Restate the code; rot on refactor. |
| Rationale essays in docstrings | "We tried X, measured Y on 2026-08-12, so now Z" — the plan and commit hold this; in source it rots and drowns the code. |
| History / changelog in source | "Retargeted after commit abc123", "was P, now Q" — `git log` is the history. |
| Review or task attribution | `# Review: <reviewer> — …`, "added for issue #123" — `REVIEW-ATTRIBUTION-LIVES-IN-THE-SIDECAR-NOT-THE-SOURCE`. |
| In-source spec backlinks | `# Implements pln-…` — the commit carries the citation (§ 3). |
| Docstrings on self-describing functions | `def load_config(path)` → `"""Load the config."""` adds bytes, not signal. |
| Negative-spec inventories | A block listing everything a module doesn't do; reserve `DO NOT` for real traps. |
| Behaviour-level docstrings | "Calls validate(), then store()" — lies once the implementation changes. |
| Copy-pasted purpose blocks | Wrong signal for both chunks. |
| Vocabulary drift | "enrichment worker" for "enricher" — fragments recall on coined terms. |
