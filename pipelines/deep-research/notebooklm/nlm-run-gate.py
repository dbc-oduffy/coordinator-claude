"""NotebookLM run gates: deterministic halts between scout, workers and sweep.

`sources` answers "does every scout-provided notebook have an accessible source?" and, with
`--probe-ingest`, whether YouTube ingest is rate-limited (HTTP 429) for this IP;
`claims` answers "did exactly worker_count in-strategy workers run, and did they produce a claim?".
Prints one JSON object {ok, remedy, checks} and always exits 0 on a decided result; the calling
stage reads `ok`. Any unreadable input is ok:false, never a pass.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.S)
_WORKER_COUNT = re.compile(r"^worker_count:\s*(\d+)\s*$", re.M)
_NOTEBOOK_SECTION = re.compile(r"^##\s+Notebook\s+([A-Z])\b[^\n]*$", re.M)
_SOURCES_SECTION = re.compile(r"^##\s+Sources\s+for\s+Notebook\s+([A-Z])\b[^\n]*$", re.M)
_SOURCE_STRATEGY = re.compile(r"Source\s+strategy:\s*`?([A-Za-z_\-]+)", re.I)
_URL = re.compile(r"https?://\S+")
_ACCESSIBLE_OK = re.compile(r"Accessible:\s*\**\s*(?:YES|PARTIAL)\b", re.I)
_ANY_HEADING = re.compile(r"^##\s", re.M)
_YOUTUBE_URL = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/[^\s)>\]]+", re.I)
_TEXT_ENTRY = re.compile(r"\btext:\s*\S")


def _sections(text: str, heading: re.Pattern[str]) -> dict[str, str]:
    """Map letter -> section body, each running to the next `## ` heading."""
    out: dict[str, str] = {}
    matches = list(heading.finditer(text))
    for m in matches:
        nxt = _ANY_HEADING.search(text, m.end())
        out[m.group(1)] = text[m.end() : nxt.start() if nxt else len(text)]
    return out


def parse_worker_count(strategy_text: str) -> int | None:
    fm = _FRONTMATTER.match(strategy_text)
    if not fm:
        return None
    m = _WORKER_COUNT.search(fm.group(1))
    return int(m.group(1)) if m else None


def probe_youtube(url: str, timeout: float = 10.0) -> str:
    """Fetch one YouTube page; "rate_limited" only on HTTP 429, "unreachable" on any other failure.

    A rate-limited IP makes every YouTube `source_add` fail with a generic error, so 429 is the one
    status the gate names; other failures stay non-blocking because they say nothing about ingest.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return "ok"
    except urllib.error.HTTPError as exc:
        return "rate_limited" if exc.code == 429 else "unreachable"
    except (OSError, ValueError, http.client.HTTPException):
        return "unreachable"


def gate_sources(
    strategy_text: str | None,
    sources_text: str | None,
    probe: Callable[[str], str] | None = None,
) -> dict:
    """`probe` (url -> status) is run once on the first YouTube URL; None skips the ingest probe."""
    remedy: list[str] = []
    checks: dict = {"sources_md": "absent" if sources_text is None else "present", "notebooks": {}}
    if strategy_text is None:
        return {"ok": False, "remedy": ["strategy.md is unreadable: re-run the scope stage"], "checks": checks}
    if parse_worker_count(strategy_text) is None:
        remedy.append("strategy.md has no worker_count in its frontmatter: re-run the scope stage")
    notebooks = _sections(strategy_text, _NOTEBOOK_SECTION)
    if not notebooks:
        remedy.append("strategy.md has no '## Notebook <L>' section: re-run the scope stage")
    scouted = _sections(sources_text, _SOURCES_SECTION) if sources_text is not None else {}
    probe_status = "skipped"
    if probe is not None:
        probe_status = "no_youtube_urls"
        first = _YOUTUBE_URL.search(strategy_text) or _YOUTUBE_URL.search(" ".join(scouted.values()))
        if first:
            probe_status = probe(first.group(0))
            checks["ingest_probe"] = {"youtube": probe_status, "url": first.group(0)}
    if "ingest_probe" not in checks:
        checks["ingest_probe"] = {"youtube": probe_status}
    for letter, body in notebooks.items():
        m = _SOURCE_STRATEGY.search(body)
        strategy = m.group(1).lower().replace("-", "_") if m else "unknown"
        urls = len(_URL.findall(body))
        accessible = len(_ACCESSIBLE_OK.findall(scouted.get(letter, "")))
        checks["notebooks"][letter] = {"strategy": strategy, "accessible": accessible, "strategy_urls": urls}
        if strategy == "research_start":
            continue
        if probe_status == "rate_limited" and accessible == 0:
            section = scouted.get(letter, "")
            all_urls = _URL.findall(body) + _URL.findall(section)
            youtube_only = bool(all_urls) and not _TEXT_ENTRY.search(section) and all(
                _YOUTUBE_URL.match(u) for u in all_urls
            )
            checks["notebooks"][letter]["youtube_rate_limited"] = True
            if youtube_only:
                remedy.append(
                    f"Notebook {letter} is scout-provided with YouTube sources only and YouTube answered "
                    "HTTP 429 (this IP is rate-limited, so every YouTube source_add will fail): wait and re-run, "
                    "re-run scout for non-YouTube sources or text: transcripts, or switch the notebook to research_start"
                )
                continue
        if urls > 0 or accessible > 0:
            continue
        if sources_text is None:
            remedy.append(
                f"Notebook {letter} is scout-provided but sources.md is absent (scout failed or never ran): "
                "re-run scout, or switch the notebook to research_start in strategy.md"
            )
        else:
            remedy.append(
                f"Notebook {letter} is scout-provided but has no accessible source in sources.md "
                "(zero entries, or every entry Accessible: NO): re-run scout with other search guidance, "
                "supply URLs in strategy.md, or switch the notebook to research_start"
            )
    return {"ok": not remedy, "remedy": remedy, "checks": checks}


