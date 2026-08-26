"""
bin-templates-manifest.py — single source of truth for which of DoE's
`coordinator/templates/bin/` artifacts claude-klabauter's installer classifies as
`code` vs `operator-config`, and how it installs each one.

Imported (never executed) by:
  - coordinator_core.install.substrate._load_bin_templates_manifest
    (spec_from_file_location load — the hyphenated filename precludes a
    normal `import` statement, same reason setup-templates-manifest.py is
    loaded that way)

`ml_bin` (`coordinator_core/install/substrate.py`'s `plugin_root / "templates"
/ "bin"`) resolves to DoE's tree — every artifact this manifest names is
authored and owned by DoE; claude-klabauter only classifies and copies it. That
classification used to live in four hand-maintained tuples
(`_ML_FAMILY_FILES` / `_CH_FAMILY_FILES` / `_ML_EXPLICIT_FILES` /
`_PLATFORM_LOCALIZE_FILES`) hardcoded against a directory claude-klabauter does not
own, which is exactly how `coordinator-settings-home` (stale since Jul 6)
and `claude-machine-local.ps1` (stale since Jul 22) drifted silently. This
manifest is the fix: ONE declared, tested table, edited HERE and nowhere
else — the parity test
`coordinator/tests/install/test_bin_templates_manifest_sync.py` fails the
build if `templates/bin/` gains a file this manifest does not classify, or
if an entry here no longer exists on disk.

Spec backlink: pln-install-surface-freshness-exte-f702c8
               § C12 / AC19 / AC20

Every entry's `artifact_class` is `"code"` and `force_overwrite` is `True` —
per C1 (already landed), none of DoE's `templates/bin/` artifacts is
operator-config; a stale destination is always repaired on re-install. C12
does NOT re-decide this — it transcribes C1's landed decision verbatim.
`exec_bit` is the POSIX permission bit `_install_one` applies at the
destination (NOT a code/config classifier — see substrate.py's own
`_install_one` docstring on why `.ps1` files are legitimately code with
`exec_bit=False` by construction).

Negative spec: do NOT add `_CH_FAMILY_FILES`'s three names here
(`claude-home`, `_claude_home.py`, `claude-home.cmd`). Their source is
`coordinator/lib/claude-home/` — CLAUDE-KLABAUTER'S OWN tree, not DoE's
`templates/bin/` — so they are out of this manifest's scope by
construction; `_CH_FAMILY_FILES` stays a separate, hand-maintained tuple in
substrate.py. Likewise `_RM_FAMILY_FILES` (`_resolve_claude_klabauter.py`, sourced
from `coordinator/lib/resolve-claude-klabauter/`) is out of scope for the same
reason. Folding either in would make this manifest's own parity test lie —
it walks DoE's `templates/bin/` directory, and neither family's source
lives there.
"""

from __future__ import annotations

from typing import NamedTuple


class BinTemplateEntry(NamedTuple):
    """One DoE `templates/bin/` artifact's install classification.

    `artifact_class`: "code" | "operator-config" (declared by AC19; every
        current entry is "code" per C1's landed decision — see module
        docstring).
    `exec_bit`: POSIX +x bit `_install_one` applies at the destination.
        False-by-construction for every `.cmd`/`.ps1` twin (no POSIX exec
        bit exists on those platforms) — this is NOT a code/config signal,
        see `_install_one`'s own docstring.
    `force_overwrite`: True = force-overwrite-on-diff (code), False =
        preserve-on-diff (operator config). Declared per-entry here for
        completeness/audit, but the write loops in
        `_install_bin_resolvers` still pass the family-level literal
        `force_overwrite=True` at the call site (C1's landed, unchanged
        decision) rather than reading this field — this manifest is a
        classification-source swap, not a rewiring of that call-site
        literal (AC20 anti-scope).
    """

    name: str
    artifact_class: str
    exec_bit: bool
    force_overwrite: bool


