"""Test-only mirror of the Phase 5 `deletion_groups:` expansion contract.

spec-backlink: docs/plans/2026-06-14-distill-phase3d-output-budget.md § C4 (fixture lib)
contract-source: PIPELINE.md § Phase 5 step 5 deletion_groups: expansion

Phase 5 is a coordinator-orchestrated Sonnet-applied step that cannot be invoked
directly from a test runner — this module implements the same documented contract
in Python so fixtures can assert expansion correctness without a live /distill run.

EXPANSION CONTRACT (from PIPELINE.md § Phase 5 step 5):
  1. Read the Phase 3d manifest's schema_version.
     - schema_version: 1 -> no deletion_groups: key; consume deletions: only (backward-compat).
     - schema_version: 2 -> expand deletion_groups: entries via scout-file YAML-block read.
     - schema_version: 3+ -> abort with named error (fail-loud per DR-082).
  2. For each deletion_groups: entry:
     a. Read the file at scout_source:.
     b. Locate the H2 heading that exactly matches section_anchor:.
     c. Read the fenced YAML block (```yaml...```) immediately under that heading.
     d. Consume the artifact_paths: list from that YAML block.
     e. Assert len(artifact_paths) == count; abort on mismatch.
     f. Each path from artifact_paths: becomes a synthetic DELETE row.
  3. Also consume all per-file deletions: rows with disposition: DELETE.
  4. Apply .md-only audit guard: non-.md paths are excluded and logged.
  5. Return the expanded delete set, sorted.
"""

from __future__ import annotations

import os

import yaml

SUPPORTED_VERSIONS = {1, 2}


class ManifestExpansionError(Exception):
    """Raised when the manifest fails the expansion contract (fail-loud per DR-082)."""


def _strip_front_matter(raw: str) -> str:
    """Extract the YAML front-matter block between the first pair of --- fences.

    Manifests may have prose content after the closing ---, which creates a second
    YAML document and causes yaml.safe_load to reject the stream. Strategy: if the
    file starts with ---, extract only the text between the first --- and the second
    ---. If there is no closing fence, strip the leading --- and use the rest. If
    there are no fences at all, use the raw text as-is (plain YAML document).
    """
    lines = raw.splitlines()
    if lines and lines[0].rstrip() == "---":
        close_idx = None
        for i in range(1, len(lines)):
            if lines[i].rstrip() == "---":
                close_idx = i
                break
        if close_idx is not None:
            return "\n".join(lines[1:close_idx])
        return "\n".join(lines[1:])
    return raw


def _resolve_scout_path(scout_source: str, scout_base: str) -> str:
    # Review: code-reviewer F3 (2026-07-23) — dropped the bare
    # `os.path.exists(scout_source)` branch: it resolved against the
    # process cwd, not scout_base, so a same-named path in an unrelated
    # cwd could silently short-circuit to the wrong file.
    if os.path.isabs(scout_source):
        return scout_source
    return os.path.join(scout_base, scout_source)


