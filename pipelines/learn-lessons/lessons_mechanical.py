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
      D/budget-ledger.json. Rejects any id outside the manifest; a `doctrine-edit` or `memory-pointer` verdict fails the triage schema and its batch stays open as unrefuted. Applies only refute-upheld discard,
      dedupe, wiki-append and wiki-new verdicts whose target checks out; an overturned, unrefuted or
      unappliable verdict is never applied; a `discard` naming no target closes the row, any other target
      must check out. A wiki-new target is a new `.md` with an index to link from (an `_index.md`, else a
      DIRECTORY_GUIDE.md/README.md table in its directory or the docs/README.md table, already indexing it): the script writes the page, the index link and, for a page
      under coordinator/docs/wiki, its register row. A wiki-new naming an existing index-reachable page appends to it.
      Writes D/records/<id>.json per closed row and D/finalize-report.json:
      grind_seeds (one {id, verdict, target, evidence, tests} per grind row, also written
      to records/<id>.json with `seed: true`),
      residue_for_grind (refute-upheld code-edit rows only, admitted only while count x GRIND_ROW_TOKENS
      fits the remaining budget), unrefuted (rows left open for the next triage run, including any the
      triage call returned no verdict for), malformed and handed_back (judgment rows for the EM: universal and escalation verdicts, and overturned,
      unappliable or unreadable rows, each with its reason), budget_exhausted (the rest, still open), deferred and
      remaining_budget (the budget_tokens to pass the residue grind).

Exit 0 ok, 1 a phase halted (the report names it), 2 unusable input. Every report carries agent_spawns: 0.
"""
from __future__ import annotations

import argparse
import hashlib
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
from types import ModuleType
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
# What one grind row costs end to end, in fresh tokens: measured at 293,894 for a 1-row lessons grind
# (six agents, each paying its own context load), so residue admission reserves that, not a projection.
GRIND_ROW_TOKENS = 294000
# How much of a lesson body one payload carries.
LESSON_BODY_BYTES = 1200
PRIOR_ART_MAX = 2
# Candidate homes one lesson carries: triage has no tools, so a page it is not shown is a page it invents.
HOMES_MAX = 5
PRIOR_ART_ONELINER_CHARS = 160
WIKI_ROOTS = ("docs/wiki", "coordinator/docs/wiki")
WIKI_SCAN_MAX_FILES = 3000
_BATCH_OVERHEAD_BYTES = 64

SCRIPT_APPLIABLE = ("discard", "dedupe", "wiki-append", "wiki-new")
CODE_EDIT_VERDICTS = ("agent-prompt-edit", "hook-edit", "script-edit", "snippet-sync-update",
                      "project-structural")
# A wiki-new page under this prefix joins the rule-class register in the target repo; elsewhere it gets no row.
REGISTER_REL = "state/audits/2026-09-06-doctrine-rule-class-register.yaml"
REGISTER_UNIVERSE = "coordinator/docs/wiki/"
HANDBACK_VERDICTS = ("universal", "doe-escalation", "direction-call", "malformed")
REQUIRED_FIELDS = ("created", "title", "body", "status", "scope", "from_repo")
LESSON_WIKI_DIR = "coordinator/docs/wiki/lesson-triage"
# Table indexes, tried when no `_index.md` covers a page: these names in the page's own directory, then the
# docs-root README. Each is a markdown table whose first cell links a page (`[name](path)`, backticks and
# bold optional); one indexes a directory only when it already carries a row linking into it.
TABLE_INDEX_NAMES = ("DIRECTORY_GUIDE.md", "README.md")
DOCS_README_INDEX = "docs/README.md"
_TABLE_ROW_RE = re.compile(r"^\| (\*\*|)\[(`?)([^`\]]+)\2\]\(([^)#]+)\)\1 \|(.*)$", re.M)

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
    if not isinstance(doc, dict):
        return None
    return _restore_comment_cut_scalars(text, doc)


_TOP_PLAIN = re.compile(r"^([A-Za-z_][\w-]*):[ \t]+(?![\"'|>&*!\[{])(.*\S)[ \t]*$")


def _restore_comment_cut_scalars(text: str, doc: dict) -> dict:
    """Undo YAML's ` #` comment cut on a single-line top-level plain scalar.

    Trap: lesson rows are tool-written data, and a body like `(PM #41, ...)` left unquoted parses
    as `(PM` -- the rest becomes a comment and a writer would land the truncated text. A row's
    value never carries an intended trailing comment, so the raw line is the author's text."""
    for line in text.splitlines():
        m = _TOP_PLAIN.match(line)
        if not m or m.group(1) not in doc or not isinstance(doc[m.group(1)], str):
            continue
        raw, parsed = m.group(2), doc[m.group(1)]
        if raw != parsed and re.search(r"\s#", raw) and raw.startswith(parsed):
            doc[m.group(1)] = raw
    return doc


