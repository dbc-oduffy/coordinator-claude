"""Research-rules gate: the installed plugins' research rules, applied to one repo research run.

`brief --stage S --brief <file>` prints the rules the applicable overlays add to stage S (or "rules: none").
`scout --brief <scope.md> --scratch <dir>` answers "did each chunk's scout call the overlay's required tool
families?" from the scouts' transcripts. `synthesis --brief <scope.md> --synthesis <file>` answers "does the
synthesis end with the declared sections?". The two gates print one JSON object {ok, rules, failed, remedy,
checks} and always exit 0 on a decided result; the calling stage reads `ok`. Unreadable input is ok:false,
never a pass. No overlay applying is ok:true with rules "none".
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_rules_layer as layer_mod  # noqa: E402

CHUNKS = "ABCD"
_PATH_FIELD = re.compile(r"^\*\*Path:\*\*[ \t]*(.+?)[ \t]*$", re.M)
_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def target_repo(brief: Path) -> tuple[Path | None, str | None]:
    """`(repo path, error)`: the `**Path:**` field of the scope file, resolved against the working directory."""
    try:
        text = brief.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, f"brief {brief} unreadable: {exc}"
    m = _PATH_FIELD.search(text)
    if not m:
        return None, f"brief {brief} has no **Path:** field"
    raw = m.group(1).strip().strip("`'\"").strip()
    path = Path(raw).expanduser()
    if not path.is_dir():
        return None, f"target repo path {raw!r} from {brief} is not a directory"
    return path.resolve(), None


def _verdict(ok: bool, layers: list[dict], remedy=None, checks=None, failed=None) -> dict:
    return {
        "ok": ok,
        "rules": [layer["plugin"] for layer in layers] or "none",
        "failed": failed or [],
        "remedy": remedy or [],
        "checks": checks or {},
    }


def _resolve(brief: Path, plugin_roots, resolve_key) -> tuple[list[dict], list[str], dict | None]:
    """`(layers, issues, error_verdict)` for the brief's target repo."""
    repo, err = target_repo(brief)
    if repo is None:
        return [], [], {"ok": False, "rules": "unknown", "failed": [], "remedy": [err], "checks": {}}
    found = layer_mod.read_layers(repo, plugin_roots, resolve_key)
    if found["issues"]:
        remedy = [f"fix the research rules declaration: {i}" for i in found["issues"]]
        return found["layers"], found["issues"], _verdict(False, found["layers"], remedy, {"issues": found["issues"]})
    return found["layers"], [], None


def projects_root(override=None) -> Path:
    """Transcript root: the override, else the harness config dir (`CLAUDE_CONFIG_DIR`, else home/.claude)."""
    if override:
        return Path(override)
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"


_WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}
_SHELL_TOOLS = {"Bash", "PowerShell"}
_TOKEN = r"(\"[^\"]*\"|'[^']*'|[^\s;&|<>()]+)"
_ASSIGN = re.compile(r"(?:^|[\s;&(])(\w+)=" + _TOKEN)
_FOR = re.compile(r"\bfor\s+(\w+)\s+in\s+([^;\n]+?)\s*;\s*do\b")
_CD = re.compile(r"(?:^|[\s;&(])cd\s+" + _TOKEN)
_SHELL_TARGETS = [
    re.compile(r"(?<![\d&])>>?\s*" + _TOKEN),
    re.compile(r"\btee\s+(?:-a\s+)?" + _TOKEN),
    re.compile(r"\b(?:cp|mv)\s+(?:-\S+\s+)*[^\s;&|]+\s+" + _TOKEN),
    re.compile(r"\b(?:Set-Content|Add-Content|Out-File)\s+(?:-(?:Path|FilePath|LiteralPath)\s+)?" + _TOKEN, re.I),
]
_VAR = re.compile(r"\$\{(\w+)\}|\$(\w+)")


def _unquote(token: str) -> str:
    return token[1:-1] if len(token) > 1 and token[0] == token[-1] and token[0] in "\"'" else token


