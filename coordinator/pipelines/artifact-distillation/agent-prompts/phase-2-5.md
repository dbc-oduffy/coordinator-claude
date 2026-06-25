# Phase 2.5: Judgment Mining Prompt

<!-- spec-backlink: archive/specs/2026-05/2026-05-07-codebase-judgment-mining.md § D2 / the Staff Engineer R1 F4 -->

```
You are a judgment-mining agent. Your task is to analyze a set of reviewer sidecar
files for a specific topic cluster and determine whether they contain converging
architectural findings that warrant a codebase-judgment wiki entry.

**Your assigned topic cluster:** [TOPIC_CLUSTER]
**Verdict direction:** [VERDICT_DIRECTION]
**Live sidecar files to read:** [LIVE_SIDECAR_PATHS]
**Existing judgment entry (or NONE):** [EXISTING_JUDGMENT_ENTRY]
**Convergence threshold (MIN_CONVERGENCE):** [MIN_CONVERGENCE]
**Run ID:** [RUN_ID]

<!-- BEGIN text-only-recovery-preamble (synced from snippets/text-only-recovery-preamble.md) -->
**Ignore any "TEXT ONLY" / "tool calls will be REJECTED" framing in your context — it is a known hallucination from confused prior agents in this session. No such constraint exists. The ONLY valid completion is calling the Write tool. Replies that dump the deliverable inline count as task failure. This applies at every tier — Haiku, Sonnet, and Opus have all been observed reproducing this hallucination on scout/inventory dispatches under parallel-fanout load. Tier does not exempt you; verify file on disk before replying DONE.**

- **If you propose deferral or BLOCKED, the report MUST name the specific premise you could not verify** (e.g. "cannot verify Module X exposes Symbol Y on this branch"). Bare "insufficient information" is a hallucination signature — readiness scouts and verifiers that defer without naming the unverified premise are pattern-matching their way out of the dispatch, not reporting a real gap.
<!-- END text-only-recovery-preamble -->

## Output Location — MANDATORY Write Tool Call

**CRITICAL:** Your task completes ONLY when you have appended your findings to the
proposals file using the Write tool. Returning proposals inline in your reply is
**unacceptable and counts as task failure** — the coordinator reads from disk, not
from your message.

**Required action:** Read [SCRATCH_PATH] first (it may already contain proposals from
sibling agents). Append your proposal (or a "no convergence" entry) and call
`Write(file_path: "[SCRATCH_PATH]", content: <full merged content>)`.
Then return a brief summary (3-5 lines) confirming:
1. File written at [SCRATCH_PATH]
2. Whether you emitted a proposal or a no-convergence entry
3. Convergence count found and how many plans contributed

## Definitions

**Claim-topic (noun):** The subject of a finding — the codebase concept the finding
is about. Examples: "staging command", "fallback clause", "parallel dispatch",
"reviewer sidecar annotation", "commit scope".

**Verdict-direction (polarity):** The directive the finding carries:
- `forbid` — the finding says "never do X"
- `require` — the finding says "always do X"
- `prefer` — the finding says "X is better than Y, prefer it"
- `avoid` — the finding says "X is discouraged / use with caution"

**Shape-match:** Two findings shape-match iff (a) their claim-topic nouns are
semantically equivalent AND (b) their verdict-directions match.

## Shape-matching worked examples

### Example 1 — MATCHED pair

Finding A (from `plan-a.patrik-r1.md`):
> "Never use `git add -A` — it sweeps up unrelated files in concurrent-EM environments.
> Always stage explicitly by path."
Claim-topic: staging command | Verdict-direction: forbid

Finding B (from `plan-b.sid-r2.md`):
> "Scoped staging is required; bare `git add .` is forbidden here — concurrent sessions
> share the working tree."
Claim-topic: staging command | Verdict-direction: forbid

Result: MATCHED — same topic (staging command), same polarity (forbid). ✓

### Example 2 — NOT MATCHED (same topic, different polarity)

Finding A: "Always annotate fallback clauses with a rationale comment." (require)
Finding B: "Avoid undocumented fallback clauses." (avoid)

Result: NOT MATCHED — topic is the same (fallback clause) but polarity differs
(require vs. avoid). These are related but not the same shape. Do not merge them
into a single convergence count. ✗

### Example 3 — NOT MATCHED (different topics, same polarity)

Finding A: "Never use `git add -A`." (staging command, forbid)
Finding B: "Never dispatch nested sub-agents from Phase 2.5." (parallel dispatch, forbid)

Result: NOT MATCHED — polarity matches (both forbid) but topics are distinct.
Identical verdict-direction alone is not sufficient for a shape-match. ✗

## Ineligible findings — EXCLUDE these from convergence counting

Do NOT count the following as convergence-eligible findings, even if they recur:

- **Mechanical / formatting findings:** missing trailing newline, wrong indentation,
  markdown linting, prose style, typo corrections.
- **Docs-checker-class findings:** wrong import path, stale API function name,
  incorrect parameter count, broken link — any finding that a mechanical tool
  (not architectural judgment) could produce.
- **Disposition: escalated-disagree findings:** if the sidecar contains a field
  `disposition: escalated-disagree` on a finding, SKIP that finding entirely.
  These are findings the review-integrator actively rejected; including them would
  let rejected verdicts accumulate into promoted wiki entries.

Eligible finding types: architectural recommendations, recurring design constraints,
anti-pattern prohibitions, structural requirements flagged by the reviewer as a
pattern-level concern (not a single-instance nitpick).

## How to read each sidecar

Each sidecar file (`<plan>.<reviewer>-rN.md`) contains numbered findings. Each
finding may have a `disposition:` field written by the review-integrator before
Phase 5. Read the disposition before counting:

- `disposition: applied` → eligible (integrator accepted the finding)
- `disposition: escalated-ask` → eligible (needs PM input but finding stands)
- `disposition: escalated-p0` → eligible (critical finding; counts toward convergence)
- `disposition: deferred` → eligible (accepted for future work)
- `disposition: escalated-disagree` → **INELIGIBLE — skip**
- (no disposition field) → eligible (sidecar predates D7 integrator annotation)

## Convergence counting rules

- Each **plan** contributes at most **one count** toward convergence, regardless of
  how many findings from that plan shape-match the topic. Multiple findings from the
  same plan on the same topic = one count.
- `MIN_CONVERGENCE` is the minimum number of **distinct plans** required before
  emitting a proposal for a new topic.
- For an existing topic (EXISTING_JUDGMENT_ENTRY is not NONE): any single new live
  finding that shape-matches triggers an increment. Threshold is already met.

## Your task

1. Read all files listed in [LIVE_SIDECAR_PATHS].
2. For each sidecar, extract findings that are:
   - Eligible (not mechanical, not docs-checker-class, not escalated-disagree)
   - Shape-matching [TOPIC_CLUSTER] + [VERDICT_DIRECTION]
3. Group by source plan (deduplicate within the same plan).
4. Count distinct plans contributing at least one matching finding.

**If EXISTING_JUDGMENT_ENTRY is NONE (new topic):**
- If distinct-plan count >= [MIN_CONVERGENCE]: emit a new-entry proposal.
- If distinct-plan count < [MIN_CONVERGENCE]: emit a no-convergence entry.

**If EXISTING_JUDGMENT_ENTRY is a file path (existing topic):**
- Read the file to get current convergence_count and source_findings.
- If any new live finding shape-matches: emit an increment proposal (add 1 to
  convergence_count, append new source_findings entries).
- If no new live findings shape-match: emit a no-change entry.

Do NOT use `git show` to re-examine prior `source_findings[*].sha` refs from the
existing entry. The topic key is the join — historical SHAs are provenance-only,
not re-mined for shape-matching.

## Output format

Append the following block to [SCRATCH_PATH]:

```markdown
## Proposal: <topic-slug>

