#!/usr/bin/env python3
"""corpus-currency-probe — is this repo's landed corpus behind its published artifact?

Ported from DoE-claude `coordinator/bin/corpus-currency-probe.py` (W2-C6,
`docs/plans/2026-09-18-doe-holds-no-scripts.md`) — mechanical move, no behavioural change.
`_load_tier_last_run_module()` by-path-loads `tier-last-run.py`, a "doctrine asset" sibling that
arrived in this same `coordinator/bin/` directory in an earlier chunk of this plan — the by-path
load is unchanged, since it is still a same-directory sibling. `_claude_home()` is unchanged (env
var then `Path.home()`, no engine-shim fast path needed off the boot path). DoE-claude carries no
test file for this CLI (handover-confirmed absence); this arrival's test is written from the
CLI's requirement — cited by DoE-claude's `commands/workday-start.md` Step 1.10 and
`coordinator/hooks/scripts/project-orientation.py`'s `corpus_currency_banner()`, both DoE-resident
consumers this plan's handback protocol (§ Sequencing and the handback protocol) retargets at this
CLI once it ships here.

WHY THIS EXISTS. `coordinator/docs/wiki/corpus-artifact-distribution.md` rules the refresh key
as the `(source_commit_sha, embed_model_id, chunker_id)` triple, but nothing on this machine ever
evaluates it. This CLI is that evaluation: for each landed
`<repo_root>/.project-rag-corpus-store/<band>/corpus_manifest.json`, it reads the local triple,
fetches the published artifact's manifest for that band, compares, and writes a sentinel that
`corpus_currency_banner()` (plan chunk C2, `coordinator/hooks/scripts/project-orientation.py`)
reads at boot.

NOT DISCOVERABLE FROM THE LOCAL MANIFEST. The one real manifest on this machine has
`corpus_identity`, `corpus_version`, and `release_tag` all null — the publish location per band
cannot be inferred, so it is declared in `coordinator.local.md`'s `corpus_bands` frontmatter
block (band name -> publish ref). A band absent from that map is `undeclared`, never an error:
most repos declare nothing and must stay silent.

NEGATIVE SPEC: this CLI never runs on the boot path (`project-orientation.py`'s zero-subprocess,
zero-network mandate does not apply here — see that hook's module docstring and this plan's
Anti-scope) and never raises or exits non-zero on a network failure. A fetch failure is
`verdict: unreachable`, recorded per band, so the caller (`/workday-start`'s batched probes)
never has to special-case this CLI.

Sentinel: `<claude_home>/.claude/plugins/coordinator-claude/data/corpus-currency-last-run.json`,
resolved the same way `project-orientation.py`'s `_claude_home()` does — it sits beside
`doctor-last-run.json`, which that file's `install_currency_banner()` reads. `ran_at` is stamped
in `_GENERATED_AT_FORMAT` (`%Y-%m-%dT%H:%M:%SZ`) so the age arithmetic already in
`project-orientation.py` reads it unchanged.

A repo with no `.project-rag-corpus-store/` writes no sentinel at all and exits 0 silently —
most repos are this case, and silence there is correct, not a missed check.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_STORE_RELATIVE = Path(".project-rag-corpus-store")
_MANIFEST_NAME = "corpus_manifest.json"
_GENERATED_AT_FORMAT = "%Y-%m-%dT%H:%M:%SZ"  # matches project-orientation.py's own constant
_TRIPLE_FIELDS = ("source_commit_sha", "embed_model_id", "chunker_id")
_FETCH_TIMEOUT_SECONDS = 10


def _repo_root(explicit: Optional[str]) -> Path:
    return Path(explicit).resolve() if explicit else Path.cwd()


def _claude_home() -> Path:
    """Resolve the $HOME analog. Mirrors `project-orientation.py`'s `_claude_home()` local
    fallback ladder — this CLI is not on the boot path, so it does not need that function's
    engine-shim fast path, only the same env-var-then-`Path.home()` degradation.
    """
    v = os.environ.get("CLAUDE_HOME")
    if v:
        return Path(v)
    return Path.home()


def _sentinel_path() -> Path:
    return (
        _claude_home() / ".claude" / "plugins" / "coordinator-claude" / "data"
        / "corpus-currency-last-run.json"
    )


def _load_tier_last_run_module():
    """Import `tier-last-run.py` (same directory) by file path and return the loaded module.

    Hyphenated filename, so `import tier-last-run` is not valid Python — same pattern as
    `project-orientation.py`'s own `_load_tier_last_run_module()`. Reused here so this CLI does
    not carry a third in-tree copy of `_load_local_doctrine`; returns `None` on any failure
    (missing file, import error), and every caller here fails open on `None`.
    """
    try:
        import importlib.util

        module_path = Path(__file__).resolve().parent / "tier-last-run.py"
        spec = importlib.util.spec_from_file_location("_tier_last_run_probe", module_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _load_local_doctrine(repo_root: Path) -> dict[str, Any]:
    """Parse `coordinator.local.md`'s YAML frontmatter and return the parsed mapping.

    Delegates to `tier-last-run.py`'s `_load_local_doctrine` (imported via
    `_load_tier_last_run_module`) rather than keeping a second copy of the same parser in-tree.
    Raises `ValueError` on a missing file, missing/malformed frontmatter, a non-mapping document,
    or if `tier-last-run.py` itself could not be imported — callers here treat all of that as
    "no bands declared", not a crash.
    """
    module = _load_tier_last_run_module()
    if module is None:
        raise ValueError("could not import tier-last-run.py's coordinator.local.md parser")
    return module._load_local_doctrine(repo_root)


def _declared_bands(repo_root: Path) -> dict[str, Any]:
    """The declared `corpus_bands` mapping (band name -> publish ref), or `{}` if unreadable."""
    try:
        doctrine = _load_local_doctrine(repo_root)
    except (OSError, ValueError):
        return {}
    bands = doctrine.get("corpus_bands")
    if not isinstance(bands, dict):
        return {}
    return bands


def _landed_bands(repo_root: Path) -> list[str]:
    """Band names with a landed `corpus_manifest.json`, discovered via `Path.glob` only."""
    store = repo_root / _STORE_RELATIVE
    if not store.is_dir():
        return []
    bands = []
    for manifest_path in sorted(store.glob(f"*/{_MANIFEST_NAME}")):
        bands.append(manifest_path.parent.name)
    return bands


def _read_local_manifest(repo_root: Path, band: str) -> Optional[dict[str, Any]]:
    """The parsed local manifest dict, or `None` if missing/unreadable/not a mapping."""
    manifest_path = repo_root / _STORE_RELATIVE / band / _MANIFEST_NAME
    try:
        parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _triple_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {field: manifest.get(field) for field in _TRIPLE_FIELDS}


def _default_fetch_published_manifest(publish_ref: Any) -> dict[str, Any]:
    """Fetch the published manifest at `publish_ref` (a URL string) and parse it as JSON.

    Raises on any failure — network, HTTP, or parse — so callers translate that into
    `verdict: unreachable` rather than this function silently returning a partial triple.
    Tests stub this out entirely; no network call is ever made under test.
    """
    if not isinstance(publish_ref, str) or not publish_ref:
        raise ValueError(f"corpus_bands publish ref is not a usable URL: {publish_ref!r}")
    with urllib.request.urlopen(publish_ref, timeout=_FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
        raw = response.read()
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("published manifest did not parse to a mapping")
    return parsed


def _remount_command(publish_ref: str, band: str, repo_slug: str) -> str:
    """The two-command pipeline an operator pastes to refresh `band`.

    Real flags only — `download_corpus.py`'s `_build_cli_parser()` has no `--repo-slug` and no
    `--band`; a fabricated flag defeats the point of this field, since C2 echoes it verbatim so
    it can be pasted.

    `--target-dir` is a `<staging>` PLACEHOLDER, deliberately not resolved to a real path, and
    neither conventioned path is correct for it: `.project-rag-corpus-artifacts/` is produce-side,
    and `.project-rag-corpus-store/<band>/` is what the importer WRITES, not what the fetcher
    extracts into. Emitting either would hand the operator a command that corrupts one of the two
    conventioned trees.

    `--min-schema 1` is not optional: `_DEFAULT_MIN_SCHEMA` is 3 while the produce-side
    `CORPUS_MANIFEST_SCHEMA_VERSION` is 1, so the default refuses every artifact the current
    exporter writes. Memo'd to project-rag as their defect; until they rule, omitting the flag
    makes the pasted command fail.
    """
    staging_dir = f"<staging>/{band}"
    return (
        f"python project_rag_scripts/lib/download_corpus.py "
        f"--release-url {publish_ref} "
        f"--target-dir {staging_dir} "
        f"--expected-sha256 <sha256-from-publish> "
        f"--min-schema 1 "
        f"&& python project_rag_cli.py import-lance-parquet-consumer "
        f"--parquet-dir {staging_dir} "
        f"--repo-slug {repo_slug}"
    )


def _probe_band(
    repo_root: Path,
    band: str,
    declared_bands: dict[str, Any],
    fetch_published_manifest,
) -> dict[str, Any]:
    local_manifest = _read_local_manifest(repo_root, band)
    local_triple = _triple_from_manifest(local_manifest) if local_manifest else None
    # Review: code-reviewer (finding 2, held for Kira's enum audit, applied per EM ruling) —
    # `_landed_bands` found this band's manifest file, but `_read_local_manifest` can still
    # return `None` on a corrupt/unreadable manifest. That is a distinct actionable state from
    # staleness and must not render `behind` with a fabricated `<repo-slug>` remount command.
    if local_manifest is None:
        return {
            "band": band,
            "verdict": "local-manifest-unreadable",
            "local_triple": None,
            "published_triple": None,
            "remount_command": None,
        }
    if band not in declared_bands:
        return {
            "band": band,
            "verdict": "undeclared",
            "local_triple": local_triple,
            "published_triple": None,
            "remount_command": None,
        }

    publish_ref = declared_bands[band]
    try:
        published_manifest = fetch_published_manifest(publish_ref)
    except Exception:
        return {
            "band": band,
            "verdict": "unreachable",
            "local_triple": local_triple,
            "published_triple": None,
            "remount_command": None,
        }

    published_triple = _triple_from_manifest(published_manifest)
    repo_slug = local_manifest.get("source_repo_slug") or "<repo-slug>"

    if local_triple == published_triple:
        return {
            "band": band,
            "verdict": "current",
            "local_triple": local_triple,
            "published_triple": published_triple,
            "remount_command": None,
        }

    return {
        "band": band,
        "verdict": "behind",
        "local_triple": local_triple,
        "published_triple": published_triple,
        "remount_command": _remount_command(publish_ref, band, repo_slug),
    }


def run_probe(
    repo_root: Path,
    fetch_published_manifest=_default_fetch_published_manifest,
) -> Optional[dict[str, Any]]:
    """Probe every landed band in `repo_root` and return the sentinel object, or `None` if
    there is no landed store at all (the "most repos are this case" branch — no sentinel is
    written and the caller must not write one either).
    """
    bands = _landed_bands(repo_root)
    if not bands:
        return None

    declared_bands = _declared_bands(repo_root)
    ran_at = datetime.now(timezone.utc).strftime(_GENERATED_AT_FORMAT)
    return {
        "ran_at": ran_at,
        "repo_root": str(repo_root),
        "bands": [
            _probe_band(repo_root, band, declared_bands, fetch_published_manifest)
            for band in bands
        ],
    }


def _write_sentinel(sentinel_path: Path, sentinel: dict[str, Any]) -> None:
    sentinel_path.parent.mkdir(parents=True, exist_ok=True)
    sentinel_path.write_text(json.dumps(sentinel, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=None,
        help="repo root to probe for a landed corpus store (default: cwd)",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    repo_root = _repo_root(args.repo_root)

    try:
        sentinel = run_probe(repo_root)
    except Exception as exc:  # never crash — this CLI is not on the boot path but must still
        # degrade gracefully for its own caller.
        print(f"corpus-currency-probe: {exc}", file=sys.stderr)
        return 0

    if sentinel is None:
        return 0

    try:
        _write_sentinel(_sentinel_path(), sentinel)
    except OSError as exc:
        print(f"corpus-currency-probe: could not write sentinel: {exc}", file=sys.stderr)
        return 0

    # Review: overengineering-reviewer (Kira, finding 3) — the sentinel file keeps every band
    # (weight); `/workday-start`'s batched-probes contract (workday-start.md Step 1.10) wants
    # stdout silent unless there is something to act on (volume). Print nothing when every band
    # is clean; otherwise one short line per actionable band.
    actionable = {"behind", "unreachable", "local-manifest-unreadable"}
    actionable_bands = [b for b in sentinel["bands"] if b.get("verdict") in actionable]
    if actionable_bands:
        names = ", ".join(f"{b['band']} ({b['verdict']})" for b in actionable_bands)
        print(f"corpus-currency-probe: {names}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