def read_lesson(path: Path) -> Optional[dict]:
    try:
        return _load_yaml(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None


_MD_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.S)
_UNIVERSAL_SCOPES = ("universal", "fleet")


def _md_lesson_row(repo: Path, path: Path) -> dict:
    """The `.yaml` row form of a legacy frontmatter-plus-markdown lesson; fields it cannot name stay blank."""
    text = path.read_text(encoding="utf-8")
    m = _MD_FRONTMATTER.match(text)
    fm = (_load_yaml(m.group(1)) or {}) if m else {}
    body = text[m.end():] if m else text
    heading = re.match(r"\s*#[ \t]+(.+?)[ \t]*\r?\n", body)
    if heading:
        body = body[heading.end():]
    stamp = re.match(r"(\d{4}-\d{2}-\d{2})", path.stem)
    scope = str(fm.get("scope") or "").strip().lower()
    row = {
        "created": str(fm.get("created") or fm.get("date") or (stamp.group(1) if stamp else "")),
        "title": str(fm.get("title") or fm.get("name") or (heading.group(1) if heading else "")
                     or path.stem.replace("-", " ")),
        "body": body.strip(),
        "status": "open",
        "scope": "universal" if scope in _UNIVERSAL_SCOPES else "project",
        "from_repo": repo.resolve().name,
    }
    session = fm.get("source_session") or fm.get("session")
    if session:
        row["source_session"] = str(session)
    return row


def migrate_md_lessons(repo: Path, dry_run: bool) -> dict:
    """Rewrite each legacy `<stem>.md` lesson as `<stem>.yaml`, so discovery, triage and archive see it.

    A stem already holding a `.yaml` is a collision, left untouched and reported."""
    import yaml

    class _Dumper(yaml.SafeDumper):
        pass

    def _str(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)

    _Dumper.add_representer(str, _str)
    home = repo / LESSONS_DIR
    migrated, collisions = [], []
    for path in sorted(home.glob("*.md")) if home.is_dir() else []:
        dest = path.with_suffix(".yaml")
        if dest.exists():
            collisions.append(path.stem)
            continue
        try:
            row = _md_lesson_row(repo, path)
        except (OSError, UnicodeDecodeError):
            collisions.append(path.stem)
            continue
        if not dry_run:
            dest.write_text(yaml.dump(row, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=10**6),
                            encoding="utf-8")
            path.unlink()
        migrated.append(path.stem)
    return {"migrated": migrated, "collisions": collisions}


# A row already carrying one of these is closed by its own record; triage never sees it, so only an
# archive move ends it. Anything else (open, blank, unknown) stays for triage.
TERMINAL_STATUSES = ("closed", "applied", "resolved", "discarded", "archived", "superseded")


def sweep_terminal_rows(repo: Path, dry_run: bool) -> List[str]:
    """Archive every lesson row whose own `status:` is terminal; the ids moved."""
    swept = []
    for lid in lesson_ids(repo):
        src = repo / LESSONS_DIR / f"{lid}.yaml"
        doc = read_lesson(src) or {}
        status = str(doc.get("status") or "").split("#", 1)[0].strip().strip("\"'").lower()
        if status not in TERMINAL_STATUSES:
            continue
        if not dry_run:
            _archive_row(repo, src, {"disposition": "discard", "closed_by": "learn-lessons-prepare",
                                     "closed_reason": f"already terminal (status: {status}) in the row itself"}, _month())
        swept.append(lid)
    return swept


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


_SCRATCH_ROOT_MODULE = Path(__file__).resolve().parents[2] / "hooks" / "scripts" / "_scratch_root.py"


