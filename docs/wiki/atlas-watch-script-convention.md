# atlas-watch-script convention

> Per-system `<name>.watch.sh` sibling files that emit one mechanical FRESH/DRIFT/MISSING line — cheap atlas-drift detection between full audit rotations.

## Purpose

`/architecture-audit` graded scoring depends on each atlas page being reasonably current. A full audit pass is the heavyweight refresh; this convention is the lightweight, mechanical *detection* surface that runs between those rotations.

The pair:

- **Audit-pass closeout gate** (claude-klabauter `coordinator/bin/verify-arch-audit-atlas-refresh.py`) — enforces atlas refresh AT the moment `/architecture-audit` closes (Branch A inline refresh, or Branch B `atlas-current-as-of:<date>` token). Stops a graded audit from landing against a stale baseline.
- **`.watch.sh` convention** (this page) — surfaces mechanical atlas drift BETWEEN audit rotations, so structural facts the atlas claims (a count, a version pin, a registry composition) don't silently rot and invalidate the next audit's prior baseline.

Both surfaces preserve the two-clock doctrine: neither touches `Last full audit` (that clock is exclusively `/architecture-survey`'s). This convention drives only the detection surface; rotation scoring continues to read `Last targeted audit` from the health-ledger via the existing rotation-clock helper.

## The convention

Each atlas page MAY ship a sibling `<name>.watch.sh` script alongside `docs/architecture/systems/<name>.md`. The script is optional per system — pages without one are not in any way non-conformant.

Contract:

- **OPTIONAL.** No atlas page is required to ship a `.watch.sh`. Pages without one cause the aggregator to emit `FRESH <system> (no watch script)`.
- **No args.** The script receives no positional arguments and reads no environment configuration. It relies on **`cwd` being the repo root** — the aggregator chdir's there before invocation, and a hand-run from elsewhere is undefined.
- **Exactly one line on stdout** matching the regex:

  ```
  ^(FRESH|DRIFT|MISSING) <system_name>( .*)?$
  ```

  Where the leading token is one of:
  - `FRESH` — observed source value matches the atlas claim.
  - `DRIFT` — observed source value differs from the atlas claim; optional trailing text explains (e.g. `expected=29 got=27`).
  - `MISSING` — the source value the script tried to read is absent (file deleted, registry empty, etc.).

- **Exit 0 on successful emission**, regardless of which token was emitted (FRESH/DRIFT/MISSING are all "the script worked"). **Non-zero exit = failure mode** — the aggregator treats non-zero as `ERROR <system>: <name>.watch.sh exit=<N>` and never silently re-interprets it as FRESH.
- **Bash 3.2 + BSD coreutils + Git-Bash portable** per DR-061. The same cross-platform-shell-portability lens that applies to every `bin/*` script applies here — these are first-class repo shell scripts, not throwaway one-liners. No bash-4 idioms (`declare -A`, `mapfile`, `${v^^}`), no GNU-isms without a portable fallback (`sed -i`, `date -d`, `grep -P`, `realpath`).

## How it composes

Claude-klabauter `coordinator/bin/check-atlas-watch-drift.py` is the aggregator. It is read at run-time by:

- `/architecture-audit` Step 1 (Calculate Rotation Target) — surfaces `DRIFT` / `MISSING` / `ERROR` / `STALE` on rotation candidates so a drift signal on the proposed target system bumps it to the top of the rotation regardless of formula score.
- `/workweek-complete` (weekly atlas drift walk) — runs aggregator across every atlas page, surfaces drift + staleness lines in the weekly report.

Aggregator-side interpretation rules (enforced in claude-klabauter `coordinator/bin/check-atlas-watch-drift.py`, restated here so script authors understand the consumer):

- Non-zero exit from `<name>.watch.sh` → `ERROR <system>: <name>.watch.sh exit=<N>`. Never silently FRESH.
- Malformed stdout (not exactly one line, or first token not in `FRESH|DRIFT|MISSING`) → `MALFORMED <system>: <name>.watch.sh output unparseable`. Never silently FRESH.
- No `.watch.sh` present for a given atlas page → `FRESH <system> (no watch script)`. (Optionality is built into the consumer, not paid for at authoring time.)
- Independently of any `.watch.sh`, atlas pages whose `last_attested` frontmatter date exceeds the staleness threshold (default 30 days) emit a sibling `STALE <system> last_attested=<date> age=<N>d` line. (Reads `last_attested` per the within-atlas clock split below — a Branch B re-attestation un-stales without a body rewrite.)

## Worked example

`docs/architecture/systems/coordinator-skills.watch.sh` is the seed worked example: it counts `SKILL.md` files under `plugins/coordinator/skills/*/SKILL.md` and compares the count against the atlas-claimed value (29 at seed time). On match: `FRESH coordinator-skills skill_count=29`. On mismatch: `DRIFT coordinator-skills skill_count expected=29 got=<N>`.

That shape — count-or-grep a structural fact the atlas asserts, compare against an inline constant the atlas page also asserts, emit one line — is the canonical pattern. Other reasonable shapes:

- Compare a registry version pin (`probe_registry_version`) extracted from source against the version named in the atlas.
- Count entries in an enum or registry composition (`_VALID_PHASES`) and compare to the atlas-claimed cardinality.
- Check that a file the atlas page treats as authoritative still exists at the cited path (emit `MISSING` if not).

## Within-atlas clock split

Atlas frontmatter carries two date clocks under the `Last targeted audit` rubric:
- `last_mapped:` — most recent body rewrite (content rotation).
- `last_attested:` — most recent currency assertion. Bumped by every audit (Branch A) AND every bare re-attestation (Branch B).

The STALE-walk reads `last_attested`. A Branch B same-day re-attestation un-stales an atlas without a body rewrite — this is the design intent. Branch A always bumps both clocks (a real audit IS the strongest attestation; narrow-attestation would let a just-rotated atlas read STALE).

The inter-skill two-clock contract above is unaffected: `Last full audit` remains `/architecture-survey`-exclusive; `Last targeted audit` remains `/architecture-audit`-owned. The within-atlas split sits entirely inside `Last targeted audit`.

Spec backlink: `archive/specs/2026-06/2026-06-08-atlas-attested-clock-split.md`.

## Non-goals (anti-scope)

- **NOT a pluggable predicate framework.** Mechanical scripts only — count files, grep a version, check a path. Anything that requires real interpretation belongs in a `/architecture-audit` pass, not a `.watch.sh`.
- **NOT a frontmatter field.** An earlier shape considered an `atlas_watch:` YAML block in atlas-page frontmatter; that approach was explicitly rejected. The sibling-file convention replaces it entirely — there is no `atlas_watch:` schema, and atlas-page frontmatter must not carry one.
- **NOT required per atlas page.** Optionality is structural, not a TODO. Pages without a `.watch.sh` are fully conformant; the aggregator handles them with `FRESH <system> (no watch script)`.
- **NOT a closeout gate.** This convention is the detection surface that runs between audits. The closeout-gate sibling — claude-klabauter `coordinator/bin/verify-arch-audit-atlas-refresh.py` — is what enforces "you didn't close `/architecture-audit` against a stale atlas." Two surfaces, two jobs.
- **NOT a writer of any kind.** A `.watch.sh` reads source and emits one line. It does not modify the atlas page, the health-ledger, or anything else.

## Two-clock doctrine

Both surfaces preserve the two-clock contract:

- `Last targeted audit` is the rotation clock for `/architecture-audit`.
- `Last full audit` is the survey clock for `/architecture-survey`.

Neither the closeout gate nor the `.watch.sh` aggregator reads or writes `Last full audit`. Drift detection here is purely advisory input to the rotation clock — surfacing structural drift earlier so the rotation picks the right target.

## Cross-repo note

The convention itself is the doctrine. Per-system `.watch.sh` seeds are per-repo. Example-game-repo's known case (atlas drift on `probe_registry_version` bumps and `_VALID_PHASES` rotation) lives as `.watch.sh` siblings in the example-game-repo repo's own `docs/architecture/systems/`, authored against that repo's source layout — not seeded from here. Other repos adopt the convention by:

1. Vendoring claude-klabauter `coordinator/bin/check-atlas-watch-drift.py` (or pulling it via the coordinator publish chain).
2. Writing `.watch.sh` siblings against the repo's own atlas pages, observing the contract on this page.
3. Wiring the aggregator into the local `/architecture-audit` Step 1 and weekly walk.

## See also

- claude-klabauter `coordinator/bin/check-atlas-watch-drift.py` — the aggregator.
- claude-klabauter `coordinator/bin/verify-arch-audit-atlas-refresh.py` — the closeout-gate sibling that enforces refresh-at-close.
- `bin/check-arch-audit-staleness.py` — the rotation-clock helper (canonical; unchanged by this convention).
- `coordinator/docs/wiki/coordinator-tripwires/` § Atlas-refresh gate at /architecture-audit closeout — the tripwire registry entry for both surfaces.
- `cross-platform-shell-portability.md` — the portability rules that apply to `.watch.sh` scripts.
