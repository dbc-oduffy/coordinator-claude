# Linux install friction log — doctrine-side findings, 2026-09-05

Companion to `claude-klabauter/docs/friction/2026-09-05-linux-dogfood.md`, which carries
the engine-side findings and the full environment description. This file records only what
belongs to **this** repo.

**Run.** A from-scratch install of coordinator-claude + claude-klabauter by an agent
following the published INSTALL.md as written, on a Debian container: Linux 6.18 x86_64,
Python 3.11.15, bash 5.2, GNU coreutils, running as **root**, no Homebrew, no GUI, no
keychain, no GPU, Claude Code CLI 2.1.261.

**Headline for this repo: the code is fine; the install narrative is the problem.** A
systematic sweep of `hooks/` (128 files) and `bin/`, `skills/`, `commands/`, `agents/`,
`lib/`, `templates/`, `snippets/`, `subagent-sandbox-policy.yaml` (1289 files) found **no
hard breaks and no latent Linux bugs**. No hardcoded `/Users/` or `/opt/homebrew` paths, no
macOS-only binaries, no BSD-vs-GNU flag hazards (`sed -i ''`, `stat -f`, `date -v`,
`base64 -D`, `find -E` — all absent), all 125 hook scripts on `#!/usr/bin/env python3`,
`Path.home()` rather than bare `expanduser`, Windows-only constants reached through
`getattr`, and case-folding used deliberately and only for Windows path comparison with
comments noting Linux is case-sensitive. `subagent-sandbox-policy.yaml` turned out to carry
no filesystem path allowlist at all, so there is no `/Users`-vs-`/home` asymmetry to find.
This is a good result and worth stating plainly.

Everything below is documentation, sequencing, or a message that misdescribes the state of
the box.

---

## 1. The documented install order contradicts itself

`README.md` § Quick Start:

> 1. Install this plugin. 2. **Restart Claude Code.** 3. Run `/coordinator:install`.
> 4. Install the engine. 5. Run `/coordinator:setup`. 6. Run `/coordinator:repo-setup`.

`commands/install.md` § Requirements:

> **Sequence, exactly:** (1) clone the engine repo; (2) run this coordinator install;
> (3) **restart Claude Code**; (4) only then run the engine repo's own installer.

