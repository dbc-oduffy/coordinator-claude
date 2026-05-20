# Install-Status Tags

> Conventions for the two distinct install-state files in the coordinator install chain. The prior-art-checker has conflated these — they are not interchangeable.

## Two files, two purposes

The coordinator install chain maintains TWO separate JSON files. Confusing them produces wrong-locus fixes and stale-state assertions.

### `setup-state.json` — per-machine setup transient

- **Scope:** the local machine running setup.
- **Lifetime:** transient — rewritten on every `setup.sh` / `/setup` invocation.
- **Purpose:** captures setup-time environment (detected runtime, prerequisite check results, last-run timestamp).
- **Read by:** setup scripts during preflight; doctor skill during diagnostic runs.

### `install-status.json` — declared deployment state

- **Scope:** the project install (intended persistent state).
- **Lifetime:** durable — only mutated by explicit install/uninstall operations.
- **Purpose:** declares which plugins / agents / hooks are installed and at what version.
- **Read by:** runtime agents needing to know "is X installed here?".

## Comparison

| Field/Property | `setup-state.json` | `install-status.json` |
|---|---|---|
| Lifetime | Transient (per-setup-run) | Durable (per-install) |
| Mutator | `setup.sh`, `/setup` | install/uninstall commands |
| Authoritative for | "what does setup see on this machine right now?" | "what is declared installed here?" |
| Safe to delete | Yes — will be regenerated | No — loses install ledger |

## Disambiguation rule

When citing install state in a plan or lesson, name the file explicitly. Bare references to "install status" are ambiguous; prior-art-checker should flag them.

## Known distinctions — prior-art checker corpus notes

**`~/.holodeck/setup-state.json` vs `~/.claude/holodeck/install-status.json` are distinct files by design** (2026-05-08 claude-unreal-holodeck). `~/.holodeck/setup-state.json` is the Wave-4 persistent mode state file; `~/.claude/holodeck/install-status.json` is per-run telemetry from agentic-install-hardening. Checker corpora and prior-art lookups must document both as canonical separately. Conflating them produces false Conflict findings.

**`status_phase_skip` vs `status_phase_end status=skip` have distinct semantics** (2026-05-07 self). `status_phase_skip` is an explicit opt-out; `status_phase_end status=skip` is an idempotency-done branch. Both are valid in the current codebase per Patrik WAVE2H F8 (9 idempotency-done sites + 7 explicit-opt-out sites in `holodeck_setup.sh`). Prior-art tooling must distinguish the two forms to avoid miscalling the idempotency form a violation.
