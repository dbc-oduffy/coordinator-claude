#!/usr/bin/env bash
# setup-github-auth-1password.sh — optional, opt-in: wire GitHub auth + commit signing
# through the 1Password SSH agent on an interactive machine.
#
# What it does (all idempotent, all consent-gated):
#   1. Detects 1Password (op CLI, SSH agent socket, op-ssh-sign). Offers to `brew install`
#      the op CLI if absent and the operator agrees. (The CLI is convenience; the desktop
#      agent + op-ssh-sign do the actual auth + signing.)
#   2. Routes GitHub SSH over ssh.github.com:443 in ~/.ssh/config (port 22 is blocked on
#      many corporate / cafe networks) and points it at the 1Password agent.
#   3. Configures SSH commit signing globally via op-ssh-sign (gpg.format=ssh).
#   4. Offers to flip the current repo's origin remote from HTTPS to SSH.
#
# It is a NO-OP (clean exit 0) on machines without 1Password — coordinator users who do not
# use 1Password can ignore it. This is the Tier-1 (interactive-machine) recipe; headless
# machines keep token-based HTTPS (`gh auth setup-git`) — see docs/wiki/github-auth-setup.md.
#
# Usage:
#   setup-github-auth-1password.sh            # interactive (default)
#   setup-github-auth-1password.sh --check    # report state only, no mutation
#   setup-github-auth-1password.sh --yes      # non-interactive: accept every offer
#   setup-github-auth-1password.sh --help
#
# Signing-key selection: if the agent holds exactly one key it is used; if it holds several,
# set COORDINATOR_GH_SIGNING_KEY to a fixed substring of the key's comment to disambiguate
# non-interactively. Multi-match fails loud — never silent-pick.
#
# The final line is machine-readable for the install command:
#   STATUS: github_auth_1password=<present|configured|absent|incomplete|n-a-no-1password>
#
# Portable bash (no bash-4 features, no GNU-isms) so it runs on stock shells.
# --- end help ---

set -u
set -o pipefail

# ---------------------------------------------------------------------------
# args / output helpers
# ---------------------------------------------------------------------------
MODE="interactive"
for arg in "$@"; do
  case "$arg" in
    --check|--check-only|--dry-run) MODE="check" ;;
    --yes|-y|--non-interactive)     MODE="yes" ;;
    --help|-h)
      sed -n '/^# --- end help ---/q; 2,$p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) printf 'unknown argument: %s (try --help)\n' "$arg" >&2; exit 2 ;;
  esac
done

_say()  { printf '%s\n' "$*"; }
_ok()   { printf '  ✓ %s\n' "$*"; }
_skip() { printf '  • %s\n' "$*"; }
_warn() { printf '  ⚠ %s\n' "$*" >&2; }

# Emit the machine-readable status line and exit.
_emit_status_and_exit() {
  # $1 = token, $2 = exit code (default 0)
  printf 'STATUS: github_auth_1password=%s\n' "$1"
  exit "${2:-0}"
}

# Ask a yes/no question honoring MODE. Returns 0 for yes.
_consent() {
  # $1 = prompt
  case "$MODE" in
    check) return 1 ;;          # report-only: never mutate
    yes)   return 0 ;;          # accept everything
    *)
      printf '%s [y/N] ' "$1"
      local reply=""
      read -r reply </dev/tty 2>/dev/null || read -r reply || reply=""
      case "$reply" in [yY]|[yY][eE][sS]) return 0 ;; *) return 1 ;; esac
      ;;
  esac
}

# Validate the optional signing-key selector early — reject embedded newlines.
if [ "${COORDINATOR_GH_SIGNING_KEY:-}" != "" ]; then
  case "$COORDINATOR_GH_SIGNING_KEY" in
    *"
"*) printf 'COORDINATOR_GH_SIGNING_KEY must not contain newlines\n' >&2; exit 2 ;;
  esac
fi

SSH_CFG="$HOME/.ssh/config"
SSH_MARKER="Added by coordinator setup-github-auth-1password"
# Agent key lines: ssh-*, ecdsa-*, and FIDO sk-* variants.
KEY_RE='^(ssh-|ecdsa-|sk-)'

# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------
detect_agent_sock() {
  local s
  for s in \
    "$HOME/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock" \
    "$HOME/.1password/agent.sock"; do
    if [ -S "$s" ]; then printf '%s\n' "$s"; return 0; fi
  done
  return 1
}

detect_op_ssh_sign() {
  local c
  if command -v op-ssh-sign >/dev/null 2>&1; then command -v op-ssh-sign; return 0; fi
  for c in \
    "/Applications/1Password.app/Contents/MacOS/op-ssh-sign" \
    "/opt/1Password/op-ssh-sign" \
    "$HOME/.local/share/1password/op-ssh-sign"; do
    if [ -x "$c" ]; then printf '%s\n' "$c"; return 0; fi
  done
  return 1
}

# github.com routed over ssh.github.com:443 with an identity agent?
ssh_routed() {
  if grep -q "$SSH_MARKER" "$SSH_CFG" 2>/dev/null; then return 0; fi   # our own marker wins
  local eff
  eff="$(ssh -G github.com 2>/dev/null)" || return 1                   # old ssh w/o -G → treat as not-routed
  printf '%s\n' "$eff" | grep -qi '^hostname ssh.github.com$' \
    && printf '%s\n' "$eff" | grep -qi '^port 443$' \
    && printf '%s\n' "$eff" | grep -qi '^identityagent '
}

# signing already configured?
sign_configured() {
  [ "$(git config --global --get gpg.format 2>/dev/null)" = ssh ] \
    && [ -n "$(git config --global --get gpg.ssh.program 2>/dev/null)" ]
}

_say "== GitHub auth via 1Password (optional) =="
_say "mode: $MODE"

OP_CLI="$(command -v op 2>/dev/null || true)"
AGENT_SOCK="$(detect_agent_sock || true)"
OP_SSH_SIGN="$(detect_op_ssh_sign || true)"

[ -n "$OP_CLI" ]      && _ok   "op CLI: $OP_CLI"           || _skip "op CLI: not found"
[ -n "$AGENT_SOCK" ]  && _ok   "1Password SSH agent: $AGENT_SOCK" || _skip "1Password SSH agent: socket not found"
[ -n "$OP_SSH_SIGN" ] && _ok   "op-ssh-sign: $OP_SSH_SIGN" || _skip "op-ssh-sign: not found"

# Offer to install the op CLI if absent. The CLI is convenience-only — auth + signing work
# through the desktop agent + op-ssh-sign — so a brew failure here is non-fatal: we continue.
if [ -z "$OP_CLI" ]; then
  if command -v brew >/dev/null 2>&1; then
    if _consent "Install the 1Password CLI (brew install 1password-cli)?"; then
      brew install 1password-cli || _warn "brew install failed (non-fatal — op CLI is optional): https://developer.1password.com/docs/cli/get-started/"
    fi
  else
    _skip "Homebrew not found — install the 1Password CLI manually if you want it: https://developer.1password.com/docs/cli/get-started/"
  fi
fi

# The desktop app (agent socket) + op-ssh-sign are what actually do auth + signing.
if [ -z "$AGENT_SOCK" ] || [ -z "$OP_SSH_SIGN" ]; then
  _say ""
  _warn "1Password SSH agent and/or op-ssh-sign not detected on this machine."
  _warn "Enable them in the 1Password desktop app: Settings → Developer → 'Use the SSH agent'"
  _warn "and 'Integrate with 1Password CLI'. Re-run this script afterward."
  _warn "Nothing was changed. On machines without 1Password this is expected — ignore this step."
  _emit_status_and_exit "n-a-no-1password" 0
fi

# ---------------------------------------------------------------------------
# 1. SSH config — route github.com over ssh.github.com:443 via the 1Password agent
# ---------------------------------------------------------------------------
_say ""
_say "-- SSH config (github.com over port 443 + 1Password agent) --"
if ssh_routed; then
  _ok "already routed: github.com → ssh.github.com:443 via the 1Password agent"
