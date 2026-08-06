#!/usr/bin/env python3
"""
migrate-lessons-md-to-yaml.py -- one-shot migration of state/lessons.md entries
into per-entry YAML files under state/lessons/.

Purpose: the monolithic state/lessons.md append-only markdown file is migrated to
a per-entry YAML directory (state/lessons/<date>-<slug>.yaml), one file per lesson.
This prevents concurrent-append git conflicts and enables dedup pre-checking at
capture time.

Handles ALL three legacy entry shapes:
  A) **Bold title [universal]** body prose...  (most common)
  B) ## Headed entries (H2, no bold title marker)
  C) Bare-line entries ([universal]... or 2026-YYYY-MM-DD: prefixes)

Spec backlink: docs/plans/2026-06-30-lessons-md-to-queryable-yaml-queue.md § C5
Improvement-queue: state/improvement-queue/2026-06-19-extract-lessons-py-misses-headed-and-bar.yaml

Negative-spec: Do NOT run --apply until all consumers (C3/C4 chunks) are migrated.
Do NOT remove state/lessons.md manually -- only --apply does this after count-parity
verification. Do NOT run --apply if state/lessons/ already contains YAML files
(double-apply guard prevents duplicates).

Modes:
  --dry-run   Parse state/lessons.md, classify every entry by shape, write a
              classification JSON to state/migrate-lessons-dryrun-DATE.json.
              Does NOT write to state/lessons/ or remove state/lessons.md.
  --apply     Write each entry to state/lessons/<created>-<slug>.yaml, verify
              COUNT PARITY (N parsed == N written), then git rm state/lessons.md.
              Double-apply guard: aborts if state/lessons/ already contains YAML files.
"""

from __future__ import annotations

import sys
import os
import re
import json
import datetime
import argparse
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants and patterns
# ---------------------------------------------------------------------------

DATE_PATTERN = re.compile(r'\b(\d{4}-\d{2}-\d{2})\b')

# Match "Belongs in foo.md" or "Belongs to foo.md" or "Route to foo.md"
TARGET_WIKI_PATTERN = re.compile(
    r'(?:[Bb]elongs? (?:in|to)|[Rr]outes? to)\s+[`\'"[]?([A-Za-z0-9_./-]+\.md)[`\'"\\]]*'
)

SLUG_STRIP = re.compile(r'[^a-z0-9]+')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug(text: str, max_len: int = 40) -> str:
    """Convert title to lowercase kebab-case slug, truncated to max_len."""
    s = text.lower()
    s = SLUG_STRIP.sub('-', s)
    s = s.strip('-')
    s = s[:max_len]
    s = s.rstrip('-')
    return s or 'entry'


def _extract_date(text: str) -> str | None:
    """Extract the first YYYY-MM-DD date string from text. Returns None if absent."""
    m = DATE_PATTERN.search(text)
    return m.group(1) if m else None


def _extract_target_wiki(text: str) -> str | None:
    """Extract routing target wiki from 'Belongs in X.md' trailing clause."""
    m = TARGET_WIKI_PATTERN.search(text)
    return m.group(1) if m else None