The restart sits on opposite sides of `/coordinator:install`, and both documents describe
their own ordering as load-bearing (the README calls it "the single thing most likely to
break a new install"). They cannot both be followed. `install.md`'s list also omits the
plugin install itself, starting at the engine clone.

Mechanically the README looks right — `/coordinator:install` is a plugin-provided slash
command, so the plugin must be loaded, which requires the restart first. But `install.md`'s
step (3) may be intended as a *second* restart before the engine installer, in which case
the fix is to say so rather than to reorder. **Not changed here**: picking one is a
doctrine call, not a portability fix. Flagging it because it is the first thing a fresh
agent trips over.

## 2. The documented install cannot be completed by the actor it addresses

The README's Quick Start opens with *"You don't install this — your agent does"* and gives
the agent a paste-ready prompt. But step 2 is "restart Claude Code", and steps 3, 5 and 6
are slash commands that **only exist after that restart**, because plugins load at boot. A
running agent cannot restart its own session, so it cannot reach steps 3–6 of the procedure
written for it.

In this run everything from step 3 onward had to be driven by reading `commands/install.md`
and executing its fences by hand. That worked, but it is a fair amount of inference for an
"amnesiac" agent, and `install.md` is written as doctrine for a session that has the plugin
loaded — it assumes `${CLAUDE_PLUGIN_ROOT}` and a resolved `ENGINE_ROOT` in its POSIX
preamble, neither of which is set for a shell running before the restart.

Worth either (a) giving the agent an explicit no-slash-command path for each of steps 3, 5
and 6, or (b) framing the Quick Start as human-driven with agent-assisted parts, rather
than as a task an agent can complete unattended.

## 3. `repos.doe_claude` is never set, and its remediation cites a step that no longer exists

The engine installer reports:

> `doe_root_pointer: skipped (repos.doe_claude not resolved — complete step 3.5a first)`

There is no §3.5a in the shipped `commands/install.md` — Phase 7 ends around line 389, and
`bin/ensure-doe-clone.py`'s docstring still cites "lines 731 and 747 of the DoE-claude
source". `docs/safety.md` also still narrates the step as live (§ "3.5a — Clone the DoE repo
(idempotent)"). This is a restructure miss: the citation survived the step's removal.

The key itself is never written on a fresh box. The only writer is Phase 3's *optional
interactive seed prompt*, which is documented as **skipped whenever a registry file already
exists** — and one does, by the time the engine installer runs. So the registry ends up with
`engine.working_repos.doe_claude` (a different namespace) but not `repos.doe_claude`.

Note also that "DoE-claude" is the pre-scrub internal codename for **this repo**, not a third
repo. That is not obvious from the outside, and the message reads as though a missing
dependency needs cloning.

The engine-side log has the impact analysis; the short version is that the message
("coordinator will NOT load in any interactive session") considerably overstates it — the
plugin loads fine, the resolution ladder has five other rungs, and what actually breaks is
the `claude()` shell shim plus the doctrine-maintainer CLIs that insist on the canonical key.

**Actions for this repo:** fix the §3.5a citations in `bin/ensure-doe-clone.py` and
`docs/safety.md`, and decide where `repos.doe_claude` should be auto-seeded from the plugin
root (Phase 3 of `commands/install.md`, or the SessionStart self-heal hook that already
maintains `engine.working_repos.doe_claude`).

## 4. Linux is documented almost entirely by omission **[partially patched]**

Windows gets a shell-environment table, an App-Execution-Alias workaround, and a Defender
process-exclusion section. macOS gets Homebrew guidance throughout. Linux is addressed by
implication — correct almost everywhere, but never affirmatively.

Two places where that had teeth, both fixed here:

- `docs/safety.md` named `brew` and `winget` as the package managers `/coordinator:install`
  may invoke with consent, and never named apt/dnf. A Debian box hitting a missing
  prerequisite got no remediation path at all. **[patched]** — now names the platform's
  package manager generically, with the Linux options enumerated.
- `bin/doctor-probes.toml` P-20 (bash < 4) offered only `brew install bash` and
  `/opt/homebrew`-shaped PATH advice. Inert on Debian, where the probe would only fire on a
  genuinely old distro. **[patched]** — now also names `apt-get`/`dnf` and `/usr/bin`. The
  sibling P-19 probe already listed both, so the two were inconsistent.

Left alone: the Windows-specific sections themselves. They are not wrong, and adding "N/A on
Linux" markers everywhere would be noise. The asymmetry is worth knowing about rather than
mechanically erasing.

## 5. Smaller observations

- **`_sentinel_write_guard.py` case-folds sentinel names unconditionally** (lines ~113–125).
  Its own docstring justifies this by the read side's `os.path.isfile()` being effectively
  case-insensitive on APFS. On ext4 that read is case-*sensitive*, so the guard is stricter
  than it needs to be and will deny a write to a genuinely distinct file differing only by
  case. Over-blocks, never under-blocks — not a safety issue, and not worth changing without
  evidence of a real false positive. Noted so the reasoning is on record.
- **`derive-global-doctrine-live-copy.py:68`** says "Portability: macOS + Windows" where its
  sibling `derive-setup-copies.py:68` says "macOS + Windows + Linux". The code is fine on
  Linux (and its strict `Path.resolve()` equality is more correct on ext4 than on APFS);
  only the docstring is short a platform.
- **`_prompt_surface_citations.py:281`** cites `DR-166-require-bash4-on-macos.md`. Inert
  citation-matching prose, listed only for completeness.

---

## What would have made this run clean

1. Reconcile §1 — one stated ordering, in both files.
2. Address §2 — either give the agent a slash-command-free path, or stop addressing the
   Quick Start to an agent that cannot finish it.
3. Fix the §3.5a citations and auto-seed `repos.doe_claude` (§3).
