# >>> claude-code fast profile (DoE-claude) >>>
# Git-for-Windows' stock /etc/profile costs ~800ms per invocation. Claude Code's Bash
# tool spawns `bash -c -l` per call and its own contract states shell state does not
# persist between calls -- so that work is paid per call and discarded by design. On a
# box running many concurrent sessions it is the largest single fixed cost on the
# machine.
#
# Every environment difference the stock profile produces for a NON-INTERACTIVE shell is
# reproduced below, all but one of them spawn-free. The stock profile's cost is six spawns
# (`cygpath -Wu`, `cygpath -m` x2, `hostname`, `which bash`, `locale -uU`) plus two
# `$(echo /etc/profile.d/*)` glob subshells and a /etc/post-install scan. Only `locale -uU`
# computes something that genuinely varies per host and cannot be derived from an already-
# inherited variable, so it is the one that survives; the other five are replaced by
# parameter expansion or an already-present env var.
#
# Deliberately NOT reproduced: PS1. It is the only other thing the stock profile adds, it
# is meaningless without a terminal, and this block cannot be reached by an interactive
# shell (see the `$-` guard).
#
# PORTABILITY. Nothing here is pinned to MINGW64/x86_64. `/etc/msystem` -- which the
# stock profile itself sources at the same point -- is `source`d to derive MSYSTEM_*/
# MINGW_* for whatever MSYSTEM this install actually is (MINGW32, UCRT64, CLANGARM64,
# bare MSYS). It sources `/etc/msystem.d/${MSYSTEM}`; both are file reads, no forks. Every
# prefix below is then `${MINGW_PREFIX}`, never a literal. Hardcoding this host's values
# would write a wrong environment onto a 32-bit or ARM64 Git install.
#
# Scope guard, all three conditions required:
#   - the shell is NON-INTERACTIVE ($- has no `i`), so an interactive Git Bash --
#     including one launched from inside a Claude session, which would inherit
#     CLAUDECODE -- always takes the full stock path and keeps its prompt.
#   - CLAUDECODE is set, which Claude Code puts in its own environment and every bash it
#     spawns inherits. No Windows env var needs configuring for this.
#   - MSYS2_PATH_TYPE is unset, `inherit`, or `strict`. Any other value sends the stock
#     profile down a branch that spawns `cygpath -Wu` to synthesise a Windows path, which
#     cannot be reproduced spawn-free -- so that configuration falls through to stock
#     rather than being silently approximated.
# NOT ZERO-SPAWN, exactly once: `locale -uU` survives, for LANG. See the lang.sh block
# below for why it cannot be guessed and why gating the whole fast path on it instead
# silently disables the fast path on every real invocation.
# Escape hatch: set COORDINATOR_FULL_PROFILE=1 to force the stock path for debugging
# without editing this file.
#
# THIS BLOCK DOES NOT SURVIVE A GIT-FOR-WINDOWS UPDATE -- an update replaces /etc/profile
# wholesale and silently restores the cost. Re-run
# coordinator/templates/bin/install-git-bash-fast-profile.py after updating Git.
case "$-" in
  *i*) ;;
  *)
    if [ -n "$CLAUDECODE" ] && [ -z "$COORDINATOR_FULL_PROFILE" ] &&
       { [ -z "$MSYS2_PATH_TYPE" ] || [ "$MSYS2_PATH_TYPE" = inherit ] ||
         [ "$MSYS2_PATH_TYPE" = strict ]; }; then

      # Mirrors the stock profile's own `. '/etc/msystem'`. Populates MSYSTEM,
      # MSYSTEM_PREFIX/CARCH/CHOST and MINGW_PREFIX/CHOST/PACKAGE_PREFIX for this
      # install's actual MSYSTEM. File reads only.
      unset MINGW_MOUNT_POINT
      . /etc/msystem

      # ORIGINAL_PATH capture: `strict` unsets it, `inherit` (the default) preserves it.
      if [ "$MSYS2_PATH_TYPE" = strict ]; then
        unset ORIGINAL_PATH
      else
        ORIGINAL_PATH="${ORIGINAL_PATH:-$PATH}"
      fi

      _msys2_path="/usr/local/bin:/usr/bin:/bin"
      _manpath='/usr/local/man:/usr/share/man:/usr/man:/share/man'
      _infopath='/usr/local/info:/usr/share/info:/usr/info:/share/info'

      case "${MSYSTEM}" in
      MINGW*|CLANG*|UCRT*)
        MINGW_MOUNT_POINT="${MINGW_PREFIX}"
        PATH="${MINGW_MOUNT_POINT}/bin:${_msys2_path}${ORIGINAL_PATH:+:${ORIGINAL_PATH}}"
        PKG_CONFIG_PATH="${MINGW_MOUNT_POINT}/lib/pkgconfig:${MINGW_MOUNT_POINT}/share/pkgconfig"
        PKG_CONFIG_SYSTEM_INCLUDE_PATH="${MINGW_MOUNT_POINT}/include"
        PKG_CONFIG_SYSTEM_LIBRARY_PATH="${MINGW_MOUNT_POINT}/lib"
        ACLOCAL_PATH="${MINGW_MOUNT_POINT}/share/aclocal:/usr/share/aclocal"
        MANPATH="${MINGW_MOUNT_POINT}/local/man:${MINGW_MOUNT_POINT}/share/man:${_manpath}"
        INFOPATH="${MINGW_MOUNT_POINT}/local/info:${MINGW_MOUNT_POINT}/share/info:${_infopath}"
        ;;
      *)
        PATH="${_msys2_path}:/opt/bin${ORIGINAL_PATH:+:${ORIGINAL_PATH}}"
        PKG_CONFIG_PATH="/usr/lib/pkgconfig:/usr/share/pkgconfig:/lib/pkgconfig"
        MANPATH="${_manpath}"
        INFOPATH="${_infopath}"
        ;;
      esac
      unset _msys2_path _manpath _infopath

      CONFIG_SITE=/etc/config.site

      # profile.d/env.sh: ~/bin ahead of everything.
      PATH="$HOME/bin:$PATH"

      # profile.d/perlbin.sh, verbatim -- `[ -d ]` is a builtin, so these cost nothing
      # and keep the perl scriptdirs on PATH exactly as upstream does.
      [ -d /usr/bin/site_perl ] && PATH=$PATH:/usr/bin/site_perl
      [ -d /usr/lib/perl5/site_perl/bin ] && PATH=$PATH:/usr/lib/perl5/site_perl/bin
      [ -d /usr/bin/vendor_perl ] && PATH=$PATH:/usr/bin/vendor_perl
      [ -d /usr/lib/perl5/vendor_perl/bin ] && PATH=$PATH:/usr/lib/perl5/vendor_perl/bin
      [ -d /usr/bin/core_perl ] && PATH=$PATH:/usr/bin/core_perl

      # `hostname` in the stock profile is one spawn for a value fixed per machine;
      # COMPUTERNAME carries it already. Case may differ from the stock value and is
      # cosmetic -- HOSTNAME is consumed only by PS1, which this path does not set.
      HOSTNAME="${COMPUTERNAME:-$HOSTNAME}"
      # `which bash` in the stock profile, likewise, for a fixed path.
      SHELL=/usr/bin/bash

      ORIGINAL_TMP="${ORIGINAL_TMP:-$TMP}"
      ORIGINAL_TEMP="${ORIGINAL_TEMP:-$TEMP}"
      TMPDIR="${TMPDIR:-/tmp}"

      # /etc/profile's own TMP/TEMP normalization (NOT profile.d/env.sh), reproduced with a
      # builtin substitution instead of the spawn it uses
      # (`cygpath -m "$TMP"` / `cygpath -m "$TEMP"`): for an ordinary drive-letter
      # Windows path this produces the identical mixed-form result cygpath -m does. Left
      # untouched when there's no backslash to convert, same as stock.
      case "$TMP" in *'\'*) TMP="${TMP//'\'//}" ;; esac
      case "$TEMP" in *'\'*) TEMP="${TEMP//'\'//}" ;; esac

      # profile.d/lang.sh, reproduced faithfully -- and this is THE ONE RETAINED SPAWN.
      #
      # Stock: `test -z "${LC_ALL:-${LC_CTYPE:-$LANG}}" && export LANG=$(exec /usr/bin/locale -uU)`.
      # The value is the live Windows locale and cannot be derived spawn-free, so guessing it
      # would silently set a wrong LANG on any non-US-English host. It is kept as a spawn
      # rather than guessed, and kept HERE rather than in the scope guard: gating the whole
      # fast path on "a locale var is already set" disables the fast path entirely, because at
      # the moment /etc/profile runs NONE of the three is set. That reads as safe and is not:
      # `LANG` IS present in a child of `bash -lc`, but only because the profile just set it.
      # Observing it there and concluding the guard passes is the same login-shell-parent
      # confound documented in docs/wiki/bash-on-windows-gotchas.md § 17 for PATH.
      #
      # Cost: one spawn on the common path instead of five plus two glob subshells.
      if [ -z "${LC_ALL:-${LC_CTYPE:-$LANG}}" ]; then
        LANG=$(exec /usr/bin/locale -uU)
        export LANG
      fi

      # profile.d/env.sh: lets git prompt for credentials via GUI when the terminal is
      # not usable. Load-bearing for git over HTTPS/SSH.
      #
      # The case list below is env.sh's own, enumerated LITERALLY rather than pattern-matched.
      # `MINGW*|CLANG*|UCRT*` would be wrong here: env.sh switches on four exact values, and
      # plain CLANG64 is NOT among them even though it is a real MSYSTEM that sets
      # MINGW_PREFIX. Gating on `[ -n "$MINGW_PREFIX" ]` therefore set DISPLAY/SSH_ASKPASS on
      # a CLANG64 install where stock sets neither. That is the /etc/profile PATH case split
      # (which IS `MINGW*|CLANG*|UCRT*`, above) leaking into a different file's narrower one.
      case "${MSYSTEM}" in
      MINGW64|UCRT64|MINGW32|CLANGARM64) _cc_askpass_msystem=1 ;;
      *) _cc_askpass_msystem= ;;
      esac
      if [ -z "$SSH_ASKPASS" ] && [ -n "$_cc_askpass_msystem" ] && [ -n "$MINGW_PREFIX" ]; then
        DISPLAY=needs-to-be-defined
        if [ -f "${MINGW_PREFIX}/bin/git-askpass.exe" ]; then
          SSH_ASKPASS="${MINGW_PREFIX}/bin/git-askpass.exe"
        else
          SSH_ASKPASS="${MINGW_PREFIX}/libexec/git-core/git-gui--askpass"
        fi
        export DISPLAY SSH_ASKPASS
      fi
      unset _cc_askpass_msystem

      export PATH ORIGINAL_PATH MANPATH INFOPATH ACLOCAL_PATH \
             PKG_CONFIG_PATH PKG_CONFIG_SYSTEM_INCLUDE_PATH \
             PKG_CONFIG_SYSTEM_LIBRARY_PATH CONFIG_SITE HOSTNAME SHELL \
             ORIGINAL_TMP ORIGINAL_TEMP TMPDIR TMP TEMP

      return 0 2>/dev/null || exit 0
    fi
    ;;
esac
# <<< claude-code fast profile <<<
