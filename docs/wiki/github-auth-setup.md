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

## Tier 1 — 1Password SSH agent (interactive machines)

One vault-backed SSH key, synced across all machines, biometric unlock, no plaintext keys on
disk, no PAT rotation — and the same key signs commits. This is **opt-in**: coordinator users
without 1Password ignore it entirely; nothing breaks without it.

### Automated setup

```bash
# interactive (default) — offers each change, declinable
bash scripts/setup-github-auth-1password.sh
# report current state, change nothing
bash scripts/setup-github-auth-1password.sh --check
# accept every offer (e.g. provisioning a known-good machine)
bash scripts/setup-github-auth-1password.sh --yes
```

`scripts/setup-github-auth-1password.sh` is idempotent and consent-gated. It:

1. **Detects 1Password** — `op` CLI, the SSH agent socket, and `op-ssh-sign`. Offers
   `brew install 1password-cli` if the CLI is absent. **No-ops with a clean exit** if the
   desktop agent isn't present (the not-a-1Password-user case).
2. **Routes GitHub SSH over `ssh.github.com:443`** in `~/.ssh/config`, pointed at the 1Password
   agent (see port-22 note below).
3. **Configures SSH commit signing** globally via `op-ssh-sign` (`gpg.format=ssh`,
   `commit.gpgsign=true`, `user.signingkey=<agent key>`, plus an `allowed_signers` file so
   `git log --show-signature` verifies locally).
4. **Offers to flip the current repo's `origin`** from HTTPS to `git@github.com:`, verifying
   `git ls-remote` over SSH before keeping the change (reverts on failure).

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
`setup-github-auth-1password.sh` helper targets macOS/Linux; on Windows follow that gotchas doc.

## Relationship to the `clone_auth` preflight probe

`scripts/lib/prereq_probe.sh::_co_probe_clone_auth` (run by install Step Zero) is the read-only
**detector** — it asserts *some* non-interactive GitHub auth path exists (gh → SSH → credential
helper) and WARNs advisory if none do. This doc + the setup script are the **fixer** for the
Tier-1 case. The probe stays auth-method-agnostic; the 1Password path is one way to make it pass.

## See also
- `install-surface-completeness.md` — why a fresh-machine credential path must be wired at install
- `machine-local-registry.md` — why secrets don't live in the registry
- `claude-code-platform-gotchas.md` — Windows 1Password SSH agent specifics
