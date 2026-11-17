"""Deterministic driver for the /learn-lessons local flow; no agent is ever spawned.

  prepare  --repo-root R [--run-dir D] [--run-id ID] [--dry-run] [--age-cutoff YYYY-MM-DD | --age-days N]
           [--invoke-bin PATH] [--apply-timeout SECONDS]
      Discovers lessons under R/state/lessons (no roots op; --repo-root is required, never cwd).
      Age-sweeps universal-tagged rows whose `created` precedes the cutoff (no cutoff given: the sweep
      is skipped, never guessed), closes dedupe, retag and target_wiki discard/wiki-append through
      `coordinator-invoke learn_lessons_pipeline.apply_mechanical` under a timeout, then runs the
      script rules over what is left: a row missing a required field is `malformed` (reported, left
      untouched, never backfilled), a body verbatim in an index-reachable wiki page is archived
      `discard`, and a body absent from an index-reachable wiki page the lesson names is appended and
      archived `wiki-append`. The rest is residue, sorted by batch_key [proposed_target, target_wiki], packed into
      <run-dir>/synth-batch-NN.json (per lesson: body plus at most PRIOR_ART_MAX wiki-heading
      one-liners; at most MAX_SYNTH_CALLS files, each under SYNTH_BATCH_BYTES). Overflow is
      prepared.deferred, handed back, never a further call. Writes <run-dir>/prepared.json: runId,
      synth {payloads (inline), schema}, deferred, unreadable, malformed, mechanical (engine closes
      plus `script_closed`), age_sweep. A payload lesson never carries a verdict or change-kind.
      --dry-run reads and reports, writing and moving nothing.

  finalize --run-dir D [--repo-root R] [--budget-tokens N] [--dry-run]
      Reads D/prepared.json, D/synth-results.json (the triage workflow's synth_results) and
      D/budget-ledger.json. Rejects any id outside the manifest; a `doctrine-edit` or `memory-pointer` verdict fails the triage schema and its batch goes to the grind. Applies only refute-upheld discard,
      dedupe and wiki-append verdicts whose target checks out; an overturned, unrefuted or unappliable
      verdict is never applied; a `discard` naming no target closes the row, any other target must
      check out. Writes D/records/<id>.json per closed row and D/finalize-report.json:
      residue_for_grind (code-edit and overturned rows, admitted only while count x GRIND_ROW_TOKENS
      fits the remaining budget), malformed and handed_back (judgment rows), budget_exhausted (the rest, still open), handed_back, deferred and
      remaining_budget (the budget_tokens to pass the residue grind).

Exit 0 ok, 1 a phase halted (the report names it), 2 unusable input. Every report carries agent_spawns: 0.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lessons_contract as lc  # noqa: E402

LESSONS_DIR = "state/lessons"
ARCHIVE_DIR = "archive/lessons"
SCRATCH_ROOT = "state/scratch/learn-lessons"
INVOKE_NAME = "coordinator-invoke"
APPLY_MECHANICAL_OP = "learn_lessons_pipeline.apply_mechanical"
# How long the engine may take to close the mechanical dispositions before the run halts.
APPLY_TIMEOUT_SECONDS = 300
# What one grind row may cost end to end (the base projection is ~5M tokens over 148 rows).
GRIND_ROW_TOKENS = 34000
# How much of a lesson body one payload carries.
LESSON_BODY_BYTES = 8000
PRIOR_ART_MAX = 2
PRIOR_ART_ONELINER_CHARS = 160
WIKI_ROOTS = ("docs/wiki", "coordinator/docs/wiki")
WIKI_SCAN_MAX_FILES = 3000
_BATCH_OVERHEAD_BYTES = 64

SCRIPT_APPLIABLE = ("discard", "dedupe", "wiki-append")
CODE_EDIT_VERDICTS = ("agent-prompt-edit", "hook-edit", "script-edit", "snippet-sync-update",
                      "project-structural", "wiki-new")
HANDBACK_VERDICTS = ("universal", "doe-escalation", "direction-call", "malformed")
REQUIRED_FIELDS = ("created", "title", "body", "status", "scope", "from_repo")
LESSON_WIKI_DIR = "coordinator/docs/wiki/lesson-triage"

_RUN_ID_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]*$")
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
_WORD = re.compile(r"[a-z0-9]{4,}")
_WIKI_PATH_RE = re.compile(r"(?:coordinator/)?docs/wiki/[\w./-]+?\.md")
_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
_STOPWORDS = frozenset({"that", "this", "with", "from", "when", "never", "always", "lesson", "into", "have",
                        "does", "were", "which", "their", "about", "should", "would", "there"})


class DriverError(Exception):
    """A phase cannot proceed; `code` is the halt name carried into the report."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------- shared helpers

