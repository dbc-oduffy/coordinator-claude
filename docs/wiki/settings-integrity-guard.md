# Settings-Integrity Guard

> SessionStart hook that auto-recovers a clobbered user `settings.json`.
> Script: `hooks/scripts/guard-settings-integrity.py`. Registry: `coordinator/docs/wiki/coordinator-tripwires/` § `SETTINGS-INTEGRITY-GUARD`.

## The failure mode

`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json` is intermittently truncated to a near-empty stub — typically down to a single key:

```json
{ "skipDangerousModePermissionPrompt": true }
```

The casualty is the `enabledPlugins` block (and `extraKnownMarketplaces`). When it vanishes, **every plugin goes dark**: coordinator doctrine, deep-research, game-dev, example-game-repo, project-rag. The session keeps running, just degraded — no coordinator hooks, no MCP, no domain agents — and the operator usually only notices when something that should work silently doesn't. This has been hand-recovered multiple times in git history before this guard existed.

The trigger mechanism is not fully pinned — candidates are a CRLF/autocrlf race (git has warned "LF will be replaced by CRLF" during hand recovery), a harness rewrite of the settings file, or a concurrent-session write race. The guard is deliberately **mechanism-agnostic**: it recovers from the observable end-state regardless of cause.

## Why a separate hook from the dropped-tracked-files check

That sibling hook detects unstaged worktree **deletions** (`git ls-files --deleted`). A clobber is a **modification** (truncation) — the path is still present and tracked, so it slips past the deletion detector entirely. Different signal (truncation vs. deletion), different remedy (auto-restore vs. warn).

## Why it lives in the plugin, not in `settings.json`

A guard configured inside `settings.json`'s own `hooks` block would be wiped by the very clobber it exists to catch. Plugin hooks load from the plugin manifest (`hooks/hooks.json`), so this guard survives a settings stub. This is the load-bearing architectural constraint.

## Why it protects every session (not just `cwd=~/.claude`)

The file at risk is always at the fixed config path, independent of the session's working directory. The guard targets that path, and its primary restore source (the snapshot) is cwd-independent — so a session opened in any project still gets the guard. The git-HEAD fallback is the only cwd-sensitive piece, and it degrades gracefully (a non-`~/.claude` cwd simply means the snapshot path is used instead).

## Mechanism

Runs at `SessionStart` (matcher `startup|clear|compact`), first in the block so recovery precedes other hooks. Always exits 0; never blocks session open.

**Health predicate** — one `jq -e '(.enabledPlugins | objects | length) > 0'`. A single call covers corrupt JSON, a stub, and a genuinely-empty plugin set (`jq -e` exits non-zero on parse error / false / null / no-result). The `objects` filter is load-bearing: it drops non-object values, so a garbage scalar such as `"enabledPlugins": "false"` (string length 5 > 0) is correctly classified UNHEALTHY rather than passing as healthy and overwriting the good snapshot. A non-empty object whose values are all `false` deliberately reads *healthy* — requiring a `true` value would false-restore over a user who has legitimately disabled every plugin (a worse failure than the all-disabled-clobber it would catch, which is not an observed shape).

**On a HEALTHY boot:** refresh the snapshot `.settings-last-good.json`, but only when content actually changed (`cmp -s`) — no mtime churn, no needless writes. Concurrent identical writes are harmless (same content, atomic `mv`).

**On an UNHEALTHY boot:** restore, in priority order —
1. `.settings-last-good.json` snapshot (cwd-independent; works on OSS installs where `~/.claude` is not a git repo).
2. git `HEAD:./settings.json` of the config dir — fallback when no usable snapshot exists yet and the config dir is a git repo with a healthy commit. (Materialized to a temp file before health-checking — never piped into `jq` via `/dev/stdin`, which is unreliable on Git-Bash.)

The clobbered file is saved to `.settings-clobbered.bak` (forensic, for root-cause work) before being overwritten — but that backup is **best-effort** (`|| true`): a failed backup (read-only path, lock, full disk) must never short-circuit the actual restore, or the user would be left clobbered *and* unrecovered. A loud banner is then emitted. It's phrased as an agent `Action:` directive (matching the dropped-tracked-files check), because SessionStart stdout becomes additionalContext the *agent* reads — so it instructs the agent to surface the event to the PM and recommend `/reload-plugins`: **this session already loaded the broken file at boot**, so the on-disk fix only takes effect on reload.

