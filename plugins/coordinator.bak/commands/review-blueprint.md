---
description: LLM-powered Blueprint review with RAG grounding. Invokes manage_review.prepare (MCP), dispatches Sid with docs-checker pre-pass, validates schema, and escalates to Patrik for architecture-heavy BPs.
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "<bp-asset-path> [--diff <previous-bp-path>] [--architecture] [--no-architecture] [--no-rag] [--problems-only]"
---

# Review Blueprint — LLM-Powered Blueprint Review with RAG Grounding

Full review pipeline for Unreal Engine Blueprints:
- `manage_review.prepare` (or `prepare_diff`) from holodeck-control MCP
- Docs-checker pre-pass (RAG coverage verification)
- Sid (game-dev expert, Opus) with RAG-authoritative prompt
- FWarning-shaped JSON schema validation + one-retry corrective protocol
- Patrik escalation tripwire for architecture-heavy BPs (auto + `--architecture` flag)
- Contradiction detection between Sid and Patrik (escalated to PM, never silently merged)
- Dedup across reviewers (same nodeGuid + category → keep higher severity)
- Merged output JSON + markdown summary

## Instructions

Execute all phases in strict order. Fail fast on any phase that cannot proceed.

---

### Argument Parsing

Parse `$ARGUMENTS` at the start:

| Flag | Variable | Default |
|---|---|---|
| `<bp-asset-path>` (positional, required) | `bp_path` | — |
| `--diff <previous-bp-path>` | `payload_mode = "diff"`, `previous_bp_path` | `payload_mode = "full"` |
| `--architecture` | `force_architecture = true` | `false` |
| `--no-architecture` | `skip_architecture = true` | `false` |
| `--no-rag` | `no_rag = true` | `false` (internal A/B test flag) |
| `--problems-only` | `problems_only = true` | `false` |

Validate `bp_path` is non-empty and plausible (starts with `/Game/`). If invalid:
```
ERROR: Invalid BP asset path "<path>". Expected format: /Game/Path/To/BP_Name
```
Stop.

If both `--architecture` and `--no-architecture` are present: `skip_architecture` wins (safety default).

---

### Phase 1 — Obtain payload

**If `payload_mode == "full"`:** Call holodeck-control `manage_review`:
```json
{ "action": "prepare", "target": "blueprint", "asset_path": "<bp_path>" }
```

**If `payload_mode == "diff"`:** Call holodeck-control `manage_review`:
```json
{ "action": "prepare_diff", "current_path": "<bp_path>", "previous_path": "<previous_bp_path>" }
```

On error or empty payload:
```
ERROR: manage_review.prepare failed for <bp_path>.
Ensure Phase 1 (manage_review tool) is operational and the editor is running with ClaudeUnrealHolodeck plugin.
```
Stop.

Store result as `payload_json`. Write to `tasks/review-blueprint/{timestamp}-payload.json`.

Create `tasks/review-blueprint/` and `tasks/review-findings/` directories if they do not exist.

---

### Phase 1.1 — Chunking decision (large BPs)

**Skip if `payload_json.payload_size_bytes ≤ 30000` AND `payload_json.size_warnings` is empty.** Set `chunked = false` and proceed to Phase 1.5.

Otherwise, the BP exceeds the payload cap and must be chunked for per-graph Sid dispatch. Execute:

1. **Parse graph bodies** from `payload_json.payload_text`:
   - Extract the `=== HEADER ===` through end of `=== RULES-PASS ===` as `shared_prefix`.
   - Extract the `=== COMMENTS ===` section as `comments_block`.
   - Split the `=== GRAPH BODIES ===` section on `--- Graph: <name> ---` markers. Each split produces a `{name, body_text, body_bytes}` entry. Preserve the marker line in each graph's body.

2. **Measure sizes:**
   - `shared_prefix_bytes = len(shared_prefix.encode('utf-8'))`
   - For each graph: `graph_bytes = len(body_text.encode('utf-8'))`

