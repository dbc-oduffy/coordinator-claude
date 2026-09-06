# Code-Comparison Record Schema

Neutral intermediate record schema for the deep-research **code-comparison emission mode** — a single self-contained agent (fan-out shape, not the phased scout→specialist→synthesizer orchestrator of Pipelines A/B/C) that compares a subject repo against a peer/competitor code target and emits structured comparison records. DoE emits an **observed, entity-agnostic** record; market-intel's downstream producer resolves entities (`peer_ref` → `competitor_uid`) and computes merge classification. This doc defines the record shape only — dispatch mechanics for the comparison agent live in a sibling doc.

---

## Purpose

Code-comparison mode answers "how does `subject_repo` compare to `peer_repo` on axis X?" for a caller-supplied list of axes, and emits one record per `(repo, axis)` pair. The record is **neutral**: it carries DoE's raw observation (what the agent saw, on which axis, with what evidence) and explicitly omits any resolved-entity or classification data that depends on downstream state the agent does not have visibility into.

---

## Design principle — DoE observes, the producer resolves

DoE-deep-research has no visibility into market-intel's `competitors[]` table or prior-merge history. The record format reflects that boundary:

- DoE emits `peer_ref` — the raw, unresolved peer handle it observed (a repo coordinate, else a strong-id coordinate). It does **not** emit `competitor_uid`.
- DoE emits `observation.verdict` — a raw peer-relative-to-subject comparison. It does **not** emit CONFIRMED/UPDATED/NEW/REFUTED — that classification requires comparing against existing intelligence state, which only the producer has.

See `## Negative Specs` below for the two hard omissions this implies.

---

## Record Schema

One record per `(repo, axis)` observation:

```yaml
repo: <string>                    # subject repo identifier (owner/name or equivalent)
signal_id: <string>               # deterministic kebab-case slug of axis — see § signal_id below
axis: <string>                    # human-readable axis label, verbatim from the invoker-supplied axis list

peer_ref: <string>                # RAW unresolved peer handle DoE observed — e.g. "owner/peer-repo"
                                   # or a clone URL, else a strong-id coordinate (QID, else
                                   # registrant domain) when no repo coordinate exists. Also present
                                   # as the permalink target inside observation.peer.evidence[].url
                                   # whenever that permalink exists. Carried as a first-class field
                                   # so the producer can resolve it without re-parsing evidence.

observation:
  peer:
    state: <string>                # free-text description of what the agent observed on the peer side
    evidence: [SourceRef, ...]     # see § SourceRef below (code-comparison-local vocabulary)
    evidence_tier: source_read | artifact_forensic   # REQUIRED iff evidence is non-empty
  subject:
    state: <string>                # free-text description of what the agent observed on the subject side
    evidence: [SourceRef, ...]
    evidence_tier: source_read | artifact_forensic   # REQUIRED iff evidence is non-empty
  verdict: MEETS | LAGS | BEATS | INDETERMINATE    # peer relative to subject on this axis — see § verdict below

confidence: HIGH | MEDIUM | LOW    # agent's confidence in this observation — see § confidence below

analysis: <string>                 # free-text annotation — NEVER a recommendation, see § analysis below

observed_at: <ISO-8601 timestamp>  # when the agent made this observation

provenance:
  source_kind: code_comparison
  derivation: "doe-deep-research/code-compare@<run-id>"   # <run-id> = the mode's run identifier
```

---

## Worked Example — paste this, do not retype

The record below is complete, valid, and copy-pasteable. Paste it into a dispatch prompt or an
emit file and replace the values. Do not reconstruct the shape by reading the field reference
below and retyping it.

**Negative spec — the record shape is pasted, never hand-transcribed.** Every field in this
document is specified correctly in prose, and prose is still the wrong thing to retype from: the
first real adopter run emitted three independent shape defects, all three entering at the
retyping step, none at the reading step. The three classes, each of which pasting this instance
makes unreachable:

1. **`verdict` written at the record top level.** It is `observation.verdict` — nested, one level
   down, a sibling of `observation.peer` and `observation.subject`.
