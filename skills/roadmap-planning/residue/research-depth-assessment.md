## Step 1.5.0 — Research-depth assessment (EM judgment, PM-authorized)

Before dispatching the default parallel Sonnet scouts in Step 1.5.1, the EM assesses whether the roadmap's ambition exceeds solo-scout depth. **Solo scouts are 5–10 minute web searches per topic — not state-of-the-art surveys.** When the roadmap aims at "best in class", "cutting edge", "novel architecture", or "matches/exceeds <named-frontier-system>", model memory alone is insufficient (knowledge cutoff + non-existence-of-public-state-of-the-art — the techniques may not be in training data at all).

**EM-side escalation criteria — if ANY hit, surface a deep-research recommendation to the PM:**

- Roadmap framing uses "best in class", "state of the art", "cutting edge", "novel", or names a frontier-tier reference system to match.
- ≥3 KEEP clusters touch the same novel domain (a single scout per cluster fragments the survey; one deep-research run cross-pollinates).
- A cluster's topic surface is research-active (LLM agent architectures, novel RAG patterns, frontier ML training infra, etc.) where the half-life of best-practice is <12 months.
- PM-stated ambition exceeds what current `docs/wiki/` + peer-repo wikis cover.

**EM recommendation format (to PM):**

> Phase 1.5 research-depth assessment. Default is parallel Sonnet scouts (5–10 min/topic). For this roadmap I recommend escalating to `/research` (deep-research-web pipeline) on the following topic surface: <one-line per topic + why>. Cost: one deep-research run (~30–60 min, Opus synthesizer). Benefit: cross-topic claim verification, adversarial peer review of findings, structured claims.json that stubs can cite. Authorize, decline, or pick a subset.

`/research` is PM-gated (per the skill description — "PM-GATED: ask first; never from subagent"). EM never auto-invokes it; the recommendation is the gate. PM may authorize (a) full deep-research replacing solo scouts, (b) deep-research on a subset + solo scouts on the rest, or (c) decline and stay with solo scouts.

**When authorized:** dispatch `/research` per its skill contract; output lands under `state/roadmap/<run-id>/research-corpus/deep-research/<topic-slug>/`. OVERVIEW.md citations in Step 1.5.2 point at the deep-research artifacts (claims.json + summary.md + executive-summary.md) instead of (or in addition to) solo-scout files. Update the Phase 1.5 exit gate's "research-corpus exists" check to accept either shape. **When declined or not triggered:** proceed to Step 1.5.1 with solo Sonnet scouts. This step forces the EM to surface the depth call so the PM authorizes it — the doctrinal fix is not "always deep-research" (too expensive for routine roadmaps).