3. **Greedy bin-pack** (per aggregation-spec.md §1):
   - `cap_bytes = 30000`
   - Iterate graphs in payload order (UbergraphPages first = EventGraph, then FunctionGraphs, then any interface/delegate graphs).
   - For each graph: if `current_chunk_bytes + graph_bytes > cap_bytes` AND current chunk is non-empty → flush chunk. Add graph to current chunk.
   - Flush final chunk.
   - If a single graph exceeds `(cap_bytes - shared_prefix_bytes)`, it becomes a solo chunk (not an error).

4. **Compose sub-payloads:** For each chunk (index `i`, total `N`):
   ```
   {shared_prefix}

   === GRAPH BODIES (chunk {i+1}/{N}) ===
   {concatenated graph bodies for this chunk}

   {comments_block — filtered to only comments from graphs in this chunk}

   === RAG CONTEXT (EMPTY — Phase 1) ===
   (empty — populated in Phase 1.5)

   === META ===
   {original META content}
   chunk_index: {i}
   total_chunks: {N}
   chunk_graphs: {comma-separated graph names in this chunk}
   chunk_id: {sha256(bp_path + ":" + first_graph_name_in_chunk)[:16]}
   ```

   Also filter the `=== RULES-PASS ===` section within each chunk's `shared_prefix`: keep only warnings whose `GraphName` matches a graph in this chunk. Warnings with empty `GraphName` (BP-level) go in every chunk.

5. **Set chunking state:**
   - `chunked = true`
   - `chunk_payloads = [...]` (array of sub-payload text strings)
   - `chunk_metadata = [{chunk_index, total_chunks, graphs: [...], chunk_id}, ...]`
   - `total_chunks = N`

6. **Report to terminal:**
   ```
   Chunked: {N} chunks from {graph_count} graphs ({payload_size_bytes} bytes → ~{avg_chunk_size} bytes/chunk).
   Chunk layout: {for each chunk: "C{i}: [{graph_names}]"}
   ```

**All subsequent phases operate on `chunk_payloads` when `chunked = true`.** Phase 1.5 (RAG) enriches each chunk identically (same RAG block spliced into each). Phase 4 dispatches Sid per chunk. Phase 4.5 aggregates.

---

### Phase 1.5 — Extant-doc reuse + RAG fetch (domain classifier)

**Skip entirely if `--no-rag`.** In that case: replace the `=== RAG CONTEXT (EMPTY — Phase 1) ===` section in `payload_json.payload_text` with `=== RAG CONTEXT (EMPTY — --no-rag flag) ===` and proceed to Phase 2.

Otherwise, execute in order:

**Step A — Check for extant Blueprint Inspector documentation.**

The `ue-blueprint-inspector` agent may have previously produced per-BP structured markdown. Reuse it if fresh.

1. Glob `data/blueprint_extractions/*/manifest.jsonl`. For each manifest file, scan for an entry whose `path` field equals `bp_path` (exact match).
2. If a match is found:
   - Note `manifest_dir = <dirname of manifest.jsonl>` and `grouped_file = <manifest entry's "file" field>`.
   - Read `{manifest_dir}/{grouped_file}` and locate the section for this BP. Headings observed in practice: `# Blueprint: {bp_name}` (ue-blueprint-inspector format), `## {bp_name}`, or `### {bp_name}`. Match any of these. The section runs until the next heading at the same or higher level, or end-of-file.
   - **Known data defect:** ue-blueprint-inspector extractions may report `Functions: None` and `Events: None` even when the BP has them (fingerprint `func_count` is unreliable repo-wide). Use the extraction for narrative description, parent class, and component tree — but trust the live payload for the inventory. Do not carry forward "Functions: None" / "Events: None" lines from the extraction into `prior_analysis_block` if the live payload contradicts them; strip those lines.
   - Extract the manifest entry's `fingerprint` object: `{var_count, func_count, component_count}`.
