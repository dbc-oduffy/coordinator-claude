---
title: Release Cadence and Currency Notification
status: active
kind: doctrine-wiki
created: 2026-06-01
spec: docs/plans/2026-06-01-boot-currency-notification-hook.md
---

# Release Cadence and Currency Notification

> The coordinator plugin ships to OSS consumers as a versioned GitHub release. Two problems follow from that: (a) releases accumulate as drafts with no systematic un-draft cadence, so the Release API's "Latest" drifts behind shipped code; and (b) consumers who installed an earlier snapshot have no passive signal that an update exists. This wiki describes the cadence that keeps the human-facing Release current, and the boot notification hook that delivers the signal. **The machine currency *check* anchors on the latest `v*` git tag, not the Release object** (2026-06-01 alignment with the project-rag host team) — so problem (a)'s drift cannot produce a wrong "behind" signal: the tag advances even when the Release stays drafted. See § Version baseline — `version.txt`.

## Release-Publish Cadence

*2026-06-01, coordinator-claude.*

### What gets tagged — and what does not

**Claude Prime (this meta-repo, `~/.claude`) is `source_is_live` and is never tagged.** The coordinator plugin is authored here but consumed via the OSS publish repos. Tagging the meta-repo would create false release signal on a repo that is not the install surface. Only the OSS publish repos receive version tags:

- `dbc-oduffy/coordinator-claude` — coordinator plugin releases.
- `dbc-oduffy/deep-research-claude` — deep-research plugin releases (spinoff scope; see `tasks/handoffs/2026-06-01_122922_deep-research-currency-notification.md`).

### Primary anchor — `/merge-to-main`

`skills/merging-to-main/SKILL.md` already carries (a) a version-bump suggestion step that proposes `patch / minor / major` based on diff scope, and (b) a skip rule that omits release notes when the merge touches only `tasks/`, `tmp/`, or internal-tracking paths.

The tagged-publish decision rides on these **existing** steps — no new parallel triviality gate:

- When the bump suggestion is **`>= patch`** AND the merge is **not skip-rule-eligible**, the skill proposes a **tagged version bump + GitHub-release un-draft** built on the already-drafted release notes.
- Bump level (`patch / minor`) is an EM-proposed, PM-confirmable call surfaced inline at merge — this is a release/product surface, not a silent EM pick.
- The publish target is `coordinator-claude` (and, after the spinoff ships, `deep-research-claude`). Claude Prime itself is never tagged (`source_is_live`).

> **The `v*` git tag is the load-bearing artifact for currency — push it explicitly.** Since the boot check anchors on the latest `v*` tag (§ Version baseline), the tagged-publish leg cuts and pushes the annotated tag (`git tag -a vX.Y.Z && git push origin vX.Y.Z`) *before* and independent of un-drafting the GitHub Release — un-drafting a release creates the tag only as a side-effect, and only if a draft with that tag_name pre-exists. A released-but-untagged (or release-edit-failed) state would leave every consumer anchored on a stale older tag. The `gh release` un-draft remains for the human-facing changelog; the `git push origin vX.Y.Z` is what advances the currency anchor. → `skills/merging-to-main/SKILL.md` Step 1.5 Part 2 tagged-publish leg.

This makes `/merge-to-main` the tightest cadence path: "Latest" advances per meaningful merge.

### Backstop anchor — `/workweek-complete`

The weekly ceremony (`commands/workweek-complete.md`) already owns "cut a coherent batch" via the version-bump + merge step. A release-publish (un-draft) step there catches any non-trivial work that reached main without a per-merge tag — for example, direct commits on the daily branch that bypassed `/merge-to-main`. Belt-and-suspenders with the per-merge anchor above.

### Summary

| Trigger | Condition | Action |
|---|---|---|
| `/merge-to-main` | bump suggestion >= patch AND NOT skip-rule-eligible | EM proposes tagged version bump + un-draft release |
| `/workweek-complete` | weekly cadence | backstop un-draft of any accumulated draft releases |
| Claude Prime (`source_is_live`) | always | no-op — never tagged |

---

## The Boot Currency-Notification Hook

*2026-06-01, coordinator-claude.*

