"""
coordinator-lesson-promote — write a universal lesson to the local lessons-outbox
for drain by the central /learn-lessons --central procedure.

Spec backlink: docs/plans/2026-06-15-universal-lesson-routing-mechanical-capture.md § C1

Purpose: Write ONE YAML entry to state/lessons-outbox/<ISO-ts>-<slug>.yaml.
The file is left uncommitted (dirty) so it surfaces in `git status` and is
picked up by the /learn-lessons --central drain procedure.

Output path: state/lessons-outbox/<ISO-ts>-<slug>.yaml
  - ISO-ts: UTC timestamp, colons replaced with hyphens for filesystem safety
  - Slug: title sanitised to lowercase + hyphens, alphanumeric + hyphens only,
    truncated to 40 chars

from_repo resolution order (same convention as cross-repo-memo):
  1. cwd git-root → reverse-lookup against machine-local repos.* table
  2. repos.doe_claude (DoE-claude repo) → "claude-central-em"
  3. Unregistered git repo → basename of git root + "-em"
  4. Not in a git repo → "unknown-sender-em"
  Never uses `git remote get-url origin` — that yields a URL, not a shortname.

Negative-spec: this CLI writes ONLY to state/lessons-outbox/. It does NOT
append to state/improvement-queue.md, lessons.md, or any other surface.
Those routes are for project-scoped or wiki-only entries; this CLI is for
universal lessons destined for the central coordinator wiki.

Invocation:
  coordinator-lesson-promote \\
    --title "lesson title" \\
    --body "lesson body prose" \\
    --change-kind doctrine-edit \\
    --target-wiki docs/wiki/some-wiki.md \\
    [--scope-tags "tag1,tag2"] \\
    [--evidence "commit-sha or plan path"] \\
    [--allow-new-wiki]

Exit-code contract:
  0  success — the entry was written to state/lessons-outbox/.
  1  unexpected error (schema load failure, filesystem error, unexpected op result shape).
  2  invalid arguments — argparse-detected (missing/unknown flag, invalid --change-kind),
     or --target-wiki not found in the central wiki inventory (see § A7 below).
  3  DoE-claude root unresolvable — the write (or the --target-wiki inventory check) was
     SKIPPED, not silently treated as success. Remediate per the stderr message
     (`machine-local set repos.doe_claude /path/to/DoE-claude`).
     Also used when the DISPATCH engine root (claude-klabauter) itself is
     unresolvable, a fresh-machine case reachable before the DoE-root check
     ever runs — remediate per the stderr message ('machine-local set
     repos.claude_klabauter /path/to/claude-klabauter').

Negative-spec (A13): a skipped write due to an unresolvable DoE-claude root is NEVER
exit 0. A caller checking only `returncode == 0` must be able to trust that outcome —
exit 0 means an entry was actually written.

--target-wiki validation (A7): validated against the real central wiki inventory
(<doe_root>/coordinator/docs/wiki/*.md) unless the literal value 'unknown' is passed,
or --allow-new-wiki is given (escape hatch for a genuine change_kind: wiki-new
promotion, where the target intentionally does not exist yet). An unresolvable
DoE-claude root during this check is the SAME exit 3 as the write-skip case above —
never a silently-skipped validation.

--target-wiki normalization (A9): normalized to the canonical 'docs/wiki/<name>.md'
form before validation and before being written, so 'foo', 'foo.md', and
'docs/wiki/foo.md' all collapse to the same target and dedupe correctly downstream.

--target-wiki is change_kind-gated (A7/A9 scope fix, 2026-07-23): `target_wiki` is
the generic promotion-target field for EVERY change_kind, not only wiki entries — a
`skill-edit` promotion stores a `SKILL.md` path here, a `script-edit` promotion
stores a `bin/` script path. Only `wiki-new` and `wiki-append` (the two schema
change_kind members whose semantics are unambiguously wiki-targeting — see
docs/wiki/lessons-outbox-schema.md § Change-kind enum) run through
_normalize_target_wiki and the central-wiki-inventory check below. Every other
change_kind's --target-wiki passes through completely UNCHANGED and UNVALIDATED.
Negative-spec: this CLI previously ran BOTH the collapse and the inventory check
unconditionally for every change_kind, which silently corrupted non-wiki targets
(a `skill-edit` value became `docs/wiki/coordinator/skills/pickup/SKILL.md`) and
then hard-failed the write on the corrupted value never matching the wiki
inventory — every non-wiki promotion was broken. See
coordinator/bin/lib/target_wiki_canon.py for the shared canonicalization both this
CLI and lessons-outbox-drain.py's dedupe key now import.
"""
from __future__ import annotations

