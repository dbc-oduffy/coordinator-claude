# Pipeline C — Research Spec Format

Reference for the structured research spec format used by Pipeline C of the deep-research skill. The coordinator reads this when validating a spec; agents reference it for schema field definitions and change type taxonomy.

---

## Purpose

A research spec defines **what to research**, **how to evaluate it**, and **what shape the output must take**. It replaces the coordinator's improvised orchestration (Pipelines A/B) with a repeatable brief that produces consistent, schema-conforming output across subjects and sessions.

---

## Complete Schema

```yaml
# ── Subjects ──────────────────────────────────────
subjects:
  source: <path to JSON/YAML file listing subjects, OR inline list>
  key_field: <field name used as subject identifier — e.g., "code", "id", "name">
  total: <integer — total number of subjects>
  batching:
    tier_1: <N per run>    # e.g., "1 per run" — highest attention
    tier_2: <N per run>
    tier_3: <N per run>    # can pair geographically, thematically, etc.
    tier_4: <N per run>    # lightest coverage

# ── Topic Areas ───────────────────────────────────
topics:
  - id: <letter — A, B, C, ...>
    name: <human-readable topic name>
    search_domains:
      - <search area 1 — what to search for>
      - <search area 2>
    focus_questions:
      - <specific question 1 — what we need to know>
      - <specific question 2>
    model_tier: haiku       # always haiku for Phase 1 discovery
    notes: <optional — special instructions for this topic>

# ── Acceptance Criteria ───────────────────────────
acceptance_criteria:
  per_topic:
    - <criterion applied to every topic — e.g., "at least 2 independent sources">
  per_subject:
    - <criterion applied to the subject as a whole>
  output:
    - <criterion on the final structured output — e.g., field minimums>

# ── Quality Gates ─────────────────────────────────
gates:
  after_phase_1:
    - name: <gate_name — snake_case identifier>
      rule: >
        <Multi-line rule text. The coordinator evaluates this against
        phase output. Be specific about what constitutes pass/fail.>
      skip_for: [<list of subject keys where this gate doesn't apply>]

    - name: <another_gate>
      rule: >
        <rule text>

  after_phase_2:
    - name: <gate_name>
      rule: >
        <rule text>

# ── Output Schema ─────────────────────────────────
output_schema:
  reference: <path to full schema definition file, if external>
  key_fields:
    - path: <dotted field path — e.g., "formation.primary">
      type: <string | string[] | number | boolean | enum | array of objects>
      values: [<enum values, if type is enum>]       # optional
      example: <example value>                        # optional
      required_fields: [<for array-of-objects types>] # optional
      optional_fields: [<for array-of-objects types>] # optional

# ── Known Context ─────────────────────────────────
known_context:
  per_subject:
    source_file: <path template — e.g., "data/{code}_intel.json">
    instruction: >
      <How to use existing data — typically "read before Phase 0,
      identify gaps, target research at gaps not full schema">

  language_requirements:
    reference: <path to language/outlet mapping, if applicable>

# ── Phase Configuration ───────────────────────────
phases:
  phase_0:
    actor: coordinator
    task: >
      <What the coordinator does in Phase 0>
    output_path: <path template — e.g., "tasks/research/{SUBJECT}/research-brief.md">

  phase_1:
    actor: haiku
    dispatch: "1 agent per topic, parallel"
    output_path: <path template — e.g., "tasks/research/{SUBJECT}/phase1-{TOPIC_ID}-{TOPIC_NAME}.md">
    agent_writes_own_output: true

  phase_2:
    actor: sonnet
    dispatch: "1 agent per topic, parallel"
    output_path: <path template — e.g., "tasks/research/{SUBJECT}/phase2-{TOPIC_ID}.md">
    agent_writes_own_output: true

  phase_3:
    actor: sonnet
    dispatch: "1 agent per subject"
    output_path: <path template — e.g., "tasks/research/{SUBJECT}/phase3-synthesis.md">
    agent_writes_own_output: true
    output_format: structured_yaml_or_json

# ── Manifest ──────────────────────────────────────
manifest_path: <path — e.g., "tasks/research/manifest.json">

# ── Options ───────────────────────────────────────
scratch_cleanup: false    # true to delete intermediate files after Phase 3 validation
```

---

## Field Reference

### subjects

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | string | Yes | Path to a JSON/YAML file listing subjects, or `inline` with a list below |
| `key_field` | string | Yes | Field name used as the unique subject identifier |
| `total` | integer | Yes | Total number of subjects in the source |
| `batching` | object | Yes | Per-tier batch sizes. Keys are tier names; values are "N per run" strings |

