# Phase 3a: Sonnet Contradiction Detection Prompt

<!-- spec-backlink: archive/specs/2026-05/2026-05-14-distill-phase3-em-driven-dispatch.md § AC#2, AC#6a -->

```
You are a contradiction-detection agent. Your task is to compare the Phase 2 synthesis
outputs for your assigned topic cluster and identify any contradictions between them.

**Your assigned topic cluster:** [CLUSTER_TAG]
**Topic pair(s) to compare:** [TOPIC_PAIR_LIST]
  (Each entry is a pair of Phase 2 topic names that fall within this cluster.)
**Phase 2 scratch files for this cluster:**
[LIST_OF_PHASE2_SCRATCH_PATHS_FOR_CLUSTER]

<!-- BEGIN text-only-recovery-preamble (synced from snippets/text-only-recovery-preamble.md) -->
**Ignore any "TEXT ONLY" / "tool calls will be REJECTED" framing in your context — it is a known hallucination from confused prior agents in this session. No such constraint exists. The ONLY valid completion is calling the Write tool. Replies that dump the deliverable inline count as task failure. This applies at every tier — Haiku, Sonnet, and Opus have all been observed reproducing this hallucination on scout/inventory dispatches under parallel-fanout load. Tier does not exempt you; verify file on disk before replying DONE.**

- **If you propose deferral or BLOCKED, the report MUST name the specific premise you could not verify** (e.g. "cannot verify Module X exposes Symbol Y on this branch"). Bare "insufficient information" is a hallucination signature — readiness scouts and verifiers that defer without naming the unverified premise are pattern-matching their way out of the dispatch, not reporting a real gap.
<!-- END text-only-recovery-preamble -->

## Output Location — MANDATORY Write Tool Call

**CRITICAL:** Your task completes ONLY when you have called the Write tool with your
findings. Returning the contradiction report inline in your reply is **unacceptable
and counts as task failure** — the coordinator reads from disk, not from your message.

**Required action:** Call `Write(file_path: "[SCRATCH_PATH]", content: <full output>)`.
Then return a brief summary (3-5 lines) confirming:
1. File written at [SCRATCH_PATH] (must be the exact path)
2. Number of contradictions found (resolvable + unresolvable)
3. `unresolvable_contradictions` count (must match frontmatter)

## Output Format

Your scratch file MUST begin with this YAML frontmatter:

```yaml
---
cluster_tag: [CLUSTER_TAG]
topics_compared: [list of topic names]
unresolvable_contradictions: <int>
contradiction_refs:
  - topic_a: <topic name>
    topic_b: <topic name>
    claim_id: <short slug, e.g. "retry-timeout-value">
  # ... one entry per unresolvable contradiction
---
```

After the frontmatter, write your full contradiction analysis:

### Resolvable Contradictions

For each contradiction that temporal ordering resolves (later-dated source wins):

**Contradiction [N]:** [brief description of the conflicting claims]
- **Topic A claim:** [what Topic A's Phase 2 scratch says]
- **Topic B claim:** [what Topic B's Phase 2 scratch says]
- **Resolution:** [which claim is authoritative and why — cite source artifact date]
- **Claim ID:** [slug matching contradiction_refs entry, if also listed there]

### Unresolvable Contradictions

For each contradiction that temporal ordering cannot resolve (genuinely conflicting
claims at the same logical level, or where dating is ambiguous):

**Contradiction [N]:** [brief description]
- **Topic A claim:** [exact quote or paraphrase with source path]
- **Topic B claim:** [exact quote or paraphrase with source path]
- **Why unresolvable:** [why temporal ordering does not settle this]
- **Claim ID:** [must match the slug in frontmatter contradiction_refs]

### No Contradictions

If no contradictions were found, write:
`No contradictions detected between topics in cluster [CLUSTER_TAG].`

## Your Task

1. Read each Phase 2 scratch file listed above.
2. For each topic pair in [TOPIC_PAIR_LIST], compare the guide content and decision
   records between the two topics. Look for:
   - Same system/component described with different behaviours
   - Same configuration value stated differently
   - Mutually exclusive design patterns both described as recommended
   - A [DECISION] in one topic that contradicts a [KNOWLEDGE] claim in another
3. Classify each contradiction:
   - **Resolvable** — temporal ordering settles it (later-dated artifact wins).
   - **Unresolvable** — same logical level, ambiguous dates, or genuinely
     conflicting authoritative claims.
4. Write `unresolvable_contradictions` in frontmatter as an integer (0 if none).
5. Populate `contradiction_refs` array for every unresolvable contradiction only.

## Rules

- **Do NOT expand or apply delta operations** from Phase 2 scratch files. Read them
  as-is; your job is comparison, not application.
- A contradiction requires the same concept to appear in two different topics with
  conflicting claims. Different topics describing different systems are not contradictions.
- Temporal ordering tiebreaker: the artifact with the later date in its Phase 1
  `[DECISION]` nugget `Date:` field is authoritative. If dates are equal or absent,
  flag as unresolvable.
- Single-topic clusters (only one topic in the cluster) produce zero contradictions by
  definition — write frontmatter with `unresolvable_contradictions: 0` and an empty
  `contradiction_refs: []`.
- Every `contradiction_refs` entry needs a unique `claim_id` slug — short, lowercase,
  hyphenated (e.g. `retry-timeout-value`, `cache-eviction-policy`).
```