import argparse
import datetime
import difflib
import json
import os
import re
import sys
import uuid

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from coordinator_registry import doe_root, _DoeUnresolvable  # noqa: E402
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402
from cc_invoke import route as _cc_route  # noqa: E402
import cli_shared  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402
from target_wiki_canon import (  # noqa: E402
    WIKI_TARGETING_CHANGE_KINDS as _WIKI_TARGETING_CHANGE_KINDS,
    normalize_target_wiki as _normalize_target_wiki,
    TARGET_WIKI_UNKNOWN as _TARGET_WIKI_UNKNOWN,
    TARGET_WIKI_PREFIX as _TARGET_WIKI_PREFIX,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum slug length (chars) for the filename component.
_SLUG_MAX_CHARS = 40

# Env var for test isolation — overrides the outbox root directory.
# Tests chdir into a temp dir; the CLI resolves state/lessons-outbox/ relative to
# cwd by default. This env var allows absolute override without chdir.
_OUTBOX_ROOT_ENV = "LESSON_PROMOTE_OUTBOX_ROOT"

# Env var for test isolation — overrides the central wiki inventory directory used
# by --target-wiki validation (A7). Mirrors _OUTBOX_ROOT_ENV's override shape: when
# set, points DIRECTLY at a directory of .md files (not the DoE repo root), so tests
# never need a real DoE-claude checkout on disk to exercise validation.
# Spec backlink: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-learn-lessons-dogfood-2026-07-23.md
# (finding A7)
_WIKI_ROOT_ENV = "LESSON_PROMOTE_WIKI_ROOT"

# Exit code for a write (or --target-wiki validation) SKIPPED because the DoE-claude
# root could not be resolved. Deliberately distinct from 0 (success) and 1 (generic
# error) so a caller checking only `returncode == 0` can trust that outcome (A13
# negative-spec: a skipped write is never exit 0).
_EXIT_DOE_UNRESOLVABLE = 3

# Env var overrides for test isolation. Canonical spellings now live in
# bin/lib/cli_shared.py (T2-g2a consolidation) — aliased here so existing
# doc/error-message references in this file don't need a rename.
_MACHINE_LOCAL_IMPL_ENV = cli_shared.MACHINE_LOCAL_IMPL_ENV

# Env var for CLAUDE_HOME override (mirrors cross-repo-memo pattern).
_CLAUDE_HOME_ENV = cli_shared.CLAUDE_HOME_ENV

# Env var for CLAUDE_KLABAUTER_ROOT override — mirrors coordinator-claude-klabauter-root.sh §4b
# idempotency gate. Set to the claude-klabauter repo root to bypass machine-local resolution.
# Spec backlink: pln-stop-the-rot-claude-klabauter-state-home-placement-4cc787 § AC1 / AC13
_CLAUDE_KLABAUTER_ROOT_ENV = cli_shared.CLAUDE_KLABAUTER_ROOT_ENV

# Env var for DOE_ROOT override — mirrors CLAUDE_KLABAUTER_ROOT §4b idempotency gate.
# Honoured by coordinator_registry.doe_root() (imported above) — kept here as a
# local constant for documentation and error-message reference.
# Spec backlink: docs/plans/2026-07-06-gate2-w23-state-seam-caller-switch.md § C1
_DOE_ROOT_ENV = "DOE_ROOT"


def _claude_klabauter_resolution_error_class() -> type[Exception] | None:
    """Return the exact ``ClaudeKlabauterResolutionError`` class the DISPATCH-engine
    resolution ladder raises, or None if that ladder never got far enough to
    define it.

    `require_dispatch_engine_on_path()` -> `cc_invoke._resolve_engine_root()`
    -> `coordinator_core.engine_root.coordinator_engine_root_with_class()`
    (imported as a normal package import once a candidate `coordinator_core`
    is self-located) -> that module's own `_load_shim()`, which loads
    `coordinator/lib/resolve-claude-klabauter/_resolve_claude_klabauter.py` BY PATH under the
    fixed synthetic name `_claude_klabauter_root_gate_shim` and memoizes the module
    object on `coordinator_core.engine_root._shim_module`. The raised
    exception's class therefore lives on THAT cached module object, not on
    any copy this CLI could import itself — `_resolve_claude_klabauter.py` is loaded
    by path independently in at least two places in this tree (this shim
    loader and `percolate-liveops-preflight.py`'s own direct import), and
    `spec_from_file_location` gives each loader a distinct module/class
    object with no identity relationship. Re-importing the file under our
    own name would produce a DIFFERENT class object that `isinstance()`
    would never match against an exception raised from the shim loader's
    copy, so catching narrowly requires reading the class back off the one
    module object the ladder actually used.

    Returns None (never raises) when `coordinator_core.engine_root` was
    never reached (an earlier, unrelated resolution rung raised instead) or
    its shim memo is unset — callers treat that as "not this error, re-raise
    the original exception unchanged."
    """
    mod = sys.modules.get("coordinator_core.engine_root")
    shim = getattr(mod, "_shim_module", None) if mod is not None else None
    return getattr(shim, "ClaudeKlabauterResolutionError", None) if shim is not None else None


class _ClaudeKlabauterUnresolvable(RuntimeError):
    """Raised when the engine root cannot be resolved via env var or machine-local registry.

    Callers in the central write loop catch this and degrade gracefully (WARN + skip,
    exit 0) per AC13. The low-level resolver itself fails loud; this is the caller-layer
    resilience wrapper.

    Spec backlink: pln-stop-the-rot-claude-klabauter-state-home-placement-4cc787 § AC13
    """

# ---------------------------------------------------------------------------
# Native schema seam — replaces schema_loader.load_schema, then the deleted
# schema-cli.js Node bridge (removed 480ad8f8).
# Spec backlink: dual-yaml-parser option-d, C4 (original Node-CLI bridge)
# Spec backlink: coordinator_core/frontmatter/schema_cli.py (parity port + op
#   dual-registration this seam routes to)
# ---------------------------------------------------------------------------


def _describe_schema_node(schema_name: str) -> dict:
    """Call the native "schema.describe" op and return its result dict.

    Routes via cc_invoke.route(): State-2 (native seam present) calls the op;
    State-1 (seam absent) raises a hard, actionable error — schema-cli.js (the
    former Node bridge) was deleted in 480ad8f8 and there is no legacy
    implementation to fall back to, so the legacy_fn passed to route() always
    raises rather than degrading schema introspection to a fake-valid result.

    Raises RuntimeError on any route()/transport failure or "unknown schema"
    op-level error — caller (main()) catches this and exits 1.
    """
    def _no_legacy() -> dict:
        raise RuntimeError(
            f"coordinator-lesson-promote: schema-cli.js was deleted (480ad8f8) — "
            f"schema.describe requires the native coordinator_core.invoke seam "
            f"(schema='{schema_name}'); no legacy fallback exists."
        )

    repo_root = _current_repo_root() or os.getcwd()
    return _cc_route("schema.describe", {"schema_name": schema_name}, repo_root, _no_legacy)


# ---------------------------------------------------------------------------
# from_repo resolution — mirrors cross-repo-memo._sender_em_id pattern
# ---------------------------------------------------------------------------

# Registry aliases: stable doctrine EM names that diverge from the repo's
# machine-local shortname convention. Derived from schemas/coordinator-registry.manifest.json
# via coordinator_registry.REPO_ALIASES (loaded above). Mirrors cross-repo-memo RECEIVER_EM_ALIASES.


# _claude_home / _claude_klabauter_root / _machine_local_impl / _resolve_python /
# _machine_local_get / _machine_local_repos_keys / _current_repo_root: extracted
# to bin/lib/cli_shared.py (T2-g2a consolidation, ~150 LoC dup with
# coordinator-queue-append). Thin aliases preserve the pre-consolidation call
# sites below without a mass rename.
_claude_home = cli_shared.claude_home
_claude_klabauter_root = cli_shared.claude_klabauter_root
_machine_local_impl = cli_shared.machine_local_impl
_resolve_python = cli_shared.resolve_python
_machine_local_get = cli_shared.machine_local_get
_machine_local_repos_keys = cli_shared.machine_local_repos_keys


def _current_repo_root() -> str | None:
    """cwd's git root via the checked resolver (`repo_identity`).

    Was `cli_shared.current_repo_root`, deleted by C2 of the one-checked-resolver
    plan on the premise that `resolve_from_repo` was its only caller; this alias,
    `coordinator-queue-append`'s twin, and `coordinator-queue-close` were three
    surviving callers.

    Classification: READER — a MISMATCH warns and proceeds with the resolved
    root (identity attribution, not a destructive action), matching
    `cli_shared.resolve_from_repo`'s disposition under DR-277.
    """
    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict.get("verdict") == "MISMATCH":
        print(
            verdict.get("message", "coordinator-lesson-promote: repo-identity MISMATCH"),
            file=sys.stderr,
        )
    return root

# _resolve_from_repo: extracted to bin/lib/cli_shared.py (T2-g2a consolidation) —
# same cwd git-root -> machine-local reverse-lookup -> doe_claude -> unregistered
# -> "unknown-sender-em" ladder, byte-identical to the pre-consolidation body.
_resolve_from_repo = cli_shared.resolve_from_repo


# ---------------------------------------------------------------------------
# Output path helpers
# ---------------------------------------------------------------------------

def _outbox_root() -> str:
    """Return the lessons-outbox directory path.

    Respects LESSON_PROMOTE_OUTBOX_ROOT env var for test isolation (takes precedence).
    Default: central state root via the DoE seam → <doe_root>/state/lessons-outbox/.
    Raises _DoeUnresolvable (from coordinator_registry.doe_root()) when the DoE root
    cannot be resolved and no env override is present — callers catch this and degrade
    to a SKIP with a non-zero exit (A13: never exit 0 — see legacy_fn's
    _DoeUnresolvable handler in main()).

    Negative-spec: does NOT fall back to cwd-relative state/ or to claude-klabauter when
    DOE_ROOT is unresolvable — silent fallback is a write-plane landmine.

    Spec backlink: docs/plans/2026-07-06-gate2-w23-state-seam-caller-switch.md § C1
    """
    override = os.environ.get(_OUTBOX_ROOT_ENV)
    if override:
        return override
    # Central state (lessons-outbox) routes to DoE — doctrine class.
    # doe_root() raises _DoeUnresolvable when repos.doe_claude is unregistered and
    # DOE_ROOT env var is not set; _DoeUnresolvable propagates to legacy_fn() catch.
    # Spec backlink: gate2-w23-state-seam-caller-switch.md § C1 / AC2
    return os.path.join(doe_root(), "state", "lessons-outbox")


# ---------------------------------------------------------------------------
# --target-wiki normalization and validation (A9, A7)
# ---------------------------------------------------------------------------

def _wiki_inventory_dir() -> str:
    """Return the directory of central wiki .md files to validate --target-wiki against.

    Respects LESSON_PROMOTE_WIKI_ROOT env var for test isolation (takes precedence;
    points DIRECTLY at a directory of .md files, mirroring _OUTBOX_ROOT_ENV's
    override shape — no real DoE-claude checkout required to exercise validation).
    Default: <doe_root>/coordinator/docs/wiki/.

    Raises _DoeUnresolvable (from coordinator_registry.doe_root()) when the DoE root
    cannot be resolved and no env override is present.
    """
    override = os.environ.get(_WIKI_ROOT_ENV)
    if override:
        return override
    return os.path.join(doe_root(), "coordinator", "docs", "wiki")


def _list_central_wiki_targets(wiki_dir: str) -> frozenset[str]:
    """Return the canonical 'docs/wiki/<name>.md' form of every .md file in wiki_dir.

    Raises RuntimeError if wiki_dir does not exist — a resolvable DoE root with a
    missing coordinator/docs/wiki/ directory is an install-integrity problem, not a
    graceful-skip case (contrast the DoE-root-unresolvable case, which IS a
    graceful-skip via _DoeUnresolvable).
    """
    if not os.path.isdir(wiki_dir):
        raise RuntimeError(f"central wiki directory not found: {wiki_dir!r}")
    return frozenset(
        f"{_TARGET_WIKI_PREFIX}{name}"
        for name in os.listdir(wiki_dir)
        if name.endswith(".md")
    )


def _validate_target_wiki(
    parser: argparse.ArgumentParser, normalized_target_wiki: str, allow_new_wiki: bool
) -> int | None:
    """Validate a normalized --target-wiki value against the central wiki inventory (A7).

    Returns an exit code the caller should return immediately, or None when
    validation passed (or was legitimately bypassed) and normal processing should
    continue.

    Bypassed (returns None without touching the DoE root) when:
      - normalized_target_wiki is the 'unknown' sentinel (schema-documented for an
        unresolved classifier target — never a real wiki path).
      - allow_new_wiki is True (the --allow-new-wiki escape hatch, for a genuine
        change_kind: wiki-new promotion where the target intentionally does not
        exist yet).

    On a miss, fails loud via parser.error() (design-as-offers: leads with the
    top-5 closest existing targets via difflib, not just the bare violation) —
    this exits 2, the same family as every other argparse-detected invalid-argument
    case in this CLI.

    Negative-spec (A13 interaction): an unresolvable DoE root during this check is
    NOT a silently-skipped validation — it is the SAME _EXIT_DOE_UNRESOLVABLE (3)
    as the write-skip case, because the inventory this check needs lives under the
    same DoE root the write does.
    """
    if normalized_target_wiki == _TARGET_WIKI_UNKNOWN or allow_new_wiki:
        return None

    try:
        wiki_dir = _wiki_inventory_dir()
    except _DoeUnresolvable as exc:
        print(
            f"error: coordinator-lesson-promote: cannot validate --target-wiki — "
            f"coordinator doctrine repo root unresolvable: {exc}",
            file=sys.stderr,
        )
        print(
            "  Remediation: run 'machine-local set repos.doe_claude /path/to/the-coordinator-doctrine-repo'\n"
            "  or set DOE_ROOT=/path/to/the-coordinator-doctrine-repo before invoking this CLI.\n"
            "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c",
            file=sys.stderr,
        )
        return _EXIT_DOE_UNRESOLVABLE

    try:
        valid_targets = _list_central_wiki_targets(wiki_dir)
    except RuntimeError as exc:
        print(f"error: coordinator-lesson-promote: {exc}", file=sys.stderr)
        return 1

    if normalized_target_wiki in valid_targets:
        return None

    suggestions = difflib.get_close_matches(
        normalized_target_wiki, sorted(valid_targets), n=5
    )
    lines = [
        f"--target-wiki {normalized_target_wiki!r} does not exist in the central wiki "
        f"inventory ({len(valid_targets)} files under {wiki_dir}).",
    ]
    if suggestions:
        lines.append("Did you mean one of:")
        lines.extend(f"  {s}" for s in suggestions)
    lines.append(
        "If this is a genuine new wiki (change_kind: wiki-new), pass --allow-new-wiki "
        "to skip this check."
    )
    parser.error("\n".join(lines))
    return 2  # unreachable — parser.error() always calls sys.exit(2); kept for type-checkers.


def _write_path_excl(out_path: str, content: str) -> str:
    """Write content to out_path using an exclusive-create + retry-with-suffix loop.

    Thin wrapper over bin/lib/cli_shared.write_path_excl (T2-g2a consolidation,
    ~150 LoC dup with coordinator-queue-append) — pins caller_name so the
    exhausted-retry error message still names this CLI. Byte-identical retry/cap/
    fail-loud-after-cap-exhausted behavior to the pre-consolidation body.

    Negative-spec: do NOT swap this for a plain open(path, "w") — that silently
    clobbers a same-key concurrent write. Do NOT swap this for a bare fail-loud
    FileExistsError (the cross-repo-memo shape) either — legacy_fn() here is a
    terminal caller with no retry path, so failing loud on the FIRST collision
    would drop the entry rather than preserve it; retry-with-suffix is required.

    Counter-pattern (deliberate divergence): coordinator/bin/cross-repo-memo.py's
    _write_file FAILS LOUD (FileExistsError, no retry) on collision because its
    caller is interactive and retries with a new --topic.

    Spec backlink: F1/F2 legacy-fallback silent-overwrite collision guard (chunk C1).
    """
    return cli_shared.write_path_excl(
        out_path, content, caller_name="coordinator-lesson-promote"
    )


def _slug_from_title(title: str) -> str:
    """Sanitize a title into a filesystem-safe slug.

    Lowercase, alphanumeric + hyphens only, no leading/trailing hyphens.
    Truncated to _SLUG_MAX_CHARS chars.
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    # Review: code-reviewer — F1/F3: strip("-") before truncation, but truncation can
    # leave a trailing hyphen (e.g. "foo-bar-" at char 40). rstrip("-") after
    # truncation, matching coordinator-queue-append and migrate-queues-to-base.py:292.
    return slug[:_SLUG_MAX_CHARS].rstrip("-")


def _now_iso() -> str:
    """Return current UTC datetime as ISO 8601 string (seconds precision)."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _ts_for_filename(iso_ts: str) -> str:
    """Convert an ISO timestamp to a filesystem-safe filename component.

    Replaces ':' and '+' with '-' for cross-platform filename safety.
    e.g. '2026-06-15T10:30:00+00:00' → '2026-06-15T10-30-00-00-00'
    """
    return re.sub(r"[:+]", "-", iso_ts)


# ---------------------------------------------------------------------------
# YAML serialization (minimal, no external deps)
# ---------------------------------------------------------------------------

def _yaml_str(value: str) -> str:
    """Serialize a string value for YAML.

    Uses block scalar (|) for multi-line values; quoted scalar for single-line
    values that contain YAML-special characters.
    """
    if "\n" in value:
        # Block scalar — indent each line by 2 spaces.
        # Review: code-reviewer Slice-B — (B-F8) changed | (clip chomping) to |- (strip
        # chomping) for byte-fidelity parity with coordinator-queue-append._yaml_block_scalar.
        # Clip chomping adds a trailing newline on round-trip; strip chomping preserves exact bytes.
        indented = "\n".join("  " + line if line.strip() else "" for line in value.splitlines())
        return "|-\n" + indented
    # Single-line: quote if it contains YAML-special characters or leading/trailing whitespace.
    needs_quoting = any(c in value for c in ('"', "'", ":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", ">", "!", "%", "@", "`"))
    needs_quoting = needs_quoting or value != value.strip() or value.lower() in ("true", "false", "null", "yes", "no")
    if needs_quoting:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _compose_yaml(fields: dict[str, str | list[str] | None]) -> str:
    """Compose a YAML document from an ordered dict of fields.

    Handles str and list[str] values. None values are serialized as empty string.
    """
    lines = ["---"]
    for key, value in fields.items():
        if value is None:
            lines.append(f"{key}: ")
        elif isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {_yaml_str(item)}")
        else:
            # Review: code-reviewer — collapsed the former "\n" in str(value) elif and
            # this else branch: both emitted byte-identical code since _yaml_str already
            # internally branches on newline presence (block scalar vs. quoted scalar).
            lines.append(f"{key}: {_yaml_str(str(value))}")
    lines.append("---")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Core write logic
# ---------------------------------------------------------------------------

def _write_entry(
    *,
    title: str,
    body: str,
    change_kind: str,
    target_wiki: str,
    scope_tags: list[str],
    evidence: str | None,
    entry_id: str,
    created: str,
    from_repo: str,
) -> str:
    """Write a lessons-outbox YAML entry. Returns the path written."""
    outbox = _outbox_root()
    os.makedirs(outbox, exist_ok=True)

    ts_safe = _ts_for_filename(created)
    slug = _slug_from_title(title)
    filename = f"{ts_safe}-{slug}.yaml"
    path = os.path.join(outbox, filename)

    fields: dict = {
        "id": entry_id,
        "created": created,
        "from_repo": from_repo,
        "change_kind": change_kind,
        "target_wiki": target_wiki,
        "title": title,
        "body": body,
    }
    if scope_tags:
        fields["scope_tags"] = scope_tags
    if evidence:
        fields["evidence"] = evidence

    content = _compose_yaml(fields)
    # Collision guard (C1, legacy-fallback silent-overwrite fix): plain open(path, "w")
    # is a silent overwrite when path already exists — a same-timestamp+slug collision
    # from a concurrent second write would destroy the first entry with no error.
    # _write_path_excl replaces this with an exclusive-create + retry-with-suffix loop
    # so BOTH entries persist under distinct filenames.
    return _write_path_excl(path, content)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser(change_kind_values: tuple[str, ...]) -> argparse.ArgumentParser:
    """Build the argument parser. change_kind_values is derived at runtime from the schema."""
    parser = argparse.ArgumentParser(
        prog="coordinator-lesson-promote",
        description=(
            "Write a universal lesson entry to state/lessons-outbox/ for drain "
            "by the /learn-lessons --central procedure.\n\n"
            "Spec: docs/plans/2026-06-15-universal-lesson-routing-mechanical-capture.md § C1\n"
            "Schema: docs/wiki/lessons-outbox-schema.md\n\n"
            "Exit codes:\n"
            "  0  success — entry written to state/lessons-outbox/.\n"
            "  1  unexpected error (schema load failure, filesystem error).\n"
            "  2  invalid arguments — including --target-wiki not found in the\n"
            "     central wiki inventory (see --allow-new-wiki).\n"
            "  3  coordinator doctrine repo root unresolvable — write (or --target-wiki\n"
            "     validation) SKIPPED, never treated as success."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--title",
        required=True,
        help="One-line lesson title (bold heading in lessons.md format).",
    )
    parser.add_argument(
        "--body",
        default=None,
        help=(
            "Lesson body prose — 1-2 sentences describing the pattern and fix. "
            "Exactly one of --body / --body-file is required."
        ),
    )
    parser.add_argument(
        "--body-file",
        dest="body_file",
        default=None,
        help=(
            "Read the lesson body from PATH ('-' for stdin) instead of --body. "
            "Exactly one of --body / --body-file is required. The only body "
            "transport that survives every launcher leg intact — see --body's "
            "own refusal for why."
        ),
    )
    parser.add_argument(
        "--change-kind",
        required=True,
        choices=change_kind_values,
        metavar="CHANGE_KIND",
        help=(
            f"Kind of change this lesson routes to. One of: {', '.join(change_kind_values)}. "
            "See docs/wiki/lessons-outbox-schema.md for semantics."
        ),
    )
    parser.add_argument(
        "--target-wiki",
        required=True,
        help=(
            "Central wiki path this lesson targets, e.g. docs/wiki/some-wiki.md — validated "
            "against the real central wiki inventory unless 'unknown' or --allow-new-wiki. "
            "Use 'unknown' when the target wiki is not yet identified."
        ),
    )
    parser.add_argument(
        "--allow-new-wiki",
        action="store_true",
        help=(
            "Skip the --target-wiki inventory check for a genuine change_kind: wiki-new "
            "promotion, where the target intentionally does not exist yet."
        ),
    )
    parser.add_argument(
        "--scope-tags",
        default="",
        help="Optional comma-separated scope tags, e.g. 'executor,plan-authoring'.",
    )
    parser.add_argument(
        "--evidence",
        default=None,
        help="Optional evidence: commit SHA, plan path, or lesson source reference.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code."""
    # Derive the valid change_kind enum from the lessons-outbox schema at runtime
    # via the native "schema.describe" op (schema='lessons-outbox').
    # Fails loud (non-zero exit + stderr) if the schema cannot be loaded.
    # Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § C1
    # Rewired from schema_loader.load_schema → node CLI (dual-yaml-parser option-d C4)
    # → native coordinator_core op seam (schema-cli.js deleted 480ad8f8)
    try:
        _cli_output = _describe_schema_node("lessons-outbox")
        change_kind_values: tuple[str, ...] = tuple(_cli_output["enums"]["change_kind"])
    except RuntimeError as exc:
        print(f"error: schema load failed: {exc}", file=sys.stderr)
        return 1
    except (KeyError, TypeError) as exc:
        print(f"error: unexpected schema structure for 'lessons-outbox': {exc}", file=sys.stderr)
        return 1

    parser = _build_parser(change_kind_values)
    args = parser.parse_args(argv)
    # Review: code-reviewer Slice-B — (B-F3) deleted unreachable dead block that re-validated
    # change_kind after argparse; argparse choices= already rejects invalid values with exit 2
    # naming the valid set, so the explicit check was dead code.

    # coordinator_core is not on sys.path here by construction on the
    # published mirror (not pip-installed there) — the _LIB_DIR insert at the
    # top of this file only reaches coordinator/bin/lib, never the engine root.
    #
    # A fresh machine with repos.claude_klabauter unregistered (no CLAUDE_KLABAUTER_ROOT
    # env override either) is the reachable, production case this guards:
    # `_resolve_engine_root()` walks all the way to
    # `coordinator_core.engine_root.coordinator_engine_root_with_class()`,
    # whose own resolve-claude-klabauter shim fails loud with `ClaudeKlabauterResolutionError`
    # (its documented, correct contract — see that module's own docstring;
    # NOT touched here). Prior to this fix that propagated as an unhandled
    # traceback instead of the same graceful WARN+skip degrade this CLI
    # already gives an unresolvable DoE-claude root. Caught narrowly (never
    # a bare `except Exception`) via `_claude_klabauter_resolution_error_class()`,
    # because the exception class this raises has no import-stable identity
    # this CLI can name ahead of time — see that helper's docstring.
    try:
        require_dispatch_engine_on_path()
    except RuntimeError as exc:
        _resolution_err_cls = _claude_klabauter_resolution_error_class()
        if _resolution_err_cls is None or not isinstance(exc, _resolution_err_cls):
            raise
        # Same remediation vocabulary the resolver itself already names —
        # do not invent a second one (message-register doctrine, one fact
        # once). Reuses _EXIT_DOE_UNRESOLVABLE: the one caller in this tree
        # that shells out to this CLI (coordinator-harvest-deferrals.py)
        # only ever branches on `returncode != 0`, never on the specific
        # code, so a distinct exit code would buy no caller anything today.
        print(
            f"warn: coordinator-lesson-promote: claude-klabauter root unresolvable — "
            f"skipping central lessons-outbox write: {exc}",
            file=sys.stderr,
        )
        return _EXIT_DOE_UNRESOLVABLE
    from coordinator_core.argv_fidelity import ArgvFidelityError, refuse_newline_argv, resolve_body

    try:
        refuse_newline_argv(args.body, flag_name="--body")
        args.body = resolve_body(args.body, args.body_file)
    except ArgvFidelityError as exc:
        parser.error(str(exc))

    # --allow-new-wiki is documented (and only sound) as an escape hatch for a genuine
    # change_kind: wiki-new promotion, where the target intentionally does not exist yet.
    # wiki-append targets an EXISTING wiki section by schema semantics (see
    # docs/wiki/lessons-outbox-schema.md § Change-kind enum) — an append target should
    # always be inventory-validated. Reject the mismatch here, at argparse time, rather
    # than threading change_kind into _validate_target_wiki, so a caller combining the
    # flag with wiki-append (or any other change_kind) fails loud and early instead of
    # silently skipping the inventory check.
    if args.allow_new_wiki and args.change_kind != "wiki-new":
        parser.error(
            f"--allow-new-wiki is only valid with --change-kind wiki-new "
            f"(got --change-kind {args.change_kind!r})"
        )

    # A9: normalize BEFORE the A7 inventory check, so 'foo' and 'foo.md' validate
    # (and later write) identically instead of diverging into two dedup keys.
    # Gated on change_kind (A7/A9 scope fix): --target-wiki is the generic
    # promotion-target field for every change_kind, not only wiki entries — a
    # skill-edit promotion stores a SKILL.md path here, not a central-wiki name.
    # Only wiki-new/wiki-append (the schema's wiki-targeting change_kinds — see
    # docs/wiki/lessons-outbox-schema.md § Change-kind enum) run the directory
    # collapse and the central-wiki-inventory check; every other change_kind's
    # --target-wiki passes through UNCHANGED and UNVALIDATED.
    if args.change_kind in _WIKI_TARGETING_CHANGE_KINDS:
        args.target_wiki = _normalize_target_wiki(args.target_wiki)
        _early_exit = _validate_target_wiki(parser, args.target_wiki, args.allow_new_wiki)
        if _early_exit is not None:
            return _early_exit

    scope_tags = [t.strip() for t in args.scope_tags.split(",") if args.scope_tags.strip() and t.strip()]

    entry_id = str(uuid.uuid4())
    created = _now_iso()
    # Review: code-reviewer strang-08-slice3 — (F3) hoist _current_repo_root() so git rev-parse
    # spawns exactly once per invocation; pass resolved root to _resolve_from_repo and reuse
    # for _cc_route repo_root arg below.
    _raw_root = _current_repo_root()
    repo_root = _raw_root or ""
    from_repo = _resolve_from_repo(root=_raw_root)

    # ── routing gate ─────────────────────────────────────────────────────────
    # Capture the legacy write body as a closure; byte-identical to pre-swap HEAD.
    # State-1 (seam absent): _cc_route calls legacy_fn() and returns its int exit code.
    # State-2 (seam present): _cc_route returns the bare result dict from queue.promote.
    # Spec backlink: docs/plans/2026-07-06-strang-08-arm-queue-facade-invoke-retarget.md § C4
    def legacy_fn() -> int:
        try:
            path = _write_entry(
                title=args.title,
                body=args.body,
                change_kind=args.change_kind,
                target_wiki=args.target_wiki,
                scope_tags=scope_tags,
                evidence=args.evidence if args.evidence else None,
                entry_id=entry_id,
                created=created,
                from_repo=from_repo,
            )
        except _DoeUnresolvable as exc:
            # A13 fix: graceful-skip on unresolvable DOE_ROOT is WARN + skip, but the
            # skip is NEVER silent success — exit _EXIT_DOE_UNRESOLVABLE (3), not 0.
            # A coordinator install without repos.doe_claude registered (pre-fleet-clone
            # or non-DoE machine) WARNs, writes nothing, and reports that honestly via
            # a non-zero exit code — a caller checking only `returncode == 0` must be
            # able to trust that outcome. Negative-spec: this was PREVIOUSLY `return 0`
            # (A13 defect) — every promotion on a machine without repos.doe_claude
            # registered evaporated while the exit code claimed success.
            # Spec backlink: docs/plans/2026-07-06-gate2-w23-state-seam-caller-switch.md § C1 / AC2
            print(
                f"warn: coordinator-lesson-promote: DOE_ROOT unresolvable — "
                f"skipping central lessons-outbox write: {exc}",
                file=sys.stderr,
            )
            print(
                "  Remediation: run 'machine-local set repos.doe_claude /path/to/the-coordinator-doctrine-repo'\n"
                "  or set DOE_ROOT=/path/to/the-coordinator-doctrine-repo before invoking this CLI.\n"
                "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c",
                file=sys.stderr,
            )
            return _EXIT_DOE_UNRESOLVABLE
        except OSError as exc:
            print(f"error: could not write outbox entry: {exc}", file=sys.stderr)
            return 1

        print(f"Lesson outbox entry written: {path}")
        print(f"  id:          {entry_id}")
        print(f"  from_repo:   {from_repo}")
        print(f"  change_kind: {args.change_kind}")
        print(f"  target_wiki: {args.target_wiki}")
        # C5 floor (docs/plans/2026-08-14-cli-authored-writes-get-claimed.md):
        # this genuine dual-path CLI's State-1 body writes in-process, so the
        # write must be declared, not just printed. Guarded import: `route()`
        # only calls legacy_fn() when coordinator_core.invoke was already
        # unresolvable, so coordinator_core is usually unimportable here too —
        # this degrades to a no-op except under the LESSON_PROMOTE_OUTBOX_ROOT
        # test-isolation gate below, which forces legacy_fn with a live engine
        # still on sys.path.
        try:
            require_dispatch_engine_on_path()
            from coordinator_core.session.declared_writes import declare_write  # noqa: PLC0415

            declare_write(path)
        except ImportError:
            pass
        return 0

    def _run_legacy_with_write_declaration() -> int:
        """Run `legacy_fn` inside cli_entry's declare-write collection when
        the engine happens to be importable — see legacy_fn's own comment on
        why this is usually a no-op degrade. Both legacy_fn call sites below
        route through this instead of calling legacy_fn directly.

        Review: coordinator:code-reviewer — the LESSON_PROMOTE_OUTBOX_ROOT
        test-isolation gate is not a rare edge case: it is exactly the shape
        this repo's own test suite invokes, with coordinator_core genuinely
        importable, so `recording_declared_writes`/`declare_write` fire for
        real under it. What keeps that safe is
        `ipc._record_self_reported_touches`'s F1 containment (2026-08-04):
        a declared path is only recorded as a session claim when it resolves
        INSIDE the caller's own `_origin_worktree`; a fixture path outside
        the repo tree (every existing test here uses a `tmpdir` outside the
        repo as both the env-gate root and cwd) is skipped, never claimed
        against whatever real session is an ancestor of the test process.
        This stays safe only as long as fixtures for this gate live outside
        the repo tree — an in-tree fixture path would be a live claim
        against the wrong session.
        """
        try:
            require_dispatch_engine_on_path()
            from coordinator_core.cli_entry import recording_declared_writes  # noqa: PLC0415
        except ImportError:
            return legacy_fn()
        with recording_declared_writes(cwd=repo_root):
            return legacy_fn()

    # Build queue.promote params from validated fields; from_repo passed explicitly
    # so the op does not fall to its basename+"-em" default (provenance parity, AC11).
    # repo_root already computed above (F3 hoist — single git rev-parse per invocation).
    params: dict = {
        "title": args.title,
        "body": args.body,
        "change_kind": args.change_kind,
        "target_wiki": args.target_wiki,
        "scope_tags": scope_tags,
        "evidence": args.evidence if args.evidence else None,
        "from_repo": from_repo,
    }
    # Test isolation gate: LESSON_PROMOTE_OUTBOX_ROOT redirects the outbox path (see
    # _outbox_root() above), which the native queue.promote op does not honour — it
    # resolves repos.doe_claude on its own, independent of this process's env. When
    # set, routing native would silently escape the override and write to whatever
    # doe_claude is ACTUALLY registered as on the invoking machine — mirrors
    # coordinator-queue-append's identical QUEUE_APPEND_OUTPUT_ROOT gate immediately
    # above _cc_route("queue.append", ...) in that sibling CLI. In production,
    # LESSON_PROMOTE_OUTBOX_ROOT is NEVER set, so this check is a no-op.
    if os.environ.get(_OUTBOX_ROOT_ENV):
        return _run_legacy_with_write_declaration()

    result = _cc_route("queue.promote", params, repo_root, _run_legacy_with_write_declaration)

    # Native path: result is the bare dict from queue.promote.
    if isinstance(result, dict):
        if result.get("skipped"):
            # A13 fix (native-op mirror of the legacy_fn _DoeUnresolvable handler
            # above): skipped:true → WARN + exit _EXIT_DOE_UNRESOLVABLE (3), never 0.
            # Negative-spec: this was PREVIOUSLY `return 0` (A13 defect) — identical
            # silent-success hole to the legacy path, just reached via the native
            # queue.promote op's {"skipped": true, "reason": ...} result shape instead
            # of a raised _DoeUnresolvable exception.
            reason = result.get("reason", "DOE_ROOT unresolvable")
            print(
                f"warn: coordinator-lesson-promote: DOE_ROOT unresolvable — "
                f"skipping central lessons-outbox write: {reason}",
                file=sys.stderr,
            )
            return _EXIT_DOE_UNRESOLVABLE
        # Review: code-reviewer strang-08-slice3 — (F1) guard out_path access; bare KeyError
        # on unexpected op result shape (missing both out_path and skipped) gives a misleading
        # traceback instead of a clean error. TWO-SIGNAL contract lives in the op, not here.
        out_path = result.get("out_path")
        if not out_path:
            print(
                f"error: coordinator-lesson-promote: op returned unexpected result shape "
                f"(no out_path and skipped not set): {result!r}",
                file=sys.stderr,
            )
            return 1
        print(out_path)
        return 0
    # Legacy path: legacy_fn() returned an int exit code.
    return int(result)


if __name__ == "__main__":
    sys.exit(main())