**Batching tiers** are user-defined labels (e.g., `tier_1`, `tier_2`, or `priority`, `standard`, `bulk`). The coordinator reads these to propose batch sizes to the PM at the start of each run.

### topics

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Single letter identifier (A, B, C, ...) |
| `name` | string | Yes | Human-readable topic name |
| `search_domains` | string[] | Yes | What to search for — fed verbatim to discovery agents |
| `focus_questions` | string[] | Yes | Specific questions — fed verbatim to discovery agents |
| `model_tier` | string | Yes | Always `haiku` for Phase 1 discovery |
| `notes` | string | No | Special instructions (e.g., "factual data ONLY — not predictions") |

### acceptance_criteria

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `per_topic` | string[] | Yes | Criteria applied to every topic's output |
| `per_subject` | string[] | No | Criteria applied to the subject as a whole |
| `output` | string[] | No | Criteria on the final structured output (field minimums, etc.) |

### gates

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `after_phase_1` | array | No | Gates evaluated after Phase 1 completes |
| `after_phase_2` | array | No | Gates evaluated after Phase 2 completes |

Each gate:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Snake_case identifier (used in manifest `gate_retries`) |
| `rule` | string | Yes | Evaluation rule — coordinator applies this to phase output |
| `skip_for` | string[] | No | Subject keys where this gate doesn't apply |

### output_schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `reference` | string | No | Path to external full schema definition |
| `key_fields` | array | Yes | List of schema field definitions |

Each key field:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | Yes | Dotted path (e.g., `formation.primary`, `sources[]`) |
| `type` | string | Yes | Data type: `string`, `string[]`, `number`, `boolean`, `enum`, `array of objects` |
| `values` | string[] | Conditional | Required if type is `enum` — allowed values |
| `example` | any | No | Example value for agent reference |
| `required_fields` | string[] | Conditional | Required if type is `array of objects` — required fields per object |
| `optional_fields` | string[] | No | Optional fields per object (for `array of objects` types) |

### known_context

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `per_subject.source_file` | string | No | Path template to existing data file. Supports `{SUBJECT}` variable or subject's `key_field` in braces |
| `per_subject.instruction` | string | No | How to use existing data in Phase 0 |
| `language_requirements.reference` | string | No | Path to language/outlet mapping |

### phases