# --- ml_family (substrate.py's former _ML_FAMILY_FILES, transcribed verbatim) ---
ML_FAMILY_FILES: "tuple[BinTemplateEntry, ...]" = (
    BinTemplateEntry("machine-local", "code", True, True),
    BinTemplateEntry("_machine_local.py", "code", False, True),
    BinTemplateEntry("machine-local.cmd", "code", False, True),
    BinTemplateEntry("resolve-coordinator-clone", "code", True, True),
    BinTemplateEntry("resolve-coordinator-clone.cmd", "code", False, True),
)

# --- ml_explicit (former _ML_EXPLICIT_FILES, transcribed verbatim) ---
ML_EXPLICIT_FILES: "tuple[BinTemplateEntry, ...]" = (
    BinTemplateEntry("coordinator-settings-home", "code", True, True),
    BinTemplateEntry("coordinator-settings-home.cmd", "code", False, True),
    BinTemplateEntry("coordinator-settings-home.ps1", "code", False, True),
    BinTemplateEntry("claude_machine_local.py", "code", False, True),
    BinTemplateEntry("claude-machine-local.sh", "code", False, True),
    BinTemplateEntry("claude-machine-local.ps1", "code", False, True),
)

# --- platform_localize (former _PLATFORM_LOCALIZE_FILES, transcribed verbatim) ---
PLATFORM_LOCALIZE_FILES: "tuple[BinTemplateEntry, ...]" = (
    BinTemplateEntry("platform-localize.py", "code", True, True),
    BinTemplateEntry("platform-localize.cmd", "code", False, True),
)

# --- git_bash_fast_profile: the login-shell-tax fix (see docs/wiki/
# coordinator-tripwires/tripwire-registry/a-git-update-silently-restores-the-
# login-shell-tax.md). `install-git-bash-fast-profile.py` carries a shebang
# and is run directly from an elevated shell (exec_bit=True, like
# platform-localize.py above); `git-bash-fast-profile.sh` is sourced by the
# installer into Git-for-Windows' /etc/profile rather than executed on its
# own, so exec_bit=False — same convention as claude-machine-local.sh above
# (every plain `.sh` entry in this manifest is exec_bit=False).
GIT_BASH_FAST_PROFILE_FILES: "tuple[BinTemplateEntry, ...]" = (
    BinTemplateEntry("install-git-bash-fast-profile.py", "code", True, True),
    BinTemplateEntry("git-bash-fast-profile.sh", "code", False, True),
)

# --- launcher templates: NOT consumed by `_install_bin_resolvers` at all.
# Rendered (not copied verbatim) by `coordinator_core.ops.gen_claude_doe_launcher`,
# which already has its own correct check-mode freshness pattern (tempfile +
# filecmp) — see that module. These two names were absent from ALL FOUR
# original tuples; this is the one open classification question C12's brief
# calls out explicitly. Conservative pick, not a re-derivation of an
# existing decision (there was none to transcribe): class "code" (they are
# code, just not installed via `_install_one`), `exec_bit=False` (no
# `.cmd`/`.ps1` twin in this whole manifest ever carries the POSIX bit,
# consistent with every other entry above), `force_overwrite=True` (they
# are always re-rendered fresh, never preserved-as-stale, by their own
# consumer). Included here ONLY so the parity test can classify every
# artifact `templates/bin/` actually contains — `_install_bin_resolvers`
# does not read this group.
LAUNCHER_TEMPLATE_FILES: "tuple[BinTemplateEntry, ...]" = (
    BinTemplateEntry("claude-doe-launcher.cmd.tmpl", "code", False, True),
    BinTemplateEntry("claude-doe-launcher.ps1.tmpl", "code", False, True),
)

# Union of every group above — the complete classification of DoE's
# `templates/bin/` directory. The parity test asserts this set's name
# collection is EXACTLY the on-disk listing (minus __pycache__), in both
# directions.
ALL_BIN_TEMPLATE_FILES: "tuple[BinTemplateEntry, ...]" = (
    ML_FAMILY_FILES
    + ML_EXPLICIT_FILES
    + PLATFORM_LOCALIZE_FILES
    + GIT_BASH_FAST_PROFILE_FILES
    + LAUNCHER_TEMPLATE_FILES
)