def _count_claims(path: Path) -> int | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return len(data) if isinstance(data, list) else None


def gate_claims(strategy_text: str | None, scratch_dir: Path) -> dict:
    checks: dict = {
        "worker_count": None,
        "dispatched": [],
        "out_of_strategy": [],
        "claims_by_letter": {},
        "total_claims": 0,
    }
    if strategy_text is None:
        return {"ok": False, "remedy": ["strategy.md is unreadable: re-run the scope stage"], "checks": checks}
    worker_count = parse_worker_count(strategy_text)
    if worker_count is None:
        return {
            "ok": False,
            "remedy": ["strategy.md has no worker_count in its frontmatter: re-run the scope stage"],
            "checks": checks,
        }
    checks["worker_count"] = worker_count
    letters = sorted(_sections(strategy_text, _NOTEBOOK_SECTION))

    dispatched: list[str] = []
    out_of_strategy: list[str] = []
    malformed: list[str] = []
    for marker in sorted(scratch_dir.glob("*-dispatch.json")):
        letter = marker.name[: -len("-dispatch.json")]
        dispatched.append(letter)
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            in_strategy = isinstance(data, dict) and data.get("in_strategy") is True
        except (OSError, ValueError):
            in_strategy = False
        if not in_strategy or letter not in letters:
            out_of_strategy.append(letter)
    checks["dispatched"] = dispatched
    checks["out_of_strategy"] = out_of_strategy

    by_letter: dict[str, int] = {}
    for letter in letters:
        claims_file = scratch_dir / f"{letter}-claims.json"
        count = _count_claims(claims_file) if claims_file.exists() else 0
        if count is None:
            malformed.append(letter)
            count = 0
        by_letter[letter] = count
    total = sum(by_letter.values())
    checks["claims_by_letter"] = by_letter
    checks["total_claims"] = total
    if malformed:
        checks["malformed_claims"] = malformed

    remedy: list[str] = []
    if len(dispatched) > worker_count:
        remedy.append(
            f"fan-out {len(dispatched)} != strategy worker_count {worker_count}: the run fanned workers over "
            f"a list other than strategy.md's notebooks; re-emit with notebooks = {', '.join(letters)}"
        )
    elif len(dispatched) < worker_count:
        missing = [letter for letter in letters if letter not in dispatched]
        remedy.append(
            f"{len(dispatched)} of {worker_count} workers wrote a dispatch marker; no marker for "
            f"{', '.join(missing) or 'any notebook'}: those workers crashed before their first step, re-run them"
        )
    if out_of_strategy:
        remedy.append(
            f"workers {', '.join(out_of_strategy)} are not in strategy.md (in_strategy false or marker unreadable): "
            f"re-emit with notebooks = {', '.join(letters)}"
        )
    if total == 0:
        detail = f" (malformed claims files: {', '.join(malformed)})" if malformed else ""
        remedy.append(
            f"0 claims across notebooks {', '.join(letters) or '(none)'}{detail}: sweep has nothing to merge; "
            "inspect worker output and re-run the workers"
        )
    return {"ok": not remedy, "remedy": remedy, "checks": checks}


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_src = sub.add_parser("sources")
    p_src.add_argument("--strategy", required=True)
    p_src.add_argument("--sources", required=True)
    p_src.add_argument(
        "--probe-ingest",
        action="store_true",
        help="fetch one YouTube URL and fail YouTube-only notebooks on HTTP 429",
    )
    p_clm = sub.add_parser("claims")
    p_clm.add_argument("--strategy", required=True)
    p_clm.add_argument("--scratch", required=True)
    args = parser.parse_args(argv)

    strategy = _read(args.strategy)
    if args.cmd == "sources":
        result = gate_sources(strategy, _read(args.sources), probe_youtube if args.probe_ingest else None)
    else:
        result = gate_claims(strategy, Path(args.scratch))
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
