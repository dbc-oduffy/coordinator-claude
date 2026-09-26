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
(<doe_root>/coordinator/docs/wiki/**/*.md, enumerated recursively — nested pages such
as coordinator-tripwires/ count) unless the literal value 'unknown' is passed, or
--allow-new-wiki is given (escape hatch for a genuine wiki-new OR wiki-append
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


_SLUG_MAX_CHARS = 40

_OUTBOX_ROOT_ENV = "LESSON_PROMOTE_OUTBOX_ROOT"

# by --target-wiki validation (A7). Mirrors _OUTBOX_ROOT_ENV's override shape: when
# set, points DIRECTLY at a directory of .md files (not the DoE repo root), so tests
_WIKI_ROOT_ENV = "LESSON_PROMOTE_WIKI_ROOT"

_EXIT_DOE_UNRESOLVABLE = 3

_PUBLISH_MIRROR_MARKERS = (
    os.path.join("plugins", "coordinator-claude"),
    os.path.join("plugins", "cache", "coordinator-claude"),
)


def _is_publish_mirror_root(resolved_root: str) -> bool:
    normalized = os.path.normpath(resolved_root)
    return any(marker in normalized for marker in _PUBLISH_MIRROR_MARKERS)

# Env var for DOE_ROOT override — mirrors CLAUDE_KLABAUTER_ROOT §4b idempotency gate.
_DOE_ROOT_ENV = "DOE_ROOT"


_BOOTSTRAPPED_NAMES = (
    "doe_root",
    "_DoeUnresolvable",
    "require_dispatch_engine_on_path",
    "_cc_route",
    "cli_shared",
    "resolve_checked_repo_root",
    "_WIKI_TARGETING_CHANGE_KINDS",
    "_normalize_target_wiki",
    "_TARGET_WIKI_UNKNOWN",
    "_TARGET_WIKI_PREFIX",
    "_MACHINE_LOCAL_IMPL_ENV",
    "_CLAUDE_HOME_ENV",
    "_CLAUDE_KLABAUTER_ROOT_ENV",
    "_claude_home",
    "_claude_klabauter_root",
    "_machine_local_impl",
    "_resolve_python",
    "_machine_local_get",
    "_machine_local_repos_keys",
    "_resolve_from_repo",
)


_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Bind the engine on the DISPATCH axis, then everything downstream of it.

    Idempotent. THE ORDER INSIDE THIS FUNCTION IS THE POINT, which is why it is
    one function rather than deferred imports at each use site: the original
    module-scope sequence is preserved below byte-for-byte, comments included.

    What moved is the trigger, not the order. This ran at MODULE scope until now,
    so every import of this file mutated the `sys.path` of a warm server ~50
    sessions share -- the AC20 impurity this plan exists to remove.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    try:

        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        from coordinator_registry import doe_root, _DoeUnresolvable
        from cc_invoke import require_dispatch_engine_on_path
        from cc_invoke import route as _cc_route

        require_dispatch_engine_on_path()
        # LOAD-BEARING, NOT DEAD. Do not delete on an unused-import sweep: this line is
        import coordinator_core

        import cli_shared
        from repo_identity import resolve_checked_repo_root
        from target_wiki_canon import (
            WIKI_TARGETING_CHANGE_KINDS as _WIKI_TARGETING_CHANGE_KINDS,
            normalize_target_wiki as _normalize_target_wiki,
            TARGET_WIKI_UNKNOWN as _TARGET_WIKI_UNKNOWN,
            TARGET_WIKI_PREFIX as _TARGET_WIKI_PREFIX,
        )

        _MACHINE_LOCAL_IMPL_ENV = cli_shared.MACHINE_LOCAL_IMPL_ENV

        # Env var for CLAUDE_HOME override (mirrors cross-repo-memo pattern).
        _CLAUDE_HOME_ENV = cli_shared.CLAUDE_HOME_ENV

        # Env var for CLAUDE_KLABAUTER_ROOT override — mirrors coordinator-claude-klabauter-root.sh §4b
        _CLAUDE_KLABAUTER_ROOT_ENV = cli_shared.CLAUDE_KLABAUTER_ROOT_ENV

        _claude_home = cli_shared.claude_home
        _claude_klabauter_root = cli_shared.claude_klabauter_root
        _machine_local_impl = cli_shared.machine_local_impl
        _resolve_python = cli_shared.resolve_python
        _machine_local_get = cli_shared.machine_local_get
        _machine_local_repos_keys = cli_shared.machine_local_repos_keys

        _resolve_from_repo = cli_shared.resolve_from_repo

    finally:
        _resolved = locals()
        for _name in _BOOTSTRAPPED_NAMES:
            if _name not in globals() and _name in _resolved:
                globals()[_name] = _resolved[_name]

    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    """PEP 562 hook: consumers that import this module rather than execute it --
    its own test suite, and `workstream_complete.apply._load_cli_module`'s
    in-process dispatch -- read these names before `main()` runs. Deferring the
    bootstrap without this leaves them simply absent, which is what forced an
    earlier repair pass to hoist the whole block back to module scope.

    Note this hook covers module-ATTRIBUTE access only. A sibling function in
    THIS module reading the same name as a global does not route through it, so
    every such function calls `_bootstrap_engine()` itself.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_engine()
        if name not in globals():
            global _BOOTSTRAP_DONE
            _BOOTSTRAP_DONE = False
            _bootstrap_engine()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} after bootstrap"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    pass


def _describe_schema_node(schema_name: str) -> dict:
    _bootstrap_engine()
    def _no_legacy() -> dict:
        raise RuntimeError(
            f"coordinator-lesson-promote: schema-cli.js was deleted (480ad8f8) — "
            f"schema.describe requires the native coordinator_core.invoke seam "
            f"(schema='{schema_name}'); no legacy fallback exists."
        )

    repo_root = _current_repo_root() or os.getcwd()
    return _cc_route("schema.describe", {"schema_name": schema_name}, repo_root, _no_legacy)


# via coordinator_registry.REPO_ALIASES (loaded above). Mirrors cross-repo-memo RECEIVER_EM_ALIASES.


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
    _bootstrap_engine()
    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict.get("verdict") == "MISMATCH":
        print(
            verdict.get("message", "coordinator-lesson-promote: repo-identity MISMATCH"),
            file=sys.stderr,
        )
    return root


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

    Negative-spec (klabauter#39): does NOT write into an OSS publish-mirror install
    (a scrubbed/marketplace copy of the doctrine repo) even when doe_root() resolves
    one — raises RuntimeError instead. The lessons-outbox is a private central corpus;
    a write into a publish mirror duplicates it into a tree the drain procedure never
    reads back from, and is never correct.

    Spec backlink: docs/plans/2026-07-06-gate2-w23-state-seam-caller-switch.md § C1
    """
    _bootstrap_engine()
    override = cli_shared.isolation_root_if_under_test(
        _OUTBOX_ROOT_ENV, caller_name="coordinator-lesson-promote"
    )
    if override:
        return override
    # DOE_ROOT env var is not set; _DoeUnresolvable propagates to legacy_fn() catch.
    resolved_doe_root = doe_root()
    if _is_publish_mirror_root(resolved_doe_root):
        raise RuntimeError(
            f"coordinator-lesson-promote: refusing to write the lessons-outbox into "
            f"an OSS publish-mirror install ({resolved_doe_root!r}) — the private "
            f"DoE-claude source repo is unresolvable via env/registry. Remediation: "
            f"run 'machine-local set repos.doe_claude /path/to/the-coordinator-doctrine-repo' "
            f"or set DOE_ROOT=/path/to/the-coordinator-doctrine-repo before invoking this CLI."
        )
    return os.path.join(resolved_doe_root, "state", "lessons-outbox")


def _wiki_inventory_dir() -> str:
    """Return the directory of central wiki .md files to validate --target-wiki against.

    Respects LESSON_PROMOTE_WIKI_ROOT env var for test isolation (takes precedence;
    points DIRECTLY at a directory of .md files, mirroring _OUTBOX_ROOT_ENV's
    override shape — no real DoE-claude checkout required to exercise validation).
    Default: the resolved DoE root's coordinator content root, either layout
    (coordinator_data_root.content_root_for), plus docs/wiki/.

    Raises _DoeUnresolvable (from coordinator_registry.doe_root()) when the DoE root
    cannot be resolved and no env override is present.
    """
    _bootstrap_engine()
    from coordinator_data_root import content_root_or_private

    override = os.environ.get(_WIKI_ROOT_ENV)
    if override:
        return override
    resolved = doe_root()
    return os.path.join(content_root_or_private(resolved), "docs", "wiki")


def _list_central_wiki_targets(wiki_dir: str) -> frozenset[str]:
    _bootstrap_engine()
    if not os.path.isdir(wiki_dir):
        raise RuntimeError(f"central wiki directory not found: {wiki_dir!r}")
    targets = []
    for dirpath, _dirnames, filenames in os.walk(wiki_dir):
        for name in filenames:
            if not name.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), wiki_dir)
            rel = rel.replace(os.sep, "/")
            targets.append(f"{_TARGET_WIKI_PREFIX}{rel}")
    return frozenset(targets)


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
    _bootstrap_engine()
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
    return 2


