---
title: Rename /session-end → /session-complete (full clean rename + OSS deprecation alias)
date: 2026-06-01
slug: session-complete-rename
scope_mode: feature
status: superseded
superseded_by: plugins/coordinator/docs/plans/2026-06-01-workstream-rename.md
workstream: session-complete-rename
spinoff_source: state/handoffs/2026-06-01_125306_session-complete-rename.md
problem_set: handoff body (PM-ratified) — restores the {session,workday,workweek}×{start,complete} ceremony grid
depends_on:
  - plugins/coordinator/docs/plans/2026-06-01-session-boot-nomenclature.md  # front-half; disjoint file scope, soft seam at CLAUDE.md
---

# Rename `/session-end` → `/session-complete` (full clean rename + OSS deprecation alias)

> **⚠ SUPERSEDED 2026-06-01** by `docs/plans/2026-06-01-workstream-rename.md`. The PM retargeted the rename from `/session-complete` to `/workstream-complete` (platform-vocabulary alignment — our skills must not shadow the `SessionEnd` platform hook) and unified it with the `/session-start → /workstream-start` rename + the "session boot" coinage reversal. Do NOT execute this plan. Its substrate (alias-stub mechanism, data-field decision, commit-gate machinery) is absorbed into the unified plan. Retained for audit trail.

Back half of the session-lifecycle nomenclature reorientation. Rename the `/session-end` **skill** to `/session-complete` everywhere across the coordinator plugin, keep `/session-end` working as a deprecation alias for OSS consumers, and converge `grep -rc session-end` down to a documented intentional-keep set.

**Why (PM-ratified):** the end-of-unit ceremony family is already `-complete` for the two larger time units (`/workday-complete`, `/workweek-complete`). `/session-end` is the lone `-end` holdout. Renaming restores a clean **2×3 grid**: `{session, workday, workweek} × {start, complete}`, and "complete" names the doctrinal meaning out loud — `/session-complete` caps a DONE workstream (vs `/handoff` for in-flight).

## Scope mode

`feature` — it is a mechanical rename in bulk, but it introduces a **new deprecation-alias mechanism** (a stub skill) and makes a **stored-data-field decision** with schema-validation implications. Those two design calls warrant feature-depth review, not production-patch depth.

## Substrate verified at plan-write time (2026-06-01, HEAD 38ef4e61)