def _scratch_root_module() -> ModuleType:
    """The hook-side scratch resolver, loaded by path so hooks/scripts never joins sys.path."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_lessons_scratch_root", _SCRATCH_ROOT_MODULE)
    if spec is None or spec.loader is None:
        raise DriverError("scratch-root-unloadable", str(_SCRATCH_ROOT_MODULE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def apply_mechanical(repo: Path, invoke: List[str], dry_run: bool, timeout: int) -> dict:
    """Run the engine's mechanical close under a timeout; a timeout is a typed halt, never a fallback scan."""
    scratch = _scratch_root_module().scratch_dir(repo, "learn-lessons", f"apply-{date.today():%Y%m%d}")
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
                    _append_to_wiki(page, lesson_heading(doc), render_body(repo, lid, doc, page, None))
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


def candidate_homes(repo: Path, doc: dict, index: Dict[str, List[Tuple[str, str]]],
                    reachable: Dict[str, bool]) -> List[str]:
    """At most HOMES_MAX wiki pages finalize would accept as a wiki-append/dedupe target for this lesson.

    The lesson's own named target comes first when it qualifies; the rest rank by heading words shared
    with the title and tags. `reachable` memoises the index-reach check across lessons.
    """
    def ok(rel: str) -> bool:
        if rel not in reachable:
            page = _wiki_page(repo, rel)
            reachable[rel] = page is not None and page.name != "_index.md" and _index_reaches(repo, page)
        return reachable[rel]

    named = [t for t in (_clean_target(doc.get(k)) for k in ("proposed_target", "target_wiki")) if t]
    words = _words(" ".join([str(doc.get("title") or "")] + _tags(doc)))
    score: Dict[str, int] = {}
    for w in words:
        for rel, _heading in index.get(w, ()):
            score[rel] = score.get(rel, 0) + 1
    ranked = sorted(score, key=lambda rel: (-score[rel], rel))
    homes: List[str] = []
    for rel in named + ranked:
        if rel not in homes and ok(rel):
            homes.append(rel)
            if len(homes) == HOMES_MAX:
                break
    return homes


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


def lesson_entry(lid: str, doc: dict, index: Dict[str, List[Tuple[str, str]]],
                 homes: Optional[List[str]] = None) -> dict:
    title = str(doc.get("title") or "")
    entry = {"id": lid, "title": title,
             "body": _cap_bytes(strip_frontmatter(str(doc.get("body") or "")), LESSON_BODY_BYTES),
             "scope": str(doc.get("scope") or ""), "created": str(doc.get("created") or ""),
             "tags": _tags(doc)}
    for key in ("proposed_target", "target_wiki"):
        value = _clean_target(doc.get(key))
        if value:
            entry[key] = value
    art = prior_art(title, index)
    if art:
        entry["prior_art"] = art
    entry["homes"] = homes or []
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
    report["md_migrated"] = migrate_md_lessons(repo, dry_run)
    report["terminal_swept"] = sweep_terminal_rows(repo, dry_run)
    report["age_sweep"] = age_sweep(repo, cutoff, dry_run)
    report["seconds"]["age_sweep"] = round(time.monotonic() - t0, 3)

    t0 = time.monotonic()
    mech = apply_mechanical(repo, invoke, dry_run, timeout)
    left, malformed, script_closed = script_rules(repo, sorted(map(str, mech["residue_ids"])), dry_run)
    # The engine names rows whose YAML does not load beside residue_ids; they never reach triage.
    malformed += [{"id": str(i), "evidence": "unparseable YAML"} for i in mech.get("unreadable") or []]
    report["mechanical"] = {"closed": mech.get("closed", {}), "script_closed": script_closed, "residue_ids": left}
    report["malformed"] = malformed
    report["seconds"]["mechanical"] = round(time.monotonic() - t0, 3)

    t0 = time.monotonic()
    index = wiki_heading_index(repo)
    reachable: Dict[str, bool] = {}
    entries, unreadable = [], []
    for lid in report["mechanical"]["residue_ids"]:
        doc = read_lesson(repo / LESSONS_DIR / f"{lid}.yaml")
        if doc is None:
            unreadable.append(lid)
        else:
            entries.append(lesson_entry(lid, doc, index, candidate_homes(repo, doc, index, reachable)))
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
            return _table_links(repo, page)
        cur = cur.parent