### Role: push notification, not pull action

`/coordinator-update` (shipped 2026-05-30, `docs/plans/2026-05-30-oss-coordinator-update-skill.md`) is the **pull action** — a PM-invoked verb that fetches the latest release, computes a delta, and advises a path. Consumers only benefit from it if they think to run it.

The boot hook is the **push notification** — a lightweight "are you behind?" check that fires automatically at session start and points the consumer at `/coordinator-update` when an update is available. The hook deliberately does NOT re-implement the delta engine, the clone, or the classifier. It is the toast; `/coordinator-update` is the action the toast points at.

### Software-update-notification semantics

The hook operates with the same three-branch semantics as a desktop software update notification:

| Branch | Condition | Output |
|---|---|---|
| **current** | installed SHA == latest `v*` tag's commit SHA | silent (empty stdout, exit 0) |
| **behind / differs** | installed SHA differs from the latest `v*` tag's commit SHA | one-line stdout banner naming that plugin's own update action (see § Per-plugin action) |
| **offline** | tag source unreachable (DNS failure, timeout, no network, no `v*` tags) | quiet low-key stdout note (validated 2026-06-01: the `additionalContext` JSON shape is NOT honored for SessionStart — only PreToolUse — so the offline branch uses plain stdout like every other SessionStart hook) |

The "behind / differs" framing is intentionally honest: SHA-inequality does not assert "behind" — an install from a `main` clone newer than the latest published tag would get a false-downgrade nag under a directional assertion. The copy reads:

> *"your install differs from the latest published release (`<tag>`) — run `/coordinator-update` to review."*

When ancestry can be confirmed (the local SHA IS a true ancestor of the tag SHA), the directional form `<from> → <to>` is used. When the local SHA is a descendant or diverged, the neutral "differs from" framing is used.

### Per-plugin action

The action the nag points at is **per-plugin**, not always `/coordinator-update` (`_action_hint_for` in the hook script). A nag that names the wrong remedy is worse than no nag:

| Plugin | Honest update action |
|---|---|
| `coordinator` | `run \`/coordinator-update\` to review` — the shipped pull-action reconciles a coordinator install |
| `deep-research` (standalone) | `re-run the deep-research install to update` — a standalone `deep-research-claude` install has **no** `/coordinator-update` equivalent; that verb reconciles only the coordinator footprint (and the bundled deep-research add-on), never a standalone DR clone |

Adding a further plugin = one `PLUGINS_TO_CHECK` entry + one `_action_hint_for` case arm. The `offline`/unknown awareness notes are also plugin-named (`[<plugin> update check] …`). Spinoff: `tasks/handoffs/2026-06-01_122922_deep-research-currency-notification.md` (Leg 1 + Leg 2 option (a)).

### Version baseline — `version.txt`

The hook reuses the `version.txt` baseline planted by `/coordinator-update` Chunk 1 (`dist/publish-repo-setup/install.sh`). The format is a single-line 40-hex SHA, pinned by `cross-repo-handshake-doctrine.md` § Carve-out — **the hook does not change this format**.

**Currency anchor — git tags, not the Release API (2026-06-01 alignment).** "Latest" is the highest-semver `v*` git tag, resolved entirely with `git ls-remote` — the GitHub **Release object** is never consulted by the currency check. To compare, the hook (via `lib/release-currency.sh`):