3. **Gut-check alignment** against the live payload:
   - `live_var_count` = count of `Variables:` lines in payload_json.payload_text inventory section.
   - `live_component_count` = count of `Components (SCS):` lines.
   - `live_func_count` = count of `Functions:` lines.
   - Compute alignment score: if **abs(manifest.var_count − live_var_count) ≤ max(3, 0.2 × live_var_count)** AND **abs(manifest.component_count − live_component_count) ≤ max(1, 0.25 × live_component_count)**, mark `extant_aligned = true`. Otherwise `extant_aligned = false`.
   - The function-count tolerance is looser (extraction may count differently) — treat as informational only.
4. If `extant_aligned == true`: stash the extracted BP section as `prior_analysis_block`. Log to terminal: `Extant extraction reused: {manifest_dir}/{grouped_file} (fingerprint aligned — var_count {manifest} vs {live}, components {manifest} vs {live})`.
5. If `extant_aligned == false`: log `Extant extraction stale or misaligned — falling back to RAG-only context. (manifest: {fingerprint}, live: {counts})`. Do not use the extracted doc.
6. If no manifest match: log `No extant extraction for {bp_path}. RAG-only context.`

**Step B — Invoke rag-fetch skill.**

Follow the procedure in `~/.claude/plugins/coordinator-claude/coordinator/skills/review-blueprint/rag-fetch.md` verbatim:

1. Extract `parent_class` from payload header.
2. Run the three-tier domain classifier (IAbilitySystemInterface check → path-prefix table → parent-class rule table → Haiku fallback). Emit `domain_tags[]`.
3. Call `mcp__holodeck-docs__ue_mcp_status` once; parse `RAG index version` for `rag_index_version`.
4. Fetch RAG:
   - 1× `mcp__holodeck-docs__ue_expert_examples` with `query = "{primary_domain_tag} Blueprint pattern {top_function_name}"`, `source="all"`, `max_results=5`.
   - N× `mcp__holodeck-docs__quick_ue_lookup` for each distinct class in `[parent_class_name] + implemented_interfaces`, skipping `UObject`/`AActor`/`None`, deduped, capped at 3 calls.
5. Assemble the `rag_context_block` per rag-fetch.md Step 4.3.

**Step C — Splice into payload.**

Replace the `=== RAG CONTEXT (EMPTY — Phase 1) ===` section in `payload_json.payload_text` with:

```
=== RAG CONTEXT BLOCK ===
{rag_context_block}
```

If `prior_analysis_block` exists (Step A succeeded), insert BEFORE the RAG context block:

```
=== PRIOR ANALYSIS (extracted by ue-blueprint-inspector — project-specific context) ===
Source: {manifest_dir}/{grouped_file}
Alignment: verified (var_count {manifest} vs {live}, component_count {manifest} vs {live})

{prior_analysis_block}

=== RAG CONTEXT BLOCK ===
```

Also update the `=== META ===` section:
- `rag_index_version: phase1-rag-disabled` → `rag_index_version: {rag_index_version}`
- `classifier_version: phase1-classifier-disabled` → `classifier_version: 1.0`
- `domain_tags: (empty — populated in Phase 2)` → `domain_tags: {domain_tags joined by ", "}`
- If prior analysis used, append a line: `prior_analysis_source: {manifest_dir}/{grouped_file}`

Write the enriched payload back to `tasks/review-blueprint/{timestamp}-payload.json` (overwrite).

**Report to terminal:**
```
RAG fetch complete. Domain tags: {domain_tags}. Extant extraction: {reused|stale|absent}. RAG index version: {version}.
```

---

### Phase 2 — Tripwire evaluation

Read from payload:
- `parent_class_engine_base` — from payload header `parent_class:` field, walk to first `/Script/`-prefixed engine class
- `implemented_interfaces[]` — from payload inventory section  
- `functions[]` — from payload inventory section

```
FRAMEWORK_BASE_LIST = [
  "AGameModeBase", "AGameMode", "APlayerController",
  "UGameInstance", "AGameStateBase", "APlayerState"
]

tripwire_fired = false
if skip_architecture → tripwire_fired = false (skip remaining checks)
else:
  if force_architecture → tripwire_fired = true
  if parent_class_engine_base ∈ FRAMEWORK_BASE_LIST → tripwire_fired = true
  if count(implemented_interfaces) ≥ 2 → tripwire_fired = true
  if count(functions) > 20 → tripwire_fired = true
```