def _repo_relative_outbox_path(path: str) -> str:
    """Best-effort convert an absolute lessons-outbox PATH into a
    'state/lessons-outbox/<file>'-style path relative to the resolved DoE
    root (23c: printing an absolute host path is a portability trap for a
    local EM who stamps the printed line verbatim into a `promoted_to`
    field, per the 2026-09-24 example-game-repo-em memo).

    Falls back to PATH unchanged when the DoE root is unresolvable (e.g.
    `_DoeUnresolvable`) or PATH does not resolve under it (a
    LESSON_PROMOTE_OUTBOX_ROOT test-isolation override pointing somewhere
    unrelated to the resolved DoE root) — never raises, this is a display
    nicety only, never a gate on the write that already succeeded."""
    _bootstrap_engine()
    try:
        root = doe_root()
    except _DoeUnresolvable:
        return path
    try:
        rel = os.path.relpath(path, root)
    except ValueError:
        return path
    if rel.startswith(".."):
        return path
    return rel.replace(os.sep, "/")


def _write_path_excl(out_path: str, content: str) -> str:
    _bootstrap_engine()
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
    return slug[:_SLUG_MAX_CHARS].rstrip("-")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _ts_for_filename(iso_ts: str) -> str:
    """Convert an ISO timestamp to a filesystem-safe filename component.

    Replaces ':' and '+' with '-' for cross-platform filename safety.
    e.g. '2026-06-15T10:30:00+00:00' → '2026-06-15T10-30-00-00-00'
    """
    return re.sub(r"[:+]", "-", iso_ts)