2. **`evidence[]` entries with invented or dropped fields.** A `SourceRef` is exactly
   `{url, fetch_date, platform, comment_id}` — all four keys present on every entry, with
   `comment_id: null` when the source is not comment-scoped. There is no `note` key.
3. **`url` written as a bare `blob/<sha>/path#Lx-Ly` fragment.** It is a fully-qualified
   permalink — `https://<host>/<owner>/<repo>/blob/<sha>/path#Lx-Ly` — whenever the target is a
   git repo with a resolvable SHA. The bare-fragment degradation is only for a target that has
   neither, and it must be noted in `analysis`.

```yaml
repo: dbc-oduffy/DoE-claude
signal_id: cli-argument-parsing-robustness
axis: "CLI Argument-Parsing Robustness"

peer_ref: dbc-oduffy/project-rag

observation:
  peer:
    state: >
      project-rag's cli.py builds its CLI with stdlib argparse
      (ArgumentParser + subparsers), which provides typed argument
      validation (type=int, choices=[...]), auto-generated --help/usage
      text, and structural argument grouping via a shared `_db_parent`
      parent parser reused across subcommands (audit, diff, reindex).
      Flag values are enforced at parse time (e.g. --last requires an
      int, --group-by is constrained to {tool, day}) without hand-rolled
      case-statement validation.
    evidence:
      - url: "https://github.com/dbc-oduffy/project-rag/blob/aba9ea96b5b77804de06c07c3fdaf8d2fb22b35c/cli.py#L1565-L1627"
        fetch_date: "2026-07-12"
        platform: github
        comment_id: null
    evidence_tier: source_read
  subject:
    state: >
      coordinator-safe-commit is a bash script that hand-parses flags via
      a manual `while [[ $# -gt 0 ]]; case "$1" in ... esac` loop (lines
      112-186). Each flag (--blanket, --scope-from, --dry-run,
      --include-orphans, --expected-branch, --expected-owner) has its own
      hand-written arity check (e.g. `if [[ $# -lt 2 ]]`) and error
      message; there is no auto-generated usage/help beyond the static
      heredoc in usage() (lines 82-109). --expected-owner additionally
      hand-validates its value against a single literal ("em-only") via
      an explicit string comparison (lines 167-170) rather than a
      declarative choices list.
    evidence:
      - url: "https://github.com/dbc-oduffy/DoE-claude/blob/cbbd7cd220bbb9e2f92a511cd7abfc2f5c7ef354/coordinator/bin/coordinator-safe-commit#L111-L186"
        fetch_date: "2026-07-12"
        platform: github
        comment_id: null
    evidence_tier: source_read
  verdict: BEATS

confidence: HIGH

analysis: >
  Peer's argparse-based parsing centralizes arity/type/choices validation
  declaratively and gets --help generation for free, which the subject's
  hand-rolled bash case-loop must instead reimplement per-flag (each new
  flag needs its own arity check and its own usage() heredoc line kept in
  sync manually). This is a structural robustness gap on this axis: the
  subject's approach has already shown drift risk (the --expected-owner
  literal-value validator at lines 167-170 is exactly the kind of
  per-flag hand validation argparse's `choices=[...]` would express in
  one line). The observation is scoped to this one file; it does not
  speak to the subject's broader bash-tooling conventions elsewhere in
  the repo.

observed_at: "2026-07-12T00:00:00Z"

provenance:
  source_kind: code_comparison
  derivation: "doe-deep-research/code-compare@fixture-c4-2026-07-12"
```

The permalinks above cite real file:line ranges at each repo's sha as of the example's authoring
date — a point-in-time citation, not an invariant that survives either repo's history advancing.

**Explicit-absence variant.** A side documenting a searched-but-absent finding carries
`evidence: []` and **no** `evidence_tier` — there is nothing to qualify. Everything else is
unchanged:

```yaml
  peer:
    state: >
      No rate-limiting mechanism found. Searched `middleware/`, `config/`, and every
      `*.py` matching `rate.?limit`; the request path in `server/app.py` reaches the
      handler with no interposed throttle.
    evidence: []