elif [ "$MODE" = check ]; then
  _skip "would add a Host github.com block routing over ssh.github.com:443 to $SSH_CFG"
elif _consent "Add a github.com → ssh.github.com:443 block (1Password agent) to ~/.ssh/config?"; then
  mkdir -p "$HOME/.ssh"; chmod 700 "$HOME/.ssh" 2>/dev/null || true
  if [ -f "$SSH_CFG" ]; then
    if cp "$SSH_CFG" "$SSH_CFG.coordinator-bak.$$"; then
      _ok "backed up existing config → $SSH_CFG.coordinator-bak.$$"
    else
      _warn "backup of $SSH_CFG failed — aborting SSH config write (nothing changed)"
      false
    fi
  fi || true
  if [ ! -f "$SSH_CFG" ] || [ -f "$SSH_CFG.coordinator-bak.$$" ]; then
    {
      printf '\n# %s\n' "$SSH_MARKER"
      printf '# port 22 is blocked on many networks; ssh.github.com:443 carries the git SSH protocol.\n'
      printf 'Host github.com\n\tHostname ssh.github.com\n\tPort 443\n\tUser git\n\tIdentityAgent "%s"\n' "$AGENT_SOCK"
    } >> "$SSH_CFG"
    chmod 600 "$SSH_CFG" 2>/dev/null || true
    _ok "wrote github.com block to $SSH_CFG"
  fi
fi

# ---------------------------------------------------------------------------
# 2. SSH commit signing via op-ssh-sign (global)
# ---------------------------------------------------------------------------
_say ""
_say "-- SSH commit signing (op-ssh-sign) --"
if sign_configured; then
  _ok "signing already configured: gpg.format=ssh, program=$(git config --global --get gpg.ssh.program)"
elif [ "$MODE" = check ]; then
  _skip "would configure SSH commit signing via op-ssh-sign (gpg.format=ssh, commit.gpgsign=true)"