## No-snapshot-no-opinion

The snapshot is both the restore source *and* the evidence that "this install previously had plugins enabled." A genuinely minimal install (0 enabled plugins) never writes a snapshot, so it never triggers a false restore — absent a healthy snapshot/HEAD, the guard only WARNS. This property is what makes auto-restore (rather than warn-only) safe to default on, and it's why the guard is exempt from the `design-as-offers` warn-don't-act default: recovering a corrupt config from a known-good copy is a deterministic repair (fsck-shape), not a judgment nudge.

## Runtime artifacts

Both gitignored (`.gitignore`), regenerated automatically, never committed:
- `.settings-last-good.json` — last known-good snapshot.
- `.settings-clobbered.bak` — most recent clobbered copy (forensic).

The atomic-write temp files (`settings.json.tmp.*`, `settings.json.head.*`, `.settings-last-good.json.tmp.*`, `.settings-clobbered.bak.tmp.*`) are also gitignored — they exist only between a `cp` and its `mv`, but a hook killed on the 5 s timeout or a mid-restore crash could orphan one, and under this repo's track-everything policy an un-ignored orphan could be swept into a blanket commit.

## Known limitations

- **Symlinked `settings.json` (restore path only).** If a user symlinks `settings.json` to a dotfiles source, a *restore* replaces the symlink with a regular file (the atomic `mv` swaps inode), detaching it from the managed source. This only happens after a clobber (when recovery outweighs topology), and never on a healthy boot (healthy boots write only the snapshot, never `settings.json`). Accepted tradeoff in favor of atomicity.
- **Snapshot is most-recent-healthy, not best-healthy.** Under concurrent sessions with *different* healthy configs, the later boot's config becomes the snapshot. Benign in the meta-repo (one canonical `settings.json`); a lean-but-healthy variant could be restored in place of a richer one.
- **Partial clobber.** The predicate keys on `enabledPlugins`; a hypothetical truncation that *keeps* a stale `enabledPlugins` but drops `env`/`permissions`/`extraKnownMarketplaces` would read healthy and could refresh the snapshot from the partial file. Not an observed shape (the real clobber is total), and tightening the predicate further risks false-positive restores — so it is left as the single robust signal.
- **Relocated config dir + `.gitattributes`.** The `eol=lf` pin is root-anchored; if `CLAUDE_CONFIG_DIR` points into a subdir of a larger repo, the pin does not cover it. The runtime guard is mechanism-agnostic and still protects that case; only the complementary EOL hardening is scoped to the meta-repo layout.

## Complementary hardening

`.gitattributes` pins `/settings.json` and `/settings.local.json` (root-anchored) to `text eol=lf`, so autocrlf does not rewrite line endings on every checkout. This addresses one plausible clobber mechanism (EOL churn) directly; it is insurance, not the primary fix — the guard recovers regardless of cause.

## Testing

5-branch coverage run manually in throwaway `CLAUDE_CONFIG_DIR` dirs (healthy→snapshot; clobber+snapshot→restore; clobber+git-HEAD→restore; clobber+nothing→warn-only; idempotent re-run→no churn). ShellCheck-clean. The `scan-addon-health.py --red-and-stale` SessionStart-hook-existence probe auto-covers this script via its `hooks.json` declaration.

## Cross-references

- The dropped-tracked-files check — sibling guard for worktree deletions.
- `docs/wiki/plugin-session-start-hooks.md` — SessionStart hook authoring rules this guard follows.
- `coordinator/docs/wiki/coordinator-tripwires/` § `SETTINGS-INTEGRITY-GUARD` — registry entry.
- `docs/wiki/tracked-machine-local-corruption-incident.md` — the incident where this guard's
  own `.settings-last-good.json` snapshot was found tracked and, because the health predicate below
  never validates hook-path shape, had snapshotted a foreign-machine config as "known good"
  (defeating § Runtime artifacts above; see that page's § 4). Separately, this guard sat wired to
  nothing in `hooks.json` despite passing tests (§ 5 of that page) — and **still does not run on
  this machine even now that it's registered**, because `hooks.json` is not the surface that
  delivers hooks here (see `external-plugin-live-resolution.md § Hook-delivery`) and
  `settings.json`'s own hooks block, the surface that does deliver, has been deliberately stripped
  to stop the bricking. Registration is not delivery — do not read the `c12623534` wiring as this
  guard being live.