def _table_indexes(repo: Path, page: Path) -> List[Path]:
    """The existing table-index files that could index the page, nearest first."""
    cands = [page.parent / n for n in TABLE_INDEX_NAMES] + [repo / DOCS_README_INDEX]
    return [c for i, c in enumerate(cands) if c.is_file() and c not in cands[:i]]


def _link_rel(index: Path, page: Path) -> Optional[str]:
    """The page's link as written from the index's directory; None when the page is not under it."""
    try:
        return page.relative_to(index.parent).as_posix()
    except ValueError:
        return None


def _table_links(repo: Path, page: Path) -> bool:
    """True when a table index carries a link to the page."""
    for index in _table_indexes(repo, page):
        rel = _link_rel(index, page)
        try:
            if rel is not None and f"]({rel})" in index.read_text(encoding="utf-8"):
                return True
        except (OSError, UnicodeDecodeError):
            continue
    return False


def _table_row_insert(text: str, rel: str, title: str) -> Optional[str]:
    """The index text with a row for `rel` in name order among the rows indexing rel's directory: title in
    the last cell, link style and column count copied from those rows. None when no row indexes it."""
    folder = rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""
    rows = [m for m in _TABLE_ROW_RE.finditer(text)
            if m.group(4).startswith(folder) and "/" not in m.group(4)[len(folder):]]
    if not rows:
        return None
    nl = "\r\n" if "\r\n" in text else "\n"
    name = rel.rsplit("/", 1)[-1]
    tick, cells = rows[0].group(2), max(1, rows[0].group(5).count("|"))
    row = f"| [{tick}{name}{tick}]({rel}) |" + " |" * (cells - 1) + f" {title} |"
    after = next((m for m in rows if m.group(3) > name), None)
    if after is not None:
        return text[:after.start()] + row + nl + text[after.start():]
    return text[:rows[-1].end()] + nl + row + text[rows[-1].end():]


def strip_frontmatter(text: str) -> str:
    """A lesson body without a leading `---` frontmatter block (memory-rerouted rows carry one).

    The block is store metadata (name, metadata.node_type, originSessionId): appended to a wiki page
    it lands mid-page as junk, and in a triage payload it is spend that judges nothing.
    """
    lines = text.lstrip().splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:]).strip()
    return text


_WIKILINK = re.compile(r"\[\[([^\]|#\n]+)\]\]")
_SLUG_TITLE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
_FM_DESCRIPTION = re.compile(r"^description:[ \t]*(.+?)[ \t]*$", re.M)
_ACRONYMS = {"pm", "em", "ui", "db", "api", "ip", "qa"}
HEADING_FROM_DESCRIPTION_MAX = 90


class WriteCtx:
    """What a page write needs beyond the lesson: EM-ruled superseded rows and EM status notes.

    `dropped` holds the slugs of rows an EM ruling discarded as superseded: a `[[slug]]` link to one is
    removed with its Related/See clause, so a page never points a reader at retired doctrine.
    `notes` maps a lesson id to an EM status line appended to that lesson's text.
    `created` holds the repo-relative pages this finalize wrote from wiki-new verdicts: a later
    wiki-new naming one appends to it, because batched triage routinely sends sibling lessons to
    one new page.
    """

    def __init__(self, dropped: Optional[set] = None, notes: Optional[Dict[str, str]] = None) -> None:
        self.dropped = set(dropped or ())
        self.notes = dict(notes or {})
        self.created: set = set()


def row_slug(lid: str) -> str:
    """A lesson id without its date prefix and hash suffix: the name a `[[link]]` uses for the row."""
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", re.sub(r"-[0-9a-f]{12}$", "", lid))


def lesson_heading(doc: dict) -> str:
    """A readable heading: the title, unless it is a bare slug (memory-rerouted rows), then the
    frontmatter description when short enough, else the slug in words."""
    title = str(doc.get("title") or "").strip()
    if title and not _SLUG_TITLE.match(title):
        return title
    body = str(doc.get("body") or "")
    fm = body[: len(body) - len(strip_frontmatter(body))] if strip_frontmatter(body) != body else ""
    m = _FM_DESCRIPTION.search(fm)
    if m and len(m.group(1)) <= HEADING_FROM_DESCRIPTION_MAX:
        return m.group(1).strip().strip("\"'")
    if not title:
        return "Lesson"
    words = [w.upper() if w in _ACRONYMS else w for w in title.split("-")]
    return " ".join(words)[:1].upper() + " ".join(words)[1:]


