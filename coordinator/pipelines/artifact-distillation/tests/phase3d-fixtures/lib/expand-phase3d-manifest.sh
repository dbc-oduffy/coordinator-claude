#!/usr/bin/env bash
# lib/expand-phase3d-manifest.sh — Test-only mirror of Phase 5 deletion_groups: expansion contract.
#
# spec-backlink: docs/plans/2026-06-14-distill-phase3d-output-budget.md § C4 (fixture lib)
# contract-source: PIPELINE.md § Phase 5 step 5 deletion_groups: expansion
#
# PURPOSE: Simulates the Phase 5 deletion_groups: expansion algorithm for use in
# phase3d-fixtures. Phase 5 is a coordinator-orchestrated Sonnet-applied step that
# cannot be invoked directly from a test runner — this script implements the same
# documented contract in portable POSIX shell so fixtures can assert expansion correctness
# without a live /distill run.
#
# EXPANSION CONTRACT (from PIPELINE.md § Phase 5 step 5):
#   1. Read the Phase 3d manifest's schema_version.
#      - schema_version: 1 → no deletion_groups: key; consume deletions: only (backward-compat).
#      - schema_version: 2 → expand deletion_groups: entries via scout-file YAML-block read.
#      - schema_version: 3+ → abort with named error (fail-loud per DR-082).
#   2. For each deletion_groups: entry:
#      a. Read the file at scout_source:.
#      b. Locate the H2 heading that exactly matches section_anchor:.
#      c. Read the fenced YAML block (```yaml...```) immediately under that heading.
#      d. Consume the artifact_paths: list from that YAML block.
#      e. Assert len(artifact_paths) == count; abort on mismatch.
#      f. Each path from artifact_paths: becomes a synthetic DELETE row.
#   3. Also consume all per-file deletions: rows with disposition: DELETE.
#   4. Apply .md-only audit guard: non-.md paths are excluded and logged.
#   5. Write the expanded delete set to stdout (one path per line, sorted).
#
# USAGE:
#   expand-phase3d-manifest.sh <manifest-file> [<scout-base-dir>]
#
#   <manifest-file>   — path to the Phase 3d deletion manifest (YAML, fenced in ---)
#   <scout-base-dir>  — optional base directory; scout_source: paths are resolved
#                       relative to this dir if they do not exist as absolute/relative
#                       from cwd. Defaults to the directory of <manifest-file>.
#
# EXIT CODES:
#   0 — expansion succeeded; delete set written to stdout
#   1 — abort with named error written to stderr (schema_version unknown, count mismatch,
#       missing scout file, missing section_anchor, missing YAML block, fanout sentinel)
#
# DEPENDENCIES: python3 (for YAML parsing; required). bash >= 4.

set -euo pipefail

if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
    echo "ERROR: bash >= 4 required (current: $BASH_VERSION). On macOS: brew install bash && put /usr/local/bin first in PATH." >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required for YAML parsing but was not found in PATH." >&2
    exit 1
fi