Report to terminal: `Tripwire: {fired|not fired}. Reason: {list of fired conditions}.`

---

### Phase 3 — Docs-checker pre-pass

Dispatch `docs-checker` agent with:
```
DOCS-CHECKER BRIEF — Blueprint Review Pre-pass
Mode: Coverage check only. Do NOT re-verify APIs already in the RAG block.
RAG block content: [paste RAG block section from payload_json.payload_text]
Instruction: Call mcp__holodeck-docs__ue_mcp_status once to verify index health.
Then identify UE class/method names in the inventory section NOT in the RAG block.
For each (up to 5): call quick_ue_lookup to verify existence.
Return: (a) index health, (b) verified classes not in RAG block, (c) NOT_FOUND classes.
```

Save docs-checker report to `tasks/review-findings/{timestamp}-docs-checker-bp.md`.

If docs-checker is unavailable: skip Phase 3, note "docs-checker unavailable — skipped" in summary, continue.

---

### Phase 4 — Dispatch Sid (Blueprint Review Mode)

**If `chunked == false` (single-chunk path):**

Compose Sid dispatch brief:
1. **Read** `plugin/game-dev/prompts/blueprint-review-mode.md` — prepend verbatim.
2. If `payload_mode == "diff"`: **Read** `plugin/game-dev/prompts/review-blueprint-diff.md` — append after the base prompt.
3. Append full `payload_json.payload_text` (with or without RAG block per `--no-rag`).
4. Append: `API COVERAGE REPORT: tasks/review-findings/{timestamp}-docs-checker-bp.md — trust VERIFIED claims.`
5. If `tripwire_fired == true`: append `ARCHITECTURE NOTE: Patrik will review architecture-tagged findings after you. Surface escalation points explicitly with category "Architecture".`
6. If `problems_only`: append `--problems-only: Return only findings that require action. Omit praise, suggestions without clear action, and informational observations.`

Dispatch as:
- `subagent_type: "staff-game-dev"`, `model: "opus"`

Save Sid's raw output to `tasks/review-findings/{timestamp}-sid-blueprint-raw.txt`.

**If `chunked == true` (multi-chunk path):**

For each chunk `i` in `chunk_payloads` (sequentially, NOT in parallel — each dispatch must complete before the next starts):

1. **Read** `plugin/game-dev/prompts/blueprint-review-mode.md` — prepend verbatim.
2. Append the chunk's enriched sub-payload text (from Phase 1.5 enrichment).
3. Append: `API COVERAGE REPORT: tasks/review-findings/{timestamp}-docs-checker-bp.md — trust VERIFIED claims.`
4. Append chunk-specific context:
   ```
   CHUNKING CONTEXT: This is chunk {i+1} of {total_chunks}. You are reviewing graphs: [{chunk's graph names}].
   Other graphs in this BP (not in this chunk): [{graphs NOT in this chunk}].
   The INVENTORY section is the FULL BP inventory — use it for cross-graph reasoning.
   If you identify a finding that references state outside your chunk's graphs, tag it with "scope": "cross-graph" in the finding JSON.
   ```
5. If `tripwire_fired == true`: append architecture note.
6. If `problems_only`: append problems-only instruction.

Dispatch as: `subagent_type: "staff-game-dev"`, `model: "opus"`

Save each chunk's raw output to `tasks/review-findings/{timestamp}-sid-chunk-{i}-raw.txt`.

Run schema validation on each chunk's findings (same V-1/V-2/V-3 rules). Write validated per-chunk findings to `tasks/review-findings/{timestamp}-sid-chunk-{i}.json`.

**After all chunks complete → proceed to Phase 4.5.**

---

### Phase 4.5 — Chunk aggregation (conditional on `chunked == true`)

**Skip if `chunked == false`.** The single-chunk findings ARE the Sid findings — proceed to Phase 5.