def _wiki_pages_by_stem(repo: Path) -> Dict[str, Path]:
    pages: Dict[str, Path] = {}
    seen = 0
    for root in WIKI_ROOTS:
        base = repo / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            seen += 1
            if seen > WIKI_SCAN_MAX_FILES:
                return pages
            pages.setdefault(path.stem, path)
    return pages


def render_body(repo: Path, lid: str, doc: dict, page: Path, ctx: Optional[WriteCtx]) -> str:
    """The lesson text as it lands on `page`: no frontmatter, `[[links]]` resolved, EM note appended.

    A link to an EM-discarded row is removed with its clause; a link naming an existing wiki page
    becomes a relative markdown link; any other link is left as written.
    """
    ctx = ctx or WriteCtx()
    body = strip_frontmatter(str(doc.get("body") or "")).strip()
    for slug in ctx.dropped:
        name = re.escape(slug)
        body = re.sub(rf"[ \t]*\(?(?:Related|See also|See|see also|see):?[ \t]*\[\[{name}\]\]\)?\.?", "", body)
        body = body.replace(f"[[{slug}]]", "")
    pages = _wiki_pages_by_stem(repo) if _WIKILINK.search(body) else {}

    def link(m: "re.Match[str]") -> str:
        target = pages.get(m.group(1).strip())
        if target is None:
            return m.group(0)
        return f"[{m.group(1).strip()}]({os.path.relpath(target, page.parent).replace(os.sep, '/')})"

    body = _WIKILINK.sub(link, body)
    note = ctx.notes.get(lid)
    if note:
        body = f"{body}\n\n**Status (EM ruling):** {note.strip()}"
    return re.sub(r"[ \t]+\n", "\n", body).strip()


def _append_to_wiki(wiki: Path, title: str, body: str) -> bool:
    text = wiki.read_text(encoding="utf-8", newline="")
    heading = title.strip() or "Lesson"
    if _norm(f"## {heading} {body}") in _norm(text):
        return False
    nl = "\r\n" if "\r\n" in text else "\n"
    block = f"## {heading}{nl}{nl}{body.strip()}{nl}"
    wiki.write_text(text + ("" if text.endswith(nl) else nl) + nl + block, encoding="utf-8", newline="")
    return True


def _nearest_index(repo: Path, page: Path) -> Optional[Path]:
    """The `_index.md` in the page's directory or the nearest ancestor below the repo root, else the nearest
    table index already indexing the page's directory; None when neither."""
    cur = page.parent
    while cur != repo and repo in cur.parents:
        if (cur / "_index.md").is_file():
            return cur / "_index.md"
        cur = cur.parent
    for index in _table_indexes(repo, page):
        rel = _link_rel(index, page)
        try:
            if rel is not None and _table_row_insert(index.read_text(encoding="utf-8"), rel, "") is not None:
                return index
        except (OSError, UnicodeDecodeError):
            continue
    return None


def _register_insert(text: str, row_id: str, rel: str) -> Optional[str]:
    """The register text with one classified row for `rel` appended under `rows:` and `counts:` refreshed.

    Text-level on purpose: the register is a 26k-line file that a yaml round-trip would rewrite.
    None when the register has no `counts:` block or already carries a row for the file.
    """
    nl = "\r\n" if "\r\n" in text else "\n"
    marks = list(re.finditer(r"^counts:[ \t]*\r?$", text, re.M))
    if not marks or f"file: {rel}{nl}" in text:
        return None
    at = marks[-1].start()
    row = nl.join([
        f"- id: {row_id}", f"  file: {rel}", "  line: null", "  rule: null", "  stated_party: null",
        "  harmed_party: null", "  disposition: no-environment-scoped-premise",
        "  reason: Page written by learn-lessons finalize from an upheld wiki-new verdict; no environment-scoped premise.",
        "  predicate: read-at-source", ""])
    head, tail = text[:at], text[at:]
    if head and not head.endswith(nl):
        head += nl
    for key in ("rows_total", "no_environment_scoped_premise"):
        tail, n = re.subn(rf"^(  {key}: )(\d+)", lambda m: f"{m.group(1)}{int(m.group(2)) + 1}", tail, count=1, flags=re.M)
        if not n:
            return None
    return head + row + tail