else
  # Resolve which agent key to sign with. Contacting the agent may prompt for Touch ID.
  _say "  querying keys from the 1Password agent (may prompt for Touch ID)…"
  keys="$(SSH_AUTH_SOCK="$AGENT_SOCK" ssh-add -L 2>/dev/null || true)"
  agent_keys="$(printf '%s\n' "$keys" | grep -E "$KEY_RE" || true)"
  nkeys="$(printf '%s\n' "$agent_keys" | grep -cE "$KEY_RE" || true)"
  signing_key=""
  if [ "${COORDINATOR_GH_SIGNING_KEY:-}" != "" ]; then
    matches="$(printf '%s\n' "$agent_keys" | grep -F "$COORDINATOR_GH_SIGNING_KEY" || true)"
    mcount="$(printf '%s\n' "$matches" | grep -cE "$KEY_RE" || true)"
    if [ "$mcount" -gt 1 ]; then
      _warn "COORDINATOR_GH_SIGNING_KEY matched $mcount keys — refusing to guess:"
      printf '%s\n' "$matches" | sed 's/^/      /' >&2
    elif [ "$mcount" = 1 ]; then
      signing_key="$matches"
    else
      _warn "COORDINATOR_GH_SIGNING_KEY did not match any agent key"
    fi
  elif [ "$nkeys" = 1 ]; then
    signing_key="$agent_keys"
  elif [ "$nkeys" -gt 1 ]; then
    _warn "the 1Password agent holds $nkeys keys — cannot pick a signing key automatically:"
    printf '%s\n' "$agent_keys" | sed 's/^/      /' >&2
    if [ "$MODE" = interactive ]; then
      printf '  Enter a substring of the key comment to sign with: '
      sel=""; read -r sel </dev/tty 2>/dev/null || read -r sel || sel=""
      if [ -n "$sel" ]; then
        selm="$(printf '%s\n' "$agent_keys" | grep -F "$sel" || true)"
        scount="$(printf '%s\n' "$selm" | grep -cE "$KEY_RE" || true)"
        if [ "$scount" = 1 ]; then signing_key="$selm"; else _warn "'$sel' matched $scount keys — re-run and be more specific"; fi
      fi
    else
      _warn "set COORDINATOR_GH_SIGNING_KEY=<comment-substring> and re-run to enable signing"
    fi
  else
    _warn "no keys in the 1Password agent — unlock 1Password, then re-run"
  fi

  if [ -n "$signing_key" ]; then
    # Strip the comment field — user.signingkey and allowed_signers want "type base64" only.
    key_core="$(printf '%s\n' "$signing_key" | awk '{print $1, $2}')"
    # Identify the GitHub account this key authenticates as (for the allowed_signers principal).
    # UserKnownHostsFile=/dev/null so the probe never writes known_hosts.
    who="$(SSH_AUTH_SOCK="$AGENT_SOCK" ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -T git@github.com 2>&1 | sed -n 's/^Hi \([^!]*\)!.*/\1/p' | head -n1)"
    email="$(git config --global --get user.email 2>/dev/null || true)"
    [ -z "$email" ] && [ -n "$who" ] && email="$who@users.noreply.github.com"
    _say "  signing key: $key_core"
    [ -n "$who" ] && _ok "authenticates to GitHub as: $who"
    if _consent "Enable SSH commit signing globally with this key?"; then
      git config --global gpg.format ssh
      git config --global gpg.ssh.program "$OP_SSH_SIGN"
      git config --global user.signingkey "$key_core"
      git config --global commit.gpgsign true
      git config --global tag.gpgsign true
      if [ -n "$email" ]; then
        mkdir -p "$HOME/.config/git"
        as_file="$HOME/.config/git/allowed_signers"
        if [ ! -f "$as_file" ] || ! grep -qF "$key_core" "$as_file" 2>/dev/null; then
          printf '%s %s\n' "$email" "$key_core" >> "$as_file"
        fi
        git config --global gpg.ssh.allowedSignersFile "$as_file"
        _ok "allowed_signers: $as_file (principal $email)"
      fi
      _ok "signing enabled — new commits will be SSH-signed via op-ssh-sign"
      _say "  NOTE: add this key as a *Signing key* at https://github.com/settings/keys for the verified badge."
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 3. Offer to flip the current repo's origin remote to SSH
# ---------------------------------------------------------------------------
_say ""
_say "-- current repo origin remote --"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  url="$(git remote get-url origin 2>/dev/null || true)"
  case "$url" in
    https://github.com/*)
      _repo_path="${url#https://github.com/}"; _repo_path="${_repo_path%.git}"
      ssh_url="git@github.com:${_repo_path}.git"
      _skip "origin is HTTPS: $url"
      if [ "$MODE" = check ]; then
        _skip "would offer to switch origin → $ssh_url"
      elif _consent "Switch origin to SSH ($ssh_url)?"; then
        git remote set-url origin "$ssh_url"
        if git ls-remote origin HEAD >/dev/null 2>&1; then
          _ok "origin → $ssh_url (verified)"
        else
          git remote set-url origin "$url"
          _warn "SSH ls-remote failed — reverted origin to HTTPS. Check key access on GitHub."
        fi
      fi
      ;;
    git@github.com:*|ssh://git@github.com/*) _ok "origin already SSH: $url" ;;
    "") _skip "no origin remote" ;;
    *) _skip "origin not a github.com remote: $url" ;;
  esac
else
  _skip "not inside a git repository — skipping remote flip"
fi

# ---------------------------------------------------------------------------
# Final status (machine-readable for the install command)
# ---------------------------------------------------------------------------
_say ""
if ssh_routed && sign_configured; then
  [ "$MODE" = check ] && final="present" || final="configured"
else
  [ "$MODE" = check ] && final="absent" || final="incomplete"
fi
_say "Done. Tier-1 (interactive) GitHub auth via 1Password — recipe in docs/wiki/github-auth-setup.md."
_say "Headless machines keep token HTTPS (gh auth setup-git)."
_emit_status_and_exit "$final" 0