```

That side still takes a directional verdict — a peer that demonstrably lacks a mechanism is a
callable `LAGS`/`BEATS`, never `INDETERMINATE`. See § `observation.verdict`.

**One record, and a file of records are different shapes.** The block above is one record body.
An emit *file* holds a top-level YAML sequence of these bodies, one entry per `(repo, axis)` pair
— see § Downstream emit.

**The same record lives on disk** at
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/fixtures/code-comparison-sample-record.yaml`, with
`fixtures/validate-code-comparison-record.py` as its checker. Run that validator against your own
records before emitting them; it enforces every rule this section names. **It takes either shape** —
a single record body, or the emit file's top-level sequence, which it validates element-by-element
and reports as `record[<i>]: <violation>`. Point it at the file you are about to emit.

---

## Field Reference

### `repo`

The subject repo identifier — the repo being evaluated, expressed in the same identifier form the invoker used to name it (owner-qualified slug or equivalent). Stable across all records emitted in a run.

### `signal_id`

A deterministic kebab-case slug of `axis`, using the **same conversion `spec-format.md` documents for `{TOPIC_NAME}`**: lowercase, spaces → hyphens, strip special characters. See `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/spec-format.md` § Variable Substitution — cite that conversion rule verbatim; do not redefine it here.

Example: axis `"API Rate Limiting"` → `signal_id: api-rate-limiting`.

**Negative spec — the agent does not coin axes.** The axis list is an **input** to code-comparison mode, supplied by the invoker at dispatch time. The comparison agent never invents a new axis or a `signal_id` beyond what appears in the supplied list — it slugs the given axes, it does not extend them.

### `axis`

The human-readable axis label, carried verbatim from the invoker-supplied axis list (the pre-slug source string for `signal_id`).

### `peer_ref`

The raw, unresolved peer entity handle DoE observed. Its vocabulary has two arms, in preference order:

1. **Repo coordinate** — an owner-qualified peer/repo slug (`"peer-org/peer-repo"`) or a clone URL. This is the same identity already present as the permalink target inside `observation.peer.evidence[].url`; it is duplicated here as a first-class field so a downstream consumer can resolve identity without parsing evidence payloads.
2. **Strong-id coordinate** — a Wikidata QID, else the peer's registrant domain. Used when **no repo coordinate exists**, which is the normal case for an `artifact_forensic` peer: there is no repository, so there is no permalink to ground arm 1 on, and a free string of unspecified shape is not a substitute. See § `evidence_tier` below.

**Negative spec — peer identity is one field, never two.** Both arms live in `peer_ref`; there is no sibling `peer_coordinate`. One identity field keeps one producer-side resolution path: market-intel's `resolve_peer_ref` falls through a `NON_GITHUB_STRONG_ID_LADDER = ("qid", "cik", "domain")` reading `peer_ref` itself. A second field would strand that ladder and fork the natural-key join on which field to read.

**Negative spec 1 — DoE does not emit `competitor_uid`.** The record omits it entirely. Resolving `peer_ref` → `competitor_uid` is a stateful join against market-intel's `competitors[]` table, which is producer-side state DoE has no access to. DoE emits observed identity; the producer resolves entities.

### `observation.peer` / `observation.subject`

Each side carries:

| Field | Type | Description |
|---|---|---|
| `state` | string | Free-text description of what the agent directly observed on that side of the comparison for this axis |
| `evidence` | `SourceRef[]` | One or more source citations backing `state` — see the explicit-absence exception below |
| `evidence_tier` | enum \| absent | Provenance class of that side's evidence. Required iff `evidence` is non-empty — see § `evidence_tier` below |

