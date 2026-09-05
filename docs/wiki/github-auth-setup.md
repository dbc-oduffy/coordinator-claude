# GitHub auth + commit signing — tiered standard

How the coordinator wires git ↔ GitHub credentials so `git push` and the auto-push hook work
non-interactively on a fresh machine, and (optionally) so commits are signed. The standard is
**tiered**, not "one method everywhere" — the right credential path depends on whether the
machine has an interactive desktop session.

> **Why this exists.** A fresh macOS machine failed its first `git push` with
> `fatal: could not read Username for 'https://github.com': Device not configured` — the HTTPS
> remote had no credential helper wired to the `gh` token, git fell back to a username prompt,
> found no tty, and died. Textbook install-surface-completeness (`install-surface-completeness.md`):
> a credential path that was never wired, caught at first push instead of at install.

## The two tiers

| Tier | Machine | Auth | Signing |
|---|---|---|---|
| **1 (default)** | interactive dev machine | 1Password SSH agent (this doc) | SSH signing via `op-ssh-sign` (optional) |
| **2** | headless (cron / CI / RemoteTrigger) | token HTTPS — `gh auth setup-git` or a scoped PAT | none |

**Tier 2 is not optional for headless boxes.** The 1Password SSH agent needs the desktop app and
an interactive unlock — it does **not** work headless. The auto-push hook, cron loops, and any
RemoteTrigger flow depend on a non-interactive path, so headless machines keep token-based HTTPS.

### Tier 1 blind spot — the idle-lock window (interactive machine, intermittent `publickey`)

Even on an interactive Tier-1 machine, the async **auto-push hook fires unattended** — it can land
minutes after you've stepped away. The 1Password agent auto-locks on idle (default policy: keys
served only while unlocked, absent `~/.config/1Password/ssh/agent.toml`). If the hook fires during
a locked window, ssh has no on-disk key to fall back to (Tier-1 machines keep none) and GitHub
returns `git@ssh.github.com: Permission denied (publickey)`.

- **Tell:** a *contiguous cluster* of `publickey` rows in `.git/push-failures.log`, **bracketed by
  successful pushes** (a row that reached `non-fast-forward` got past auth). Auth worked → failed
  for a stretch → worked again = a locked-vault interval, not a config breakage. This is NOT the
  Windows ssh-binary-selection trap (`bash-on-windows-gotchas.md`) — the ssh binary + `IdentityAgent`
  are correct here; the failure is credential *availability*, not binary selection, so a
  `core.sshCommand` pin does not help.
- **No commits are lost.** `git push` is cumulative — the next successful push (interactive, or the
  next commit's hook once the vault is unlocked) carries every pending commit. Real exposure is only
  a machine crash *during* the locked window. The `AUTO-PUSH-MID-SESSION-DETECT` alarm reads scarier
  than the actual data risk.
- **Mitigations** (give the unattended hook a credential that does not need an interactive unlock):
  (a) **keychain-HTTPS** — `git config credential.helper osxkeychain` + a PAT stored once in the
  login keychain (the keychain serves background processes without approval); (b) a **dedicated
  on-disk hook deploy key** via `git config --local core.sshCommand 'ssh -i ~/.ssh/hook_ed25519
  -o IdentitiesOnly=yes'` (key registered on GitHub as a deploy key); or (c) relax the 1Password
  idle-auto-lock on trusted dev machines. (a) is the least-surprising cure.

**Adopted cure — HTTPS remote + OS credential store (cross-platform).** The chosen fix moves the
repo's `origin` to HTTPS so the unattended hook authenticates from the OS credential store (which
serves background processes with no interactive unlock) instead of the human-gated SSH agent. This
is the same mechanism the Tier-2 headless path already uses — not a mac-only hack — and it leaves
commit signing untouched (SSH signing via 1Password is independent of push transport). Per-OS form
of the *identical* design:

| OS | Credential helper | Flip command |
|---|---|---|
| macOS | `osxkeychain` (+ `gh auth git-credential`) | `git remote set-url origin https://github.com/<owner>/<repo>.git` |
| Windows | Git Credential Manager (`manager`) / `wincred` | same `git remote set-url … https://…`; GCM ships by default on Git-for-Windows |

The gh token (scope `repo`) already in the keyring/keychain serves the push; no new PAT is needed if
`gh auth status` shows a `repo`-scoped token. Reverse with `git remote set-url origin
git@github.com:<owner>/<repo>.git`. Validate **live on both platforms** (DR-076 / both-platform
discipline) — a `git ls-remote origin` + a real push must authenticate with the SSH agent
unreachable. Fleet note: other `work/*` repos hitting the same idle-lock symptom flip identically;
the engine (`coordinator_core/hooks/auto_push.py`) is protocol-agnostic and needs no change.

## Tier 1 — 1Password SSH agent (interactive machines)

One vault-backed SSH key, synced across all machines, biometric unlock, no plaintext keys on
disk, no PAT rotation — and the same key signs commits. This is **opt-in**: coordinator users
without 1Password ignore it entirely; nothing breaks without it.