def _apply_wiki_new(repo: Path, src: Path, doc: dict, row: dict, target: str, dry_run: bool,
                    ctx: Optional[WriteCtx] = None) -> Tuple[bool, str]:
    """Write an upheld wiki-new: page, `_index.md` link, and (inside the register's universe) its register row.

    Nothing is left behind on a refusal or a failed write; a dry run checks and writes nothing.
    """
    dest = _inside(repo, target) if target else None
    if dest is None or dest.suffix != ".md" or repo.resolve() not in dest.resolve().parents:
        return False, "wiki-new-target-not-a-repo-md-path"
    if (repo / LESSONS_DIR).resolve() in dest.resolve().parents:
        return False, "wiki-new-target-in-lessons-dir"
    ctx = ctx if ctx is not None else WriteCtx()
    rel = dest.relative_to(repo).as_posix()
    if rel in ctx.created or (dest.is_file() and _index_reaches(repo, dest)):
        return _append_wiki_new(repo, src, doc, row, dest, rel, dry_run, ctx)
    if dest.exists():
        return False, "wiki-new-target-exists"
    index = _nearest_index(repo, dest)
    if index is None:
        return False, "wiki-new-no-index"
    title = lesson_heading(doc)
    body = render_body(repo, src.stem, doc, dest, ctx)
    if not body:
        return False, "wiki-new-empty-body"
    register = repo / REGISTER_REL
    row_id = "rcr-" + hashlib.sha1(f"{rel}\0".encode("utf-8")).hexdigest()[:8]
    reg_old: Optional[str] = None
    reg_new: Optional[str] = None
    try:
        idx_old = index.read_text(encoding="utf-8", newline="")
        if register.is_file() and rel.startswith(REGISTER_UNIVERSE):
            reg_old = register.read_text(encoding="utf-8", newline="")
            reg_new = _register_insert(reg_old, row_id, rel)
            if reg_new is None:
                return False, "wiki-new-register-unwritable"
    except (OSError, UnicodeDecodeError):
        return False, "wiki-new-write-failed"
    nl = "\r\n" if "\r\n" in idx_old else "\n"
    link_rel = dest.relative_to(index.parent).as_posix()
    idx_new = (idx_old + ("" if not idx_old or idx_old.endswith(nl) else nl) + f"- [{title}]({link_rel})" + nl
               if index.name == "_index.md" else _table_row_insert(idx_old, link_rel, title))
    if idx_new is None:
        return False, "wiki-new-no-index"
    if not dry_run:
        made: List[Path] = []
        try:
            for d in reversed([p for p in dest.parents if not p.exists()]):
                d.mkdir()
                made.append(d)
            dest.write_text(f"# {title}{nl}{nl}{body}{nl}", encoding="utf-8", newline="")
            index.write_text(idx_new, encoding="utf-8", newline="")
            if reg_new is not None:
                register.write_text(reg_new, encoding="utf-8", newline="")
            _archive_row(repo, src, {"disposition": "wiki-new", "covered_by": rel,
                                     "closed_reason": str(row.get("evidence") or "triage verdict"),
                                     "closed_by": "learn-lessons-triage"}, _month())
        except (OSError, ValueError):
            index.write_text(idx_old, encoding="utf-8", newline="")
            if reg_old is not None:
                register.write_text(reg_old, encoding="utf-8", newline="")
            dest.unlink(missing_ok=True)
            for d in reversed(made):
                try:
                    d.rmdir()
                except OSError:
                    break
            return False, "wiki-new-write-failed"
    ctx.created.add(rel)
    return True, ""


def _append_wiki_new(repo: Path, src: Path, doc: dict, row: dict, dest: Path, rel: str,
                     dry_run: bool, ctx: WriteCtx) -> Tuple[bool, str]:
    """Append a wiki-new lesson to an existing page: one this finalize created, or an index-reachable one."""
    body = render_body(repo, src.stem, doc, dest, ctx)
    if not body:
        return False, "wiki-new-empty-body"
    if dry_run:
        return True, ""
    try:
        _append_to_wiki(dest, lesson_heading(doc), body)
        _archive_row(repo, src, {"disposition": "wiki-append", "covered_by": rel,
                                 "closed_reason": str(row.get("evidence") or "triage verdict"),
                                 "closed_by": "learn-lessons-triage"}, _month())
    except (OSError, ValueError, UnicodeDecodeError):
        return False, "wiki-new-write-failed"
    return True, ""