Dispatch `review-chunk-aggregator` agent (Sonnet) via Agent tool:
```
CHUNK AGGREGATION BRIEF

BP: <bp_path>
Total chunks: <total_chunks>

Per-chunk finding files:
<for each chunk: "Chunk {i}: tasks/review-findings/{timestamp}-sid-chunk-{i}.json — graphs: [{graph names}]">

Chunk metadata:
<JSON array of chunk_metadata from Phase 1.1>

Full inventory section:
<paste the INVENTORY section from the original (pre-chunked) payload>

Output path: tasks/review-findings/{timestamp}-sid-blueprint-aggregated.json

Read each per-chunk finding file. Execute the aggregation pipeline per your instructions:
1. Flatten all findings → all_findings[]
2. Tag cross-graph scope
3. Detect contradictions
4. Dedup by (nodeGuid, category)
5. Cross-graph reconciliation using inventory

Write the aggregated result to the output path.
```

Wait for completion. Read the aggregated file. Use it as the Sid findings for all subsequent phases:
- Copy to `tasks/review-findings/{timestamp}-sid-blueprint.json` (the canonical Sid output path).
- Log aggregation stats to terminal:
  ```
  Aggregation complete: {total_input} findings → {after_dedup} merged, {contradictions} contradictions, {cross_graph_unresolved} cross-graph unresolved.
  ```

---

**Schema validation (for both single-chunk and multi-chunk paths):**

Parse Sid's output. Extract the JSON block.

For each finding, check:
- **V-1 (severity):** `severity` ∈ `{Red, Orange, Yellow, Green}`
- **V-2 (category):** `category` ∈ `{Performance, Architecture, Correctness, Style, Networking, GAS, Anim, UMG}`
- **V-3 (rag_citation non-empty):** `rag_citation` is a non-empty array AND every element matches `^(quick_ue_lookup|ue_expert_examples):[^:]+:.+$`

If violations exist: compose corrective prompt, send Sid a follow-up (single retry). After retry:
- N ≤ 2 violations remaining: drop silently, log drop count in summary
- N > 2 violations remaining: emit WARNING to terminal, proceed with valid set
- All findings invalid (zero valid after retry):
  ```
  ESCALATION: Review on <bp_path> returned zero valid findings after retry — total review failure. PM must decide whether to proceed manually.
  ```
  Stop.

Write validated findings to `tasks/review-findings/{timestamp}-sid-blueprint.json`.

---

### Phase 5 — Review-integrator pass 1 (Sid findings)

Dispatch `review-integrator` agent (Sonnet) via Agent tool:
```
Apply Sid's Blueprint review findings to the review output document.
Findings JSON: tasks/review-findings/{timestamp}-sid-blueprint.json
Artifact: tasks/review-blueprint/{timestamp}-payload.json
Reviewer: sid
IMPORTANT: This is a Blueprint review. Do NOT attempt to edit any .uasset, .cpp, or .h file.
Apply findings as annotations to the review output document only (the payload JSON and any markdown summary).
```

Wait for integrator completion. Log any `ESCALATION:` blocks in the integrator report.

---

### Phase 6 — Patrik dispatch (conditional on tripwire)

**Skip this phase if `tripwire_fired == false`.** Continue to Phase 8.

Dispatch `staff-eng` (Patrik, Opus) via Agent tool:
```
BLUEPRINT ARCHITECTURE REVIEW

BP: <bp_path>
Payload mode: <full|diff>
Domain tags: <from payload header>

Sid's findings: tasks/review-findings/{timestamp}-sid-blueprint.json
Read Sid's findings before starting. Your pass covers architecture, correctness, and code quality.

SCOPE:
- Do NOT re-flag findings already in Sid's list unless you disagree.
- If you disagree with a Sid finding, state it explicitly:
  "Sid finding #N says [X]; I recommend [Y] instead — reason: [reason]."
  Use category: "Architecture" for such disagreements.
- Focus on architectural risks, framework misuse, system design issues.

PAYLOAD:
[paste payload_json.payload_text — same as Sid received, full or diff]

OUTPUT: Return ReviewOutput JSON (same FWarning-shaped schema) + narrative.
<if problems_only>: Return only findings that require action.
```