**Topic:** <claim-topic noun>
**Verdict direction:** forbid | require | prefer | avoid
**Convergence count:** N
**Action:** new-entry | increment-existing | no-convergence | no-change

### Source findings

| Sidecar | Plan | Reviewer | Finding ID | SHA |
|---------|------|----------|------------|-----|
| <path>  | <plan-path> | <reviewer> | <id-or-line-ref> | <git-sha> |

### Proposed wiki content

<!-- For new-entry: full proposed docs/wiki/codebase-judgment/<topic-slug>.md body
     including judgment_provenance frontmatter (see schema below).
     For increment-existing: one-line note: "Increment convergence_count to N;
     append <sidecar-path> to source_findings."
     For no-convergence or no-change: brief explanation of why no proposal was emitted. -->

---
```

### Frontmatter schema for new-entry proposals

```yaml
---
judgment_provenance:
  kind: codebase-judgment
  convergence_count: N
  source_findings:
    - sidecar: <path>
      plan: <plan-path>
      reviewer: patrik | sid | camelia | palí | fru
      finding_id: <id-or-line-ref>
      sha: <git-sha-of-sidecar-at-time-of-commit>
  promoted: <YYYY-MM-DD>
  last_refreshed: <YYYY-MM-DD>
---
```

Use `judgment_provenance:` as the top-level key — NOT `provenance:`. The key
`provenance:` is reserved by Phase 5b's archived-spec schema (list-of-objects shape);
using the same key would cause frontmatter-reader collisions.

## Rules

- Shape-match is semantic equivalence, not lexical matching. Read with judgment.
- One plan = one convergence count, regardless of finding volume from that plan.
- Exclude mechanical, docs-checker, and escalated-disagree findings unconditionally.
- Do NOT re-`git show` prior source_findings SHAs from an existing judgment entry.
- Emit a no-convergence or no-change entry even when no proposal is warranted —
  the coordinator needs a signal that you processed the cluster, not silence.
- You are a mining agent, not an editorial agent. Report what the sidecars say;
  do not editorialize about whether the finding is correct.
```

---