**Explicit-absence exception — `evidence: []` is permitted.** When a side's `state` documents a
searched-but-absent finding (e.g. "no rate-limiting middleware found; searched `middleware/`,
`config/`, and all `*.py` files matching `rate.limit`"), the absence itself is the evidence and
`evidence` MAY be an empty array — a synthetic `SourceRef` pointing at the searched scope is NOT
required. The "no X found; searched Y" text lives in `state`, not in a fabricated citation. This
is the schema-side statement of the rule the agent template documents in Phase 2 (peer lacking a
capability).

### `evidence_tier`

A closed two-member enum naming the **provenance class of the bytes** a side's evidence was read
from. Ordinal: `source_read` > `artifact_forensic`.

| Value | Meaning |
|---|---|
| `source_read` | Evidence located in source code — a repo clone or equivalent source tree on disk |
| `artifact_forensic` | Evidence located in a lawfully-obtained compiled/packaged artifact corpus on disk — `strings` dumps, PDB symbol tables, a decompiled `.asar`, route manifests, SQL migrations, dependency trees |

**Carried per-side, never per-record.** Tier qualifies evidence, and evidence lives on the side; a
record is an aggregate of two independent evidence sets with no evidence of its own to qualify. A
record-level tier is derivable from per-side as weakest-of-sides, and the reverse does not hold, so
per-side is strictly more expressive. A source-read subject compared against an artifact-forensic
peer is the common case and is representable only per-side. Market-intel's counterpart is
`CodeComparisonSide.evidence_tier`, on the side for the same reason.

**Required iff the side carries evidence.** A side with `evidence: []` — the explicit-absence
exception above — carries no tier, because there is nothing to qualify. A side with evidence and no
tier is rejected, with no default-fill: such a record would serialize identically to a
properly-tiered one, which is the laundering this field exists to prevent, so the honest gap beats
the guess.

**Mixed provenance takes the weakest tier on that side.** Any single `artifact_forensic` citation
makes the whole side `artifact_forensic`, even alongside `source_read` citations. **This is DoE's
obligation as the producer, not something a consumer can compute** — `SourceRef` carries no
per-citation tier, so nothing downstream can recover the mix. The agent resolves it deliberately;
it never takes the first citation's tier as the side's.

**Literals are snake_case** — one closed wire vocabulary takes one spelling across both repos.
Market-intel's `EvidenceTier` (`market_intel/contract/enums.py`) is the same closed two-member set,
wire-carried at `EMISSION_SCHEMA_VERSION = "3.6.0"`, and its `CodeComparisonSide` enforces both
rules above.

**Negative spec — the exclusion of behavioral evidence is categorical, not ordinal.** A target's
self-report about its own capabilities — vendor documentation, conversational probing of the
running product, network observation of its behaviour — has **no position on this ordinal at all**,
not a rung below `artifact_forensic`. A claim about an implementation and an observation of one are
different kinds of thing and do not share a scale; admitting the first as a tier would launder
claim as evidence, which is what this field exists to prevent. Should published vendor
documentation ever be wanted as a signal, it belongs in a separate field with its own semantics —
never as a third rung here, however carefully sourced.

`docs/research/2026-07-11-aura-investigation-no-source-calibration.md` § Preamble corroborates the
exclusion — five behavioral claims refuted by artifact forensics one day later — but is **not the
reason for it**. Cite the categorical argument, which survives a contrary study; the n=5 result
would not.

**The local-only fence binds identically at both tiers.**
`code-comparison-agent-prompt-template.md` :100-102, :107-108 and :128-134 forbid network fetches
and recollection from training data, and require the agent to find the code on disk. An
artifact-forensic corpus satisfies every one of those rules literally when passed as
`[PEER_TARGET_PATH]` — the fence is about **provenance of bytes**, not about the bytes being
source. `file:line` evidence against a strings dump is a real citation, and the explicit-absence
exception above applies unchanged. No fence text is weakened to admit tier 2, and none may be.

### `SourceRef`

Code-comparison-local vocabulary, inspired by (but not identical to) spec-format.md's `sources[]`
shape (`url, date, type` — see `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/spec-format.md`
§ Minimal Example):

```yaml
url: <string>                      # source URL / permalink — see § url below for permalink-vs-local-path rule
fetch_date: <ISO-8601 date>        # when the agent fetched/observed this source
platform: <string>                 # e.g. "github", "gitlab", docs host, etc.
comment_id: <string | null>        # discussion/comment anchor, or null if the source is not comment-scoped
```

`SourceRef` is defined and owned here, not in spec-format.md. If a code-comparison-specific need
arises, extend it here directly.

#### `SourceRef.url`

`url` is a fully-qualified permalink in `https://.../blob/<sha>/path#Lx-Ly` form when the peer or
subject target is a git repo with a resolvable SHA. When the target is not a git repo, or has no
resolvable SHA, `url` degrades to a bare local `path#Lx-Ly` fragment (no scheme, no host) — this
degradation MUST be noted in the record's `analysis` field. See the agent template's Phase 1 /
Per-Axis Record Construction sections for the same rule stated for the dispatched agent.

### `observation.verdict`

One of `MEETS`, `LAGS`, `BEATS`, `INDETERMINATE` — expressed **peer relative to subject** on this axis:

| Value | Meaning |
|---|---|
| `MEETS` | Peer is at parity with subject on this axis |
| `LAGS` | Peer is behind subject on this axis |
| `BEATS` | Peer is ahead of subject on this axis |
| `INDETERMINATE` | The axis is genuinely incomparable, or the evidence on one/both sides is too thin to establish any direction |

**`INDETERMINATE` is not the "peer lacks the capability" case.** A peer that demonstrably lacks a
mechanism is a callable `LAGS`/`BEATS` with `evidence: []` (the explicit-absence exception — see
§ `observation.peer` / `observation.subject` above), NOT `INDETERMINATE`. `INDETERMINATE` is the
honest alternative to forcing a directional verdict you cannot support — prefer it over a
`LOW`-confidence directional guess when you genuinely cannot call the direction; do not fabricate
a `MEETS`/`LAGS`/`BEATS` verdict just to avoid it.

This is DoE's raw observed comparison. It is not a merge/change-type classification — see § Merge classification below for the distinct, downstream-only taxonomy.

### `confidence`

One of `HIGH`, `MEDIUM`, `LOW` — the agent's confidence in the observation backing this record.
**DoE emits the enum only; DoE is the SSOT for confidence.** DoE does not compute or emit a float.
Whether a downstream consumer preserves the ordinal verbatim or projects it onto its own scale is
that consumer's choice, not asserted here (market-intel, as one such consumer, preserves it
verbatim — `confidence=None` in its claims ledger, no float projection).