Save Patrik's raw output to `tasks/review-findings/{timestamp}-patrik-blueprint-raw.txt`.
Parse Patrik's ReviewOutput JSON.
Write to `tasks/review-findings/{timestamp}-patrik-blueprint.json`.

---

### Phase 7 — Review-integrator pass 2 (Patrik findings, conditional)

**Skip if `tripwire_fired == false`.**

Dispatch `review-integrator` (Sonnet) via Agent tool:
```
Apply Patrik's Blueprint review findings to the review output document.
Patrik's JSON: tasks/review-findings/{timestamp}-patrik-blueprint.json
Artifact: tasks/review-blueprint/{timestamp}-payload.json (post-Sid integration)
Reviewer: patrik
IMPORTANT: This is a Blueprint review. Do NOT edit .uasset, .cpp, or .h files.
Annotate review output document only.
```

Wait for integrator completion. Log any `ESCALATION:` blocks.

---

### Phase 8 — Merge, dedup, contradiction detection

Load `{timestamp}-sid-blueprint.json` (always) and `{timestamp}-patrik-blueprint.json` (if Patrik ran).

**DEDUP (across reviewers only):**

For each pair (A from Sid, B from Patrik) where:
- `A.location.nodeGuid == B.location.nodeGuid` (exact match)
- `A.category == B.category` (case-insensitive)

→ These are duplicates. Keep higher severity (Red > Orange > Yellow > Green). If equal severity, keep Sid's. Drop the other into `deduplicated_findings[]` with annotation: `"Deduplicated: kept {reviewer} at {severity}; dropped {other_reviewer} at {other_severity}."`

**CONTRADICTION DETECTION:**

For each pair (A from Sid, B from Patrik) where:
- `A.location.nodeGuid == B.location.nodeGuid` (exact match)
- `A.category == "Architecture"` AND `B.category == "Architecture"`
- `A.suggestion` contains an add/use/prefer verb AND `B.suggestion` contains a remove/avoid/replace verb for the same subject (or vice versa) — use the same subject noun to confirm they are about the same element

→ Flag as contradiction. Add both findings to `contradictions[]` (NOT `findings[]`). Neither is applied.

**Write merged output** to `tasks/review-findings/{timestamp}-merged-blueprint.json`:
```json
{
  "bp_path": "<bp_path>",
  "payload_mode": "full|diff",
  "tripwire_fired": true|false,
  "tripwire_reasons": [...],
  "findings": [...],
  "contradictions": [...],
  "deduplicated_findings": [...],
  "sid_raw": "tasks/review-findings/{timestamp}-sid-blueprint.json",
  "patrik_raw": "tasks/review-findings/{timestamp}-patrik-blueprint.json"
}
```

---

### Phase 9 — Summary and PM escalation output

Write human-readable summary to `tasks/review-findings/{timestamp}-review-blueprint-summary.md`:

```markdown
# Blueprint Review: <BP name>
**Date:** <YYYY-MM-DD>
**BP path:** <full asset path>
**Payload mode:** full | diff
**Domain tags:** <from payload>
**Tripwire:** fired | not fired (<reasons>)

## Findings Summary
| Severity | Count |
|---|---|
| Red | N |
| Orange | N |
| Yellow | N |
| Green | N |

## Findings
[rendered finding list]

## Deduplication
N findings deduplicated (see merged JSON `deduplicated_findings` array).

## Docs-Checker Report
Coverage: <index health>
Report: tasks/review-findings/{timestamp}-docs-checker-bp.md

## Notes
[drop count warnings, integrator escalations]

## Rules-Pass Findings Not Re-Flagged by Sid (Implicitly Endorsed, Not Actively Contradicted)

> Sid reviewed these findings from the automated rules-pass and did not re-flag them. This means Sid did not contradict them — treat the list as implicit endorsement. Most entries are `unused_variables`; expand only the ones that look architecturally interesting (e.g., variables with `[Net]` tags or names suggesting gameplay state).

**Matching algorithm** (applied after Phase 8 merge, before writing this section):

1. **Parse rules-pass findings** from `payload_json.payload_text` section `=== RULES-PASS ===`.
   Each line has format: `[<Severity>/<Category>] <rule_id>: <body>`
   Extract tuples `(rule_id, target_name)` where `target_name` is:
   - The name inside `Variable '<X>'` if the body matches that pattern, OR
   - The name inside `Graph '<X>'` if the body matches that pattern, OR
   - The first single-quoted identifier in the body otherwise.
   Pseudo-code:
   ```
   for line in rules_pass_lines:
       m = re.match(r'\[(\w+)/(\w+)\]\s+(\w+):\s+(.*)', line)
       if not m: continue
       severity, category, rule_id, body = m.groups()
       var_m = re.search(r"Variable '([^']+)'", body)
       graph_m = re.search(r"Graph '([^']+)'", body)
       any_m = re.search(r"'([^']+)'", body)
       target_name = (var_m or graph_m or any_m).group(1) if (var_m or graph_m or any_m) else ""
       rules_pass_tuples.append((rule_id, target_name, severity, category, body))
   ```

2. **Extract Sid finding targets** from `{timestamp}-sid-blueprint.json`.
   For each Sid finding, derive a `sid_target` string = `finding.message + " " + finding.location.get("nodeGuid", "")`.

3. **Match (AND over both signals)**: a rules-pass tuple `(rule_id, target_name)` is "re-flagged" iff there exists at least one Sid finding where:
   - `rule_id` appears as a substring of `finding.rule_name` (case-insensitive), AND
   - `target_name` is non-empty AND appears as a substring of `sid_target` (case-insensitive).
   If either condition fails (including empty `target_name`), the tuple is **not** re-flagged.

4. **Non-re-flagged tuples → this section.** Group by `rule_id`. For each group emit a sub-table:

```markdown
### <rule_id> (<N> findings)
| Severity | Target | Detail |
|---|---|---|
| <severity> | <target_name> | <body (truncated to 120 chars if needed)> |
...
```

Cap each group table at 30 rows. If the group has more, append: `… and <M> more. See full rules-pass in payload.`

If the entire endorsed list is empty (all rules-pass findings were re-flagged by Sid), omit this section entirely.
```

**Terminal output:**

```
Review complete. {N} findings. {M} deduplicated. {K} contradictions.
Output: tasks/review-findings/{timestamp}-merged-blueprint.json
```

If `contradictions[]` is non-empty, also print:
```
ESCALATION REQUIRED — {K} contradiction(s) between Sid and Patrik require PM decision before applying:

[For each contradiction:]
CONTRADICTION: nodeGuid={guid}
  Sid finding #{idx}: <message> — suggests: <suggestion>
  Patrik finding #{idx}: <message> — suggests: <suggestion>
  Action: PM decision required. Neither finding applied to merged output.
```

If integrator escalations were logged in Phase 5 or Phase 7, print them.

---

## Error handling

| Condition | Action |
|---|---|
| Invalid/empty BP path | Fail fast with ERROR |
| manage_review.prepare fails | Fail fast with ERROR + troubleshooting hint |
| Sid dispatch fails | Fail fast with ERROR |
| All Sid findings invalid after retry | ESCALATION + stop |
| Patrik dispatch fails (tripwire fired) | Log warning, proceed with Sid-only output; note in summary |
| JSON parse failure on reviewer output | Treat all findings as V-3 violations; one corrective retry |
| docs-checker unavailable | Skip Phase 3; note in summary |
| Chunk Sid dispatch fails (one chunk) | Log warning for that chunk, continue with remaining chunks; note in summary |
| All chunk Sid dispatches fail | ESCALATION + stop (same as single-chunk total failure) |
| Aggregator fails | Fall back to manual flatten of per-chunk findings (skip dedup/contradiction); note in summary |