def _shell_writes(command: str) -> list[str]:
    """Paths a shell command writes through a redirect, tee, cp/mv destination or *-Content/Out-File.

    Trap: scouts write their inventory with `printf > $D/A-inventory.md` and `cat >> ...` far more
    often than with Write, so a gate reading only Write calls finds no scout at all. Simple
    `NAME=value` assignments, `for v in a b; do` loop items and `cd` bases are expanded; anything
    subtler is left unexpanded and simply fails to match.
    """
    env = {name: _unquote(val) for name, val in _ASSIGN.findall(command)}
    loops = {var: items.split() for var, items in _FOR.findall(command)}
    bases = [_unquote(d) for d in _CD.findall(command)]
    out: list[str] = []
    for pattern in _SHELL_TARGETS:
        for raw in pattern.findall(command):
            target = _VAR.sub(lambda m: env.get(m.group(1) or m.group(2), m.group(0)), _unquote(raw))
            expanded = [target]
            for var, items in loops.items():
                if re.search(r"\$\{?" + var + r"\b", target):
                    expanded = [re.sub(r"\$\{" + var + r"\}|\$" + var + r"\b", item, t) for t in expanded for item in items]
            for t in expanded:
                out.append(t)
                if not re.match(r"^(?:[\\/~]|[A-Za-z]:)", t):
                    out += [f"{base.rstrip('/')}/{t}" for base in bases]
    return out


def _written_paths(path: Path) -> str:
    """Every file path the transcript's file-writing calls target, newline-joined: Write/Edit/MultiEdit
    `file_path`s plus the targets of Bash/PowerShell writes.

    Trap: the scout is the agent that WRITES `<chunk>-inventory.md`. Naming it is not enough: a
    specialist's prompt names the same inventory as its input, and scoring the specialist's calls
    instead of the scout's passes a run whose scouts never queried the index.
    """
    paths = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"tool_use"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                content = (rec.get("message") or {}).get("content") if isinstance(rec, dict) else None
                for block in content if isinstance(content, list) else []:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    args = block.get("input") or {}
                    if block.get("name") in _WRITE_TOOLS and isinstance(args.get("file_path"), str):
                        paths.append(args["file_path"])
                    elif block.get("name") in _SHELL_TOOLS and isinstance(args.get("command"), str):
                        paths += _shell_writes(args["command"])
    except OSError:
        pass
    return "\n".join(paths)


def _repo_name(name: str) -> str:
    """A project-rag repo argument or directory name, reduced to its machine-local key form."""
    name = name.strip().lower().replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return name.removeprefix("repos.").replace("-", "_")


def out_of_tree_repo(repo: "Path | None", cwd: "Path | None" = None) -> "str | None":
    """The `repo` argument project-rag calls need for `repo`, or None when the session already serves it.

    Trap: project-rag serves the session's own checkout by default; a call about another repo without
    `repo` answers not_found from the wrong index yet still looks like a compliant call.
    """
    if repo is None:
        return None
    here = (cwd or Path.cwd()).resolve()
    if here == repo or repo in here.parents:
        return None
    return repo.name


def _tool_counts(path: Path, wanted: set[str], repo: "str | None" = None) -> dict[str, int]:
    """Attempts per wanted tool name: every `tool_use` block counts, whatever its tool_result.

    With `repo` set (an out-of-tree target), only calls whose `repo` argument names it count.
    """
    counts: dict[str, int] = {}
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"tool_use"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                content = (rec.get("message") or {}).get("content") if isinstance(rec, dict) else None
                for block in content if isinstance(content, list) else []:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") in wanted:
                        arg = (block.get("input") or {}).get("repo")
                        if repo is not None and not (isinstance(arg, str) and _repo_name(arg) == _repo_name(repo)):
                            continue
                        counts[block["name"]] = counts.get(block["name"], 0) + 1
    except OSError:
        pass
    return counts


