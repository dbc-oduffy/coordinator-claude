"""
query-file-attribution.py — Read-only CLI for session→file attribution queries.

Purpose: Answer two reverse-lookup queries derived from Claude Code transcripts:
  --session <id>   → which files that session touched (with edited/read/referenced counts)
  --file <path>    → which sessions touched that file (with counts)

Thin CLI wrapper over derive-file-attribution.py (importlib-loaded from the same bin/).
Queries transcripts directly — does NOT read state/file-attribution-ledger/ shards.
Output is JSON by default; --format table for human-readable tabular output.

CLI:
    python3 query-file-attribution.py --session <id> [--project <root>]
    python3 query-file-attribution.py --file <path>  [--project <root>]
    python3 query-file-attribution.py --session <id> --file <path>  [--project <root>]

Spec backlink: pln-ccos-6-rehome-attribution-python-9966da § C2
Spec backlink: pln-three-query-trampolines-and-th-309bf9 § C5 (owner-qualified repo slug)
Replaces:      plugins/coordinator/bin/query-file-attribution.mjs

`repo` is stamped via the canonical producer
(`coordinator_core.ops.emit.context.resolve_repo_name`), never a second
`git remote` parser here. `--project` MUST name a repo root, not a
subdirectory — checked via `coordinator_core.git.repo_root.show_toplevel`
(fail-loud on mismatch); a remoteless repo's `local/<basename>` fallback is
stamped as-is, not rejected. `coordinator_root_path` is left at
`derive-file-attribution.aggregate`'s own default (`"."`) rather than passed
as an absolute path.

--file matching: accepts an absolute path or a path relative to --project (or
cwd if --project is unset), either separator style ('/' or '\\'), matched
case-insensitively on Windows only. A relative arg is resolved against the
project root and compared to stored (often absolute) record paths, and vice
versa — no filesystem access, no symlink following, '.'/'..' collapsed via
os.path.normpath only.

Negative-spec:
  - Do NOT write to state/ or any other disk location — read-only consumer.
  - Do NOT query state/file-attribution-ledger/ shards (that is the old .mjs path).
  - git-cross-check is NOT ported — the ledger-based reconciliation mode had no
    transcript-derived equivalent and is superseded by the new derivation model.
  - Do NOT fabricate file paths — derive-file-attribution.py's null-on-ambiguity
    invariant is respected; unknown rows with null file_path are absent from output.
  - --file matching is whole-path equality after resolution only — never a
    suffix/endswith match (would falsely match ingest.ts against vendor/ingest.ts).
  - Do NOT case-canonicalise the repo slug — casing is producer-authoritative
    (resolve_repo_name's own return value), stamped as-is.
  - Do NOT touch derive-file-attribution.py's _derive_handoff_id or _repo_name —
    both are out of scope for this CLI (see pln-three-query-trampolines-and-th-309bf9 § C5).
"""

import argparse
import importlib.util
import json
import os
import sys
from typing import Any, Dict, List, Optional

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib')
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from op_trampoline import resolve_claude_klabauter_root_or_exit  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402


# ---------------------------------------------------------------------------
# Load derive-file-attribution.py via importlib (filename has hyphens).
# Both files live in bin/; resolve relative to this script's directory.
# ---------------------------------------------------------------------------