def apply_verdict(repo: Path, lid: str, row: dict, dry_run: bool,
                  ctx: Optional[WriteCtx] = None) -> Tuple[bool, str]:
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
    if verdict == "wiki-new":
        return _apply_wiki_new(repo, src, doc, row, target, dry_run, ctx)
    dest = _inside(repo, target) if target else None
    if dest is None or not dest.is_file():
        return False, "target-not-an-existing-repo-file"
    if repo.resolve() not in dest.resolve().parents:
        return False, "target-not-an-existing-repo-file"
    if dest.resolve() == src.resolve():
        return False, "target-is-the-row"
    if verdict == "wiki-append":
        body = render_body(repo, lid, doc, dest, ctx)
        if dest.suffix != ".md" or not body.strip() or dest.parent.resolve() == src.parent.resolve() \
                or not _index_reaches(repo, dest):
            return False, "wiki-target-not-index-reachable"
        if not dry_run:
            try:
                _append_to_wiki(dest, lesson_heading(doc), body)
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


_ID_HASH_SUFFIX_RE = re.compile(r"-([0-9a-f]{12})$")


def _resolve_id(lid: str, batch_ids: List[str]) -> str:
    """Map a model-echoed id back to its batch id when the model "corrected" a truncated slug.

    Trap: slugs are cut mid-word (`benchmar-<hash>`) and a model completes the word, so an exact
    match misses a verdict it plainly meant. Only the 12-hex hash suffix is trusted, and only when
    exactly one batch id carries it; anything else stays unresolved and is rejected as before.
    """
    if lid in batch_ids:
        return lid
    m = _ID_HASH_SUFFIX_RE.search(lid)
    if not m:
        return lid
    hits = [i for i in batch_ids if i.endswith("-" + m.group(1))]
    return hits[0] if len(hits) == 1 else lid


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


EM_RULINGS_FILE = "em-rulings.json"