def _slashes(text: str) -> str:
    return text.replace("\\", "/").lower()


def chunk_transcript(chunk: str, scratch: Path, transcripts: list[tuple[Path, str]]) -> Path | None:
    """The newest transcript that writes `<scratch>/<chunk>-inventory.md`.

    A write may name the scratch dir absolutely or repo-relative, so its last two path components
    plus the leaf also match (a run dir's name carries a timestamp and hash).
    """
    leaf = f"/{chunk}-inventory.md".lower()
    real = scratch.resolve()
    needles = {
        _slashes(str(scratch)).rstrip("/") + leaf,
        _slashes(str(real)).rstrip("/") + leaf,
        f"/{real.parent.name}/{real.name}".lower() + leaf,
    }
    hits = [p for p, text in transcripts if any(n in text for n in needles)]
    return max(hits, key=lambda p: (p.stat().st_mtime, str(p)), default=None)


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _scratch_birth(scratch: Path) -> "float | None":
    """The oldest file mtime in the scratch dir, less a minute of clock slack; None when it holds none."""
    times = [_mtime(p) for p in scratch.iterdir() if p.is_file()] if scratch.is_dir() else []
    return min(times) - 60 if times else None


def gate_scout(brief: Path, scratch: Path, projects: Path, plugin_roots=None, resolve_key=None) -> dict:
    layers, _, refused = _resolve(brief, plugin_roots, resolve_key)
    if refused:
        return refused
    families = [(layer["plugin"], fam) for layer in layers for fam in layer["families"]]
    if not families:
        return _verdict(True, layers, checks={"reason": "no overlay applies or none declares scout tool families"})
    # A scout's transcript is written after the run's scratch files exist; skipping older transcripts
    # keeps the scan to this run's era instead of every subagent transcript on the box.
    since = _scratch_birth(scratch)
    transcripts = [
        (p, _slashes(_written_paths(p)))
        for p in sorted(projects.glob("*/*/subagents/**/*.jsonl"))
        if since is None or _mtime(p) >= since
    ]
    wanted = {t for _, fam in families for t in fam["tools"]}
    repo_arg = out_of_tree_repo(target_repo(brief)[0])
    chunks: dict[str, dict] = {}
    remedy: list[str] = []
    for chunk in CHUNKS:
        inventory = scratch / f"{chunk}-inventory.md"
        transcript = chunk_transcript(chunk, scratch, transcripts)
        if transcript is None and not inventory.is_file():
            continue
        if transcript is None:
            chunks[chunk] = {"transcript": None, "missing": ["no scout transcript names this chunk's inventory"]}
            remedy.append(f"Chunk {chunk}: no scout transcript found under {projects}; re-run its scout")
            continue
        counts = _tool_counts(transcript, wanted, repo_arg)
        short = []
        for plugin, fam in families:
            have = sum(counts.get(t, 0) for t in fam["tools"])
            if have < fam["min_calls"]:
                short.append({"plugin": plugin, "family": fam["name"], "calls": have, "min_calls": fam["min_calls"]})
        chunks[chunk] = {"transcript": str(transcript), "calls": counts, "short": short}
        if short:
            names = ", ".join(f"{s['family']} {s['calls']}/{s['min_calls']}" for s in short)
            on_repo = f" with repo={repo_arg!r}" if repo_arg else ""
            remedy.append(f"Chunk {chunk}: below the required tool calls ({names}); re-scout it using "
                          f"{', '.join(sorted(wanted))}{on_repo}")
    if not chunks:
        return _verdict(False, layers, [f"no chunk inventories or scout transcripts found for {scratch}"],
                        {"chunks": {}})
    failed = [c for c, info in chunks.items() if info.get("short") or info.get("missing")]
    return _verdict(not failed, layers, remedy, {"chunks": chunks}, failed)