def _expand_group(group: dict, scout_base: str, warnings: list[str]) -> list[str]:
    scout_source = group.get("scout_source", "")
    section_anchor = group.get("section_anchor", "")
    expected_count = group.get("count")

    scout_path = _resolve_scout_path(scout_source, scout_base)
    if not os.path.isfile(scout_path):
        raise ManifestExpansionError(
            f"scout_source not found: {scout_source} (resolved: {scout_path})"
        )

    with open(scout_path, encoding="utf-8") as fh:
        scout_text = fh.read()

    # Locate the H2 heading that exactly matches section_anchor.
    # Review: code-reviewer F1 — pin H2-only; lstrip("#") alone matches H1/H3/H4
    # with same text; DR-3 mandates H2 headings only.
    anchor_line = section_anchor.lstrip("#").strip()
    lines = scout_text.splitlines()
    anchor_idx = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and line.lstrip("#").strip() == anchor_line:
            if anchor_idx is not None:
                # Review: code-reviewer F8/F2 (2026-07-23) — warn on duplicate
                # anchor match (non-fatal): the comment claimed a warning was
                # surfaced but nothing appended to `warnings` — fixed to
                # actually emit one, matching the WARN-only pattern used by
                # the .md-only audit guard below.
                warnings.append(
                    f"duplicate section_anchor match for '{section_anchor}' in "
                    f"{scout_path} — using first match at line {anchor_idx + 1}."
                )
                break
            anchor_idx = i

    if anchor_idx is None:
        raise ManifestExpansionError(
            f"section_anchor not found in scout file: '{section_anchor}' in {scout_path}"
        )

    # Read the fenced YAML block immediately following the heading.
    # Allow blank lines between heading and fence.
    fence_start = None
    for i in range(anchor_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped == "":
            continue
        if stripped.startswith("```"):
            fence_start = i
        break

    if fence_start is None:
        raise ManifestExpansionError(
            f"no fenced YAML block found immediately under section_anchor "
            f"'{section_anchor}' in {scout_path}"
        )

    fence_end = None
    for i in range(fence_start + 1, len(lines)):
        if lines[i].strip().startswith("```"):
            fence_end = i
            break

    if fence_end is None:
        raise ManifestExpansionError(
            f"unclosed YAML fence under section_anchor '{section_anchor}' in {scout_path}"
        )

    yaml_block = "\n".join(lines[fence_start + 1 : fence_end])

    try:
        block_doc = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        raise ManifestExpansionError(
            f"YAML parse failure in scout block under '{section_anchor}': {exc}"
        ) from exc

    artifact_paths = block_doc.get("artifact_paths", []) if isinstance(block_doc, dict) else []
    actual_count = len(artifact_paths)

    # Review: code-reviewer F10 — count: is required per DR-3 sanity-check discipline;
    # silently skipping the assertion when count: is absent defeats the invariant.
    if expected_count is None:
        raise ManifestExpansionError(
            f"missing required 'count:' field for group '{section_anchor}' in manifest. "
            "DR-3 mandates count: for sanity-check assertion."
        )

    if actual_count != expected_count:
        raise ManifestExpansionError(
            f"count mismatch for group '{section_anchor}': "
            f"expected {expected_count}, got {actual_count} from scout YAML block."
        )

    return list(artifact_paths)


def check_fanout_sentinel(manifest_path: str) -> None:
    """Fanout sentinel — mirrors the shell runner's fragment-vs-canonical guard.

    Fires when: (a) fragment files ARE present in the manifest dir, AND (b) the
    canonical assembled manifest (phase3d-deletion-manifest.md) is NOT the file
    being expanded. I.e. fragments exist but assembly hasn't completed yet.
    """
    manifest_dir = os.path.dirname(manifest_path)
    manifest_base = os.path.basename(manifest_path)
    fragment_count = 0
    if os.path.isdir(manifest_dir):
        for name in os.listdir(manifest_dir):
            if name.startswith("phase3d-fragment-") and name.endswith(".md"):
                fragment_count += 1

    if fragment_count > 0 and manifest_base != "phase3d-deletion-manifest.md":
        raise ManifestExpansionError(
            f"fanout assembly incomplete — {fragment_count} fragments found, "
            "no canonical manifest (expected phase3d-deletion-manifest.md)."
        )


def expand(manifest_path: str, scout_base: str | None = None) -> tuple[list[str], list[str]]:
    """Expand a Phase 3d deletion manifest into its final delete set.

    Returns (md_paths, warnings) — md_paths is the sorted, deduped, .md-only delete
    set; warnings is a list of human-readable WARN strings (non-.md exclusions,
    duplicate-anchor matches) that the shell runner printed to stderr.

    Raises ManifestExpansionError on any condition the shell runner treated as a
    fatal ERROR (unsupported schema_version, missing scout file, missing anchor,
    missing/unclosed YAML fence, count mismatch, missing count:, fanout sentinel).
    """
    if not os.path.isfile(manifest_path):
        raise ManifestExpansionError(f"manifest file not found: {manifest_path}")

    if scout_base is None:
        scout_base = os.path.dirname(manifest_path)

    check_fanout_sentinel(manifest_path)

    with open(manifest_path, encoding="utf-8") as fh:
        raw = fh.read()

    stripped = _strip_front_matter(raw)

    try:
        doc = yaml.safe_load(stripped)
    except yaml.YAMLError as exc:
        raise ManifestExpansionError(f"manifest YAML parse failure: {exc}") from exc

    if not isinstance(doc, dict):
        raise ManifestExpansionError(
            "manifest parsed as non-dict — check fenced YAML block shape."
        )

    schema_version = doc.get("schema_version", 1)

    # Schema version gate (fail-loud per DR-082 / AC12).
    if schema_version not in SUPPORTED_VERSIONS:
        raise ManifestExpansionError(
            f"unsupported schema_version: {schema_version}. "
            f"Supported versions: {sorted(SUPPORTED_VERSIONS)}. "
            "Upgrade the Phase 5 consumer or downgrade the manifest."
        )

    delete_paths: list[str] = []

    # Consume per-file deletions: rows (both schema v1 and v2).
    for row in doc.get("deletions", []) or []:
        if not isinstance(row, dict):
            continue
        if row.get("disposition") == "DELETE":
            path = row.get("artifact_path", "")
            if path:
                delete_paths.append(path)

    # .md-only audit guard.
    # Review: code-reviewer F16 — soft/cosmetic guard, WARN-only, no dedicated
    # negative fixture (documented coverage gap, not a bug).
    warnings: list[str] = []

    # Expand deletion_groups: (schema_version: 2 only).
    if schema_version == 2:
        for group in doc.get("deletion_groups", []) or []:
            if not isinstance(group, dict):
                continue
            # Review: code-reviewer F9 — whitelist DELETE only; missing disposition
            # is a schema error, not an implicit DELETE.
            if group.get("disposition") != "DELETE":
                continue
            delete_paths.extend(_expand_group(group, scout_base, warnings))

    non_md = [p for p in delete_paths if not p.endswith(".md")]
    for p in non_md:
        warnings.append(f"non-.md path excluded by audit guard: {p}")

    md_paths = [p for p in delete_paths if p.endswith(".md")]

    return sorted(set(md_paths)), warnings