1. Lists the publish repo's `v*` tags: `git ls-remote --tags <url> 'refs/tags/v*'`.
2. Selects the **highest semver** — major.minor.patch compared numerically, NOT lexically (`v2.10.0 > v2.9.0`; a naive `tail -1` over `ls-remote` ref order picks the wrong tag). BSD-portable: a zero-padded numeric sort key fed to plain `sort`, since GNU `sort -V` is absent on macOS stock.
3. Resolves that tag to its **commit** SHA with `git ls-remote <url> 'refs/tags/<tag>^{}'` — the `^{}` peel dereferences an annotated tag to its underlying commit (an annotated tag's own object SHA is NOT the commit SHA), falling back to the bare ref for lightweight tags. A non-zero `git` exit / empty tag list doubles as the offline signal.
4. Compares the resolved SHA against the installed `version.txt` SHA.

**Why git-tags, not `releases/latest`:** consumers propagate via `git clone` + `/coordinator-update` (git fetch + delta) and never pull a Release tarball, so the Release object was never on the install path. The Release API also **anchors stale**: when a `v*` tag is cut ahead of the next drafted-and-un-drafted Release, `releases/latest` reports the older Release while the code (and tag) have moved on — the realized v2.0.0-anchoring drift this wiki's intro flags. Git-tags can't anchor stale because the tag IS the thing that advances. **GitHub Releases are still cut** for OSS changelog / discoverability (see § Release-Publish Cadence) — only the machine currency *check* moved to git-tags. This matches the mechanism the **project-rag host team** chose, converging the ecosystem on one currency anchor; our reference impl now matches the adopters rather than quietly diverging.

`releases/latest.target_commitish` was never used (it stores the ref name passed at release-creation — typically a branch like `"main"` — not a resolvable SHA); that concern is now moot since the Release API is off the currency path entirely.

### 3-day throttle

The hook throttles to once per 3 days via a per-plugin sentinel line at:

```
${XDG_STATE_HOME:-$HOME/.claude}/.cache/coordinator-currency-check
```

Format: `<plugin> <ISO-date> <last-status>` per line.

**Throttle semantics:**

- If the per-plugin line is **< 3 days old**, skip the network call.
  - If the cached status is `current`: emit nothing.
  - If the cached status is `behind`: re-emit the cached nag (so a behind state keeps nagging across boots without a network call every time).
- If **>= 3 days old** (or absent): perform the live check and update the sentinel.

**Offline results do NOT update the 3-day sentinel timestamp.** An `offline` result at boot either skips the sentinel write entirely (next boot retries the live check) or writes a short-TTL marker (< 1 hour) that is distinct from the 3-day `current`/`behind` cadence marker. This prevents a transient offline boot from silently disabling the check for 3 days.

Most boots are a sub-50ms sentinel file read.

### `source_is_live` no-op

On the authoring machine (Claude Prime, `~/.claude`), where the plugin is `source_is_live` and no `version.txt` exists, the hook resolves this state and exits silently (exit 0, empty stdout). The hook is structurally inert here.

### `startup`-only hook matcher

The hook is registered in `hooks/hooks.json` as a **new** SessionStart matcher group with matcher string exactly `"startup"` — not added to the existing `"startup|compact"` or `"startup|clear|compact"` groups (those fire on compaction too).

Rationale: an update notification is acted on *between* sessions (update, then restart), not mid-flow. Surfacing it after a mid-session compaction is noise while the user is in the middle of work. The 3-day throttle already bounds over-nagging; a long session that compacts without a fresh `startup` gets the nag at its next real start — acceptable for non-urgent advisory.

Hook registration shape:

```json
{
  "matcher": "startup",
  "hooks": [
    {
      "type": "command",
      "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check-plugin-update-currency.sh",
      "timeout": 5,
      "async": false
    }
  ]
}
```

The `timeout: 5` outer budget encompasses sentinel read/write; the inner `timeout 3` wraps the network fetch specifically so sentinel operations complete within the outer budget even on a timed-out network call. The hook ships via `hooks.json` and follows the plugin to consumers (per `claude-code-platform-gotchas.md` — `settings.json` registration does not propagate).

### Per-plugin loop structure

The hook loops over installed plugins and checks each against its own release repo. Two entries are wired: `coordinator → dbc-oduffy/coordinator-claude` (install root = plugin root) and `deep-research → dbc-oduffy/deep-research-claude` (install root = `~/.claude/plugins/deep-research-claude`, env-overridable via `DEEP_RESEARCH_INSTALL_ROOT`). The deep-research entry was added by the spinoff (`tasks/handoffs/2026-06-01_122922_deep-research-currency-notification.md`).

**Per-plugin independence:** each entry checks only if installed (absent `version.txt` → `source_is_live` → silently inert). A missing standalone deep-research never affects the coordinator check, and vice-versa. No cross-partition read — each entry reads only its own release surface and its own install root, per `doctor-probe-design.md` § "Each Doctor Owns Its Own Code-Currency Surface".

> **⚠ Install-surface dependency (deep-research) — baseline must be planted at install, not by publish.** The deep-research nag is honest only if a standalone install's `version.txt` holds a **deep-research-claude** commit. `publish.sh` stamps `version.txt` with the *source meta-repo* HEAD (a placeholder — a different repo's commit than DR's release tags), so a comparison against it mis-fires `differs` forever. Coordinator avoids this because its consumer `install.sh` re-stamps `version.txt = cloned-publish-repo HEAD`; deep-research had no such step.
>
> **Fix (shipped 2026-06-01, coordinator-side):** `/deep-research setup` now plants `version.txt = git rev-parse HEAD` of the install (see `deep-research/commands/setup.md` § 4). `docs/install.md` runs `/deep-research setup` on every install/update path, so the comparable baseline is established consumer-side. **Existing standalone installs resolve the spurious `differs` nag by re-running `/deep-research setup`** (or any `git pull` followed by it). This fix lands in standalone consumers at the next deliberate `/percolate deep-research` (the source change rides the whole-plugin sync); until then the standalone DR check is `source_is_live`-silent, not nagging. No cross-repo memo is involved — `~/.claude` DoE owns both plugins, and the fix is a coordinator-source change to the deep-research plugin's own setup command.

### Push-vs-pull relationship to `/coordinator-update`

| Concern | `/coordinator-update` (shipped 2026-05-30) | Boot hook (this plan) |
|---|---|---|
| Trigger | PM-invoked verb (pull) | SessionStart hook, 3-day throttle (push) |
| Weight | clone + three-way classifier + advisory | one `git ls-remote` for the latest `v*` tag; no clone, no classify |
| Output | overwrite / cherry-pick / plan-to-ingest recommendation + apply | silent / one-line nag / quiet Claude-context awareness |
| Local baseline | plants + reads `version.txt` (40-hex SHA) | reuses the same `version.txt` baseline |
| OSS-only | yes (absent from our tree) | yes — `source_is_live` skip; hook is inert on Claude Prime |
| Scope | coordinator + bundled deep-research add-on | coordinator + standalone deep-research (each names its own update action) |

---

## Cross-link: Doctor-Owned Currency Surfaces

The boot notification hook is the **consumer-side realization** of the seam described in `docs/wiki/doctor-probe-design.md` § [Each Doctor Owns Its Own Code-Currency Surface — No Cross-Partition Reads](doctor-probe-design.md#each-doctor-owns-its-own-code-currency-surface--no-cross-partition-reads).

That section establishes: each repo owns its own code-currency check, surfaced in its **own** doctor — no cross-partition reads of a sibling's git HEAD or version manifest. The symmetric shape: host owns host-currency, addon owns addon + corpus currency, **consumer owns consumer-currency**.

The boot hook is the coordinator consumer's currency surface. It does not reach across into the plugin's source tree to derive freshness — it compares the installed `version.txt` SHA against the latest published `v*` git tag via `git ls-remote` (no auth required for public repos). The coupling is exactly what the seam doctrine specifies: the consumer checks the published artifact surface (the tag), not the sibling's internal state.

## Related

- `docs/plans/2026-06-01-boot-currency-notification-hook.md` — originating plan (problem set, design decisions, the Staff Engineer review findings)
- `docs/plans/2026-05-30-oss-coordinator-update-skill.md` — the pull action this hook points at
- `docs/wiki/doctor-probe-design.md` § Each Doctor Owns Its Own Code-Currency Surface — No Cross-Partition Reads — partition-ownership principle this hook realizes on the consumer side
- `docs/wiki/coordinator-tripwires.md` — network-on-boot throttle invariant registered there
- `tasks/handoffs/2026-06-01_122922_deep-research-currency-notification.md` — spinoff that adds the deep-research entry to the per-plugin loop
- `lib/coordinator-currency.sh` — orthogonal axis (schema-integer onboarding currency, not release-tag currency); must remain separate per its own header note
- `cross-repo-handshake-doctrine.md` § Carve-out — pins the bare-SHA `version.txt` format this hook reads
