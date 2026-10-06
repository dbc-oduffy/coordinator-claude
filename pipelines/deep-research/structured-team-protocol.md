# Deep Research Structured Team Protocol (v2.1)

> Referenced by agent definitions and the structured-research driver.

## Overview

Chatty-Workflow structured research: the EM reads a spec YAML, pre-processes it into a scout brief, fires ONE background `Workflow` whose script runs a Haiku scout, Sonnet verifiers, a rebuttal round, and an Opus synthesizer in order, and is **freed**. The agents handle everything autonomously — spec-driven source discovery, schema-mapped verification, adversarial cross-pollination between verifiers, cross-topic reconciliation, and schema-conforming output. The Workflow's task notification carries the synthesizer's return value; the EM validates schema conformance via a hard file-existence gate, then cleans up.

Pipeline C is spec-driven and schema-conforming. Unlike Pipeline A (free-form internet research), every finding maps to an output schema field, every verifier self-checks acceptance criteria and gate rules embedded in their prompts, verifiers actively challenge each other's schema field values, and the final output is validated against the spec before archival.

## Roles

| Role | Model | Count | Responsibility |
|------|-------|-------|----------------|
| **Scout** (`scout`) | Haiku | 1 | Execute spec-derived search queries from scout-brief.md, map findings to schema fields, write per-topic discovery files |
| **Verifier** (`verifier-{topic_id}`) | Sonnet | 1-5 | Verify scout's per-topic discovery, compare against existing data, produce schema field tables with change types (CONFIRMED/UPDATED/NEW/REFUTED/CONTESTED), self-check acceptance criteria and gate rules, challenge peers' field values through mailbox files |
| **Synthesizer** (`synthesizer`, overseer) | Opus | 1 | Cross-topic reconciliation, resolve CONTESTED fields, schema validation, produce YAML/JSON output conforming to output_schema. Its return value is the only one that reaches the EM. |

## Stage Lifecycle

```
EM: Read spec → pre-process into scout-brief.md → Fire Workflow → FREED
Stage 1  Scout: Read scout-brief.md → WebSearch → WebFetch (vet accessibility) → Map to schema fields → Write per-topic discovery files → Return
Stage 2  Verifiers (parallel): Read discovery files → Verify + compare existing data → Append challenges to peers' mailboxes → Produce schema field tables → Self-check gate rules → Write findings → Return {topic, challenged}
Stage 3  Rebuttal (parallel, only roles with unread mail): Fresh continuation reads its mailbox + own findings + predecessor's return → Answers challenges → Revises findings → Return
Stage 4  Synthesizer: Read all findings → Write skeleton to OUTPUT_PATH → Cross-reconcile → Resolve CONTESTED → Validate schema → Overwrite OUTPUT_PATH with final → Write annotations → Return summary to EM
```

## Stage Ordering

Ordering gates the stages: stage N+1 starts when stage N's `agent()` calls return (`await`, or `parallel()` for a fan-out). A returned agent is never resumed — `SendMessage` cannot wake it. Each later stage is a fresh dispatch, so the rebuttal round is a continuation agent per role, briefed with its mailbox path, its prior output files, and its predecessor's return value.

The script has no filesystem, so it cannot read mailboxes. Each verifier's return value names the peers it wrote to (`challenged`: topic ids); the script dispatches a rebuttal continuation for exactly those roles. The default is one rebuttal round.

## Scout Protocol

The scout builds **per-topic discovery files** — schema-mapped findings, one file per topic. It does NOT try to produce finished analysis.

- Reads topic queries and schema field mappings from `{scratch-dir}/scout-brief.md` (written by EM during pre-processing)
- Executes queries via WebSearch, including adversarial queries when provided by the EM
- Mechanically vets each result via WebFetch: accessible? paywall? date? source type?
- Maps each finding to schema fields (as listed in scout-brief.md)
- Writes one discovery file per topic: `{scratch-dir}/{subject}-scout-{topic_id}.md`
- **No messaging** — the scout's return starts the verifier stage.
- **Timing:** No floor. Ceiling: 3 minutes. This is mechanical work — go fast.

## Mailbox Protocol

Peer exchange goes through mailbox files `{scratch-dir}/mail/<role>.jsonl`. A line is `{"from": "<role>", "text": "..."}`. To message peer X, append to X's file. A reader appends `{"read": true}` after reading its file; it has unread mail when lines follow its last read marker. Roles are `scout`, `verifier-{topic_id}`, `synthesizer`. No agent messages the EM.

### Verifier → Verifier (Adversarial Cross-Pollination)

Append targeted messages to specific peers' mailboxes. Challenges are **expected**, not just permitted — verifiers should actively test each other's schema field values. The `text` of each line follows these formats:

| Category | Format | When |
|---|---|---|
| **FINDING** | `"Finding for {peer}: {brief}. Source: {URL}. Schema field: {field_name}. Relevant because {reason}."` | A discovery relevant to another verifier's schema fields |
| **CONTRADICTION** | `"Contradiction with {peer}: I found {X} for field {field_name} but your area suggests {Y}. Can you verify?"` | Sources disagree on a schema field value across topics |
| **CHALLENGE** | `"Challenge to {peer}: Your finding {X} for field {field_name} conflicts with {Y} from {source}. Which is current?"` | Direct factual conflict on a schema field value — resolution expected |
| **SOURCE** | `"Source for {peer}: {URL} — covers {aspect} relevant to your topic / field {field_name}."` | Useful source for a peer's topic or schema field |
| **SCHEMA_OVERLAP** | `"Schema overlap with {peer}: While researching {my_field}, I found evidence relevant to your field {their_field}: {value} from {source}. Flagging for your verification."` | Evidence found for a schema field owned by a different verifier |

**Resolution protocol:** Round-1 verifiers write their findings, append challenges, and return. In the rebuttal round, a verifier whose mailbox holds challenges answers each with evidence or concedes, revising its findings file. A challenge still unanswered after the rebuttal round produces `CONTESTED` change type with both sides' evidence — the synthesizer resolves these.

### Verifier → Synthesizer

No signal message. The synthesizer stage starts after the verifier and rebuttal stages return; the script passes it the verifiers' return values, and it reads `{scratch-dir}/*-findings.md`.

### Volume Governance

- **Peer messages: max 3 per peer** (max 12 total for a 5-verifier run)
- **Scout: no messages**
- Quality over quantity — **no acknowledgment-only messages** ("got it", "thanks", "acknowledged"). Every message must contain a finding, challenge, source, or schema-field overlap.

## Self-Governance Timing

Verifiers manage their own timing. The EM does not intervene.

### Three-Part Model

1. **Floor (minimum before convergence allowed)**
   - Must have fetched at least `MIN_SOURCES` sources AND worked for at least `MIN_MINUTES` minutes
   - Both conditions must be met — prevents "fast 3 sources in 2 minutes" thin convergence
   - Defaults: 5 sources, 5 minutes

2. **Diminishing Returns (between floor and ceiling)**
   - After the floor, self-assess after each source: "Did this add new verified schema field values?"
   - If last 3 consecutive sources added no new verified findings → convergence signal
   - Note in Investigation Log: "Converging: diminishing returns after source N"

3. **Ceiling (maximum research time)**
   - Configurable by the EM when filling the verifier prompts (default: 15 minutes)
   - Begin convergence regardless of state
   - Check time via `date +%s` in Bash, compare against spawn timestamp

### Clock Mechanism

Spawn timestamp is provided in the verifier prompt as `[SPAWN_TIMESTAMP]` (Unix epoch seconds). Verifiers check elapsed time via `date +%s` in Bash at each source-fetch cycle and compare.

## Convergence Protocol

Begin convergence when ANY of these conditions are met (AND the floor is satisfied):
- At least `MIN_SOURCES` verified sources and contradictions addressed
- Last 3 sources added no new schema field findings (diminishing returns)
- Ceiling time reached

**Steps:**
1. **Self-check acceptance criteria** — verify minimum sources met and required schema fields covered
2. **Self-check gate rules** — verify embedded quality gate rules pass (e.g., source recency, source type requirements)
3. **Self-check adversarial coverage** — "Have I challenged at least one peer's schema field value?" Note the answer.
4. Write complete output file (schema field table with change types)
5. Return `{topic, challenged}` — the peers whose mailboxes it appended to

**Timeout:** A challenge not answered in the rebuttal round is marked `CONTESTED` with both sides' evidence.

## Output Format

### Scout Output (per topic)

`{scratch-dir}/{subject}-scout-{topic_id}.md`:
```markdown
# Scout Discovery: {TOPIC_NAME}

## Sources Found

| URL | Title | Date | Type | Accessible | Schema Fields |
|-----|-------|------|------|------------|---------------|
| ... | ...   | ...  | ...  | yes/no     | field_a, field_b |

## Raw Findings by Schema Field

**{field_name}:** {raw finding} [Source: URL]
...
```

### Verifier Output (per topic)

