# Tier-Usage Telemetry — Final Report

> Generated 2026-05-18 immediately before ripping the telemetry hook out of the coordinator plugin.
> Source: aggregated from `~/.claude/projects/*/tier-usage/*.json` across all repos on this host.

## Why this report exists

The tier-usage telemetry shipped with an explicit promise (`tiered-context-loading.md` §8): if the counters showed `tier4 >> tier2+tier3` or persistent missing-rationale counts, the doctrine was not being followed and enforcement would be revised. ~3 weeks of data accumulated; nobody opened it. This report cashes the promise once, before the substrate is removed, so the design either gets ratified, refuted, or has its lessons written down.

## Totals

- Sessions analyzed: **995** (1 unreadable, 0 empty/zero-count)
- Tier 1 (curated narrative reads — wiki/atlas/decisions): **1331**
- Tier 2 (structured query — RAG / query-records): **255**
- Tier 3 (targeted grep/glob/read): **74140**
- Tier 4 (`Agent` dispatches): **4067** total — **1093** investigation-scope (`{Explore, general-purpose, deep-research:*, feature-dev:code-explorer}`), **2974** other coordinator/persona/domain agents
- Tier-4 dispatches missing rationale preamble: **3597** of 4067 (88.4%)
- Skip-to-scout ratio (all t4 / (t2+t3)): **0.055**
- Skip-to-scout ratio (investigation-only t4 / (t2+t3)): **0.015** — doctrine target is ≪ 1

## By month (data window was ~2026-05-01 to 2026-05-18 — single calendar month, so this row equals Totals)

| Month | Sessions | t1 | t2 | t3 | t4 | missing-rationale |
|------|---------:|---:|---:|---:|---:|---:|
| 2026-05 | 995 | 1331 | 255 | 74140 | 4067 | 3597 |

## Top subagent_types dispatched (tier 4)

| subagent_type | dispatches | doctrine-investigation? |
|---|---:|:---:|
| `coordinator:executor` | 1223 | no |
| `general-purpose` | 987 | yes |
| `coordinator:review-integrator` | 562 | no |
| `coordinator:staff-eng` | 423 | no |
| `coordinator:prior-art-checker` | 204 | no |
| `Explore` | 89 | yes |
| `coordinator:docs-checker` | 88 | no |
| `coordinator:enricher` | 84 | no |
| `coordinator:code-reviewer` | 51 | no |
| `game-dev:staff-game-dev` | 44 | no |
| `claude` | 43 | no |
| `feature-dev:code-reviewer` | 37 | no |
| `coordinator:doc-link-checker` | 35 | no |
| `data-science:staff-data-sci` | 35 | no |
| `coordinator:eng-director` | 29 | no |
| `coordinator:test-evidence-parser` | 20 | no |
| `coordinator:plan-coverage-checker` | 18 | no |
| `` | 14 | no |
| `holodeck-docs:ue-docs-researcher` | 13 | no |
| `game-dev:schema-migration-auditor` | 11 | no |

## By project (top 20 by session count)

| Project slug | Sessions | t1 | t2 | t3 | t4 | miss-rat |
|---|---:|---:|---:|---:|---:|---:|
| `X---project-rag` | 297 | 390 | 51 | 30737 | 1517 | 1394 |
| `X---claude-unreal-holodeck` | 255 | 315 | 59 | 19988 | 1173 | 1003 |
| `X---project-rag-ue-addon` | 194 | 293 | 64 | 16280 | 888 | 758 |
| `C---Users--oduffy---claude` | 147 | 288 | 60 | 5650 | 403 | 359 |
| `X---project-rag-ue-addon---claude--worktrees` | 26 | 0 | 0 | 181 | 1 | 1 |
| `X---DroneSim` | 18 | 1 | 5 | 190 | 6 | 6 |
| `X---project-rag---claude--worktrees` | 15 | 6 | 11 | 90 | 1 | 1 |
| `X---claude-unreal-holodeck--control--server` | 11 | 0 | 0 | 214 | 12 | 12 |
| `--Users--oduffy--.claude` | 7 | 3 | 5 | 91 | 4 | 3 |
| `C---Users--oduffy---claude--plugins--coordinator-claude--coordinator` | 4 | 2 | 0 | 157 | 1 | 0 |
| `X--` | 3 | 2 | 0 | 25 | 0 | 0 |
| `X---coordinator-claude` | 2 | 2 | 0 | 6 | 0 | 0 |
| `C---Users--oduffy---claude--tasks--handoffs` | 1 | 0 | 0 | 7 | 0 | 0 |
| `C---Users--oduffy---claude--tasks--learn-lessons-2026-05-17` | 1 | 22 | 0 | 83 | 3 | 3 |
| `C--Users-oduffy--claude` | 1 | 0 | 0 | 1 | 0 | 0 |
| `tmp` | 1 | 0 | 0 | 2 | 0 | 0 |
| `tmp-smoketest` | 1 | 1 | 0 | 0 | 2 | 1 |
| `X---claude-unreal-holodeck--tasks--gpu-sidecar-hardening--stubs` | 1 | 0 | 0 | 56 | 1 | 1 |
| `X---claude-unreal-holodeck--tasks--handoffs` | 1 | 0 | 0 | 4 | 0 | 0 |
| `X---claude-unreal-holodeck--tasks--scratch--artifact-distillation--2026-05-14-scoped-handoffs-shipped-specs` | 1 | 0 | 0 | 121 | 8 | 8 |

