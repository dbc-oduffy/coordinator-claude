<!-- AC10 dry-run transcript for archive/specs/2026-05-26-session-end-deviation-reconciliation-gate.md.
     Hand-trace of /distill Phase 5a (as amended by Chunk 2) against plan-deviation-reconciliation-fixture.md.
     Full multi-agent /distill pipeline not spun — disproportionate; this is a rule-application trace of the
     Phase 5a section-classifier + negative-AC guard, which is the surface Chunk 2 modified. -->

# AC10 Behavioral Dry-Run Trace — Phase 5a vs. fixture

**Date:** 2026-05-26
**Fixture:** `tests/fixtures/plan-deviation-reconciliation-fixture.md`
**Rules applied:** `commands/distill.md` § Phase 5a (DENYLIST + bounded re-homing exemption + `[SUPERSEDED]` note) and § Negative AC — Silent-Loss Guard (`## Deviations` heading-classifier exemption), as amended by Chunk 2 of this plan.

## Section classification (Phase 5a § 5a)

| Fixture section | Bucket | Fate | Notes |
|---|---|---|---|
| Goal | ALLOWLIST | survives verbatim | — |
| Premise | ALLOWLIST | survives verbatim | — |
| Decisions Made | ALLOWLIST | survives verbatim | contains `SHIPPED: async message queue with retry (was: synchronous HTTP transport)` |
| Acceptance Criteria | ALLOWLIST | survives verbatim | Criterion/Test cells unmodified; Status cells (`shipped`) intact — no parser corruption |
| Deviations | DENYLIST | `[EPHEMERAL]` → drop | **bounded re-homing exemption fires** (heading exactly `## Deviations`) → dropped WITHOUT re-homing scan |

## Assertion (i) — `## Deviations` dropped as `[EPHEMERAL]` without halting

PASS. The `## Deviations` heading matches the DENYLIST entry exactly. The bounded re-homing exemption (Chunk 2 AC4) applies: re-homing scan is skipped for this section only. Drop fate `[EPHEMERAL]`. No re-homing-driven content move occurs.

## Assertion (ii) — corrected ALLOWLIST (shipped shape) survives into the archived spec

PASS. `Decisions Made` is an ALLOWLIST section → survives verbatim into `archive/specs/`. The shipped shape `async message queue with retry` is preserved as the live decision. Per the `[SUPERSEDED]` note (Chunk 2 / plan D6), Phase 1 maps the `(was: synchronous HTTP transport)` half to the `[SUPERSEDED]` nugget class — recorded as superseded provenance, not crystallized as a competing live decision. The synchronous forecast does NOT crystallize into the wiki; the async shipped shape does.

## Assertion (iii) — no spurious negative-AC halt

PASS, and **load-bearing** (not trivial). The dropped `## Deviations` section contains an AC-shaped token: `... the transport MUST include a circuit breaker ...` (row 3, added as the assertion-(iii) tripwire). This `MUST` line:
- is in the drop-list (the `## Deviations` section is dropped), and
- has NO semantically-equivalent line in any surviving ALLOWLIST section (the kept `Decisions Made` says "no circuit breaker in scope" — the opposite, not an equivalent).

Set-diff form of the negative-AC guard would therefore compute a non-empty drop-vs-kept difference on this token and **HALT** — *if the section were scanned*. The `## Deviations` heading-classifier exemption (Chunk 2 AC5) excludes every line within the `## Deviations` section from the set-diff scan once the heading is detected. With the exemption: the `MUST` line is not scanned → set-diff is empty → **no halt**. Without the exemption: halt. The exemption is thus proven load-bearing by this fixture.

## Verdict

All three AC10 assertions PASS. The loop the plan claims to close is exercised end-to-end at the Phase 5a surface: the corrected ALLOWLIST decision crystallizes the shipped shape (the `(was: Y)` forecast rides along as inline supersession provenance, not a competing decision); the audit table is dropped as `[EPHEMERAL]` without re-homing and without spurious halt.

**Maintenance obligation (gate-bound AC, hand-trace verification):** this trace is a static hand-application, not a runnable assertion. If `commands/distill.md` § Phase 5a (DENYLIST / re-homing exemption) or § Negative AC — Silent-Loss Guard changes, this trace is stale and MUST be re-executed against the fixture. Per session-end code-reviewer Finding 6.
