---
name: cruft-sweep
description: "Scan for reclaimable scratch and orphans; apply only if confirmed."
allowed-tools: ["Read", "Bash", "Glob", "Grep", "Agent", "AskUserQuestion"]
argument-hint: "[--dry-run|--apply] [--class harness|scratch|orphans|empty-dirs|all]"
---

# Cruft Sweep — Layer 2 Skill

Consume the JSONL wire output of `bin/cruft-sweep` to surface `confirm-needed` findings and parent-folder orphans for PM review. Present reclaim opportunities in offer-shape — never violation framing. Apply only after explicit confirmation.

**Destructive-action prohibition:** This skill dispatches read-only scouts. The only write path is `bin/cruft-sweep --apply` after explicit `AskUserQuestion` confirmation. Scouts MUST NOT modify files, commit, or push.

---

## Four classes of cruft

The Layer 1 script handles four distinct classes, each with its own auto-prune and confirm-needed thresholds:

- **Class 1 — Harness state in `~/.claude/`**
  Session UUID directories (`projects/<repo>/<uuid>/`), transcript `.jsonl` files, and `file-history/<uuid>/` directories older than the retention threshold (default 14 days). Auto-pruned by Layer 1 when outside the active-handoff UUID block-list.

- **Class 2 — In-repo scratch dirs**
  Name-anchored directories inside the current git repo (`tmp-cc/`, `nonexistent/`, `fake/`, single-char `[a-z]/`, chained identical dirs). Auto-pruned by Layer 1 when untracked, older than 7 days, and outside the negative-spec list. Confirm-needed names (`tmp/`, `scratch/`, `output/`) are surfaced here for PM confirmation.

- **Class 3 — Parent-folder orphans at the machine's dev roots**
  Top-level children at the parent roots whose names match the literal cruft list AND whose contents match a sonnet-default fingerprint (`vector/store/chroma.sqlite3`, lone `mcp_queries.jsonl`, etc.). Broader registry-diff against the canonical sibling-repo list is Layer 2's responsibility — Layer 1 auto-prunes only the name+fingerprint conjoint gate.

- **Class 4 — Empty top-level directories in the current repo** (`--class empty-dirs`)
  Depth-1 children of the repo root containing **zero files anywhere in the subtree**, older than a 24h mtime floor, not git-ignored, not hard-excluded/whitelisted/dot-prefixed. Detection is structural, not name-based — git is blind to a file-free directory tree (nothing to track, so `git status --untracked-files=all` is silent and `.gitignore` never gets a say), which is exactly the gap the other three classes cannot see. Fails closed: no git work tree, no git binary, or an unreadable nested subtree all mean skip-and-delete-nothing.

  **Reclaim bytes are always 0 for this class by construction** — an empty subtree has nothing to reclaim. The item count is the whole signal; never present this class as an MB reclaim opportunity.

---

## Out-of-scope actions

The following are out of scope for this skill — do NOT attempt them:

- Cleanup of `~/.claude/plugins/cache/` (harness owns).
- `git clean -fd` style worktree cleanup.
- Auto-deletion of orphan markdown at parent altitude (always confirm-needed).
- Anything Layer 1 already auto-prunes (do not re-walk the tree; consume `cruft-sweep --dry-run --json` output instead).

### Guard rails (from spec)

These are the highest-blast-radius cases — hardcoded refusals regardless of what the Layer 1 JSONL output says:

- **Do NOT auto-prune any directory whose path contains a `.git/` boundary** (handoff Anti-scope #3). A parent-altitude `nonexistent/` that is itself a git repo retains all history inside `.git/`; pruning would be irreversible and catastrophic. Check: `[[ -d "$candidate/.git" ]]` before any prune call.
- **Do NOT expand the parent-folder scan beyond this machine's resolved dev roots** (handoff Anti-scope #5). Speculative discovery of additional parent roots is not the skill's remit. The roots are resolved deterministically per-machine (see Step 2) via `machine-local`'s registry-derived parent dirs of resolved `repos.*` entries. Registry-derived ≠ speculative — deviating from these resolved roots without PM direction introduces unpredictable blast radius.
- **Do NOT conflate "untracked" with "cruft"** (handoff Anti-scope #6). A directory that is git-untracked is not automatically cruft — it may be a new repo not yet registered, a working area created this session, or intentionally unversioned. Untracked status is a necessary but not sufficient condition for any prune action.
- **Do NOT auto-prune a session directory whose UUID is referenced as `predecessor:` in any active handoff** (handoff Anti-scope #7). The pre-flight UUID block-list check in `cruft-sweep` covers Layer 1; the skill must honor the same constraint for any confirm-needed item it surfaces. If a PM confirms deletion of a UUID dir, verify against the active-handoff block-list before invoking `--apply`.

---

## Steps

### Step 0 — Surface last sweep staleness

Read the central state cruft-sweep log (resolved via `coordinator-state-root.py --central`'s `cruft-sweep-log.md`, claude-klabauter-resident) to surface when the last sweep ran. Staleness is computed from the log's most recent row timestamp, not from a separate recheck file.

`coordinator-state-root.py` is a claude-klabauter-resident `lib/` resolver, not a forwarded `bin/` CLI — it is not reachable via the settings-home forwarder seam. Resolve the central state directory the same way Step 0's log read above does (claude-klabauter root, then `python3 "<claude-klabauter-root>/coordinator/lib/coordinator-state-root.py" --central`), then tail the last 5 rows of `cruft-sweep-log.md` inside it (fall back to "(no sweep log — first run)" if the file is absent).

Report the last sweep date to the PM as a one-liner: _"Last sweep: YYYY-MM-DD (N days ago)."_

### Step 1 — Run Layer 1 dry-run and parse JSONL

Invoke the script with `--dry-run --json --class all` and capture the JSONL records: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/cruft-sweep" --dry-run --json --class all`.

Parse the JSONL stdout. Separate records by `disposition`:

- `auto-prune` — Layer 1 will handle these autonomously; present a summary count only.
- `confirm-needed` — surface to PM via `AskUserQuestion` (offer-shape, see Step 2).
- `skip` — informational only; do not surface unless PM asks.
- `duplicate-of-scratch` — **not a finding; never count it.** See the de-duplication rule below.
- `prune-failed` — an apply-mode delete that did not confirm removal (permission denied, wedged path). Layer 1 does not count these as reclaimed. Surface them to the PM in the Step 5 report: they are the difference between *attempted* and *actually removed*.

Compute total reclaimable MB across `auto-prune` + `confirm-needed` records only.

**Do not write de-duplication logic — the engine already guarantees one record per physical directory.** Phase B (scratch) is name-anchored (`{"tmp-cc", "nonexistent", "fake"}`, effective floor `max(scratch_age_days, 24h)`) and Phase E (empty-dirs) is structural (flat 24h floor), so both can match the same path, and their floors are *not* nested — a directory between 24h and `scratch_age_days` old is a genuine Phase-E-exclusive catch. Rather than skip such a candidate (which would silently under-report it), Phase E **relabels**: when the name is also in Phase B's auto-prune vocabulary, the `empty-dirs` record carries `disposition == "duplicate-of-scratch"` and the authoritative `auto-prune` record lives on the `scratch` record for the same path. Summing or counting on `disposition == "auto-prune"` is therefore already double-count-free. The failure mode to avoid is the inverse: treating an unrecognized disposition as a finding, which re-introduces the double count this labeling exists to prevent. Apply-mode delete behavior is identical in every case — this is a labeling distinction only.

### Step 2 — Scout parent-altitude orphans (Class 3 registry-diff)

For candidates where `class == "orphans"` and `disposition == "skip"` (name matched but no sonnet fingerprint — Layer 2 broader scan), dispatch a read-only `Explore` agent to enumerate parent-altitude children at this machine's dev roots against the sibling-repo registry (`machine-local keys` / `machine-local get repos.<key>`).

**Resolve the dev roots for THIS machine first** — they are not the same on every box, and hardcoding a platform-specific path breaks the scan on other hosts: the distinct parent directories of the non-empty `repos.*` entries, resolved via the settings-home-resolved `machine-local` CLI (`registry.local.toml` first, falling back to the tracked `registry.toml`). This is registry-derived, not speculative discovery — anti-scope #5 still forbids hunting for arbitrary roots.
- Test each candidate root with `[[ -d "$root" ]]`. **If no dev root exists on this machine, skip Class 3 entirely** and log one line — `Class 3 parent-orphan scan skipped — no dev roots present on this machine.` — then proceed to Step 3. Enumerate only roots that exist.

Dispatch shape:

```
Agent(
  subagent_type: "Explore",
  description: "Cruft-sweep Class 3 parent-altitude registry-diff scan",
  prompt: """
    Do NOT modify files, commit, or push. Read-only.

    Enumerate top-level children of these resolved dev roots: {{RESOLVED_DEV_ROOTS}}. For each child:
    1. Check whether its name appears among the `machine-local keys` sibling-repo registry entries.
    2. If NOT in the registry AND NOT matching the Layer 1 auto-prune conjoint gate
       (name match + fingerprint match), include it in the result.

    Reply with a JSON list of {path, name, mtime_iso, evidence} for each candidate.
    Evidence should name why it is suspicious (e.g., "not in sibling-repo registry",
    "no fingerprint match — fingerprint gate skipped it", etc.).
  """
)
```

No `mode: auto` or `mode: bypassPermissions` is needed — this agent is read-only and produces inline JSON output for the skill to parse. Do not use `general-purpose` or any write-capable subagent type.

The scout enumerates top-level children at this machine's resolved dev roots, cross-references against the registry, and returns candidates for PM review.

### Step 3 — Present confirm-needed items via offer-shape AskUserQuestion

When the Layer 1 dry-run and scout produce `confirm-needed` findings, present them via batched `AskUserQuestion`. The lead-with-reclaim wording is non-negotiable — never frame as a violation or warning.

Canonical template:

> _"Reclaim N MB by pruning `<path>` (`<evidence>`, mtime `<mtime>`)? [y/N/inspect]"_

Where:
- `N MB` — the reclaim opportunity (lead with the value).
- `<path>` — the candidate path.
- `<evidence>` — one-line reason (sonnet-fingerprint match / orphan dir not in registry / name in confirm-list, etc.).
- `<mtime>` — `YYYY-MM-DD` for the freshness signal.

Batch related items from the same class into a single question where practical (e.g. all `tmp/` dirs in the same repo). Never ask about items already handled by Layer 1 auto-prune — those are informational only.

### Step 4 — Apply after confirmation

After PM confirmation on selected items, invoke `cruft-sweep --apply` scoped to the confirmed classes: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/cruft-sweep" --apply --class <selected>`.

For Class 3 registry-diff orphans confirmed by the PM, pass the appropriate `--parent-root` overrides if the default roots differ. The script appends to the central state cruft-sweep log (resolved via `coordinator-state-root.py --central`'s `cruft-sweep-log.md`) on apply — no separate log write needed from the skill.

### Step 5 — Report

Summarise: classes swept (all four — an omitted class reads as "nothing found there", which is a silent under-report), items removed, MB reclaimed, items deferred. Report `empty-dirs` by item count, never by MB — its reclaim bytes are 0 by construction.

Report any `prune-failed` records explicitly rather than folding them into the removed count. They are attempted-but-not-removed, and a report that omits them overstates what the sweep actually did.

Note any items the PM declined to remove for the session record.

---

## Cadence note

Staleness is computed from the sweep log mtime (the most recent row timestamp in the central state cruft-sweep log — resolved via `coordinator-state-root.py --central`'s `cruft-sweep-log.md`), not from a separate recheck file. The `/workday-start` Step 1.11 advisory surfaces a one-liner when reclaimable > 1 GB OR staleness > 14 days — the PM invokes `/cruft-sweep` on that advisory; the skill does not auto-apply.

---

## Negative-spec

- Does NOT re-walk the filesystem independently — Layer 2 consumes `cruft-sweep --dry-run --json` output.
- Does NOT dispatch parallel scouts — sequential by design; N is small and each candidate is judgment-bearing.
- Does NOT write outside the central state cruft-sweep log (resolved via `coordinator-state-root.py --central`'s `cruft-sweep-log.md`; claude-klabauter-resident) (which the script owns via `--apply`).
- Does NOT auto-prune on the PM's behalf — every deletion requires explicit `AskUserQuestion` confirmation or Layer 1 auto-prune eligibility.