if [ $# -lt 1 ]; then
    echo "USAGE: expand-phase3d-manifest.sh <manifest-file> [<scout-base-dir>]" >&2
    exit 1
fi

MANIFEST="$1"
SCOUT_BASE="${2:-$(dirname "$MANIFEST")}"

if [ ! -f "$MANIFEST" ]; then
    echo "ERROR: manifest file not found: $MANIFEST" >&2
    exit 1
fi

# ── Fanout sentinel ─────────────────────────────────────────────────────────
# Review: code-reviewer F2 — corrected misleading comment.
# Sentinel fires when: (a) fragment files ARE present in the manifest dir, AND
# (b) the canonical assembled manifest (phase3d-deletion-manifest.md) is NOT the
# file being expanded. I.e., fragments exist but assembly hasn't completed yet.
# NOT the same as "no canonical manifest" — it's "fragments present but caller
# is not pointing at the assembled canonical file".
#
# NOTE: Negative-case fixture (fragments-present + canonical absent → non-zero exit)
# is not yet implemented. AC17 negative path is validated only by reading this code.
# Adding fixture-5 for that negative case is tracked in F2 of the code-reviewer
# Slice C sidecar.
MANIFEST_DIR="$(dirname "$MANIFEST")"
MANIFEST_BASE="$(basename "$MANIFEST")"
fragment_count=0
for f in "$MANIFEST_DIR"/phase3d-fragment-*.md; do
    [ -f "$f" ] && fragment_count=$((fragment_count + 1))
done
if [ "$fragment_count" -gt 0 ] && [ "$MANIFEST_BASE" != "phase3d-deletion-manifest.md" ]; then
    echo "ERROR: fanout assembly incomplete — $fragment_count fragments found, no canonical manifest (expected phase3d-deletion-manifest.md)." >&2
    exit 1
fi

# ── Python expansion driver ──────────────────────────────────────────────────
# Inline Python handles: YAML parsing, schema_version gate, deletion_groups:
# expansion with count assertion, .md-only filter, sorted dedup output.
python3 - "$MANIFEST" "$SCOUT_BASE" <<'PYEOF' # verify-no-console-flash: allow — test fixture, not shipped
import sys, os, re, yaml

# Force LF-only output on Windows (Git-Bash redirects stdout in text mode,
# which translates \n → \r\n; reconfiguring to newline='\n' prevents that).
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(newline='\n')

manifest_path = sys.argv[1]
scout_base    = sys.argv[2]

# ── Read manifest ────────────────────────────────────────────────────────────
with open(manifest_path, encoding="utf-8") as fh:
    raw = fh.read()

# Extract the YAML front-matter block between the first pair of --- fences.
# Manifests may have prose content after the closing ---, which creates a
# second YAML document and causes yaml.safe_load to reject the stream.
# Strategy: if the file starts with ---, extract only the text between
# the first --- and the second ---.
lines = raw.splitlines()
if lines and lines[0].rstrip() == "---":
    # Find the closing ---
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            close_idx = i
            break
    if close_idx is not None:
        raw = "\n".join(lines[1:close_idx])
    else:
        # No closing fence — strip the leading --- and use the rest
        raw = "\n".join(lines[1:])
else:
    # No fences — use as-is (plain YAML document)
    pass

try:
    doc = yaml.safe_load(raw)
except yaml.YAMLError as exc:
    print(f"ERROR: manifest YAML parse failure: {exc}", file=sys.stderr)
    sys.exit(1)

if not isinstance(doc, dict):
    print("ERROR: manifest parsed as non-dict — check fenced YAML block shape.", file=sys.stderr)
    sys.exit(1)

schema_version = doc.get("schema_version", 1)

# ── Schema version gate (fail-loud per DR-082 / AC12) ───────────────────────
SUPPORTED_VERSIONS = {1, 2}
if schema_version not in SUPPORTED_VERSIONS:
    print(
        f"ERROR: unsupported schema_version: {schema_version}. "
        f"Supported versions: {sorted(SUPPORTED_VERSIONS)}. "
        "Upgrade the Phase 5 consumer or downgrade the manifest.",
        file=sys.stderr,
    )
    sys.exit(1)

delete_paths = []

# ── Consume per-file deletions: rows (both schema v1 and v2) ────────────────
for row in doc.get("deletions", []) or []:
    if not isinstance(row, dict):
        continue
    if row.get("disposition") == "DELETE":
        p = row.get("artifact_path", "")
        if p:
            delete_paths.append(p)

# ── Expand deletion_groups: (schema_version: 2 only) ────────────────────────
if schema_version == 2:
    for group in doc.get("deletion_groups", []) or []:
        if not isinstance(group, dict):
            continue
        # Review: code-reviewer F9 — whitelist DELETE only; double-negative logic
        # previously treated disposition: None as DELETE-equivalent (silent bug).
        # Phase 3d canonical schema always emits disposition: DELETE for groups to
        # expand; missing disposition is a schema error, not an implicit DELETE.
        if group.get("disposition") != "DELETE":
            continue

        scout_source   = group.get("scout_source", "")
        section_anchor = group.get("section_anchor", "")
        expected_count = group.get("count")

        # Resolve scout_source path
        if os.path.isabs(scout_source) or os.path.exists(scout_source):
            scout_path = scout_source
        else:
            scout_path = os.path.join(scout_base, scout_source)

        if not os.path.isfile(scout_path):
            print(
                f"ERROR: scout_source not found: {scout_source} "
                f"(resolved: {scout_path})",
                file=sys.stderr,
            )
            sys.exit(1)

        with open(scout_path, encoding="utf-8") as fh:
            scout_text = fh.read()

        # Locate the H2 heading that exactly matches section_anchor.
        # Review: code-reviewer F1 — pin H2-only; lstrip("#") alone matches H1/H3/H4
        # with same text; DR-3 mandates H2 headings only.
        anchor_line = section_anchor.lstrip("#").strip()
        lines = scout_text.splitlines()
        anchor_idx = None
        duplicate_found = False
        for i, line in enumerate(lines):
            if line.startswith("## ") and line.lstrip("#").strip() == anchor_line:
                if anchor_idx is not None:
                    # Review: code-reviewer F8 — warn on duplicate anchor match (non-fatal)
                    print(
                        f"WARN: duplicate anchor match for '{section_anchor}' at line {i+1} "
                        f"in {scout_path}; first match at line {anchor_idx+1} used.",
                        file=sys.stderr,
                    )
                    duplicate_found = True
                    break
                anchor_idx = i

        if anchor_idx is None:
            print(
                f"ERROR: section_anchor not found in scout file: '{section_anchor}' "
                f"in {scout_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Read the fenced YAML block immediately following the heading.
        # Allow blank lines between heading and fence.
        fence_start = None
        for i in range(anchor_idx + 1, len(lines)):
            stripped = lines[i].strip()
            if stripped == "" :
                continue
            if stripped.startswith("```"):
                fence_start = i
                break
            # Hit something else before a fence — no YAML block
            break

        if fence_start is None:
            print(
                f"ERROR: no fenced YAML block found immediately under section_anchor "
                f"'{section_anchor}' in {scout_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        fence_end = None
        for i in range(fence_start + 1, len(lines)):
            if lines[i].strip().startswith("```"):
                fence_end = i
                break

        if fence_end is None:
            print(
                f"ERROR: unclosed YAML fence under section_anchor "
                f"'{section_anchor}' in {scout_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        yaml_block = "\n".join(lines[fence_start + 1:fence_end])

        try:
            block_doc = yaml.safe_load(yaml_block)
        except yaml.YAMLError as exc:
            print(
                f"ERROR: YAML parse failure in scout block under '{section_anchor}': {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

        artifact_paths = block_doc.get("artifact_paths", []) if isinstance(block_doc, dict) else []
        actual_count = len(artifact_paths)

        # Review: code-reviewer F10 — count: is required per DR-3 sanity-check discipline;
        # silently skipping the assertion when count: is absent defeats the invariant.
        # Phase 3d canonical schema (phase-3d.md lines 69-74) always emits count:.
        if expected_count is None:
            print(
                f"ERROR: missing required 'count:' field for group '{section_anchor}' "
                f"in manifest. DR-3 mandates count: for sanity-check assertion.",
                file=sys.stderr,
            )
            sys.exit(1)

        if actual_count != expected_count:
            print(
                f"ERROR: count mismatch for group '{section_anchor}': "
                f"expected {expected_count}, got {actual_count} from scout YAML block.",
                file=sys.stderr,
            )
            sys.exit(1)

        delete_paths.extend(artifact_paths)

# ── .md-only audit guard ─────────────────────────────────────────────────────
# Review: code-reviewer F16 — no dedicated negative fixture for this guard.
# Coverage: the WARN path is exercised only when a scout YAML block contains a
# non-.md path. This is a soft/cosmetic guard (no test failures, just warnings);
# a dedicated fixture is low-priority given no Phase 3d agent is expected to emit
# non-.md paths under the current spec. Document coverage gap here rather than
# adding a dedicated negative fixture.
non_md = [p for p in delete_paths if not p.endswith(".md")]
if non_md:
    for p in non_md:
        print(f"WARN: non-.md path excluded by audit guard: {p}", file=sys.stderr)

md_paths = [p for p in delete_paths if p.endswith(".md")]

# ── Dedup + sort and emit ─────────────────────────────────────────────────────
for p in sorted(set(md_paths)):
    print(p)

PYEOF
