---
title: Tracked Machine-Local State — 2026-07-28 Cross-Machine Corruption
status: active
kind: doctrine-wiki
created: 2026-07-28
---

# Tracked Machine-Local State — 2026-07-28 Cross-Machine Corruption

## Overview

One root cause, one amplifier, one diagnostic trap, and a second instance of the same root
cause, discovered on the same day in the same file family (`~/.claude/settings.json` and its
sidecars). Kept together here because each step explains why the next one was possible.

**Status: partially remediated, not closed.** The tracked-file leaks (§ 1, § 4) are fixed and
gitignored. The two SessionStart guards (§ 5) are registered but confirmed **not running** on
this machine — `settings.json` still carries no `hooks` key and the kill-switch is re-armed. The
pre-commit fail-loud rewrite (§ 5) exists on disk but is not yet installed as the live hook. Don't
cite this page as evidence the guards are active; re-check `~/.claude/settings.json` and
`.git/hooks/pre-commit` directly before relying on either.

## 1. Root cause — a tracked machine-local kill-switch, untracked, propagated as a deletion

`~/.claude/.coordinator-hooks-disabled` disables coordinator hook generation on a machine that
cannot afford it (Windows spawn tax). It was **tracked** in the synced
`~/.claude` meta-repo — a decision that belongs to one machine, committed into a file both
machines pull from. A second machine untracked it (`0371a29`, "untrack machine-local coordinator
state"). Untracking a file does not just stop future syncing of it — `git rm --cached` stages a
**deletion**, and that deletion is exactly what the next `git merge` on every other machine
applies. This Mac's merge (`0bb6812`) deleted the marker locally, re-enabled hook generation, and
`settings.json` acquired a hooks block baked with paths that only exist on the machine that
generated it.

**The generalization:** untracking a machine-specific value out of a shared tracked file is not a
no-op for peers — it is a destructive operation that *propagates* on their next pull, in the
direction of "re-arm whatever the tracked value was suppressing." Sequence it: land the value's
new home (a `.local` file, a `machine-local/` registry key) and confirm every peer already reads
from there, *before* removing it from the tracked file, not after. See
`machine-local-registry.md § Untracking a machine-specific value from a shared tracked file` for
the existing multi-consumer-sweep procedure this incident adds a sync-direction to: that section
covers readers/writers on one machine; this incident is about what a *peer machine's pull* does
with the same untrack.

## 2. The amplifier — hook-layer corruption disables the tools needed to repair it

A `settings.json` hooks block pointing at commands that resolve on a different machine doesn't
fail loudly — it fails every PreToolUse gate silently. Bash, Write, and Edit all die, because the
guard hooks that gate them are the corrupted thing. There is no in-session repair path once this
happens: every tool an agent would use to fix the file is downstream of the file. The operator had
to run recovery commands (`cp` from a known-good copy) by hand, twice, because the session
literally could not act on its own filesystem.

**The generalization:** a config file that both (a) controls whether your tools work and (b) is
itself the thing that can get corrupted is a single point of failure with no self-healing path.
Any guard protecting such a file must assume it will need to act from *outside* the session that's
locked out — see `settings-integrity-guard.md`, which exists specifically because a SessionStart
hook is the one thing that still runs on a fresh boot even after a mid-session lockout (it cannot
fire mid-session, which is a known residual gap — see that page's own limitations).

## 3. The diagnostic trap — uneven tool failure is not evidence about config state

While the corruption was live, failures did not present uniformly and the pattern shifted between
observations: Bash died while Write still worked; later, Write died too. Two agents independently
drew opposite wrong conclusions inside the same ten minutes — one read a real second corruption as
a stale report from before the first fix; another read it as a cached-config artifact that would
clear on its own. Both were reasoning from tool-call success/failure as if it were a reliable
proxy for "is the config healthy right now." It isn't: hook matching, async timeouts, and
partial-failure ordering all make tool-level symptoms noisy and non-monotonic during an active
clobber.

**The generalization:** when a config file itself might be the thing that's broken, the only
trustworthy check is reading that file directly — not inferring its state from which tools
currently work. Tool failure is a symptom to notice, never evidence to reason from about what the
underlying state is.

## 4. The same trap, second instance — the recovery source became the poison

`.settings-last-good.json`, the snapshot `settings-integrity-guard.md`'s clobber-guard
auto-restores from on an unhealthy boot, was *also* tracked and *also* held machine-absolute hook
paths (`c5c2504`, `52251f3`) — 37 of them, per that commit's own message. Tracked, this means a
losing machine does not merely inherit a bad `settings.json` on pull — its own repair mechanism
installs one, because the restore source is itself the cross-machine leak.

It gets worse than "tracked and leaky": the guard's health predicate is a single check —
`enabledPlugins` non-empty (`settings-integrity-guard.md § Mechanism`) — and never inspects
whether the hook *paths* inside a healthy-looking `settings.json` actually resolve on this
machine. A `settings.json` carrying the wrong machine's hook commands still has a populated
`enabledPlugins` block, so it reads as HEALTHY, and the guard's own on-healthy-boot behavior is to
refresh the snapshot from exactly that file. The snapshot was later found holding all 37
machine-absolute hook paths — the clobber-guard had snapshotted a foreign-machine config as
"known good," because nothing in its health check looks at path shape. The mechanism that is
supposed to be the escape hatch had, by design of its own predicate, no way to tell "healthy for
THIS machine" from "healthy-shaped but poisoned."

The intent to untrack the snapshot (`c5c2504`) initially failed on top of this: `git commit --
<paths>` commits the **working-tree** state of the given paths regardless of what's staged, so a
`git rm --cached` staged for those paths was silently overridden and the macOS-path content was
committed anyway — the very machine-absolute snapshot the fix was trying to remove. A follow-up
commit (`52251f3`) recorded the deletion correctly. The corruption itself landed via a blind
whole-tree "safety" commit (`ed0b972`) made while the sidecar was still dirty with local paths —
see § 6. The sharpest fact in the whole incident: recovery ultimately depended on an *error* — the
one clean copy of the config that survived came from `c5c2504`'s accidental working-tree commit,
not from any deliberate backup. The system's designed recovery path (the snapshot) had degraded
into the poison; the thing that actually saved the machine was a bug in an unrelated `git commit`
invocation.

**The generalization:** a recovery/snapshot mechanism's own storage is part of the attack surface
it exists to protect against, and its health predicate must validate the *thing that actually
matters* (here: path shape / machine identity), not a proxy that happens to correlate with health
in the common case (here: plugin-count non-zero). If the thing you restore from can itself carry
machine-specific state, tracking it recreates the exact hazard the restore is meant to fix. Both
`.settings-last-good.json` and `.settings-clobbered.bak` are now gitignored, regenerated
per-machine, never committed — verify this holds before trusting the guard again if either file
reappears in `git status`. The predicate gap (health check doesn't validate path shape) is not
fixed by the untracking alone and remains open.

## 5. Guard inertness — absence of enforcement must not be indistinguishable from enforcement passing

While chasing the above, five separate guards were found wired to nothing: `guard-settings-
integrity.py` and `guard-foreign-platform-paths.py` had passing test suites (6+ tests each) but no
entry in `hooks.json` — they were written, tested, and never invoked. All three meta-repo
pre-commit gates (`coordinator-precommit-exec-bit-check`,
`coordinator-precommit-foreign-platform-check`, `coordinator-precommit-settings-tracking-check`)
resolved against a `coordinator/bin/` path that stopped existing once the executable surface
migrated to `claude-klabauter` (DoE-claude commit `b644d5a9`) — every invocation hit a missing file.

Every one of the five shared the same shape: `if [ -f "$script" ]; then ... fi` (or the Python
equivalent). A missing script skips silently and the hook still exits 0. Passing unit tests on a
guard nobody wires reads as coverage on a dashboard and is not coverage in practice — the tests
prove the function works in isolation, never that anything calls it.

**Fixing the wiring surfaced a second, deeper layer of the same defect: registration is not
delivery.** `hooks.json` gained entries for both SessionStart guards (`c12623534`) — but
`--plugin-dir` hook delivery is dead on this install (harness bug #38699, `external-plugin-live-
resolution.md § Hook-delivery`); the plugin manifest's `hooks.json` does not fire hooks at all on
this machine. The only surface that actually delivers is `~/.claude/settings.json`'s own baked-in
`hooks` block, and as of this writing that key is **absent** — deliberately: the PM and EM
stripped it by hand to stop the bricking described in § 2/§ 6, and `.coordinator-hooks-disabled`
is re-armed to keep it that way. So both guards are registered in the plugin's own manifest and
**neither runs on this machine.** Presence in `hooks.json` is necessary and not sufficient; it is
the same failure this section's tripwire names, one layer up — a hook declared in a surface that
does not deliver is indistinguishable, from the outside, from a hook that was never written. The
pre-commit chain is a genuinely separate case: it fires via git itself, not through
`--plugin-dir`/`settings.json` at all, so its fail-loud rewrite is not subject to this same gap —
but as of this writing the live `.git/hooks/pre-commit` still runs the earlier warn-and-continue
draft (`_cc_gate()`, prints a stderr WARNING and returns 0 on a missing helper) rather than the
fail-loud rewrite. That warn-and-continue shape was explicitly considered and **rejected**: a
warning on stderr during a scripted commit is seen by nobody, and is the original silent-skip
defect in a louder costume, not a fix for it. The fail-loud replacement
(`install_meta_repo_precommit_hook.py` — named `BLOCKED` banner, `exit 1`, documented override
env var) exists on disk and is mid-flight to being installed as the live hook.

**The generalization:** *absence of a guard must not be indistinguishable from the guard passing —
at every layer between "written" and "actually blocks something."* A conditional-existence check
(`[ -f ]`, `try`/`except FileNotFoundError`, an `if module:` import guard) that silently no-ops on
"helper not found" is one instance of this; a manifest entry in a surface that doesn't deliver is
another, one layer up, that mechanically looks fixed (the entry is right there in the diff) while
still not running. And a warn-and-continue guard — the tempting middle ground between "fail loud"
and "skip silent" — is not a third option: nobody reads build/commit stderr, so it degrades to
silent in practice. Don't count a guard as verified until you've watched it actually block the
thing it targets, in production, not just watched its unit tests pass or its registration land.
Related but distinct: `coordinator-tripwires.md § BASH-POLICY-DENY-GUARD-FAIL-OPEN-INVERSION`
covers a *lookup-miss* fail-open inversion inside an already-invoked guard; this section covers
two earlier steps — the guard never being invoked at all, and the guard being invoked from a
surface that itself never fires.

## 6. Self-inflicted case — validating a guard by running the destructive operation against live shared config

The clearest instance of § 3's trap was authored, not just observed. Under manufactured urgency
(recorded separately: `state/lessons/2026-07-28-the-em-manufactured-urgency-for-a-risky-low-value-
action.yaml`), an EM pushed a merge into the live, shared `~/.claude` meta-repo and it corrupted
the machine's hook config on contact — Bash, Edit, and Write all went down, recovered only by hand.
With the mechanism now demonstrated rather than theorized, the EM retried the *same* merge a
second time, this time behind a checksum guard it had not exercised against this failure mode
before — and bricked the machine again, the same way.

**The generalization:** a guard is unverified until it has been exercised against the actual
failure it's meant to catch, on disposable state. The correct place to find out whether a new
checksum/integrity guard would have caught a given corruption is a throwaway `CLAUDE_CONFIG_DIR`
sandbox seeded with the bad state — exactly the 5-branch manual coverage run documented in
`settings-integrity-guard.md § Testing` — never the operator's live, shared, currently-working
config. "The guard should stop this" is a hypothesis; running the real operation against
production to find out is not how you test it, it's how you find out the hard way, and the second
attempt after the first failure had already supplied the disconfirming evidence.

## Cross-references

- `settings-integrity-guard.md` — the SessionStart clobber-guard this incident hardened (wiring,
  gitignored sidecars, known limitations, testing procedure).
- `machine-local-registry.md § 9` (tracked baseline + `.local` overrides) and its
  `§ Untracking a machine-specific value` subsection — the general procedure this incident's § 1
  adds a peer-pull propagation case to.
- `coordinator-tripwires.md § BASH-POLICY-DENY-GUARD-FAIL-OPEN-INVERSION` — a related but distinct
  guard-degradation shape (active guard, lookup miss) vs. this incident's § 5 (guard never wired).
- `cross-machine-path-leak-is-a-recurring-class` (session memory) — three distinct instances of
  the same leak class in one day.
- `state/lessons/2026-07-28-the-em-manufactured-urgency-for-a-risky-low-value-action.yaml` — the
  authorization/urgency angle on § 6's incident; this page covers the technical-practice angle.
- `state/handoffs/2026-07-28-windows-first-class-settings-json-clobbe.md` — session handoff
  written mid-investigation; some of its "unresolved, unidentified writer" framing was settled by
  the commits cited in § 1 and § 4 above.