The rubric is evidence-strength / locatability based, not axis-coverage based:

- **`HIGH`** — direct file:line evidence located on both sides; the comparison is unambiguous.
- **`MEDIUM`** — evidence present but partial or indirect (one side thinner, or the call rests on inference across a couple of files).
- **`LOW`** — could not fully locate supporting file:line evidence ("unable to locate"); best-effort observation.

### `analysis`

Free-text annotation elaborating on the observation — context, nuance, caveats.

**Negative spec — `analysis` is never a recommendation.** It documents what was observed and why it matters as a comparison signal; it does not prescribe what the subject repo should do about it. Recommendation authorship, if any, is a downstream/producer or human-consumer concern, not a DoE emission.

### `observed_at`

ISO-8601 timestamp of when the agent made this observation (not when the record is later ingested downstream). This is the agent's own wall-clock time when the *record* was finalized — a single value per record, independent of and not derived from any per-`SourceRef` `fetch_date` (which timestamps when an individual source was fetched, potentially earlier than `observed_at`).

### `provenance`

| Field | Value | Description |
|---|---|---|
| `source_kind` | `code_comparison` | Fixed literal identifying this record's originating mode |
| `derivation` | `"doe-deep-research/code-compare@<run-id>"` | `<run-id>` is the code-comparison run's identifier, substituted at emission time — see `spec-format.md` § Variable Substitution for `{RUN_ID}` format |

---

## Natural Key (downstream)

The producer's natural key for merging a code-comparison record into its `code_comparisons[]` array is:

```
(repo, competitor_uid, signal_id)
```

`competitor_uid` is **stamped downstream** by the producer resolving `peer_ref` against its `competitors[]` table — it is never present in the DoE-emitted record. The DoE record carries `repo` + `signal_id` + `peer_ref`, which together give the producer everything it needs to resolve `competitor_uid` and complete the natural key. See § `peer_ref` negative spec above.

