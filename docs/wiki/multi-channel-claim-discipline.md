---
title: Multi-Channel Claim Discipline
status: active
kind: doctrine-wiki
created: 2026-06-14
provenance: example-game-workbench-repo state/lessons.md L35 (2026-06-14)
---

# Multi-Channel Claim Discipline

Cross-cutting infrastructure problems usually live on more than one channel — Python, TypeScript, shell, native code, CI, docs. A changelog claim like *"X is suppressed/fixed/done"* that names a *feature* without enumerating *channels* over-claims coverage at the language-agnostic altitude: readers reasonably infer the residue doesn't exist, when in fact one or more channels were never addressed. The discipline below scopes claims by channel, makes residue visible, and prevents the next reader from inheriting a false-coverage handoff.

## Rule

When claiming that a cross-cutting infrastructure problem is *fixed / suppressed / done* in a changelog, release note, completion entry, or handoff: **scope the claim by CHANNEL, not by FEATURE name.** Enumerate every channel the problem can manifest on and either (a) name it as covered with a `file:line` or commit reference, or (b) name it as explicit-deferred. Silent residue on an unnamed channel is the failure mode.

## Case — console-popup suppression (example-game-workbench-repo, 2026-06-14)

The 2026-05-30 daily-changelog claimed *"Windows console-popup suppression — 4 deployment roots."* Audit on 2026-06-14 found:

- 240 unsuppressed `.sh` python/node spawns in the example-game-repo repo
- 10 more in coordinator-claude
- No `spawn-hidden.sh` helper, no shell-spawn annotation doctrine

The 2026-05-30 framing was *true for the channel it named* — Python `CREATE_NO_WINDOW` and TS `windowsHide` were genuinely landed. But "console popup" is a *language-agnostic symptom*: it has three channels (Python subprocess, TS child_process, shell-spawn), and only two were addressed. The shell channel was unaddressed and invisible to readers who took the changelog at face value. The 230-site retro-fit shipped as Waves 2-5 of a separate workstream (`state/handoffs/2026-06-14_115639_example_game_repo-shell-channel-console-flash-suppression.md`). (case: example-game-workbench-repo 2026-06-14)

## Discipline

At fix-time, enumerate the channels for any cross-cutting infrastructure claim. The general failure mode is *N-1 channels solved, framed as solved-period because the residue is invisible to the team that fixed the named channels.* A few channel taxonomies that recur:

| Symptom | Channels |
|---|---|
| Console popup on Windows | Python subprocess (`CREATE_NO_WINDOW`); TS / Node (`windowsHide`); shell-spawn (`spawn-hidden.sh` / `start /b`) |
| CRLF normalization | `.gitattributes` rule; existing-tree `git add --renormalize`; editor config; CI checkout flag |
| Path resolution for sibling repos | Python helper; shell `$REPO_*` env vars; PowerShell `$env:REPO_*` |
| "All hooks fail-loud on missing dep" | PostToolUse hooks; PreToolUse hooks; SessionStart hooks; pipeline hooks |
| Secrets redaction | Logs; error messages; telemetry; crash reports; agent transcripts |

**Format for the claim:**

```
console-popup suppression — channels: Python ✓ (CREATE_NO_WINDOW, commit abc1234);
TS ✓ (windowsHide, commit def5678); shell ✗ (deferred to <handoff-path>)
```

The explicit ✗-with-pointer is what prevents the next reader from inheriting a false-coverage handoff.

## When to invoke

- Writing a changelog entry for an infrastructure fix that crosses language/runtime boundaries.
- Drafting a release note or completion entry for a cross-cutting suppression / migration / contract change.
- Closing a workstream where the named symptom is observable in more than one runtime.
- Reviewing a peer's changelog claim that names a *feature* (console popup, secret redaction, path normalization) without naming *channels* — flag and request the channel breakdown.

## Related

- [`completion-log-release-loop.md`](completion-log-release-loop.md) — completion entries are the canonical surface where channel-scoped claims land for downstream readers.
