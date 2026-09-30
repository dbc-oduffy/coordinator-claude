# Reproduces, spawn-free, every environment difference the stock /etc/profile produces for
# a NON-INTERACTIVE shell -- avoiding the stock profile's per-invocation cost. PS1 is
# deliberately not reproduced: meaningless without a terminal, and unreachable here (see
# the `$-` guard). `locale -uU` is the one spawn that survives, because LANG's value is
# live per-host state and cannot be derived spawn-free.
#
# PORTABILITY: nothing here is pinned to MINGW64/x86_64. `/etc/msystem` is sourced to
# derive MSYSTEM_*/MINGW_* for whatever MSYSTEM this install actually is; every prefix
# below reads `${MINGW_PREFIX}`, never a literal -- hardcoding this host's values would
# write a wrong environment onto a 32-bit or ARM64 Git install.
#
# Scope guard, all three conditions required: non-interactive shell; CLAUDECODE set
# (Claude Code's own bash spawns inherit it); MSYS2_PATH_TYPE unset/inherit/strict (any
# other value needs a `cygpath -Wu` spawn this path cannot reproduce, so it falls through
# to stock).
#
# Escape hatch: COORDINATOR_FULL_PROFILE=1 forces the stock path for debugging.
#
# Does not survive a Git-for-Windows update -- an update replaces /etc/profile wholesale
# and silently restores the cost.
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

      # profile.d/perlbin.sh, verbatim -- `[ -d ]` is a builtin, so these cost nothing.
      [ -d /usr/bin/site_perl ] && PATH=$PATH:/usr/bin/site_perl
      [ -d /usr/lib/perl5/site_perl/bin ] && PATH=$PATH:/usr/lib/perl5/site_perl/bin
      [ -d /usr/bin/vendor_perl ] && PATH=$PATH:/usr/bin/vendor_perl
      [ -d /usr/lib/perl5/vendor_perl/bin ] && PATH=$PATH:/usr/lib/perl5/vendor_perl/bin
      [ -d /usr/bin/core_perl ] && PATH=$PATH:/usr/bin/core_perl

      
      # `hostname` in the stock profile is one spawn for a value fixed per machine;
      # COMPUTERNAME carries it already. Case may differ from the stock value and is
      # cosmetic -- HOSTNAME is consumed only by PS1, which this path does not set.
      HOSTNAME="${COMPUTERNAME:-$HOSTNAME}"
      
      SHELL=/usr/bin/bash

      ORIGINAL_TMP="${ORIGINAL_TMP:-$TMP}"
      ORIGINAL_TEMP="${ORIGINAL_TEMP:-$TEMP}"
      TMPDIR="${TMPDIR:-/tmp}"

      # /etc/profile's own TMP/TEMP normalization, reproduced with a builtin substitution
      # instead of the `cygpath -m` spawn it uses.
      case "$TMP" in *'\'*) TMP="${TMP//'\'//}" ;; esac
      case "$TEMP" in *'\'*) TEMP="${TEMP//'\'//}" ;; esac

      # profile.d/lang.sh -- THE ONE RETAINED SPAWN. LANG is live per-host locale state and
      # cannot be derived spawn-free, so guessing it would silently set a wrong LANG.
      if [ -z "${LC_ALL:-${LC_CTYPE:-$LANG}}" ]; then
        LANG=$(exec /usr/bin/locale -uU)
        export LANG
      fi

      # profile.d/env.sh: lets git prompt for credentials via GUI when the terminal is not
      # usable -- load-bearing for git over HTTPS/SSH. The case list below is env.sh's own,
      # enumerated literally rather than pattern-matched, since plain CLANG64 is a real
      # MSYSTEM but not among them.
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

