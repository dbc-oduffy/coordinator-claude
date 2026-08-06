#!/usr/bin/env python3
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

Spec backlink: docs/plans/2026-07-02-ccos-6-rehome-attribution-python.md § C2
Replaces:      plugins/coordinator/bin/query-file-attribution.mjs

Negative-spec:
  - Do NOT write to state/ or any other disk location — read-only consumer.
  - Do NOT query state/file-attribution-ledger/ shards (that is the old .mjs path).
  - git-cross-check is NOT ported — the ledger-based reconciliation mode had no
    transcript-derived equivalent and is superseded by the new derivation model.
  - Do NOT fabricate file paths — derive-file-attribution.py's null-on-ambiguity
    invariant is respected; unknown rows with null file_path are absent from output.
"""

import argparse
import importlib.util
import json
import os
import sys
from typing import Any, Dict, List, Optional


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
    """Normalise path separators for cross-platform matching."""
    return p.replace('\\', '/')


def query_by_session(
    records: List[Dict[str, Any]], session_id: str
) -> List[Dict[str, Any]]:
    """Return aggregate records for the given session_id, sorted by file_path."""
    matches = [r for r in records if r.get('session_id') == session_id]
    return sorted(matches, key=lambda r: r.get('file_path', '') or '')


def query_by_file(
    records: List[Dict[str, Any]], file_path: str
) -> List[Dict[str, Any]]:
    """Return aggregate records for the given file_path, sorted by session_id."""
    norm = _normalise_path(file_path)
    matches = [
        r for r in records
        if _normalise_path(r.get('file_path', '') or '') == norm
    ]
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

    repo_name = os.path.basename(project_root.rstrip('/\\')) or project_root

    all_records = _derive.aggregate(
        raw_rows,
        repo=repo_name,
        coordinator_root_path=project_root,
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
        file_records = query_by_file(all_records, args.file)
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
