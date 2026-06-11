#!/usr/bin/env python3
"""Weekly health check: stale branches, memory consistency, cache freshness, large files.

Writes findings to /tmp/health-check-report.md and sets GitHub Actions output.
Can also be run locally for a quick health report.
"""

import json
import os
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

findings: list[str] = []
REPORT_PATH = pathlib.Path("/tmp/health-check-report.md")
LINK_RE = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')


def add_finding(section: str, items: list[str]):
    if items:
        findings.append(f"### {section}\n")
        for item in items:
            findings.append(f"- {item}")
        findings.append("")


def check_stale_branches():
    """Find work/* branches with no commits in 7+ days."""
    result = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname:short) %(committerdate:iso-strict)",
         "refs/remotes/origin/work/"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return

    stale = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            continue
        branch, date_str = parts
        try:
            commit_date = datetime.fromisoformat(date_str)
            if commit_date < cutoff:
                age_days = (datetime.now(timezone.utc) - commit_date).days
                stale.append(f"`{branch}` — last commit {age_days} days ago")
        except ValueError:
            continue

    add_finding("Stale Branches (>7 days)", stale)


def check_memory_consistency():
    """Verify MEMORY.md index matches actual memory files on disk."""
    # Discover all memory directories dynamically rather than hardcoding a path
    memory_index_files = list(pathlib.Path("projects").glob("*/memory/MEMORY.md"))

    if not memory_index_files:
        return

    issues = []

    for index_file in memory_index_files:
        memory_dir = index_file.parent

        # Get files linked from MEMORY.md
        text = index_file.read_text(encoding="utf-8")
        linked_files = set()
        for match in LINK_RE.finditer(text):
            target = match.group(2)
            if target.startswith(("http://", "https://", "#")):
                continue
            target_path = target.split("#")[0]
            if target_path and target_path.endswith(".md"):
                linked_files.add(target_path)

        # Get actual memory files (excluding MEMORY.md)
        actual_files = set()
        if memory_dir.is_dir():
            for f in memory_dir.glob("*.md"):
                if f.name != "MEMORY.md":
                    actual_files.add(f.name)

        # Files on disk but not in index
        unlinked = actual_files - linked_files
        for f in sorted(unlinked):
            issues.append(f"`{memory_dir}/{f}` exists on disk but is not linked from MEMORY.md")

        # Files in index but not on disk
        missing = linked_files - actual_files
        for f in sorted(missing):
            issues.append(f"`{memory_dir}/{f}` linked from MEMORY.md but file not found")

    add_finding("Memory Index Consistency", issues)


def check_cache_freshness():
    """Check if marketplace timestamps are older than 14 days."""
    km_path = pathlib.Path("plugins/known_marketplaces.json")
    if not km_path.exists():
        return

    issues = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)

    try:
        data = json.loads(km_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    for name, mp in data.items():
        last_updated = mp.get("lastUpdated")
        if not last_updated:
            issues.append(f"`{name}` — no lastUpdated timestamp")
            continue
        try:
            updated_date = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            if updated_date < cutoff:
                age_days = (datetime.now(timezone.utc) - updated_date).days
                issues.append(f"`{name}` — last updated {age_days} days ago")
        except ValueError:
            issues.append(f"`{name}` — unparseable timestamp '{last_updated}'")

    add_finding("Plugin Cache Freshness (>14 days)", issues)


def check_large_files():
    """Find git-tracked files over 1MB."""
    result = subprocess.run(
        ["git", "ls-files", "--cached"],
        capture_output=True, text=True, check=True
    )
    issues = []
    threshold = 1_000_000

    for filepath in result.stdout.strip().splitlines():
        if not filepath:
            continue
        path = pathlib.Path(filepath)
        if not path.exists():
            continue
        try:
            size = path.stat().st_size
            if size > threshold:
                size_mb = size / 1_000_000
                issues.append(f"`{filepath}` — {size_mb:.1f} MB")
        except OSError:
            continue

    add_finding("Large Tracked Files (>1 MB)", issues)


def main():
    check_stale_branches()
    check_memory_consistency()
    check_cache_freshness()
    check_large_files()

    has_findings = len(findings) > 0

    if has_findings:
        report = "## Weekly Health Check\n\n" + "\n".join(findings)
        # Write report for GitHub Actions issue creation
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(report)
    else:
        print("All health checks passed — no findings.")

    # Set GitHub Actions output
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_findings={'true' if has_findings else 'false'}\n")

    # Always exit 0 — health checks are advisory, not blocking
    sys.exit(0)


if __name__ == "__main__":
    main()