---

## Merge classification (applied downstream by market-intel's producer at merge time — DoE does NOT compute this)

The CONFIRMED/UPDATED/NEW/REFUTED change-type taxonomy documented in `${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/spec-format.md` § Change Type Taxonomy is **shared vocabulary** — the same four labels and definitions apply — but the **actor differs**: in spec-format.md the taxonomy is applied by Pipeline C's own Phase 2/3 verification and synthesis agents against DoE's own prior structured output. Here, it is applied by **market-intel's producer**, at merge time, comparing an incoming code-comparison record's `observation.verdict` against the existing `intelligence[]` entry it resolves to via the natural key above.

**Negative spec 2 — DoE does not compute CONFIRMED/UPDATED/NEW/REFUTED for code-comparison records.** The comparison agent emits `observation.verdict` (MEETS/LAGS/BEATS) only. Whether that verdict is a `NEW` signal, an `UPDATE` to a prior verdict, a `CONFIRMED` restatement, or a `REFUTED` contradiction is determined entirely downstream, because only the producer has the prior `intelligence[]` state to compare against.

---

## Negative Specs — Summary

1. **No `competitor_uid` in the DoE record.** `peer_ref` is emitted raw; entity resolution is producer-side.
2. **No merge classification in the DoE record.** `observation.verdict` is emitted raw; CONFIRMED/UPDATED/NEW/REFUTED is producer-side, computed against prior `intelligence[]` state DoE cannot see.
3. **No agent-coined axes.** The axis list (and thus the `signal_id` slugs derived from it) is invoker-supplied input, never agent-invented.
4. **`analysis` is never a recommendation.** It annotates the observation; it does not prescribe subject-repo action.
5. **`confidence` is an enum, never a float.** DoE is the SSOT for confidence and never computes or emits a float; whether a downstream consumer preserves the ordinal verbatim or projects it is that consumer's choice, not DoE's concern.
6. **Peer identity is one field.** Both `peer_ref` arms live in `peer_ref`; there is no sibling `peer_coordinate`.
7. **`evidence_tier` has two members and no third.** `behavioral` — a target's self-report about its own capabilities — is excluded, and tier is carried per-side, never per-record.

---

## Downstream emit

This section defines the shape of the downstream emit path for code-comparison records, and what
is wired for it — see § "What is wired" below.

### Handoff shape

The repo running the comparison writes the neutral, entity-agnostic records defined above to its
own handoff path, in its own tree — there is no central DoE-owned directory other repos write
into. Market-intel's own producer queries across repos' handoff directories, projects each record
into its emission envelope's `code_comparisons[]` array — an own array, not `intelligence[]`
(`intelligence[]` is sentiment-shaped; a code-comparison record carries
`observation{peer,subject,verdict}` on the natural key `(repo, competitor_uid, signal_id)`, which
does not fit that shape) — stamps `competitor_uid` (resolved from `peer_ref` against its
`competitors[]` table — see § `peer_ref` negative spec above), and computes the
CONFIRMED/UPDATED/NEW/REFUTED merge classification (see § Merge classification above). No repo
writes directly into the producer's envelope; the producer is the sole writer of it.

### Path resolution — pointer-seam, not a flat hardcoded path

The handoff path a repo writes records to MUST resolve via a repo-root pointer-seam — the same
in-tree convention used throughout `repo-driver.md` for internal deep-research references (e.g.
`${CLAUDE_PLUGIN_ROOT}/pipelines/deep-research/...`). It MUST NOT be a flat hardcoded filesystem
path (e.g. a bare `~/.claude/...` or absolute-machine path). The seam is stable across the
stub-to-live transition, so live-emit wiring does not migrate the path a second time.

**The bound path is `<repo-root>/state/emissions/code-comparison/`** — `<repo-root>` is the root
of the repo running the comparison, resolved via that repo's own tree-root pointer (for DoE, the
`.doe-root` pointer; never `${CLAUDE_PLUGIN_ROOT}`, which names the plugin source tree under
`<repo-root>/coordinator/`, not the repo root that `state/` sits under). Each repo binds its own
code-comparison agent's output path to this directory, relative to its own root, plus a
run-scoped filename; `state/emissions/code-comparison/README.md` states the arrival contract for
DoE's own copy of this directory.