def _em_rulings(run_dir: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    """`<run_dir>/em-rulings.json` as (discards, notes); absent is ({}, {}).

    Each id maps to a superseding reason (a string, or {"kind": "discard", "reason": ...}) or to
    {"kind": "annotate", "note": ...}: the row still follows its triage verdict and its page text
    carries the note as its current status.
    """
    path = run_dir / EM_RULINGS_FILE
    if not path.is_file():
        return {}, {}
    data = read_json(path)
    bad = DriverError("unusable-input", f"{path} must map each lesson id to a non-empty discard reason "
                                        "or to {kind: discard|annotate, reason|note}")
    if not isinstance(data, dict):
        raise bad
    discards: Dict[str, str] = {}
    notes: Dict[str, str] = {}
    for lid, value in data.items():
        if isinstance(value, str):
            value = {"kind": "discard", "reason": value}
        if not isinstance(lid, str) or not isinstance(value, dict):
            raise bad
        kind = value.get("kind")
        text = value.get("reason") if kind == "discard" else value.get("note") if kind == "annotate" else None
        if not isinstance(text, str) or not text.strip():
            raise bad
        (discards if kind == "discard" else notes)[lid] = text
    return discards, notes


def finalize(run_dir: Path, repo_override: Optional[Path], budget_override: Optional[int], dry_run: bool) -> dict:
    prepared = read_json(run_dir / "prepared.json")
    if not isinstance(prepared, dict) or not isinstance(prepared.get("synth"), dict):
        raise DriverError("unusable-input", f"{run_dir / 'prepared.json'} is not a prepared.json")
    repo = (repo_override or Path(str(prepared.get("repo") or ""))).resolve()
    if not (repo / LESSONS_DIR).is_dir():
        raise DriverError("unusable-input", f"{repo / LESSONS_DIR} is not a directory")
    batches = _batch_records(read_json(run_dir / "synth-results.json"))
    remaining = _remaining(read_json(run_dir / "budget-ledger.json"), budget_override)
    rulings, notes = _em_rulings(run_dir)
    ctx = WriteCtx({row_slug(lid) for lid in rulings}, notes)

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
    already_closed: List[str] = []
    seeds: Dict[str, dict] = {}
    seen: set = set()
    t0 = time.monotonic()

    def seed_of(row: dict) -> dict:
        return {"id": row["id"], "verdict": row["verdict"], "target": row.get("target", ""),
                "evidence": row.get("evidence", ""), "tests": row.get("tests", [])}

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
                    unrefuted.append({"id": i, "verdict": None, "batch_id": bid, "reason": "triage-result-invalid"})
            seen.update(ids)
            continue
        verdicts = {}
        for row in triage["verdicts"]:
            rid = _resolve_id(row["id"], ids)
            verdicts[rid] = {**row, "id": rid}
        refute = {_resolve_id(k, ids): v for k, v in _refute_map(batch.get("refute")).items()}
        for lid, row in sorted(verdicts.items()):
            if lid not in manifest:
                rejected.append({"id": lid, "reason": "not-in-manifest", "batch_id": bid})
                continue
            if lid in seen:
                continue
            seen.add(lid)
            if not (repo / LESSONS_DIR / f"{lid}.yaml").exists():
                # Closed by an earlier finalize of this run (archived): a re-run is idempotent, never a grind row.
                already_closed.append(lid)
                continue
            if lid in rulings:
                # A tool-less refute cannot know a later PM ruling; the EM's recorded supersession
                # outranks the triage verdict and closes the row as discard, never as live doctrine.
                em_row = {"id": lid, "verdict": "discard", "target": "", "evidence": rulings[lid]}
                ok, why = apply_verdict(repo, lid, em_row, dry_run)
                if ok:
                    closed.append({"id": lid, "verdict": "discard", "target": "", "by": "em-ruling"})
                else:
                    handed_back.append({"id": lid, "verdict": "discard", "target": "", "reason": why})
                    unappliable.append({"id": lid, "reason": why, "batch_id": bid})
                continue
            ruling = refute.get(lid)
            if ruling is None:
                unrefuted.append({"id": lid, "verdict": row["verdict"], "batch_id": bid})
                continue
            if ruling == "overturned":
                # A refute-overturned verdict is a judgment split, not tool work: the EM rules it
                # (em-rulings.json) at no agent cost; the grind's per-row agent floor is never spent on it.
                handed_back.append({"id": lid, "verdict": row["verdict"], "target": row.get("target", ""),
                                    "reason": "refute-overturned"})
                continue
            verdict = row["verdict"]
            if verdict in SCRIPT_APPLIABLE:
                ok, why = apply_verdict(repo, lid, row, dry_run, ctx)
                if ok:
                    closed.append({"id": lid, "verdict": verdict, "target": row.get("target", "")})
                    if not dry_run:
                        write_json(run_dir / "records" / f"{lid}.json", {
                            "id": lid, "verdict": verdict, "target": row.get("target", ""),
                            "evidence": row.get("evidence", ""), "tests": row.get("tests", []), "refute": ruling})
                else:
                    handed_back.append({"id": lid, "verdict": verdict, "target": row.get("target", ""),
                                        "reason": why})
                    unappliable.append({"id": lid, "reason": why, "batch_id": bid})
            elif verdict in HANDBACK_VERDICTS:
                handed_back.append({"id": lid, "verdict": verdict, "target": row.get("target", "")})
            else:
                grind.append(lid)
                seeds[lid] = seed_of(row)
        for i in ids:
            if i in manifest and i not in seen:
                unrefuted.append({"id": i, "verdict": None, "batch_id": bid, "reason": "no-triage-verdict"})
                seen.add(i)

    handed_back += [{"id": i, "verdict": None, "target": "", "reason": "unreadable"}
                    for i in prepared.get("unreadable", []) if isinstance(i, str)]
    malformed = [m for m in prepared.get("malformed", []) if isinstance(m, dict) and isinstance(m.get("id"), str)]
    residue = sorted(set(grind))
    # The grind is handed the whole remainder as its hard cap; the per-row reservation only
    # decides which rows it gets, so the remainder after reserving is not its budget.
    admitted, over, _ = admit_grind_rows(residue, remaining)
    grind_seeds = [seeds[i] for i in residue if i in seeds]
    if not dry_run:
        for seed in grind_seeds:
            write_json(run_dir / "records" / f"{seed['id']}.json", {**seed, "seed": True})
    report.update({
        "grind_seeds": grind_seeds,
        "closed": closed, "already_closed": already_closed, "malformed": malformed, "handed_back": handed_back,
        "rejected": rejected, "unappliable": unappliable,
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