## Interpretation

Compare against the design hypothesis from `tiered-context-loading.md` §8:

> If after several sessions the counters show tier4 >> tier2+tier3 or consistent missing-rationale counts, the doctrine is not being followed — revise the enforcement, not the doctrine.

### Three confounds that make the raw ratio misleading

1. **Tier-1 undercounting is structural.** The hook classifies a `Read` as tier-1 only if the path matches a wiki/atlas/decisions glob. Boot-time tier-0 loads (orientation_cache, lessons, MEMORY.md) and most explicit-path Reads register as tier-3. So a t1 << t3 reading is mostly a measurement artifact, not a doctrine violation.
2. **Tier-2 is RAG-conditional.** Repos without project-RAG installed (most of them, most of the time) have t2 = 0 by construction. Reading t2=0 as "skipped tier 2" is wrong when tier 2 was unavailable.
3. **The t4 counter conflates two populations.** The doctrine's tier-4 enumeration is `{Explore, general-purpose, deep-research:*, feature-dev:code-explorer}` — the *investigation* scouts. But the hook counts every `Agent` dispatch, so `coordinator:executor`, `coordinator:review-integrator`, `coordinator:staff-eng`, persona reviewers, and domain authors all land in t4. These aren't skip-to-scout cases — they're the deterministic pipeline doing its job. The split above (investigation-only vs other) is the meaningful read.

### What the data does and doesn't say

- The investigation-scope skip-to-scout ratio of **0.015** is the closest thing to a doctrine-aligned signal. Read it as: across 995 sessions, 1093 dispatches went to genuine investigation scouts, against 74395 tier-2+tier-3 lookups they could have escalated from. That is not a doctrine-violation pattern.
- The **88.4%** missing-rationale rate is dominated by `coordinator:executor` and other non-investigation agents that the rationale rule doesn't actually apply to. The hook regex didn't scope to the doctrine's tier-4 subagent_type set, so this number is mismeasurement — not a finding about EM behavior.
- We learned little about whether the doctrine is followed, but we did learn that the telemetry as built could not have answered the question. A regex-on-prompt enforcement check applied to the wrong agent population produces compliance theater in both directions.

## Lessons worth keeping after the telemetry is removed

1. **Ship-and-watch instrumentation needs a calendared review or it's not real.** This data sat unread for the entire window the design promised it would be acted on. The fix for next time is a fixed review date written into a skill — or no telemetry.
2. **Measure what the doctrine defines, not what's easy to count.** The hook counted every `Agent` dispatch because that's a single tool-name match. The doctrine's tier-4 set is narrower. The conflation made the headline number meaningless.
3. **Regex-on-prompt enforcement measures compliance theater, not behavior.** If we ever reintroduce a tier-4 gate, it has to either (a) block dispatch when rationale is absent — turning the check into a hard tripwire — or (b) not exist.
4. **The tier doctrine itself stayed valuable.** What rotted was the surveillance loop, not the funnel. Tier 0 → 1 → 2 → 3 → 4 with the rationale preamble for investigation scouts is still the right shape.
