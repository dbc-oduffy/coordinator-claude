# percolate-hooks/

Per-target hook scripts run by `~/.claude/setup/publish.sh` before and after each rsync pass.

The discovery mechanism is generic: `publish.sh` iterates whatever directory tree exists under this root. The subdirectories shipped here today (`coordinator-claude/`, `coordinator-claude-toplevel-wiki/`, `deep-research-claude/`) are the PM's hooks for their own targets — reference implementations, not generic infrastructure. Add your own subdirectory per target you register.

## Directory layout

```
percolate-hooks/<target-name>/<hook-point>/<NN-name>.sh
```

- **`<target-name>`** — matches the target name registered in `publish.targets` (machine-local registry at `~/.claude/machine-local/registry.local.toml`) or, on legacy installs, in `~/.claude/setup/publish-targets.sh`. One subdirectory per target.
- **`<hook-point>`** — one of `pre-rsync`, `post-rsync`, `pre-ci`.
- **`<NN-name>.sh`** — scripts inside each hook-point dir are executed in lexical-sort order. Convention: prefix with a two-digit sequence (`10-`, `20-`, `30-`) to control order. Scripts must be executable (`chmod +x`).

Non-`.sh` files (e.g., allowlist text files) may sit alongside the scripts and are ignored by the runner — they exist so scripts can `source` or read them.

## Hook-point contracts

### pre-rsync

Runs before `publish.sh` rsyncs files into the target destination. Use it to:

- Validate source-side preconditions (refuse to publish if a required marker is missing, etc.).
- Back up destination-side state that rsync would otherwise delete (e.g., destination-resident allowlist files — see the `coordinator-claude-toplevel-wiki` example below).
- Set environment variables that later hooks will read.

Exit non-zero to abort the publish run before any files are transferred.

No stdin contract — `pre-rsync` runs before rsync has produced a file list.

### post-rsync

Runs **after** `publish.sh`'s rsync completes. **This is the critical doctrine surface.**

**Stdin contract (load-bearing — per `~/.claude/plugins/coordinator/docs/wiki/post-sync-hook-doctrine.md`):**

`post-rsync` hooks RECEIVE on stdin the list of files actually transferred by rsync — one relative path per line (rsync's `--out-format='%n'`). The hook MUST operate ONLY on those paths in the destination, NEVER tree-walk the destination directory.

Naive tree-walking is the anti-pattern this doctrine exists to prevent. When rsync syncs a delta (e.g., 3 changed files out of 200), a hook that iterates `$DEST_ROOT/**` will mutate all 200 — including operator-customised destination state and files this run had no stake in. Idempotency becomes illusory; output diverges from a from-scratch publish.

Skeleton:

```bash
#!/usr/bin/env bash
set -euo pipefail

: "${DEST_ROOT:?DEST_ROOT must be set by publish.sh}"

while IFS= read -r path; do
    # Operate ONLY on "$DEST_ROOT/$path".
    # Do NOT walk "$DEST_ROOT" independently.
    target="$DEST_ROOT/$path"
    [ -f "$target" ] || continue
    mutate "$target"
done
```

**Read-only checks are exempt.** A `post-rsync` hook that only inspects the destination (grep audit, schema validator, link-checker, structural assertion) may scan the full destination tree — no mutation, no corruption vector. The touched-list constraint is a mutation guard, not a query guard.

### pre-ci

Runs after `post-rsync` completes, before any CI gate (`gh workflow run`, local `pytest`, etc.). Typically validation-only — assert that the published tree is in a shape CI will accept, and exit non-zero to abort if not.

No stdin contract; treat the destination as fully assembled.

## Adding a hook for your own target

1. Register the target first (in `publish.targets` or `publish-targets.sh`) — `publish.sh` will not find hooks for an unregistered target name.
2. Create the subdirectory tree:
   ```bash
   mkdir -p ~/.claude/setup/percolate-hooks/<your-target>/{pre-rsync,post-rsync,pre-ci}
   ```
3. Add `.gitkeep` to empty hook-point dirs if you want to track them in your dotfiles repo.
4. Write your hooks following the contracts above. `chmod +x` them.
5. Dry-run first:
   ```bash
   ~/.claude/setup/publish.sh <your-target> --dry-run
   ```

## What's currently shipped (PM reference implementations)

These subdirectories are the PM's hooks for their own targets. Patterns are reusable; specifics (org slugs, allowlist contents, target names) are not.

- **`coordinator-claude/post-rsync/10-depersonalize.sh`** — rewrites private GitHub org slugs to public ones via `coordinator/bin/depersonalize-for-publish.sh`. The org-slug pairs themselves are operator-specific (see `coordinator/bin/depersonalize-identity.sh` and `~/.claude/setup/.percolate-identity`); the pattern (run a depersonalizer over the touched-file list) is reusable.
- **`coordinator-claude-toplevel-wiki/pre-rsync/10-backup-allowlist.sh`** + **`post-rsync/10-restore-allowlist.sh`** — backs up a destination-resident allowlist file before sync (rsync would otherwise delete it under `--delete`), restores after. Pattern applies to any target that has destination-side state the source repo doesn't own.
- **`coordinator-claude-toplevel-wiki/post-rsync/30-verify-toplevel-wiki.sh`** — target-specific structural validator. Read-only; permitted to walk the destination tree.
- **`deep-research-claude/post-rsync/10-depersonalize.sh`** — same depersonalize pattern, different target.

## See also

- `~/.claude/setup/publish.sh` — the driver that discovers and invokes these hooks.
- `~/.claude/plugins/coordinator/docs/wiki/percolate-setup.md` — full percolation setup procedure (target registration, identity config, first-run walkthrough).
- `~/.claude/plugins/coordinator/docs/wiki/post-sync-hook-doctrine.md` — canonical statement of the touched-file-list stdin contract.

## Out of scope (for this README)

- Registering a target in `publish.targets` — see `percolate-setup.md`.
- `publish.sh`'s own internals — see the script's header documentation.
- Identity configuration (`.percolate-identity`) — see the example file in `~/.claude/setup/.percolate-identity.example`.