def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%Hh%M")


def check_run_id(run_id: str) -> str:
    if not _RUN_ID_RE.match(run_id or ""):
        raise DriverError("bad-run-id", f"run id {run_id!r} must be a plain token")
    return run_id


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DriverError("unusable-input", f"{path}: {exc}") from exc


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_cmd(argv: List[str], cwd: Path, timeout: int = APPLY_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _resolve_bin(bin_name: str, override: Optional[str]) -> Optional[List[str]]:
    """argv for a settings-home CLI: the override, else PATH, else <settings-home>/bin; None when absent."""
    if override:
        return [sys.executable, override] if override.endswith(".py") else [override]
    found = shutil.which(bin_name)
    if found:
        return [found]
    home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(Path.home() / ".coordinator-claude-settings")
    for name in (bin_name, bin_name + ".exe", bin_name + ".cmd"):
        cand = Path(home) / "bin" / name
        if cand.is_file():
            return [str(cand)]
    return None


def _load_yaml(text: str) -> Optional[dict]:
    """A lesson row with every scalar left a string (no date or bool resolution); None when unreadable."""
    import yaml

    loader = getattr(yaml, "CBaseLoader", yaml.BaseLoader)
    try:
        doc = yaml.load(text, Loader=loader)
    except yaml.YAMLError:
        return None
    return doc if isinstance(doc, dict) else None


def read_lesson(path: Path) -> Optional[dict]:
    try:
        return _load_yaml(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None


def lesson_ids(repo: Path) -> List[str]:
    home = repo / LESSONS_DIR
    return sorted(p.stem for p in home.glob("*.yaml") if p.is_file()) if home.is_dir() else []


def _created(doc: dict) -> Optional[date]:
    raw = str(doc.get("created") or doc.get("date") or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _tags(doc: dict) -> List[str]:
    tags = doc.get("tags")
    return [str(t) for t in tags] if isinstance(tags, list) else []


def _norm(text: object) -> str:
    return " ".join(str(text if text is not None else "").split()).casefold()


def _yaml_scalar(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def _with_paper_trail(text: str, fields: Dict[str, str]) -> str:
    """`text` with each top-level `fields` key set: an existing single-line key is replaced, else appended."""
    nl = "\r\n" if "\r\n" in text else "\n"
    if text and not text.endswith("\n"):
        text += nl
    for key, value in fields.items():
        line = f"{key}: {_yaml_scalar(value)}"
        pat = re.compile(rf"^{re.escape(key)}:[^\r\n]*", re.MULTILINE)
        text = pat.sub(lambda _m: line, text, count=1) if pat.search(text) else text + line + nl
    return text


def _archive_row(repo: Path, src: Path, fields: Dict[str, str], month: str) -> str:
    """Stamp the paper trail into the row and move it to archive/lessons/<month>/; the repo-relative dest."""
    text = src.read_text(encoding="utf-8", newline="")
    adir = repo / ARCHIVE_DIR / month
    adir.mkdir(parents=True, exist_ok=True)
    dest, n = adir / src.name, 2
    while dest.exists():
        dest = adir / f"{src.stem}-{n}{src.suffix}"
        n += 1
    stamped = _with_paper_trail(text, fields)
    if _load_yaml(stamped) is None:
        raise ValueError("stamped row no longer parses")
    src.write_text(stamped, encoding="utf-8", newline="")
    src.replace(dest)
    return dest.relative_to(repo).as_posix()


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


# --------------------------------------------------------------------------- age-sweep

def age_cutoff(cutoff: Optional[str], days: Optional[int], today: Optional[date] = None) -> Optional[date]:
    """The sweep cutoff: an explicit date, else today minus days; None means the sweep is skipped."""
    if cutoff:
        try:
            return date.fromisoformat(cutoff)
        except ValueError as exc:
            raise DriverError("unusable-input", f"--age-cutoff {cutoff!r} is not YYYY-MM-DD") from exc
    if days is not None:
        if days < 0:
            raise DriverError("unusable-input", "--age-days must be non-negative")
        return (today or datetime.now(timezone.utc).date()) - timedelta(days=days)
    return None


def age_sweep(repo: Path, cutoff: Optional[date], dry_run: bool) -> dict:
    """Archive universal-tagged rows whose `created` precedes the cutoff; undated and project rows are kept."""
    if cutoff is None:
        return {"status": "skipped", "reason": "no cutoff: pass --age-cutoff or --age-days", "archived": []}
    swept = []
    for lid in lesson_ids(repo):
        path = repo / LESSONS_DIR / f"{lid}.yaml"
        doc = read_lesson(path)
        created = _created(doc) if doc else None
        if doc is None or created is None or created >= cutoff or "universal" not in _tags(doc):
            continue
        if dry_run:
            swept.append(lid)
            continue
        try:
            _archive_row(repo, path, {"disposition": "age-sweep", "closed_reason": f"universal older than {cutoff}"},
                         _month())
        except (OSError, ValueError):
            continue
        swept.append(lid)
    return {"status": "planned" if dry_run else "applied", "cutoff": cutoff.isoformat(), "archived": swept}


# --------------------------------------------------------------------------- mechanical dispositions

def _find_report(stdout: str) -> Optional[dict]:
    """The apply_mechanical report out of a coordinator-invoke reply: a JSON-RPC envelope or JSON lines."""
    candidates = []
    try:
        candidates.append(json.loads(stdout))
    except ValueError:
        for line in stdout.splitlines():
            try:
                candidates.append(json.loads(line))
            except ValueError:
                continue
    for whole in candidates:
        node = whole.get("result", whole) if isinstance(whole, dict) else None
        if isinstance(node, dict):
            node = node.get("report", node)
        if isinstance(node, dict) and isinstance(node.get("residue_ids"), list):
            return node
    return None


def _envelope_failure(stdout: str) -> str:
    try:
        whole = json.loads(stdout)
    except ValueError:
        return ""
    result = whole.get("result") if isinstance(whole, dict) else None
    if isinstance(result, dict):
        code = result.get("exit_code")
        if isinstance(code, int) and not isinstance(code, bool) and code != 0:
            return str(result.get("error") or f"exit_code {code}")
    return ""


def apply_mechanical(repo: Path, invoke: List[str], dry_run: bool, timeout: int) -> dict:
    """Run the engine's mechanical close under a timeout; a timeout is a typed halt, never a fallback scan."""
    scratch = repo / SCRATCH_ROOT
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        params = Path(tmp) / "params.json"
        params.write_text(json.dumps({"repo": str(repo), "dry_run": bool(dry_run)}), encoding="utf-8")
        argv = [*invoke, APPLY_MECHANICAL_OP, "--params-file", str(params)]
        try:
            proc = run_cmd(argv, repo, timeout)
        except subprocess.TimeoutExpired as exc:
            raise DriverError("apply-mechanical-timeout", f"no reply within {timeout}s") from exc
        except (subprocess.SubprocessError, OSError) as exc:
            raise DriverError("apply-mechanical-failed", f"{type(exc).__name__}: {exc}"[:300]) from exc
    failure = _envelope_failure(proc.stdout) or (proc.stderr.strip()[:300] if proc.returncode else "")
    if proc.returncode or failure:
        raise DriverError("apply-mechanical-failed", failure or f"exit {proc.returncode}")
    report = _find_report(proc.stdout)
    if report is None:
        raise DriverError("apply-mechanical-bad-reply", "reply carries no residue_ids list")
    return report


# --------------------------------------------------------------------------- script rules

def missing_fields(doc: dict) -> List[str]:
    """Required lesson fields that are absent or blank."""
    return [f for f in REQUIRED_FIELDS if not str(doc.get(f) if doc.get(f) is not None else "").strip()]


def _paragraphs(text: str) -> List[str]:
    return [p for p in (_norm(chunk) for chunk in re.split(r"\n\s*\n", text)) if p]


def _contains_run(haystack: List[str], needle: List[str]) -> bool:
    n = len(needle)
    return n > 0 and any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def _named_paths(doc: dict) -> List[str]:
    found = [_clean_target(doc.get(k)) for k in ("proposed_target", "target_wiki")]
    found += _WIKI_PATH_RE.findall(str(doc.get("body") or ""))
    return sorted({f for f in found if f.endswith(".md")})


def _wiki_page(repo: Path, named: str) -> Optional[Path]:
    """An existing .md file under a wiki root, resolved inside the repo; None otherwise."""
    path = _inside(repo, named)
    if path is None or not path.is_file() or path.suffix != ".md":
        return None
    norm = named.replace("\\", "/")
    return path if any(norm.startswith(root + "/") for root in WIKI_ROOTS) else None


def _triage_index_pages(repo: Path) -> List[Path]:
    index = repo / LESSON_WIKI_DIR / "_index.md"
    if not index.is_file():
        return []
    pages = []
    for link in _LINK_RE.findall(index.read_text(encoding="utf-8")):
        target = link.split("#", 1)[0]
        if target.endswith(".md") and "://" not in target and (index.parent / target).is_file():
            pages.append(index.parent / target)
    return pages


def covering_page(repo: Path, doc: dict, cache: Dict[Path, List[str]]) -> Optional[Path]:
    """The index-reachable wiki page holding the whole body as a paragraph run; unindexed pages never count."""
    needle = _paragraphs(str(doc.get("body") or ""))
    candidates = list(_triage_index_pages(repo))
    for named in _named_paths(doc):
        page = _wiki_page(repo, named)
        if page is not None and _index_reaches(repo, page):
            candidates.append(page)
    for page in sorted(set(candidates)):
        if page not in cache:
            try:
                cache[page] = _paragraphs(page.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                cache[page] = []
        if _contains_run(cache[page], needle):
            return page
    return None


def append_page(repo: Path, doc: dict) -> Optional[Path]:
    """The index-reachable wiki page the lesson names, for a body-absent append; None when no such page."""
    for named in _named_paths(doc):
        page = _wiki_page(repo, named)
        if page is not None and _index_reaches(repo, page):
            return page
    return None


def script_rules(repo: Path, ids: List[str], dry_run: bool) -> Tuple[List[str], List[dict], List[dict]]:
    """Apply the no-model rules to `ids`; (still-residue ids, malformed rows, script closes). Never guesses."""
    residue: List[str] = []
    malformed: List[dict] = []
    closed: List[dict] = []
    cache: Dict[Path, List[str]] = {}
    for lid in ids:
        src = repo / LESSONS_DIR / f"{lid}.yaml"
        doc = read_lesson(src) if src.is_file() else None
        if doc is None:
            residue.append(lid)
            continue
        missing = missing_fields(doc)
        if missing:
            malformed.append({"id": lid, "evidence": "missing or empty field: " + ", ".join(missing)})
            continue
        page = covering_page(repo, doc, cache)
        rule = "discard"
        if page is None:
            page, rule = append_page(repo, doc), "wiki-append"
        if page is None:
            residue.append(lid)
            continue
        rel = page.relative_to(repo).as_posix()
        if not dry_run:
            try:
                if rule == "wiki-append":
                    _append_to_wiki(page, str(doc.get("title") or ""), str(doc.get("body") or ""))
                _archive_row(repo, src, {"disposition": rule, "covered_by": rel,
                                         "closed_reason": f"script rule {rule}", "closed_by": "learn-lessons-prepare"},
                             _month())
            except (OSError, ValueError):
                residue.append(lid)
                continue
        closed.append({"id": lid, "disposition": rule, "evidence": rel})
    return residue, malformed, closed


# --------------------------------------------------------------------------- packing

def _words(text: str) -> List[str]:
    return sorted({w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS})


def wiki_heading_index(repo: Path) -> Dict[str, List[Tuple[str, str]]]:
    """word -> [(wiki path, heading)] over the wiki roots' markdown files, capped at WIKI_SCAN_MAX_FILES."""
    index: Dict[str, List[Tuple[str, str]]] = {}
    seen = 0
    for root in WIKI_ROOTS:
        base = repo / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            seen += 1
            if seen > WIKI_SCAN_MAX_FILES:
                return index
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            rel = path.relative_to(repo).as_posix()
            for line in lines:
                m = _HEADING.match(line)
                if m and m.group(1):
                    for word in _words(m.group(1)):
                        index.setdefault(word, []).append((rel, m.group(1)))
    return index


def prior_art(title: str, index: Dict[str, List[Tuple[str, str]]]) -> List[str]:
    """At most PRIOR_ART_MAX `path: heading` one-liners whose heading shares the most words with the title."""
    words = _words(title)
    if not words:
        return []
    score: Dict[Tuple[str, str], int] = {}
    for w in words:
        for hit in index.get(w, ()):
            score[hit] = score.get(hit, 0) + 1
    need = 2 if len(words) >= 2 else 1
    ranked = sorted((h for h, s in score.items() if s >= need), key=lambda h: (-score[h], h))
    return [f"{p}: {h}"[:PRIOR_ART_ONELINER_CHARS] for p, h in ranked[:PRIOR_ART_MAX]]


def _cap_bytes(text: str, limit: int) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    return raw[:limit].decode("utf-8", errors="ignore") + " [truncated]"


def _clean_target(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() == "unknown" else text


def batch_key(entry: dict) -> Tuple[str, str, str]:
    return (entry.get("proposed_target", ""), entry.get("target_wiki", ""), entry["id"])


def lesson_entry(lid: str, doc: dict, index: Dict[str, List[Tuple[str, str]]]) -> dict:
    title = str(doc.get("title") or "")
    entry = {"id": lid, "title": title, "body": _cap_bytes(str(doc.get("body") or ""), LESSON_BODY_BYTES),
             "scope": str(doc.get("scope") or ""), "created": str(doc.get("created") or ""),
             "tags": _tags(doc)}
    for key in ("proposed_target", "target_wiki"):
        value = _clean_target(doc.get(key))
        if value:
            entry[key] = value
    art = prior_art(title, index)
    if art:
        entry["prior_art"] = art
    return entry


def _dumps(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def pack_batches(entries: List[dict], cap: int = lc.SYNTH_BATCH_BYTES) -> List[List[dict]]:
    """Greedy packing of batch_key-sorted entries into batches whose serialised file stays under `cap`."""
    batches: List[List[dict]] = []
    current: List[dict] = []
    size = _BATCH_OVERHEAD_BYTES
    for entry in sorted(entries, key=batch_key):
        cost = len(_dumps(entry).encode("utf-8")) + 1
        if current and size + cost >= cap:
            batches.append(current)
            current, size = [], _BATCH_OVERHEAD_BYTES
        current.append(entry)
        size += cost
    if current:
        batches.append(current)
    return batches


def batch_name(n: int) -> str:
    return f"batch-{n:02d}"


def batch_file(n: int) -> str:
    return f"synth-batch-{n:02d}.json"


def prepare(repo: Path, run_dir: Optional[Path], run_id: Optional[str], dry_run: bool, cutoff: Optional[date],
            invoke_override: Optional[str], timeout: int = APPLY_TIMEOUT_SECONDS) -> dict:
    rid = check_run_id(run_id or new_run_id())
    out = run_dir or (repo / SCRATCH_ROOT / rid)
    report: dict = {"phase": "prepare", "run_id": rid, "run_dir": str(out), "agent_spawns": 0, "dry_run": dry_run,
                    "seconds": {}}
    if not (repo / LESSONS_DIR).is_dir():
        raise DriverError("unusable-input", f"{repo / LESSONS_DIR} is not a directory")
    invoke = _resolve_bin(INVOKE_NAME, invoke_override)
    if invoke is None:
        raise DriverError("apply-mechanical-unavailable", f"{INVOKE_NAME} not found")

    t0 = time.monotonic()
    report["age_sweep"] = age_sweep(repo, cutoff, dry_run)
    report["seconds"]["age_sweep"] = round(time.monotonic() - t0, 3)

    t0 = time.monotonic()
    mech = apply_mechanical(repo, invoke, dry_run, timeout)
    left, malformed, script_closed = script_rules(repo, sorted(map(str, mech["residue_ids"])), dry_run)
    report["mechanical"] = {"closed": mech.get("closed", {}), "script_closed": script_closed, "residue_ids": left}
    report["malformed"] = malformed
    report["seconds"]["mechanical"] = round(time.monotonic() - t0, 3)

    t0 = time.monotonic()
    index = wiki_heading_index(repo)
    entries, unreadable = [], []
    for lid in report["mechanical"]["residue_ids"]:
        doc = read_lesson(repo / LESSONS_DIR / f"{lid}.yaml")
        if doc is None:
            unreadable.append(lid)
        else:
            entries.append(lesson_entry(lid, doc, index))
    batches = pack_batches(entries)
    kept, over = batches[:lc.MAX_SYNTH_CALLS], batches[lc.MAX_SYNTH_CALLS:]
    deferred = [e["id"] for b in over for e in b]
    payloads = [{"batch_id": batch_name(i), "file": batch_file(i), "lessons": b}
                for i, b in enumerate(kept, 1)]
    sizes = [len(_dumps(p["lessons"]).encode("utf-8")) + _BATCH_OVERHEAD_BYTES for p in payloads]
    report["seconds"]["pack"] = round(time.monotonic() - t0, 3)
    report.update({"residue": len(entries), "unreadable": unreadable, "deferred": deferred,
                   "batches": [{"batch_id": p["batch_id"], "file": p["file"], "lessons": len(p["lessons"]),
                                "bytes": s} for p, s in zip(payloads, sizes)]})
    if dry_run:
        return report

    out.mkdir(parents=True, exist_ok=True)
    for p in payloads:
        (out / str(p["file"])).write_text(_dumps({"batch_id": p["batch_id"], "lessons": p["lessons"]}) + "\n",
                                          encoding="utf-8")
    write_json(out / "prepared.json", {
        "runId": rid, "repo": str(repo), "budget_tokens": lc.DEFAULT_BUDGET,
        "synth": {"payloads": payloads, "schema": lc.TRIAGE_SCHEMA},
        "deferred": deferred, "unreadable": unreadable, "malformed": malformed,
        "mechanical": report["mechanical"], "age_sweep": report["age_sweep"],
    })
    return report


# --------------------------------------------------------------------------- finalize

def _inside(repo: Path, rel: str) -> Optional[Path]:
    """A repo-relative path resolved inside the repo; None for an absolute path or a parent escape."""
    norm = str(rel).replace("\\", "/")
    parts = norm.split("/")
    if not norm or norm.startswith("/") or re.match(r"^[A-Za-z]:", norm) or ".." in parts:
        return None
    return repo / norm


def _index_reaches(repo: Path, page: Path) -> bool:
    """True when an `_index.md` in the page's directory or an ancestor below the repo root names its file."""
    cur = page.parent
    while True:
        idx = cur / "_index.md"
        if idx.is_file():
            try:
                if page.name in idx.read_text(encoding="utf-8"):
                    return True
            except (OSError, UnicodeDecodeError):
                pass
        if cur == repo or repo not in cur.parents:
            return False
        cur = cur.parent


def _append_to_wiki(wiki: Path, title: str, body: str) -> bool:
    text = wiki.read_text(encoding="utf-8", newline="")
    heading = title.strip() or "Lesson"
    if _norm(f"## {heading} {body}") in _norm(text):
        return False
    nl = "\r\n" if "\r\n" in text else "\n"
    block = f"## {heading}{nl}{nl}{body.strip()}{nl}"
    wiki.write_text(text + ("" if text.endswith(nl) else nl) + nl + block, encoding="utf-8", newline="")
    return True


def apply_verdict(repo: Path, lid: str, row: dict, dry_run: bool) -> Tuple[bool, str]:
    """Apply one upheld script-appliable verdict; (applied, why-not). Nothing is written when the target fails its check."""
    src = repo / LESSONS_DIR / f"{lid}.yaml"
    doc = read_lesson(src) if src.is_file() else None
    if doc is None:
        return False, "row-missing-or-unreadable"
    verdict, target = row["verdict"], str(row.get("target") or "").strip()
    if verdict == "discard" and not target:
        if not dry_run:
            try:
                _archive_row(repo, src, {"disposition": verdict, "closed_by": "learn-lessons-triage",
                                         "closed_reason": str(row.get("evidence") or "triage verdict")}, _month())
            except (OSError, ValueError):
                return False, "archive-failed"
        return True, ""
    dest = _inside(repo, target) if target else None
    if dest is None or not dest.is_file():
        return False, "target-not-an-existing-repo-file"
    if repo.resolve() not in dest.resolve().parents:
        return False, "target-not-an-existing-repo-file"
    if dest.resolve() == src.resolve():
        return False, "target-is-the-row"
    if verdict == "wiki-append":
        body = str(doc.get("body") or "")
        if dest.suffix != ".md" or not body.strip() or dest.parent.resolve() == src.parent.resolve() \
                or not _index_reaches(repo, dest):
            return False, "wiki-target-not-index-reachable"
        if not dry_run:
            try:
                _append_to_wiki(dest, str(doc.get("title") or ""), body)
            except (OSError, UnicodeDecodeError):
                return False, "wiki-append-failed"
    if not dry_run:
        try:
            _archive_row(repo, src, {"disposition": verdict, "covered_by": target,
                                     "closed_reason": str(row.get("evidence") or "triage verdict"),
                                     "closed_by": "learn-lessons-triage"}, _month())
        except (OSError, ValueError):
            return False, "archive-failed"
    return True, ""


def _batch_records(results: object) -> List[dict]:
    node = results.get("synth_results") if isinstance(results, dict) else results
    if not isinstance(node, list):
        raise DriverError("unusable-input", "synth-results.json must be the workflow's synth_results list")
    return [b for b in node if isinstance(b, dict)]


def _refute_map(refute: object) -> Dict[str, str]:
    rows = refute.get("verdicts") if isinstance(refute, dict) else None
    out: Dict[str, str] = {}
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row.get("verdict") in ("upheld", "overturned"):
            out[row["id"]] = row["verdict"]
    return out


def _remaining(ledger: object, budget_override: Optional[int]) -> int:
    if not isinstance(ledger, dict):
        raise DriverError("unusable-input", "budget-ledger.json must be an object")
    spent = ledger.get("spent")
    if budget_override is not None:
        if not isinstance(spent, (int, float)) or isinstance(spent, bool):
            raise DriverError("unusable-input", "budget-ledger.json carries no measured `spent`")
        return max(int(budget_override) - int(spent), 0)
    remaining = ledger.get("remaining")
    if isinstance(remaining, bool) or not isinstance(remaining, (int, float)) or remaining < 0:
        raise DriverError("unusable-input", "budget-ledger.json carries no `remaining`")
    return int(remaining)


def admit_grind_rows(ids: List[str], remaining: int) -> Tuple[List[str], List[str], int]:
    """Admit rows while their projected total cost fits `remaining`; (admitted, over-budget, remaining after)."""
    ledger = lc.BudgetLedger(remaining)
    admitted: List[str] = []
    over: List[str] = []
    for lid in ids:
        if not over and ledger.admit(GRIND_ROW_TOKENS):
            ledger.record({"input_tokens": GRIND_ROW_TOKENS, "output_tokens": 0})
            admitted.append(lid)
        else:
            over.append(lid)
    return admitted, over, ledger.remaining


def finalize(run_dir: Path, repo_override: Optional[Path], budget_override: Optional[int], dry_run: bool) -> dict:
    prepared = read_json(run_dir / "prepared.json")
    if not isinstance(prepared, dict) or not isinstance(prepared.get("synth"), dict):
        raise DriverError("unusable-input", f"{run_dir / 'prepared.json'} is not a prepared.json")
    repo = (repo_override or Path(str(prepared.get("repo") or ""))).resolve()
    if not (repo / LESSONS_DIR).is_dir():
        raise DriverError("unusable-input", f"{repo / LESSONS_DIR} is not a directory")
    batches = _batch_records(read_json(run_dir / "synth-results.json"))
    remaining = _remaining(read_json(run_dir / "budget-ledger.json"), budget_override)

    manifest = {e["id"] for p in prepared["synth"].get("payloads", []) for e in p.get("lessons", [])
                if isinstance(e, dict) and isinstance(e.get("id"), str)}
    report: dict = {"phase": "finalize", "run_id": prepared.get("runId"), "run_dir": str(run_dir),
                    "agent_spawns": 0, "dry_run": dry_run}
    closed: List[dict] = []
    grind: List[str] = []
    handed_back: List[dict] = []
    triage_exhausted: List[str] = []
    unrefuted: List[dict] = []
    rejected: List[dict] = []
    unappliable: List[dict] = []
    seen: set = set()
    t0 = time.monotonic()

    for batch in batches:
        bid = batch.get("batch_id")
        ids = [i for i in batch.get("ids", []) if isinstance(i, str)]
        status = batch.get("status")
        if status == "budget-exhausted":
            triage_exhausted += [i for i in ids if i in manifest and i not in seen]
            seen.update(ids)
            continue
        triage = batch.get("triage")
        if not isinstance(triage, dict) or lc.validate_triage(triage):
            for i in ids:
                if i in manifest and i not in seen:
                    grind.append(i)
                    unappliable.append({"id": i, "reason": "triage-result-invalid", "batch_id": bid})
            seen.update(ids)
            continue
        verdicts = {row["id"]: row for row in triage["verdicts"]}
        refute = _refute_map(batch.get("refute"))
        for lid, row in sorted(verdicts.items()):
            if lid not in manifest:
                rejected.append({"id": lid, "reason": "not-in-manifest", "batch_id": bid})
                continue
            if lid in seen:
                continue
            seen.add(lid)
            ruling = refute.get(lid)
            if ruling is None:
                unrefuted.append({"id": lid, "verdict": row["verdict"], "batch_id": bid})
                continue
            if ruling == "overturned":
                grind.append(lid)
                continue
            verdict = row["verdict"]
            if verdict in SCRIPT_APPLIABLE:
                ok, why = apply_verdict(repo, lid, row, dry_run)
                if ok:
                    closed.append({"id": lid, "verdict": verdict, "target": row.get("target", "")})
                    if not dry_run:
                        write_json(run_dir / "records" / f"{lid}.json", {
                            "id": lid, "verdict": verdict, "target": row.get("target", ""),
                            "evidence": row.get("evidence", ""), "tests": row.get("tests", []), "refute": ruling})
                else:
                    grind.append(lid)
                    unappliable.append({"id": lid, "reason": why, "batch_id": bid})
            elif verdict in HANDBACK_VERDICTS:
                handed_back.append({"id": lid, "verdict": verdict, "target": row.get("target", "")})
            else:
                grind.append(lid)
        for i in ids:
            if i in manifest and i not in seen:
                unrefuted.append({"id": i, "verdict": None, "batch_id": bid, "reason": "no-triage-verdict"})
                seen.add(i)

    grind += [i for i in prepared.get("unreadable", []) if isinstance(i, str)]
    malformed = [m for m in prepared.get("malformed", []) if isinstance(m, dict) and isinstance(m.get("id"), str)]
    residue = sorted(set(grind))
    # The grind is handed the whole remainder as its hard cap; the per-row reservation only
    # decides which rows it gets, so the remainder after reserving is not its budget.
    admitted, over, _ = admit_grind_rows(residue, remaining)
    report.update({
        "closed": closed, "malformed": malformed, "handed_back": handed_back, "rejected": rejected, "unappliable": unappliable,
        "unrefuted": unrefuted,
        "deferred": [i for i in prepared.get("deferred", []) if isinstance(i, str)],
        "triage_budget_exhausted": sorted(triage_exhausted),
        "residue_for_grind": admitted, "grind_budget_exhausted": over,
        "grind_row_tokens": GRIND_ROW_TOKENS, "remaining_budget": remaining,
        "seconds": {"finalize": round(time.monotonic() - t0, 3)},
    })
    if not dry_run:
        write_json(run_dir / "finalize-report.json", report)
    return report


# --------------------------------------------------------------------------- CLI

def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="lessons_mechanical.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--repo-root", required=True)
    p.add_argument("--run-dir")
    p.add_argument("--run-id")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--age-cutoff")
    p.add_argument("--age-days", type=int)
    p.add_argument("--invoke-bin")
    p.add_argument("--apply-timeout", type=int, default=APPLY_TIMEOUT_SECONDS)
    f = sub.add_parser("finalize")
    f.add_argument("--run-dir", required=True)
    f.add_argument("--repo-root")
    f.add_argument("--budget-tokens", type=int)
    f.add_argument("--dry-run", action="store_true")
    ns = ap.parse_args(argv)
    try:
        if ns.cmd == "prepare":
            repo = Path(ns.repo_root).resolve()
            result = prepare(repo, Path(ns.run_dir).resolve() if ns.run_dir else None, ns.run_id, ns.dry_run,
                             age_cutoff(ns.age_cutoff, ns.age_days), ns.invoke_bin, ns.apply_timeout)
        else:
            result = finalize(Path(ns.run_dir).resolve(), Path(ns.repo_root).resolve() if ns.repo_root else None,
                              ns.budget_tokens, ns.dry_run)
    except DriverError as exc:
        print(json.dumps({"status": "error", "halted": exc.code, "detail": exc.detail, "agent_spawns": 0}))
        return 2 if exc.code in ("unusable-input", "bad-run-id") else 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