### Emit file format and filename

**Records are emitted as YAML, one file per run, and the file is machine-readable throughout.**
The file's top-level node is a sequence of record bodies (§ Worked Example), one entry per
`(repo, axis)` pair — never a prose document with records in fenced blocks, and never one file per
record. `.json` carrying the same structure is equally readable downstream; `.md` is not read at
all. Market-intel's `_read_raw_records_from_one_dir` globs `*.json`/`*.yaml`/`*.yml` and never
sees anything else — a Markdown writeup emitted here does not fail loudly, it reports as zero
records, indistinguishable from a run that never happened. A human-readable writeup is welcome
alongside it, under any name the glob does not match.

**The filename is the run-id, zero-padded: `YYYY-MM-DD-HHhMM.yaml`** (e.g.
`2026-08-18-10h47.yaml`). The time component is not decoration — the downstream merge is
supersede-latest-per-natural-key and relies on lexical filename order tracking run chronology, so
a date-only or unpadded name makes two runs on one day sort ambiguously. The driver generates
this run-id (`repo-driver.md` § Mode Dispatch step 2); the agent writes to the path it is handed.

### What a live emit-run rests on

An emit-run is in contract at either `evidence_tier`. Two properties hold, and a run is out of
contract if either stops holding:

- **A consumer exists for what this path writes.** Market-intel's ingest counterpart —
  `resolve_code_comparisons`, `market_intel/ingest/code_comparison.py` on `example-market-data-repo`
  `origin/main` — queries across repos' handoff directories and projects results into
  `code_comparisons[]`. No repo emits into a void.
- **The DEC-1 boundary is ratified on both sides.** DEC-1 is the boundary this whole schema
  expresses: DoE emits a neutral, entity-agnostic intermediate record, and the producer resolves
  entities and classifies merges. Both repos carry the same wire vocabulary, market-intel's at
  `EMISSION_SCHEMA_VERSION = "3.6.0"`.

Every run binds to the local-only fence in `code-comparison-agent-prompt-template.md`, identically
at both tiers — see § `evidence_tier`.

### Downstream consumers (cited, not re-specified here)

- `example-market-data-repo:docs/06-claude-klabauter-consumer-boundary.md` — market-intel's producer-side consumer boundary doc; defines how it projects incoming neutral records into its `code_comparisons[]` array.
- cockpit's `ingestEmission` — the downstream ingestion entry point that ultimately receives the producer's projected emission envelope (now carrying a `code_comparisons[]` array for this record type, not `intelligence[]`). **⚠ WIRED BUT RETIRED — do not build against this consumer.** The consuming repo retired the `code_comparisons` emission path on 2026-08-22 as one of seven dropped emission sections: zero rows, no consumer. The Zod bridge and the SQLite table still physically exist and an emission still *validates*, so this path fails silently rather than loudly — a run lands a well-formed record that nothing reads. The wiring described above is accurate; its disposition is not. What replaced it is read-not-emit: the consumer parses a GitHub-flavoured pipe table straight out of a peer repo's `docs/research/`, gated on a `docs/research/.fleet-readable` opt-in marker in that repo. Pipeline B feeds that reader through its output *naming*, not through this schema — the table itself is emitted by `repo-synthesizer-prompt-template.md` § Fleet-Readable Competitor Row, which carries the column spec.

### What is wired

The code-comparison agent's output path is bound to `<repo-root>/state/emissions/code-comparison/`
(§ Path resolution above) — the driver no longer leaves it an EM fill-in. DoE's own copy of the
directory exists on disk, tracked, and empty: landing this wiring authorizes no comparison run on
its own, and the local-only fence in `code-comparison-agent-prompt-template.md` is unchanged. No
repo writes into `intelligence[]` or any producer envelope — that projection stays market-intel's,
at its own `resolve_code_comparisons`.