`{scratch-dir}/{topic_id}-findings.md`:
```markdown
# Verifier Findings: {TOPIC_NAME}

## Schema Field Table

| Field | Value | Source | Confidence | Existing Value | Change Type |
|-------|-------|--------|------------|----------------|-------------|
| ...   | ...   | URL    | HIGH       | ...            | CONFIRMED   |
| ...   | ...   | URL    | MEDIUM     | ...            | UPDATED     |
| ...   | ...   | URL    | HIGH       | n/a            | NEW         |
| ...   | ...   | URL    | HIGH       | ...            | REFUTED     |
| ...   | ...   | URL+URL| HIGH/MED   | ...            | CONTESTED   |

## Gate Rule Self-Check
- {Gate rule 1}: PASS / FAIL — {evidence}
- {Gate rule 2}: PASS / FAIL — {evidence}

## Acceptance Criteria Self-Check
- Minimum sources: {N} / {MIN_SOURCES} required — PASS / FAIL
- Required schema fields covered: {list} — PASS / FAIL

## Adversarial Self-Check
- Challenged at least one peer: YES / NO — {details}
- Adversarial sources found: {count} — {summary}
```

### Synthesizer Output

- **Structured data:** `[OUTPUT_PATH]` (spec-defined, e.g., `tasks/research/output/FRA-intel.json`)
- **Annotations:** `{scratch-dir}/synthesis-annotations.md`
- **Advisory:** `{scratch-dir}/advisory.md` (optional — omitted if nothing beyond scope)

## Failure Handling

- **Scout fails (no discovery files):** Verifiers fall back to self-directed discovery using focus questions from scout-brief.md (full WebSearch workflow)
- **Scout times out (partial discovery files):** Verifiers use what's there + supplement with own searches for missing topics
- **Self-timed convergence (ceiling):** Verifiers begin convergence autonomously after max time, without EM intervention
- **WebSearch/WebFetch failures:** If 3 consecutive fetch attempts fail, converge with what you have and note failures in Investigation Log
- **Gate rule failure at convergence:** Note in output as `GATE_FAIL: {rule}` — verifier still completes and returns; synthesizer and EM handle escalation
- **Synthesizer writes prose but no structured data file:** EM file-existence check catches this. The EM fires a correction Workflow (a synthesizer continuation) listing the expected output path and format, then re-validates the revised output.
- **All verifiers fail:** The synthesizer finds no findings files and says so in its return value; the EM reports to PM

## Coverage-Auditor Lifecycle

Pipeline C uses a **reduced** coverage auditor — dispatched by the EM as a plain `Agent` **after** the Workflow completes and **before the run concludes**. The auditor answers one question for structured output: did every verifier finding get mapped to an output schema field, or if dropped, was it annotated?

**Drop-justification oracle:** `{scratch-dir}/synthesis-annotations.md` (written by the synthesizer alongside the structured output). The auditor reads this file as the authoritative record of intentional drops. A finding absent from both the YAML output and `synthesis-annotations.md` is an unacknowledged silent drop — this is what the reduced auditor catches.

**Why reduced (not full A+C)?** Structured output is schema-locked YAML/JSON (`agents/structured-synthesizer.md:59`). There is no synthesis prose to distort — the fidelity failure mode the full auditor guards against (prose flattening, paraphrase drift) structurally cannot occur. The CONTESTED field-challenge mechanism already ensures every disputed value has explicit resolution before synthesis. The reduced auditor does not emit Coverage Pointers or a Completeness Map — it emits a field-mapping check: each `*-findings.md` row classified as `mapped` (field present in output), `dropped-annotated` (explicitly noted in `synthesis-annotations.md`), or `dropped-silent` (absent from both — flag).

**Tool grant:** Read, Grep, Glob only. No write access to the structured output path.

## Fidelity Relay: OUT OF SCOPE

The fidelity relay (waking idle specialists to verify their content was faithfully represented in synthesis prose) is **not applicable to Pipeline C.** Two architectural reasons compose:

1. **No prose synthesis to distort.** The structured synthesizer produces schema-conforming YAML/JSON (`agents/structured-synthesizer.md:59`). Fidelity drift means flattening or misrepresenting a finding in prose — that mechanism does not exist when the output is a typed schema field value.
2. **CONTESTED pre-empts relay need.** Verifiers challenge each other's field values before synthesis via the mailbox cross-pollination protocol. Any value contested across verifiers is explicitly flagged `CONTESTED` and resolved by the synthesizer with both sides' evidence. There is no "author is gone before synthesis runs" gap for relay to close.

The relay is revisited only if Pipeline C adds a prose-synthesis output mode. It is not an appetite call — it is absent because the problem it solves structurally cannot occur here.

## Scratch Directory

`docs/research/{run-id}-{topic-slug}-workdir/`

- Scout writes to: `{scratch-dir}/{subject}-scout-{topic_id}.md` (one per topic)
- Each verifier writes to: `{scratch-dir}/{topic_id}-findings.md` (schema field tables)
- Synthesizer writes structured data to: `[OUTPUT_PATH]` (spec-defined)
- Synthesizer writes annotations to: `{scratch-dir}/synthesis-annotations.md`
- Synthesizer writes advisory to: `{scratch-dir}/advisory.md` (optional)