- **Skill location:** `skills/session-end/SKILL.md`, `name: session-end`. Skills are invoked by the `name:` frontmatter field; the directory name is convention only (verified across 29 coordinator skills — dir name and `name:` always match by convention, not platform enforcement).
- **Alias mechanism — SPIKE RESOLVED (riskiest unknown):** Claude Code has **no native skill-alias support**. There is no `aliases:`/`redirect:` frontmatter key. The invocation name is the `name:` field; for plugin skills it namespaces to `/coordinator:<name>`. **The only mechanism to keep `/session-end` resolving is a thin second stub skill** at `skills/session-end/SKILL.md` with `name: session-end` that redirects to `/coordinator:session-complete`. (Source: claude-code-guide research against official plugins docs + the live 29-skill plugin; symlinks/redirect-fields are not supported.)
- **Runtime token is narrow:** the literal `--invoker session-end` value appears in only two functional places — the `case` arm in `bin/regenerate-orientation-cache.sh` (`session-end|handoff) TIER=mid-session`, L44, plus doc-comment lines L9/14/18/38/45) and the caller inside the renamed skill (`skills/session-end/SKILL.md` L376). **No `CLAUDE_INVOKING_COMMAND=session-end` literal is set anywhere** — that env form does not exist in the tree.
- **Stored data field:** `reviewed_at_session_end:` is a real frontmatter key in `schemas/handoff.yaml` (L101) and `schemas/handoff-archived.yaml` (L48). Every other `session_end`/`session-end` token in those schemas is a **prose comment naming the command** (handoff.yaml L15/54/64/90/93/125), or a **spec-backlink filename** (L100), not the key.
- **No `Stop`/`SessionEnd` platform hook exists** — the back-end "auto-fire" of `/session-end` is doctrine prose, not platform machinery (confirmed via `hooks/*.json`). The rename touches nothing that executes at session teardown; runtime risk ≈ zero.
- **Baseline to converge against:** `grep -rl session-end plugins/coordinator-claude/coordinator` → ~95 files / ~379 occurrences (drift up from the handoff's 90/321 from concurrent work; plan-coverage-checker counted 95 files on disk 2026-06-01; reconcile against the keep-list, not the raw count).
- **CRITICAL — commit machinery gates on the literal ceremony name (convergent finding, prior-art + plan-coverage):** `bin/coordinator-safe-commit` carries a functional regex `\bsession-end\b` that detects ceremony commits in the branch-gate, and `docs/wiki/coordinator-tripwires.md` carries a blanket-commit authorized-token list including `session-end`. After the rename, a real `/session-complete` ceremony commit will NOT match either gate → silent gate misfire. The new ceremony name `session-complete` must be ADDED to both (keeping `session-end` for the deprecation window). This is functional code, handled in C4, not the prose sweep.

## Design decisions (the two load-bearing calls)

### D1 — Deprecation alias = thin stub skill (spike-confirmed, no alternative)

Rename `skills/session-end/` → `skills/session-complete/` (dir + `name:`), then create a NEW `skills/session-end/SKILL.md`:

```markdown
<!-- VERBATIM -->
---
name: session-end
description: "[DEPRECATED] Renamed to /coordinator:session-complete. Run that instead."
disable-model-invocation: true
argument-hint: "[optional context]"
---

# `/session-end` — Renamed to `/session-complete`

This command was renamed to **`/coordinator:session-complete`** to match the
`{session, workday, workweek} × {start, complete}` ceremony grid. The behavior is
identical. Invoking the renamed skill now — run `/coordinator:session-complete`.

(Deprecation stub. Remove after the deprecation window — see CHANGELOG.)
```

`disable-model-invocation: true` keeps Claude from auto-selecting the deprecated stub; a human typing `/session-end` still reaches it and is redirected. Ships via `setup/publish.sh` like any skill dir.

### D2 — Keep the `reviewed_at_session_end:` key; document the command-name/data-field split

**Decision: KEEP the key as-is** (default lean confirmed). Renaming a frontmatter key written into real handoff records would invalidate existing records against the schema (AC: existing records must still validate). Add a one-line schema comment at the key in both schemas documenting the deliberate split:

```yaml
<!-- TEMPLATE: adapt to each schema's comment style -->
  # NOTE: key name retains the historical `session_end` token by design — the
  # /session-end command was renamed to /session-complete (2026-06-01) but this
  # stored field keeps its name for record back-compat. Command-name ≠ data-field.
  reviewed_at_session_end: string
```

No back-compat reader needed — the key never changes, so old and new records share one shape.

### D3 — Runtime token: rename to `session-complete`, tolerate `session-end` in the case arm

Rename the caller (`--invoker session-end` → `--invoker session-complete`) and the doc comments. In the `case` arm, **accept both** for the deprecation window so any lingering/stale caller does not hard-error into the `*) unknown invoker` exit:

```bash
<!-- VERBATIM -->
    session-complete|session-end|handoff)   TIER=mid-session ;;
```

Document the dual-accept as a deprecation tolerance (remove with the stub).

### D4 — Commit machinery must recognize `session-complete` as a ceremony name (convergent pre-flight finding)

Two pre-flight checkers independently flagged that the commit-gate machinery matches the literal `session-end` token to apply ceremony-commit logic. **Add `session-complete` alongside the retained `session-end`** in both gates (dual-recognition for the deprecation window):

- `bin/coordinator-safe-commit`: regex `\bsession-end\b` → `\b(session-end|session-complete)\b` (or add a parallel alternation entry — match the file's existing pattern style).
- `docs/wiki/coordinator-tripwires.md`: the blanket-commit destructive-shape gate's authorized-reference token list → add `session-complete`.

Without this, a `/session-complete` ceremony commit silently fails the branch-gate / trips the destructive-shape warning. This is the single highest-risk functional gap the pre-flights caught.

## Intentional-keep list (the convergence oracle)

After the sweep, `grep -rn session-end` must return ONLY these. Everything else becomes `session-complete`:

1. **The stored data-field key** `reviewed_at_session_end:` — `schemas/handoff.yaml` L101, `schemas/handoff-archived.yaml` L48 (D2).
2. **The case-arm deprecation-tolerance token** `session-end` in `bin/regenerate-orientation-cache.sh` (D3).
2a. **The commit-gate dual-recognition tokens** — `session-end` is KEPT alongside the new `session-complete` in `bin/coordinator-safe-commit` (regex `\bsession-end\b`) and the `coordinator-tripwires.md` blanket-commit authorized-token list (D4 / C4). Both gates must recognize both names for the deprecation window.
3. **The deprecation stub skill** `skills/session-end/SKILL.md` — `name: session-end` is the whole point (D1).
4. **Historical spec-backlink filename** `docs/plans/2026-05-08-session-end-review-and-marker-trail.md` wherever cited (e.g. handoff.yaml L100, wiki backlinks) — the filename names a past artifact; keep the token, rename surrounding prose.
5. **CHANGELOG history entries** describing past `/session-end` behavior (`dist/publish-repo-toplevel/CHANGELOG.md` L39/135/147/238/343/396/399/544) — historical record; keep. ADD one new entry for this rename.
6. **The sibling front-half plan** `docs/plans/2026-06-01-session-boot-nomenclature.md` OOS section — its `session-end` refs name "the /session-end → /session-complete rename" as the rename subject. Do NOT sweep it (belongs to the other workstream; refs are intentional).

## Chunks

Coupling: C1→C2→C3 are serial (shared skill dir + token caller). C4 (commit machinery), C5 (schema), C6 (prose sweep), C6b (bin/lib/misc), C7 (CLAUDE.md/CHANGELOG) touch disjoint files → parallel after C3. C8 reconciles after all. C9 is post-execution closeout. Chunk count expanded from 8→10 after the pre-flight INCOMPLETE fold (commit-machinery chunk + bin/lib/misc chunk added; prose sweep enumeration completed).

### C1 — Rename the skill core (serial, first)
- `git mv skills/session-end/ skills/session-complete/` FIRST, then Edit `skills/session-complete/SKILL.md`: `name: session-end` → `name: session-complete`, and rewrite the 32 internal body refs (mutex intro, headings, the `--invoker` caller at ~L376 — coordinate value with C3).
- **Test surface:** `grep:` no `session-end` in `skills/session-complete/SKILL.md` except the intentional `--invoker` (resolved by C3) and any historical spec-backlink filename. `name: session-complete` present.

### C2 — Deprecation stub skill (serial, after C1)
- Create `skills/session-end/SKILL.md` per D1 (the old dir path is now free after C1's `git mv`).
- **Test surface:** `grep:` file exists with `name: session-end` + `disable-model-invocation: true` + a `/coordinator:session-complete` redirect line.

### C3 — Runtime token rename (serial, after C1)
- `bin/regenerate-orientation-cache.sh`: case arm → `session-complete|session-end|handoff)` (D3); doc comments L9/14/18/38/45 → `session-complete` (keep `session-end` only in the dual-accept arm); update the caller in `skills/session-complete/SKILL.md` → `--invoker session-complete`.
- **Test surface:** `bash:` `regenerate-orientation-cache.sh --invoker session-complete` resolves to `TIER=mid-session`; `--invoker session-end` still resolves (deprecation tolerance); `--invoker bogus` still errors exit 2.

### C4 — Commit-machinery ceremony-name recognition (NEW — functional; convergent pre-flight finding; parallel-safe)
- `bin/coordinator-safe-commit`: extend the `\bsession-end\b` ceremony-detection regex to also match `session-complete` (keep both — deprecation window). Match the file's existing pattern style (alternation vs parallel entry).
- `docs/wiki/coordinator-tripwires.md`: add `session-complete` to the blanket-commit destructive-shape gate's authorized-reference token list (keep `session-end`); update the Persona-at-Sonnet block's greppable contact-point path `skills/session-end/SKILL.md` → `skills/session-complete/SKILL.md` (the stub remains, but the canonical skill is the rename target).
- **Test surface:** `bash:` a dry-run commit with subject containing `session-complete` is recognized as a ceremony commit by `coordinator-safe-commit` (does not fall through the gate); `grep:` tripwires token list contains both `session-end` and `session-complete`.

### C5 — Schema data-field decision (parallel-safe; schemas only)
- `schemas/handoff.yaml`: KEEP `reviewed_at_session_end:` (L101) + add D2 comment; rename prose `/session-end` comments (L15/54/64/90/93/125) → `/session-complete`; KEEP spec-backlink filename (L100).
- `schemas/handoff-archived.yaml`: KEEP key (L48) + D2 comment.
- `schemas/completion-entry.yaml`: rename all 10 prose refs → `/session-complete`.
- **Test surface:** `grep:` schemas contain `reviewed_at_session_end:` (unchanged) and zero non-key, non-backlink `session-end` prose. Schema-validate an existing handoff record still passes.

### C6 — Prose sweep (fan-out by disjoint file-group; the bulk)
- All wikis: `session-end-review.md` (20), `completion-log-release-loop.md` (22), `concurrent-em-hazards.md` (11), `coordinator-tripwires.md` (12 — prose refs only; the gate-token list is C4), `cross-repo-communication.md` (8 — incl. L278 skill-path ref `skills/session-end/SKILL.md § Step 2.66`), `plan-deviation-reconciliation.md` (6), `reviewer-pipeline.md` (5), `handoff-tracker-system.md` (4), `em-pm-collaboration-extras.md` (3 — incl. the `### PM owns session-end determination` section HEADING, not just inline refs), `sibling-surface-parity-testing.md` (L84 code-snippet path), `skill-budget-discipline.md` (the `coordinator:session-end (366)` usage-table entry), **plus ALL remaining wikis** — the per-group rule applies to every wiki under `docs/wiki/`, not only those enumerated here (the enumeration is a density guide, not a whitelist).
- Skills — enumerated: `handoff/SKILL.md` (12), `pickup/SKILL.md` (5), `execute-plan/SKILL.md` (5), `roadmap-planning/SKILL.md` (5), `project-onboarding/SKILL.md` (4), `plan/SKILL.md` (4). **Plus the 9 remaining skills with live refs the pre-flight found:** `session-start`, `spinoff`, `review`, `review-code`, `plan-delivery-audit`, `learn-lessons`, `finishing-a-development-branch`, `dogfood`, `parallel-code-review`. **Catch-all:** every skill under `skills/*/SKILL.md` with a `/session-end` command ref → rename (EXCEPT the deprecation stub `skills/session-end/SKILL.md` itself, keep-list item 3).
- Commands/hooks/pipelines/agents: `commands/workday-complete.md` (5), `commands/distill.md` (4), `commands/workday-start.md`, `commands/mise-en-place.md`, `hooks/scripts/nudge-unauthorized-handoff.sh` (6), `hooks/scripts/session-init.sh` (3), `pipelines/*` (catch-all authorizes all pipeline files), `agents/code-reviewer-weekly.md` (4), `agents/review-integrator.md`.
- **Per-group rule:** rename every `/session-end` / `session-end` command ref → `/session-complete`, **including section headings and usage-table entries** (not just inline prose); KEEP spec-backlink filenames intact. Each group is a disjoint write target → fan-out candidate.
- **AMBIGUOUS catch-all confirmation (pre-flight raised 20):** the "all remaining wikis" and "pipelines/*" clauses above EXPLICITLY authorize the executor to sweep every wiki and pipeline file containing a non-keep `session-end` ref — the executor does not need to ask per-file. The only non-sweep wiki content is keep-list items 4 (spec-backlink filenames) and the C4-owned gate-token list in coordinator-tripwires.md.
- **Wiki rename consideration:** `docs/wiki/session-end-review.md` — decide at execution whether to `git mv` the wiki file to `session-complete-review.md` (and repoint its referrers incl. `DIRECTORY_GUIDE.md` and the CLAUDE.md inline cross-ref `→ session-end-review.md`) or keep the filename + reframe intro. Default lean: **`git mv` + repoint** (the wiki is about the command, not a historical artifact) — this is what triggers the C9 doc-link-checker closeout. Reconcile ALL referrers in the same chunk.
- **Test surface:** `grep:` each swept file has zero non-keep `session-end`.

### C6b — bin/ + lib/ functional + misc surfaces (NEW — pre-flight MISSED set; parallel-safe)
- `bin/` (live command refs, none gate-functional except where noted): `coordinator-write-review-trail.sh`, `coordinator-session-loe.sh`, `aggregate-chain-loe.sh`, `check-no-monolith-completion-append.sh`, `cross-repo-memo`. Rename `/session-end` command refs → `/session-complete`. **Inspect each for functional vs prose** — if any carries a session-end-keyed branch/regex like C4's, apply dual-recognition, else prose rename.
- `lib/*`: the two lib files the pre-flight flagged (MISSED-1/2) — rename command refs.
- `canonical-structure.yaml` (review-trail "written by /session-end and /handoff", L148) → `/session-complete`.
- Root `README.md` (MISSED-9) and `dist/oss-only-skills/coordinator-update/SKILL.md` (MISSED-14) → rename live refs.
- **Test fixture disposition (MISSED-16):** `hooks/scripts/tests/test-nudge-improvement-queue-write.sh` fixture string `"coordinator:session-end"` — **default: rename to `coordinator:session-complete`** (canonical name) UNLESS the test specifically asserts deprecation-alias behavior, in which case keep + add a `session-complete` case. Inspect at execution; document the call.
- **Test surface:** `grep:` these surfaces carry no non-keep `session-end`; any test touched still passes (run it).

### C7 — CLAUDE.md + CHANGELOG + published artifacts (parallel-safe; disjoint from C4/C5/C6/C6b)
- `coordinator/CLAUDE.md`: rename command refs at L38, L139, L141, L159, L182 → `/session-complete`. **Also** the inline wiki-filename cross-ref `→ session-end-review.md` IF C6 `git mv`'d the wiki (coordinate with C6's referrer reconciliation). **Soft seam:** front-half plan touches L7-8 of this same file — disjoint lines, but coordinate landing order (whoever lands second rebases the unaffected lines cleanly).
- `dist/publish-repo-toplevel/CHANGELOG.md`: KEEP all 8 historical entries; ADD a new entry noting the rename + alias + deprecation window.
- `dist/publish-repo-toplevel/README.md`: rename any live `/session-end` command refs (not history) → `/session-complete`.
- **Test surface:** `grep:` CLAUDE.md has zero `session-end`; CHANGELOG gained the rename entry; README coherent.

### C8 — Reconcile against the keep-list (after C1–C7)
- Re-run `grep -rn session-end plugins/coordinator-claude/coordinator`; diff the result against the intentional-keep list (items 1–6 + 2a). Any residual outside the list → fix. Update the stale improvement-queue path ref (`state/coordinator-improvement-queue.md` L15 cites `skills/session-end/SKILL.md`) → `skills/session-complete/SKILL.md` if still present. Document the final keep-set in this plan's closeout.
- **Test surface:** `grep:` every remaining `session-end` maps to a keep-list item; no orphans.

### C9 — Post-execution closeout (after C8)
- **doc-link-checker** over `docs/`, `*.md`, and spec-backlink surfaces for inbound links to the moved skill path (`skills/session-end/` → `skills/session-complete/`) and the renamed wiki (if C6 `git mv`'d it). **Dispatch condition:** schedule ONLY if relative inbound markdown links to the moved paths exist that aren't already covered by `run-all-checks`/`validate-references`; otherwise note the `#anchor`-resolution check for one-click post-merge sanity and skip the dispatch (per `reviewer-routed-workers.md` substrate precondition).
- **Percolation note (do NOT execute):** next `/percolate` to OSS coordinator-claude must carry the renamed skill + the deprecation stub + the CHANGELOG entry together so the published artifact is coherent.
- **Dogfood:** run `/session-complete` on this workstream's own landing (the rename validates itself).

## Reverse-reference scan (shared-symbol rename)

The rename mutates a shared invocation symbol. Reverse-reference shapes greppped: bare `session-end`, slash `/session-end`, `--invoker session-end`, `name: session-end`, the `reviewed_at_session_end` key, and spec-backlink filename form. The keep-list (above) IS the documented residual after the scan. No bare-number/route-renumber form applies (this is an identifier rename, not a renumber).

## Cross-plan coordination

Scanned `docs/plans/*.md` for file-scope and seam overlap:
- **Front-half** `2026-06-01-session-boot-nomenclature.md` — disjoint file scope (`session-end` vs `session-start`/`session boot`). Soft seam: both touch `coordinator/CLAUDE.md` but at non-overlapping lines (front L7-8, back L139/etc.). Both pending; landing order is rebase-clean. Its 5 `session-end` refs are intentional (name the rename subject) → keep-list item 6, do NOT sweep.
- No other plan references the `session-end` command name in a file-overlapping way.

## Acceptance criteria

| ID | Criterion (prose) | Test (typed-prefix) | Binding-Class | Status |
|----|-------------------|---------------------|---------------|--------|
| AC1 | `skills/session-complete/` dir + `name: session-complete`; invokable as `/coordinator:session-complete`. | `grep:name: session-complete skills/session-complete/SKILL.md` | gate | pending realization |
| AC2 | `/session-end` still resolves via the deprecation stub skill (D1 mechanism). | `grep:name: session-end skills/session-end/SKILL.md` + redirect line present | gate | pending realization |
| AC3 | Runtime token renamed; caller + case arm coherent; old token tolerated, bogus token errors. | `bash:regenerate-orientation-cache.sh --invoker session-complete → mid-session; --invoker bogus → exit 2` | gate | pending realization |
| AC4 | `reviewed_at_session_end:` key unchanged; existing handoff records still validate; split documented. | `cited:` schema-validate a real record + comment present | gate | pending realization |
| AC4b | Commit machinery recognizes `session-complete` as a ceremony name (D4/C4): `coordinator-safe-commit` regex + tripwires token list both match `session-complete` AND retain `session-end`. | `bash:` ceremony-commit dry-run with `session-complete` subject is gate-recognized; `grep:` both tokens in tripwires list | gate | pending realization |
| AC5 | `grep -rn session-end` returns only the intentional-keep set (items 1–6 + 2a). | `cited:` reviewer diffs grep output vs keep-list | gate | pending realization |
| AC6 | `/handoff` ↔ `/session-complete` mutual-exclusion doctrine reads correctly in CLAUDE.md + all wikis. | `cited:` reviewer reads CLAUDE.md L139 + handoff/SKILL.md + session-end-review wiki | gate | pending realization |
| AC7 | Published artifacts coherent; CHANGELOG notes rename + alias + deprecation window; history kept. | `cited:` reviewer reads CHANGELOG new entry + README | gate | pending realization |
| AC8 | Cross-plan scan confirms no file-overlap drift vs front-half plan. | `cited:` § Cross-plan coordination | advisory | realized (plan-write time) |
| AC9 | Percolation follow-up noted, not executed. | `cited:` C9 closeout | advisory | pending realization |

## Anti-scope

- Do NOT rename `/session-start` — the `-start`/`-complete` grid is intentional.
- Do NOT rename the `reviewed_at_session_end` stored key (D2).
- Do NOT hard-break `/session-end` for OSS users — the stub is a requirement.
- Do NOT rewrite historical artifacts — the `2026-05-08-session-end-...` plan filename and CHANGELOG history keep `session-end`.
- Do NOT sweep the front-half `2026-06-01-session-boot-nomenclature.md` plan.
- Do NOT pre-execute the `setup/publish.sh` percolation — note it only.