def _load_derive_module():
    """Load derive-file-attribution.py via importlib (hyphenated filename)."""
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    module_path = os.path.join(bin_dir, 'derive-file-attribution.py')
    if not os.path.isfile(module_path):
        sys.stderr.write(
            f'Error: derive-file-attribution.py not found at {module_path}\n'
        )
        sys.exit(1)
    spec = importlib.util.spec_from_file_location('derive_file_attribution', module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return mod


# Review: code-reviewer (F4) — _load_derive_module() moved into main() so that
# --help invocations and argument-validation failures do not trigger importlib
# load (and a potential sys.exit(1)) at import time.


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _normalise_path(p: str) -> str:
    """Normalise path separators (and case, on Windows) for cross-platform matching."""
    p = p.replace('\\', '/')
    if sys.platform == 'win32':
        p = p.casefold()
    return p


def _resolved_forms(p: str, project_root: str) -> List[str]:
    """Return the set of normalised comparison forms for a path.

    Includes the path as given, and — if it is not already absolute — the
    path resolved against project_root. Never touches the filesystem and
    never follows symlinks; os.path.normpath only collapses '.'/'..'.
    """
    forms = [_normalise_path(os.path.normpath(p))]
    if not os.path.isabs(p):
        joined = os.path.normpath(os.path.join(project_root, p))
        forms.append(_normalise_path(joined))
    return forms


def query_by_session(
    records: List[Dict[str, Any]], session_id: str
) -> List[Dict[str, Any]]:
    """Return aggregate records for the given session_id, sorted by file_path."""
    matches = [r for r in records if r.get('session_id') == session_id]
    return sorted(matches, key=lambda r: r.get('file_path', '') or '')


def query_by_file(
    records: List[Dict[str, Any]], file_path: str, project_root: str
) -> List[Dict[str, Any]]:
    """Return aggregate records for the given file_path, sorted by session_id.

    Matches when the query arg and the stored record path agree after
    resolution against project_root in either direction — handles both an
    absolute record with a relative query arg, and a relative record (e.g.
    from a Bash-redirect row) with an absolute query arg.
    """
    query_forms = set(_resolved_forms(file_path, project_root))
    matches = []
    for r in records:
        record_path = r.get('file_path', '') or ''
        if not record_path:
            continue
        record_forms = set(_resolved_forms(record_path, project_root))
        if query_forms & record_forms:
            matches.append(r)
    return sorted(matches, key=lambda r: r.get('session_id', '') or '')


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _fmt_json(records: List[Dict[str, Any]]) -> str:
    """Format records as a pretty-printed JSON array."""
    return json.dumps(records, ensure_ascii=False, indent=2)


def _fmt_table_session(records: List[Dict[str, Any]], session_id: str) -> str:
    """Human-readable table for a --session query (rows = files)."""
    lines = [f'session: {session_id}', f'found: {len(records)} file(s)', '']
    if not records:
        return '\n'.join(lines)
    # Review: code-reviewer (F10) — compute column width dynamically so realistic
    # file paths (e.g. plugins/coordinator-claude/.../derive-file-attribution.py at
    # 67 chars) don't overflow the hardcoded 55-char column and misalign the table.
    col_width = max(max(len(r.get('file_path', '') or '') for r in records), 30)
    col_width = min(col_width, 80)
    header = f'{"file_path":<{col_width}} {"edited":>6} {"read":>5} {"ref":>5}  last_op     completeness'
    lines.append(header)
    lines.append('-' * len(header))
    for r in records:
        fp = r.get('file_path') or ''
        lines.append(
            f'{fp:<{col_width}} '
            f'{r.get("edited_count", 0):>6} '
            f'{r.get("read_count", 0):>5} '
            f'{r.get("referenced_count", 0):>5}  '
            f'{(r.get("last_operation") or "-"):<11} '
            f'{r.get("completeness") or "-"}'
        )
    return '\n'.join(lines)


def _fmt_table_file(records: List[Dict[str, Any]], file_path: str) -> str:
    """Human-readable table for a --file query (rows = sessions)."""
    lines = [f'file: {file_path}', f'found: {len(records)} session(s)', '']
    if not records:
        return '\n'.join(lines)
    header = f'{"session_id":<45} {"edited":>6} {"read":>5} {"ref":>5}  last_op     completeness'
    lines.append(header)
    lines.append('-' * len(header))
    for r in records:
        sid = r.get('session_id') or ''
        lines.append(
            f'{sid:<45} '
            f'{r.get("edited_count", 0):>6} '
            f'{r.get("read_count", 0):>5} '
            f'{r.get("referenced_count", 0):>5}  '
            f'{(r.get("last_operation") or "-"):<11} '
            f'{r.get("completeness") or "-"}'
        )
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Owner-qualified repo slug — canonical producer, checked-root two-leg gate.
# ---------------------------------------------------------------------------

def _resolve_repo_name_or_exit(project_root: str) -> str:
    """Resolve the owner-qualified repo slug for *project_root* via the
    canonical producer (`coordinator_core.ops.emit.context.resolve_repo_name`),
    gated by two orthogonal checks — do not collapse them into one.

    Leg 1 (fail-loud, AC9): is *project_root* itself a repo root, or a
    subdirectory of one? `resolve_repo_name` walks UP to the enclosing repo,
    so a subdirectory invocation would stamp the enclosing repo's slug — a
    confidently-wrong attribution, strictly worse than the honest bare
    basename being replaced. Answered via
    `coordinator_core.git.repo_root.show_toplevel(cwd=project_root)`,
    compared against `project_root` itself; failure names both paths.

    Leg 2 (advisory, DR-277): is the harness session anchored to this repo
    at all? Answered via `resolve_checked_repo_root()` with no argument
    (READER disposition — warn to stderr on MISMATCH, never refuse), same
    as every other query CLI (see `query-handoff-columns.py`'s own
    `_resolve_repo_root`). Passing `project_root` into
    `resolve_checked_repo_root` would answer neither question — an explicit
    root short-circuits to verdict EXPLICIT without ever calling
    `_show_toplevel()` or the identity gate (`repo_identity.py` AC3).

    Negative-spec: does NOT reject `resolve_repo_name`'s `local/<basename>`
    remoteless fallback (AC10) — that is documented air-gapped-repo
    behaviour, stamped as-is.
    """
    claude_klabauter_root = resolve_claude_klabauter_root_or_exit('query-file-attribution')
    if isinstance(claude_klabauter_root, int):
        sys.exit(claude_klabauter_root)

    from coordinator_core.git.repo_root import show_toplevel
    from coordinator_core.ops.emit.context import resolve_repo_name

    # Leg 1 — fail-loud: project_root must be a repo root, not a subdirectory.
    toplevel = show_toplevel(cwd=project_root)
    if toplevel is None or os.path.abspath(toplevel) != os.path.abspath(project_root):
        sys.stderr.write(
            'query-file-attribution: --project is not a git repo root — '
            f'project_root={project_root!r}, resolved toplevel={toplevel!r}\n'
        )
        sys.exit(1)

    # Leg 2 — advisory: is the harness session anchored to this repo at all?
    _session_root, verdict = resolve_checked_repo_root()
    if verdict.get('verdict') == 'MISMATCH':
        sys.stderr.write(f'{verdict["message"]}\n')

    return resolve_repo_name(project_root)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='query-file-attribution.py',
        description=(
            'Read-only reverse-query CLI over transcript-derived file attribution.\n'
            'Derives attributions from Claude Code transcripts on demand — '
            'no ledger shards required.'
        ),
        epilog=(
            'Exit codes:\n'
            '  0 — success (results found or --help)\n'
            '  1 — bad arguments or transcript directory not found\n'
            '  2 — no results for the given query\n'
            '\n'
            'Examples:\n'
            '  # Which files did a session touch?\n'
            '  query-file-attribution.py --session abc-123\n'
            '\n'
            '  # Which sessions touched a specific file?\n'
            '  query-file-attribution.py --file plugins/coordinator/bin/derive-file-attribution.py\n'
            '\n'
            '  # Use a test fixture directory\n'
            '  query-file-attribution.py --transcript-dir /path/to/fixtures --session test-session-0001'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--session', metavar='ID',
        help='Query: which files did this session touch (with edited/read/referenced counts).',
    )
    parser.add_argument(
        '--file', metavar='PATH',
        help='Query: which sessions touched this file path.',
    )
    parser.add_argument(
        '--project', metavar='ROOT',
        default=None,
        help='Project root path for transcript discovery (default: cwd). '
             'Used only when --transcript-dir is not given.',
    )
    parser.add_argument(
        '--transcript-dir', metavar='DIR',
        default=None,
        help='Override transcript directory (absolute path). '
             'If not set, derives from --project using Claude Code\'s encoding scheme.',
    )
    parser.add_argument(
        '--format', choices=['json', 'table'], default='json',
        help='Output format: json (default) or table (human-readable).',
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Validate: at least one query mode required.
    if args.session is None and args.file is None:
        parser.error('specify --session <id>, --file <path>, or both')

    # Review: code-reviewer (F4) — load derive module lazily so --help and
    # argument-validation failures don't trigger importlib load or sys.exit(1).
    _derive = _load_derive_module()

    # Resolve project root and transcript directory.
    project_root = os.path.abspath(args.project or os.getcwd())

    transcript_dir: Optional[str]
    if args.transcript_dir:
        transcript_dir = os.path.abspath(args.transcript_dir)
    else:
        encoded = _derive.encode_project_path(project_root)
        transcript_dir = os.path.join(
            os.path.expanduser('~/.claude/projects'), encoded
        )

    if not os.path.isdir(transcript_dir):
        sys.stderr.write(
            f'Error: transcript directory not found: {transcript_dir}\n'
        )
        sys.exit(1)

    # Derive rows — apply session_filter when only --session is requested
    # (avoids loading all transcripts unnecessarily).
    session_filter: Optional[str] = None
    if args.session is not None and args.file is None:
        # Only need the one session; filter at derive time.
        session_filter = args.session

    raw_rows = _derive.derive_rows(
        project_root,
        transcript_dir=transcript_dir,
        session_filter=session_filter,
    )

    repo_name = _resolve_repo_name_or_exit(project_root)

    all_records = _derive.aggregate(
        raw_rows,
        repo=repo_name,
        transcript_dir=transcript_dir,
    )

    # Execute queries and collect results.
    total_matches = 0
    outputs: List[str] = []

    if args.session is not None:
        session_records = query_by_session(all_records, args.session)
        total_matches += len(session_records)
        if args.format == 'json':
            outputs.append(_fmt_json(session_records))
        else:
            outputs.append(_fmt_table_session(session_records, args.session))

    if args.file is not None:
        file_records = query_by_file(all_records, args.file, project_root)
        total_matches += len(file_records)
        if args.format == 'json':
            outputs.append(_fmt_json(file_records))
        else:
            outputs.append(_fmt_table_file(file_records, args.file))

    # Emit output.
    separator = '\n\n' if len(outputs) > 1 else ''
    print(separator.join(outputs))

    # Exit 2 when all queries returned empty.
    return 2 if total_matches == 0 else 0


if __name__ == '__main__':
    sys.exit(main())
