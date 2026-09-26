

# Every environment difference the stock profile produces for a NON-INTERACTIVE shell is


# PORTABILITY. Nothing here is pinned to MINGW64/x86_64. `/etc/msystem` -- which the
# stock profile itself sources at the same point -- is `source`d to derive MSYSTEM_*/
# MINGW_* for whatever MSYSTEM this install actually is (MINGW32, UCRT64, CLANGARM64,

# prefix below is then `${MINGW_PREFIX}`, never a literal. Hardcoding this host's values


#   - the shell is NON-INTERACTIVE ($- has no `i`), so an interactive Git Bash --

#     CLAUDECODE -- always takes the full stock path and keeps its prompt.
#   - CLAUDECODE is set, which Claude Code puts in its own environment and every bash it

#   - MSYS2_PATH_TYPE is unset, `inherit`, or `strict`. Any other value sends the stock


# NOT ZERO-SPAWN, exactly once: `locale -uU` survives, for LANG. See the lang.sh block


# Escape hatch: set COORDINATOR_FULL_PROFILE=1 to force the stock path for debugging


# THIS BLOCK DOES NOT SURVIVE A GIT-FOR-WINDOWS UPDATE -- an update replaces /etc/profile


case "$-" in
  *i*) ;;
  *)
    if [ -n "$CLAUDECODE" ] && [ -z "$COORDINATOR_FULL_PROFILE" ] &&
       { [ -z "$MSYS2_PATH_TYPE" ] || [ "$MSYS2_PATH_TYPE" = inherit ] ||
         [ "$MSYS2_PATH_TYPE" = strict ]; }; then

      
      # MSYSTEM_PREFIX/CARCH/CHOST and MINGW_PREFIX/CHOST/PACKAGE_PREFIX for this
      
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

      
      PATH="$HOME/bin:$PATH"

      
      [ -d /usr/bin/site_perl ] && PATH=$PATH:/usr/bin/site_perl
      [ -d /usr/lib/perl5/site_perl/bin ] && PATH=$PATH:/usr/lib/perl5/site_perl/bin
      [ -d /usr/bin/vendor_perl ] && PATH=$PATH:/usr/bin/vendor_perl
      [ -d /usr/lib/perl5/vendor_perl/bin ] && PATH=$PATH:/usr/lib/perl5/vendor_perl/bin
      [ -d /usr/bin/core_perl ] && PATH=$PATH:/usr/bin/core_perl

      
      # COMPUTERNAME carries it already. Case may differ from the stock value and is
      # cosmetic -- HOSTNAME is consumed only by PS1, which this path does not set.
      HOSTNAME="${COMPUTERNAME:-$HOSTNAME}"
      
      SHELL=/usr/bin/bash

      ORIGINAL_TMP="${ORIGINAL_TMP:-$TMP}"
      ORIGINAL_TEMP="${ORIGINAL_TEMP:-$TEMP}"
      TMPDIR="${TMPDIR:-/tmp}"

      
      case "$TMP" in *'\'*) TMP="${TMP//'\'//}" ;; esac
      case "$TEMP" in *'\'*) TEMP="${TEMP//'\'//}" ;; esac

      # profile.d/lang.sh, reproduced faithfully -- and this is THE ONE RETAINED SPAWN.
      
      # Stock: `test -z "${LC_ALL:-${LC_CTYPE:-$LANG}}" && export LANG=$(exec /usr/bin/locale -uU)`.
      
      
      if [ -z "${LC_ALL:-${LC_CTYPE:-$LANG}}" ]; then
        LANG=$(exec /usr/bin/locale -uU)
        export LANG
      fi

      
      # The case list below is env.sh's own, enumerated LITERALLY rather than pattern-matched.
      
      
      # MINGW_PREFIX. Gating on `[ -n "$MINGW_PREFIX" ]` therefore set DISPLAY/SSH_ASKPASS on
      
      
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