def _yaml_str(value: str) -> str:
    if "\n" in value:
        indented = "\n".join("  " + line if line.strip() else "" for line in value.splitlines())
        return "|-\n" + indented
    needs_quoting = any(c in value for c in ('"', "'", ":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", ">", "!", "%", "@", "`"))
    needs_quoting = needs_quoting or value != value.strip() or value.lower() in ("true", "false", "null", "yes", "no")
    if needs_quoting:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _compose_yaml(fields: dict[str, str | list[str] | None]) -> str:
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
            lines.append(f"{key}: {_yaml_str(str(value))}")
    lines.append("---")
    return "\n".join(lines) + "\n"


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
    return _write_path_excl(path, content)


def _build_parser(change_kind_values: tuple[str, ...]) -> argparse.ArgumentParser:
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
        default=None,
        help=(
            "One-line lesson title (bold heading in lessons.md format). "
            "Exactly one of --title / --title-file is required."
        ),
    )
    parser.add_argument(
        "--title-file",
        dest="title_file",
        default=None,
        help=(
            "Read the lesson title from PATH ('-' for stdin) instead of --title. "
            "Exactly one of --title / --title-file is required. The only title "
            "transport that survives every launcher leg intact — see --title's "
            "own refusal for why."
        ),
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
    _bootstrap_engine()
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

    # A fresh machine with repos.claude_klabauter unregistered (no CLAUDE_KLABAUTER_ROOT
    try:
        require_dispatch_engine_on_path()
    except RuntimeError as exc:
        _resolution_err_cls = _claude_klabauter_resolution_error_class()
        if _resolution_err_cls is None or not isinstance(exc, _resolution_err_cls):
            raise
        # once). Reuses _EXIT_DOE_UNRESOLVABLE: the one caller in this tree
        # capture. It names it by REGISTRY KEY, not by repo name: a reader
        print(
            f"warn: coordinator-lesson-promote: engine root unresolvable "
            f"(repos.claude_klabauter) — skipping central lessons-outbox "
            f"write: {exc}",
            file=sys.stderr,
        )
        return _EXIT_DOE_UNRESOLVABLE
    from coordinator_core.argv_fidelity import ArgvFidelityError, refuse_newline_argv, resolve_body

    try:
        refuse_newline_argv(args.title, flag_name="--title")
        args.title = resolve_body(args.title, args.title_file, flag_name="--title")
        refuse_newline_argv(args.body, flag_name="--body")
        args.body = resolve_body(args.body, args.body_file)
    except ArgvFidelityError as exc:
        parser.error(str(exc))

    # --allow-new-wiki is an escape hatch for --target-wiki validation and is not
    # wiki-new-only: a wiki-append promotion can also legitimately target a wiki
    # page that does not exist in the central inventory yet (e.g. the page is
    # being created by a sibling change in the same batch).
    if args.allow_new_wiki and args.change_kind not in _WIKI_TARGETING_CHANGE_KINDS:
        parser.error(
            f"--allow-new-wiki is only valid with --change-kind wiki-new or "
            f"wiki-append (got --change-kind {args.change_kind!r})"
        )

    # --target-wiki passes through UNCHANGED and UNVALIDATED.
    if args.change_kind in _WIKI_TARGETING_CHANGE_KINDS:
        args.target_wiki = _normalize_target_wiki(args.target_wiki)
        _early_exit = _validate_target_wiki(parser, args.target_wiki, args.allow_new_wiki)
        if _early_exit is not None:
            return _early_exit

    scope_tags = [t.strip() for t in args.scope_tags.split(",") if args.scope_tags.strip() and t.strip()]

    entry_id = str(uuid.uuid4())
    created = _now_iso()
    _raw_root = _current_repo_root()
    repo_root = _raw_root or ""
    from_repo = _resolve_from_repo(root=_raw_root)

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
            # able to trust that outcome. Negative-spec: this was PREVIOUSLY `return 0`
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
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"error: could not write outbox entry: {exc}", file=sys.stderr)
            return 1

        print(f"Lesson outbox entry written: {_repo_relative_outbox_path(path)}")
        print(f"  id:          {entry_id}")
        print(f"  from_repo:   {from_repo}")
        print(f"  change_kind: {args.change_kind}")
        print(f"  target_wiki: {args.target_wiki}")
        # this degrades to a no-op except under the LESSON_PROMOTE_OUTBOX_ROOT
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

        The LESSON_PROMOTE_OUTBOX_ROOT
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

    params: dict = {
        "title": args.title,
        "body": args.body,
        "change_kind": args.change_kind,
        "target_wiki": args.target_wiki,
        "scope_tags": scope_tags,
        "evidence": args.evidence if args.evidence else None,
        "from_repo": from_repo,
    }
    # against (DOE_ROOT honoured), not re-resolve it from the warm server's own env
    try:
        params["doe_root"] = doe_root()
    except _DoeUnresolvable:
        pass
    # Test isolation gate: LESSON_PROMOTE_OUTBOX_ROOT redirects the outbox path (see
    # coordinator-queue-append's identical QUEUE_APPEND_OUTPUT_ROOT gate immediately
    # LESSON_PROMOTE_OUTBOX_ROOT is NEVER set, so this check is a no-op.
    if cli_shared.isolation_root_if_under_test(
        _OUTBOX_ROOT_ENV, caller_name="coordinator-lesson-promote"
    ):
        return _run_legacy_with_write_declaration()

    # DOE_ROOT gate (klabauter#33): DOE_ROOT is documented (module docstring, § from_repo
    # resolution / _DOE_ROOT_ENV) as this CLI's steering lever for the DoE-claude root, and
    # queue.promote op's resolver (coordinator_core.ops.coordinator_doe_root) has no DOE_ROOT
    # rung at all — only REPO_DOE_CLAUDE — so an operator who set DOE_ROOT (without also
    # setting REPO_DOE_CLAUDE) would see --target-wiki validation obey it while the native
    # write, which resolves through THIS module's own DOE_ROOT-aware doe_root(), whenever
    # DOE_ROOT is the only lever the operator has pulled.
    if os.environ.get(_DOE_ROOT_ENV, "").strip() and not os.environ.get("REPO_DOE_CLAUDE", "").strip():
        return _run_legacy_with_write_declaration()

    result = _cc_route("queue.promote", params, repo_root, _run_legacy_with_write_declaration)

    if isinstance(result, dict):
        if result.get("skipped"):
            # above): skipped:true → WARN + exit _EXIT_DOE_UNRESOLVABLE (3), never 0.
            # Negative-spec: this was PREVIOUSLY `return 0` (A13 defect) — identical
            reason = result.get("reason", "DOE_ROOT unresolvable")
            print(
                f"warn: coordinator-lesson-promote: DOE_ROOT unresolvable — "
                f"skipping central lessons-outbox write: {reason}",
                file=sys.stderr,
            )
            print(
                "  Remediation: run 'machine-local set repos.doe_claude /path/to/the-coordinator-doctrine-repo'\n"
                "  or set DOE_ROOT=/path/to/the-coordinator-doctrine-repo before invoking this CLI.\n"
                "  Reference: plugins/coordinator/docs/wiki/machine-local-registry.md §4c",
                file=sys.stderr,
            )
            return _EXIT_DOE_UNRESOLVABLE
        # traceback instead of a clean error. TWO-SIGNAL contract lives in the op, not here.
        out_path = result.get("out_path")
        if not out_path:
            print(
                f"error: coordinator-lesson-promote: op returned unexpected result shape "
                f"(no out_path and skipped not set): {result!r}",
                file=sys.stderr,
            )
            return 1
        # cheap check that would have made the DOE_ROOT/native-write mismatch
        print(f"Lesson outbox entry written: {_repo_relative_outbox_path(out_path)}")
        print(f"  id:          {result.get('entry_id', entry_id)}")
        print(f"  from_repo:   {result.get('from_repo', from_repo)}")
        print(f"  change_kind: {result.get('change_kind', args.change_kind)}")
        print(f"  target_wiki: {result.get('target_wiki', args.target_wiki)}")
        return 0
    return int(result)


if __name__ == "__main__":
    sys.exit(main())
