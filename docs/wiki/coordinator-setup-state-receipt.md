# Coordinator Setup-State Receipt

> Per-machine milestone receipt at `~/.claude/coordinator-setup-state.yaml` that records when coordinator setup concluded and (optionally) when the operator started and completed the guided orientation. It is the **cross-repo chaining contract**: branch/leaf repos read it to confirm coordinator is bootstrapped before chaining their own setup/orientation after it.

## What it is (and what decay model it carries)

This is a **receipt** in the sense of [`plugin-identity-and-health-sentinels.md`](plugin-identity-and-health-sentinels.md): durable evidence that *something happened at a point in time*, written by the actor whose action it witnesses, where **stale = signal, not lie**. It is neither runtime-queryable identity (no live source that goes stale mid-session) nor operator configuration (it's a record of an event, not a setting).

It clears that wiki's high bar for a *second* disk sentinel (option 4 under "Extending the surface") on all three counts:

- **The writer must be a skill.** Setup conclusion and the guided orientation are skill/EM actions — there's no MCP tool or doctor probe that owns this state.
- **The decay model is distinct.** A milestone receipt is set once and never re-checked for currency, unlike the doctor receipt (re-runs, "stale = nudge to re-run") or live identity (current = answer). It records *that an event occurred*, permanently.
- **The verdict-reduction has cross-repo structural value.** The presence of `setup_concluded_at` is a yes/no gate that other repos consume to sequence their own bootstrap.

## Schema

Flat YAML. Each `*_at` is an ISO-8601 UTC timestamp, **set once (first occurrence wins) and never overwritten**. A field is absent until its event fires.

```yaml
version: 1
setup_concluded_at: 2026-05-23T14:02:11Z       # /setup reached Phase 7 (always fires)
orientation_started_at: 2026-05-23T14:05:40Z    # guided tour began (elective)
orientation_completed_at: 2026-05-23T14:31:08Z   # guided tour completed (elective)
```

## Writers

The single writer/reader primitive is `coordinator-setup-state.sh` (idempotent, atomic temp-file + `mv`). Nothing else writes this file by hand.

| Milestone | Recorded by | When |
|---|---|---|
| `setup_concluded` | `/setup` Phase 7 Step 0 | Mechanically, on every full (non-`--check-only`) `/setup` run that reaches Phase 7. **This is the chaining gate** — it fires whether or not the operator takes the elective tour. |
| `orientation_started` | `/setup` guided-onboarding offer (on accept) **and** `getting-started.md` facilitation (tour start) | When the guided tour begins. Double-recording is harmless — first occurrence wins. |
| `orientation_completed` | `getting-started.md` facilitation | When the operator finishes the tour. |

### Why the gate is `setup_concluded`, not orientation

The orientation tour is **elective** — offered at the tail of `/setup` and declinable ("learn by doing"). If the chaining signal keyed only on orientation, a user who finished `/setup` but skipped the tour would leave no marker, and a sibling repo could not distinguish "coordinator never set up" from "set up, tour skipped." So the deterministic `setup_concluded_at` is the gate; the two `orientation_*` fields are richer detail layered on top.

## Cross-repo reader idiom (branch/leaf repos)

Sibling repos that chain their setup/orientation after coordinator's gate on `setup_concluded`. Two equivalent shapes:

**Read the file directly** (no dependency on coordinator's plugin layout):

```bash
CLAUDE_HOME="${CLAUDE_HOME:-$HOME}/.claude"
if grep -qE '^setup_concluded_at:[[:space:]]+[^[:space:]#]' \
     "$CLAUDE_HOME/coordinator-setup-state.yaml" 2>/dev/null; then
    : # coordinator is bootstrapped on this machine — proceed to chain
else
    echo "Run /coordinator:install first." >&2
fi
```

**Or use the helper verb** (when the coordinator plugin is install-resolvable):

```bash
bash "$CLAUDE_HOME/plugins/coordinator/bin/coordinator-setup-state.sh" \
    check setup_concluded && echo "ready to chain"
```

`status` prints the whole receipt (exit non-zero if absent, or if seeded but no milestone is recorded yet).

## Why per-machine (gitignored)

The receipt lives at `~/.claude/coordinator-setup-state.yaml` and is **gitignored** (anchored `/coordinator-setup-state.yaml`). The chaining question is "did coordinator setup conclude *on this machine*" — a cloned `~/.claude` on a fresh machine has **not** had its per-machine substrate (machine-local registry paths, Windows PATH shims, etc.) installed yet, so a carried-over "concluded" receipt would be an active lie there. Per-machine gitignore is the same treatment as `setup/publish-targets.sh` and the machine-local registry's `*.local.toml`.

The gitignore entry is in the meta-repo's own `.gitignore`. For OSS operators, `/coordinator:install`'s git-init path lays down a starter `~/.claude/.gitignore` from `templates/dotgitignore.tmpl`, whose `# --- Coordinator per-machine state ---` block already ignores `coordinator-setup-state.yaml` (alongside `coordinator-identity.yaml` and `working-repos.yaml`). An operator whose `~/.claude` was git-tracked *before* this starter shipped is offered the same block by `/setup` Phase 4 (already-a-repo branch); it is never auto-edited into an existing `.gitignore`.

## Sibling-repo wiring is a separate relay

Documenting this contract here is doctrine seeding (DoE altitude). Making a specific sibling repo's setup/orientation *consume* the gate is that repo's EM's work — relay the reader idiom above via the PM per the cross-repo communication doctrine; do not edit sibling repos directly.

## Cross-references

- [`plugin-identity-and-health-sentinels.md`](plugin-identity-and-health-sentinels.md) — receipt vs. identity vs. scanner decay discipline; this receipt is the justified second disk sentinel.
- `commands/install.md` Phase 7 Step 0 — `setup_concluded` writer.
- `docs/wiki/getting-started.md` — orientation facilitation playbook (`orientation_*` writers).
- `coordinator-setup-state.sh` / `bin/coordinator-setup-state.test.sh` — the primitive and its tests.