def trailing_headings(text: str) -> list[str]:
    """Every level-2 heading outside code fences, in order."""
    heads, fenced = [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced and (m := _HEADING.match(line)):
            heads.append(m.group(1))
    return heads


def _canon(heading: str) -> str:
    return heading.strip().lstrip("#").strip().casefold()


def gate_synthesis(brief: Path, synthesis: Path, plugin_roots=None, resolve_key=None) -> dict:
    layers, _, refused = _resolve(brief, plugin_roots, resolve_key)
    if refused:
        return refused
    required: list[str] = []
    fill_headings: list[str] = []
    for layer in layers:
        required += [s for s in layer["synthesis_sections"] if _canon(s) not in map(_canon, required)]
        if layer["fill_request"]:
            fill_headings.append(layer["fill_request"]["heading"])
    if not required:
        return _verdict(True, layers, checks={"reason": "no overlay applies or none declares synthesis sections"})
    try:
        text = synthesis.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return _verdict(False, layers, [f"synthesis {synthesis} unreadable: {exc}"], {"synthesis": "unreadable"})
    heads = [_canon(h) for h in trailing_headings(text)]
    want = [_canon(s) for s in required]
    remedy = []
    missing_fill = [h for h in fill_headings if _canon(h) not in heads]
    if missing_fill:
        remedy.append(f"add the fill-request section {missing_fill[0]!r}: one row per question the overlay's "
                      "corpus could not answer, or a table with a single 'none' row")
    if heads[-len(want):] != want:
        remedy.append("end the synthesis with these `##` sections, in order: " + ", ".join(f"'## {s}'" for s in required))
    return _verdict(not remedy, layers, remedy, {"required": required, "found_trailing": heads[-len(want):]},
                    [] if not remedy else ["synthesis"])


def render_brief(stage: str, brief: Path, plugin_roots=None, resolve_key=None) -> str:
    role = layer_mod.STAGE_ALIASES.get(stage, stage)
    repo, _ = target_repo(brief)
    layers = layer_mod.read_layers(repo or Path.cwd(), plugin_roots, resolve_key)["layers"]
    if not layers:
        return "rules: none\n"
    out: list[str] = []
    tools: list[str] = []
    for layer in layers:
        rules = layer["stages"].get(role)
        out.append(f"## Research rules from {layer['plugin']} (stage {role})")
        if rules:
            try:
                out.append(Path(rules).read_text(encoding="utf-8").strip())
            except OSError as exc:
                out.append(f"(rules file {rules} unreadable: {exc})")
        else:
            out.append("(no stage-specific rules)")
        tools += [t for t in layer["required_tools"] if t not in tools]
    if tools:
        out.append("required_tools: " + ", ".join(tools))
        repo_arg = out_of_tree_repo(repo)
        if repo_arg:
            out.append(f"repo: {repo_arg} -- pass repo=\"{repo_arg}\" on every required_tools call; without it "
                       "project-rag answers from this session's own checkout, and the tool gate counts only "
                       "calls that name the target repo.")
        out.append(layer_mod.GREP_LINE)
    return "\n\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("brief", "scout", "synthesis"):
        p = sub.add_parser(name)
        p.add_argument("--brief", required=True, help="the brief file: scope.md (scout, synthesis, later stages)")
        p.add_argument("--plugin-root", action="append", default=[])
        if name == "brief":
            p.add_argument("--stage", required=True)
        if name == "scout":
            p.add_argument("--scratch", required=True)
            p.add_argument("--projects-root")
        if name == "synthesis":
            p.add_argument("--synthesis", required=True)
    args = ap.parse_args(argv)
    roots = layer_mod.installed_plugin_roots(args.plugin_root)
    brief = Path(args.brief)
    if args.cmd == "brief":
        sys.stdout.write(render_brief(args.stage, brief, roots))
        return 0
    if args.cmd == "scout":
        verdict = gate_scout(brief, Path(args.scratch), projects_root(args.projects_root), roots)
    else:
        verdict = gate_synthesis(brief, Path(args.synthesis), roots)
    sys.stdout.write(json.dumps(verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