Each phase (`phase_0` through `phase_3`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `actor` | string | Yes | `coordinator`, `haiku`, or `sonnet` |
| `dispatch` | string | No | Dispatch pattern (e.g., "1 agent per topic, parallel") |
| `task` | string | No | For coordinator phases — what to do |
| `output_path` | string | Yes | Path template for output files. Supports variable substitution |
| `agent_writes_own_output` | boolean | No | Default `true` — agents write their own files |
| `output_format` | string | No | For Phase 3 — `structured_yaml_or_json` |

---

## Change Type Taxonomy

Used by Phase 2 verification agents and Phase 3 synthesis to classify how each schema field relates to existing data.

| Change Type | Meaning | Phase 3 Action |
|-------------|---------|----------------|
| **CONFIRMED** | Existing value verified by current sources | Keep existing value as-is |
| **UPDATED** | Existing value superseded by newer or better evidence | Replace with new value |
| **NEW** | No prior value existed for this field | Add the new value |
| **REFUTED** | Existing value contradicted by evidence | Remove existing value; add annotation explaining contradiction |

**Guidelines:**
- A value is `CONFIRMED` even if the source is different — what matters is the value matches
- `UPDATED` requires the new value to be from a more recent or more authoritative source
- `REFUTED` is not "different" — it's "contradicted with evidence." A newer formation doesn't refute an older one; it updates it. A claim that a manager was sacked refutes the claim they're still in charge
- When in doubt between `UPDATED` and `REFUTED`, prefer `UPDATED` — it's less disruptive and the annotation captures the nuance

---

## "Run" Definition

A **run** is one invocation of Pipeline C within a session. It is the unit of work the coordinator proposes and the PM approves.

**What happens in a run:**
1. Coordinator reads the manifest and identifies pending/incomplete subjects
2. Coordinator proposes a batch based on the spec's `batching` config and session capacity
3. PM approves (or adjusts) the batch
4. Subjects in the batch are processed sequentially (all phases per subject before moving to the next)
5. Commit after each subject completes

**What defines the batch size:**
- The `batching` config in the spec provides per-tier defaults
- The coordinator may adjust based on session time remaining, subject complexity, or PM guidance
- The PM has final say on batch composition

**Cross-session continuity:**
- The manifest persists between sessions
- A new session reads the manifest, picks up where the last session left off
- Subjects completed in prior sessions are skipped (status: `complete`)
- Subjects partially completed resume from their last completed phase + 1

---

## Variable Substitution

Path templates in the spec support these variables:

| Variable | Expands To | Example |
|----------|-----------|---------|
| `{SUBJECT}` | Subject's key field value | `ENG`, `BRA`, `FRA` |
| `{TOPIC_ID}` | Topic's `id` field | `A`, `B`, `C` |
| `{TOPIC_NAME}` | Topic's `name` field (kebab-case) | `manager-formation`, `recent-match-lineups` |
| `{RUN_ID}` | Run identifier (`YYYY-MM-DD-HHhMM`) | `2026-03-18-14h30` |
| `{DATE}` | Current date (`YYYY-MM-DD`) | `2026-03-18` |

**Kebab-case conversion for `{TOPIC_NAME}`:** Lowercase, spaces → hyphens, strip special characters. "Manager & Formation" → `manager-formation`.

**Example path resolution:**
- Template: `tasks/research/{SUBJECT}/phase1-{TOPIC_ID}-{TOPIC_NAME}.md`
- Subject: `ENG`, Topic: `id: A, name: "Manager & Formation"`
- Resolved: `tasks/research/ENG/phase1-A-manager-formation.md`

---

## Minimal Example

A spec with 5 subjects, 2 topics, and 1 quality gate:

```yaml
subjects:
  source: data/entities.json
  key_field: id
  total: 5
  batching:
    standard: 2 per run

topics:
  - id: A
    name: Pricing & Plans
    search_domains:
      - Current pricing tiers and feature limits
      - Free tier availability and restrictions
      - Enterprise pricing model
    focus_questions:
      - What are the current pricing tiers?
      - Is there a free tier, and what are its limits?
      - How does enterprise pricing work?
    model_tier: haiku

  - id: B
    name: API & Integration
    search_domains:
      - REST API availability and documentation quality
      - SDK support (languages, maintenance status)
      - Rate limits and authentication methods
    focus_questions:
      - Is there a public API? How well documented?
      - What SDKs are officially supported?
      - What are the rate limits?
    model_tier: haiku

acceptance_criteria:
  per_topic:
    - At least 2 independent sources found
    - Publication date noted on every source
  output:
    - "pricing.tiers: minimum 1 entry"
    - "api.sdks: minimum 1 entry if API exists"

gates:
  after_phase_1:
    - name: official_source_check
      rule: >
        Each topic must include at least one source from the entity's
        official website or documentation. If only third-party sources
        found, re-dispatch with "[entity name] site:[domain]" search.

output_schema:
  key_fields:
    - path: pricing.tiers[]
      type: array of objects
      required_fields: [name, price, billing, features]
      optional_fields: [limits, notes]

    - path: pricing.freeTier
      type: boolean

    - path: pricing.enterprise
      type: string | null

    - path: api.available
      type: boolean

    - path: api.docsUrl
      type: string | null

    - path: api.sdks[]
      type: array of objects
      required_fields: [language, package, maintained]

    - path: api.rateLimits
      type: string | null

    - path: sources[]
      type: array of objects
      required_fields: [url, date, type]
      type_enum: [official, documentation, blog, comparison, forum]

known_context:
  per_subject:
    source_file: "data/entities/{SUBJECT}.json"
    instruction: >
      Read existing entity data before Phase 0. Identify fields that
      are missing or have sources older than 90 days.

phases:
  phase_0:
    actor: coordinator
    output_path: "tasks/research/{SUBJECT}/research-brief.md"

  phase_1:
    actor: haiku
    dispatch: "1 agent per topic, parallel"
    output_path: "tasks/research/{SUBJECT}/phase1-{TOPIC_ID}-{TOPIC_NAME}.md"
    agent_writes_own_output: true

  phase_2:
    actor: sonnet
    dispatch: "1 agent per topic, parallel"
    output_path: "tasks/research/{SUBJECT}/phase2-{TOPIC_ID}.md"
    agent_writes_own_output: true

  phase_3:
    actor: sonnet
    dispatch: "1 agent per subject"
    output_path: "tasks/research/{SUBJECT}/phase3-synthesis.md"
    agent_writes_own_output: true
    output_format: structured_yaml_or_json

manifest_path: tasks/research/manifest.json
scratch_cleanup: false
```