def _detect_from_repo() -> str:
    """Detect from_repo registry shortname from cwd git root basename."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, check=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        root = Path(result.stdout.strip())
        return root.name
    except Exception:
        return 'unknown'


def _make_filename(entry: dict, idx: int, seen_slugs: set) -> str:
    """Generate a unique <created>-<slug>.yaml filename for entry."""
    created = entry['created'] or '0000-00-00'
    base_slug = _slug(entry['title'])
    if not base_slug:
        base_slug = f'entry-{idx}'

    slug = base_slug
    counter = 2
    while slug in seen_slugs:
        slug = f'{base_slug}-{counter}'
        counter += 1

    seen_slugs.add(slug)
    return f'{created}-{slug}.yaml'


def _build_yaml_text(entry: dict, from_repo: str) -> str:
    """Serialize one entry to YAML text using block-literal style for body.

    Uses json.dumps() for scalar values to handle special chars safely
    (backticks, quotes, Unicode, colons, etc.). Body uses YAML block literal
    (| style) to preserve verbatim prose including UPDATE addenda and
    SECOND-INSTANCE threads -- lossless, no escaping needed for block content.
    """
    created = entry['created'] or '0000-00-00'

    def qs(s: str) -> str:
        """JSON-encode a string as a valid YAML double-quoted scalar."""
        return json.dumps(s, ensure_ascii=False)

    lines = [
        f'created: {qs(created)}',
        f'scope: {qs(entry["scope"])}',
        f'from_repo: {qs(from_repo)}',
        f'title: {qs(entry["title"])}',
        'body: |',
    ]

    body = entry['body']
    for bline in body.split('\n'):
        # Indent every line by 2 spaces for block literal
        # Review: code-reviewer Slice-A — (A-F8) empty body lines should be empty string,
        # not two spaces; two-space padding in YAML block literal produces trailing whitespace.
        lines.append(f'  {bline}' if bline else '')

    if entry.get('target_wiki'):
        lines.append(f'target_wiki: {qs(entry["target_wiki"])}')

    lines.append('status: "open"')
    lines.append('')  # trailing newline

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Entry parsing -- three shapes
# ---------------------------------------------------------------------------


def _parse_entries(content: str) -> list:
    """Parse all lesson entries from lessons.md content.

    Splits on blank lines (2+ newlines) to get blocks; classifies each block
    by shape and delegates to the appropriate shape parser.

    Skips: file header (# Lessons), blockquote lines (>), YAML frontmatter (---).
    """
    entries = []

    # Split content into blocks separated by 1+ blank lines
    blocks = re.split(r'\n{2,}', content.strip())

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        entry = _classify_and_parse(block)
        if entry is not None:
            entries.append(entry)

    return entries


def _classify_and_parse(block: str) -> dict | None:
    """Classify a block by shape and parse it. Returns None to skip."""
    first_line = block.split('\n')[0].strip()

    # Skip file-level structures (top-level heading, blockquotes, frontmatter)
    if first_line.startswith('# ') and not first_line.startswith('## '):
        return None
    if first_line.startswith('>'):
        return None
    if first_line.startswith('---'):
        return None

    # Shape A: **Bold title** body (most common in lessons.md)
    if first_line.startswith('**'):
        return _parse_bold(block)

    # Shape B: ## Headed entry (H2, no bold)
    if first_line.startswith('## '):
        return _parse_headed(block)

    # Shape C: bare-line ([universal] ... or 2026-...: ...)
    if first_line.startswith('[universal]') or re.match(r'^\d{4}-', first_line):
        return _parse_bare(block)

    # Unknown shape -- skip silently (table rows, code fences, etc.)
    return None


def _parse_bold(block: str) -> dict | None:
    """Parse Shape A: **Bold title [universal]** body prose...

    Title is the content between the first pair of ** markers.
    Body is everything after the closing ** -- verbatim, lossless.
    [universal] tag may appear in title or at the very start of body.
    """
    m = re.match(r'^\*\*(.*?)\*\*(.*)', block, re.DOTALL)
    if not m:
        return None

    raw_title = m.group(1).strip()
    body_raw = m.group(2)

    # Strip a single leading space after closing ** (markdown convention)
    if body_raw.startswith(' '):
        body_raw = body_raw[1:]
    body = body_raw.rstrip()

    # Detect scope: [universal] in title OR at very start of body
    scope = 'project'
    if '[universal]' in raw_title:
        scope = 'universal'
    elif body.lstrip().startswith('[universal]'):
        scope = 'universal'

    # Title: strip [universal] tag and cleanup
    title = raw_title.replace('[universal]', '').strip().strip('* ')

    created = _extract_date(body)
    target_wiki = _extract_target_wiki(body)

    return {
        'shape': 'bold',
        'title': title,
        'body': body,
        'scope': scope,
        'created': created,
        'target_wiki': target_wiki,
    }


def _parse_headed(block: str) -> dict | None:
    """Parse Shape B: ## Heading / body lines...

    Title is the text after ## on the first line.
    Body is all subsequent lines, joined (may be empty).
    [universal] tag may appear in title or body.
    """
    lines = block.split('\n')
    heading = lines[0].strip()
    title = re.sub(r'^#+\s*', '', heading).strip()
    body = '\n'.join(lines[1:]).strip()

    scope = 'project'
    if '[universal]' in title:
        scope = 'universal'
        title = title.replace('[universal]', '').strip()
    elif '[universal]' in body:
        scope = 'universal'

    # If no separate body, use the title text as the body too
    full_body = body if body else title

    created = _extract_date(body) or _extract_date(title)
    target_wiki = _extract_target_wiki(full_body)

    return {
        'shape': 'headed',
        'title': title,
        'body': full_body,
        'scope': scope,
        'created': created,
        'target_wiki': target_wiki,
    }


def _parse_bare(block: str) -> dict | None:
    """Parse Shape C: bare-line entries.

    Handles two forms:
      [universal] prose text here. May continue on subsequent lines.
      2026-06-30: prose text here.

    Title is derived from the first clause (up to . or dash or 80 chars).
    Body is the full block, verbatim.
    """
    text = block.strip()
    scope = 'project'

    # Strip [universal] prefix for scope detection (body stays verbatim)
    remainder = text
    if text.startswith('[universal]'):
        scope = 'universal'
        remainder = text[len('[universal]'):].strip()

    # Date prefix: 2026-MM-DD: text
    date_prefix_m = re.match(r'^(\d{4}-\d{2}-\d{2}):\s*(.*)', remainder, re.DOTALL)
    if date_prefix_m:
        created_override = date_prefix_m.group(1)
        rest = date_prefix_m.group(2).strip()
        title = _first_clause(rest)
        return {
            'shape': 'bare',
            'title': title,
            'body': text,  # full block verbatim
            'scope': scope,
            'created': created_override,
            'target_wiki': _extract_target_wiki(text),
        }

    # No date prefix: derive title from first clause
    title = _first_clause(remainder)
    created = _extract_date(text)

    return {
        'shape': 'bare',
        'title': title,
        'body': text,
        'scope': scope,
        'created': created,
        'target_wiki': _extract_target_wiki(text),
    }


def _first_clause(text: str) -> str:
    """Extract a title-length first clause from text (up to ~80 chars)."""
    # Truncate at first '. ', ' -- ', or newline
    end = len(text)
    for sep in ['. ', ' -- ', '\n']:
        idx = text.find(sep)
        if 0 < idx < end:
            end = idx

    title = text[:min(end, 80)].split('\n')[0].rstrip('. ')
    return title.strip() or text[:40].strip()


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------


def cmd_dry_run(args: argparse.Namespace) -> None:
    """Parse lessons.md and write classification JSON. No state mutations."""
    lessons_md = Path(args.input)
    if not lessons_md.exists():
        print(f'ERROR: {lessons_md} not found', file=sys.stderr)
        sys.exit(1)

    content = lessons_md.read_text(encoding='utf-8')
    entries = _parse_entries(content)

    from_repo = _detect_from_repo()
    seen_slugs: set = set()

    shape_counts: dict = {'bold': 0, 'headed': 0, 'bare': 0}
    per_entry = []

    for i, entry in enumerate(entries):
        shape = entry.get('shape', 'unknown')
        shape_counts[shape] = shape_counts.get(shape, 0) + 1

        fname = _make_filename(entry, i + 1, seen_slugs)
        per_entry.append({
            'index': i + 1,
            'shape': shape,
            'title': entry['title'][:100],
            'slug': fname,
            'scope': entry['scope'],
            'created': entry['created'],
            'has_target_wiki': entry.get('target_wiki') is not None,
        })

    today = datetime.date.today().isoformat()
    report = {
        'run_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'input': str(lessons_md),
        'total_entries': len(entries),
        'shape_breakdown': shape_counts,
        'from_repo': from_repo,
        'entries': per_entry,
    }

    # Write to state/migrate-lessons-dryrun-DATE.json
    out_name = 'migrate-lessons-dryrun-' + today
    output_path = Path('state') / (out_name + '.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )

    # Summary to stdout for EM sanity-check
    universal_ct = sum(1 for e in entries if e['scope'] == 'universal')
    dated_ct = sum(1 for e in entries if e['created'])
    print(f'=== lessons.md dry-run: {len(entries)} entries detected ===')
    print(f'Shape breakdown: {shape_counts}')
    print(f'Scope: universal={universal_ct}, project={len(entries) - universal_ct}')
    print(f'Entries with date: {dated_ct}')
    print(f'Report written to: {output_path}')


# ---------------------------------------------------------------------------
# Apply mode
# ---------------------------------------------------------------------------


def cmd_apply(args: argparse.Namespace) -> None:
    """Write per-entry YAML files and (on parity) git rm lessons.md."""
    lessons_md = Path(args.input)
    if not lessons_md.exists():
        print(f'ERROR: {lessons_md} not found', file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)

    # Double-apply guard: refuse if output_dir already has YAML files
    if output_dir.exists() and any(output_dir.glob('*.yaml')):
        existing = list(output_dir.glob('*.yaml'))
        print(
            f'ERROR: Double-apply guard triggered. {output_dir} already contains '
            f'{len(existing)} YAML file(s). Remove the directory first or use a '
            f'different --output-dir to prevent duplicates.',
            file=sys.stderr
        )
        sys.exit(1)

    content = lessons_md.read_text(encoding='utf-8')
    entries = _parse_entries(content)

    if not entries:
        print('ERROR: no entries parsed from lessons.md -- refusing to proceed.', file=sys.stderr)
        sys.exit(1)

    from_repo = _detect_from_repo()
    output_dir.mkdir(parents=True, exist_ok=True)

    seen_slugs: set = set()
    written = []

    for i, entry in enumerate(entries):
        fname = _make_filename(entry, i + 1, seen_slugs)
        yaml_text = _build_yaml_text(entry, from_repo)
        out_path = output_dir / fname
        out_path.write_text(yaml_text, encoding='utf-8')
        written.append(out_path)

    # Count parity verification
    actual_count = len(list(output_dir.glob('*.yaml')))
    if actual_count != len(entries):
        print(
            f'ERROR: Count parity FAILED. Parsed {len(entries)} entries but '
            f'{actual_count} YAML files exist in {output_dir}. '
            f'Aborting git rm of {lessons_md}.',
            file=sys.stderr
        )
        sys.exit(1)

    print(f'Written {actual_count} YAML files to {output_dir}')
    print(f'Count parity: PASS ({len(entries)} parsed == {actual_count} written)')

    if not args.no_rm:
        result = subprocess.run(
            ['git', 'rm', str(lessons_md)],
            capture_output=True, text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode != 0:
            print(
                f'WARNING: git rm {lessons_md} failed (rc={result.returncode}): '
                f'{result.stderr.strip()}',
                file=sys.stderr
            )
        else:
            print(f'git rm {lessons_md}: OK')
    else:
        print(f'(--no-rm: skipped git rm of {lessons_md})')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Migrate state/lessons.md to per-entry YAML files in state/lessons/'
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        '--dry-run', action='store_true',
        help='Parse and classify entries; write classification JSON. No state mutations.'
    )
    mode.add_argument(
        '--apply', action='store_true',
        help='Write YAML files to output-dir and git rm lessons.md (after parity check).'
    )
    parser.add_argument(
        '--input', default='state/lessons.md',
        help='Path to the source lessons.md (default: state/lessons.md)'
    )
    parser.add_argument(
        '--output-dir', default='state/lessons',
        help='Output directory for YAML files (default: state/lessons)'
    )
    parser.add_argument(
        '--no-rm', action='store_true',
        help='Skip git rm of source file (useful for testing with temp dirs)'
    )

    args = parser.parse_args()

    if args.dry_run:
        cmd_dry_run(args)
    else:
        cmd_apply(args)


if __name__ == '__main__':
    main()