### Automated setup

```bash
# interactive (default) — offers each change, declinable
python3 scripts/setup-github-auth-1password.py
# report current state, change nothing
python3 scripts/setup-github-auth-1password.py --check
# accept every offer (e.g. provisioning a known-good machine)
python3 scripts/setup-github-auth-1password.py --yes
```

`scripts/setup-github-auth-1password.py` is idempotent and consent-gated. It:

1. **Detects 1Password** — `op` CLI, the SSH agent socket, and `op-ssh-sign`. Offers
   `brew install 1password-cli` if the CLI is absent. **No-ops with a clean exit** if the
   desktop agent isn't present (the not-a-1Password-user case).
2. **Routes GitHub SSH over `ssh.github.com:443`** in `~/.ssh/config`, pointed at the 1Password
   agent (see port-22 note below).
3. **Configures SSH commit signing** globally via `op-ssh-sign` (`gpg.format=ssh`,
   `commit.gpgsign=true`, `user.signingkey=<agent key>`, plus an `allowed_signers` file so
   `git log --show-signature` verifies locally).
4. **Historically offered to flip the current repo's `origin`** from HTTPS to `git@github.com:`,
   verifying `git ls-remote` over SSH before keeping the change (reverts on failure). **Superseded
   by the Adopted cure above:** the standing posture is the opposite direction (SSH → HTTPS, so the
   unattended auto-push hook survives the 1Password idle-lock window — see § Tier 1 blind spot). Do
   not run this step, and do not let the script flip a repo already on HTTPS back to SSH; treat any
   remaining SSH-flip offer in the script as a bug to fix at the script, not a step to follow.

**Prerequisite — enable the agent in the desktop app** (the one GUI step the script can't do):
1Password → Settings → Developer → *Use the SSH agent* and *Integrate with 1Password CLI*. The
GitHub SSH key must exist in the vault and be registered on GitHub as **both** an *Authentication*
key and a *Signing* key (`https://github.com/settings/keys`) — the latter for the verified badge.

### Port 22 is blocked on many networks

Bare `git@github.com:` SSH uses port 22, which corporate / cafe / some home networks silently
drop (`ssh: connect to host github.com port 22: Operation timed out`). GitHub serves the same SSH
protocol on `ssh.github.com:443`. The setup script writes this into `~/.ssh/config`:

```
Host github.com
	Hostname ssh.github.com
	Port 443
	User git
	IdentityAgent "<1Password agent socket>"
```

Standard `git@github.com:owner/repo.git` remotes then route over 443 transparently. This is the
default the script applies — it costs nothing on networks where 22 is open and rescues the ones
where it isn't.

### Signing-key selection

If the agent holds one key it's used automatically. With several, set
`COORDINATOR_GH_SIGNING_KEY` to a **fixed substring of the key's comment** (the label you gave it
in 1Password, e.g. `GitHub`) — it is matched literally (`grep -F`), not as a regex or fingerprint,
and must not contain newlines. If the substring matches more than one key the script **fails loud
and lists the matches** rather than guessing — this holds for both the env-var and the interactive
selection paths. The comment is stripped before the key is written to `user.signingkey` /
`allowed_signers`, so a comment containing spaces won't corrupt those files.

## Tier 2 — token HTTPS (headless machines)

```bash
gh auth setup-git
```

This wires `credential.https://github.com.helper = !gh auth git-credential`, so git serves the
`gh` token for all github.com HTTPS operations non-interactively. The token lives in the OS
keyring (gh-managed, no manual rotation). This is the headless default and the recovery path when
1Password isn't available.

**Raw PATs are the last resort, not the baseline.** A PAT does **not** belong in
`machine-local/` (that registry is config, not a secret vault — see `machine-local-registry.md`).
If a keyring isn't available, register the PAT in the platform credential store / CI secret store,
documented with an expiry. Prefer `gh auth setup-git` everywhere it works.

## Windows

The 1Password SSH agent on Windows uses a named pipe and Git-Bash↔PowerShell routing quirks
apply to both auth and signing — see `claude-code-platform-gotchas.md` for the workarounds. The
`setup-github-auth-1password.py` helper targets macOS/Linux; on Windows follow that gotchas doc.

## Relationship to the `clone_auth` preflight probe

`coordinator_core.install.prereq_probe.probe_clone_auth` (native Python port, claude-klabauter; run by install Step Zero) is the read-only
**detector** — it asserts *some* non-interactive GitHub auth path exists (gh → SSH → credential
helper) and WARNs advisory if none do. This doc + the setup script are the **fixer** for the
Tier-1 case. The probe stays auth-method-agnostic; the 1Password path is one way to make it pass.

## See also
- `install-surface-completeness.md` — why a fresh-machine credential path must be wired at install
- `machine-local-registry.md` — why secrets don't live in the registry
- `claude-code-platform-gotchas.md` — Windows 1Password SSH agent specifics
