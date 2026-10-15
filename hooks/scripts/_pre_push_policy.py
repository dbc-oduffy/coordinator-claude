"""Pre-push policy: a repo's pre-push hook, and everything it execs, runs no test runner, and runs git-lfs only when the repo justifies LFS.

Rule token: PRE-PUSH-RUNS-NO-TESTS-AND-NO-LFS. Tests run at merge to main, never at push.
A repo justifies LFS when its root ``.gitattributes`` routes at least one pattern through ``filter=lfs``
AND carries a line ``# lfs-justification: <non-empty reason>``; git-lfs in a pre-push closure without both
is a violation. A test runner is a violation in every repo, justified LFS or not.
In an LFS repo (root ``.gitattributes`` has a ``filter=lfs`` pattern) the closure must also exec
``git lfs pre-push``; a custom hook that never does sends pointers only, and is a violation whether or
not LFS is justified. A closure that execs it in a repo that justifies LFS reads ``allowed``
(``justified-lfs``). Two limits: detection reads the root ``.gitattributes`` only (nested
``.gitattributes`` and ``.git/info/attributes`` are not seen), and ``allowed`` for justified LFS does
not vouch for other unlisted work in the same hook.

The scan matches invocations, not prose: Python members are read with ``ast`` (call arguments,
list/tuple literals, imports), shell and JS members line by line with comment lines stripped.
Any hook whose closure matches no ALLOWED entry is ``unclassified``, which counts as a violation.

Stdlib only, zero subprocess (every answer is a file read). The ``_`` prefix keeps this module out
of the hook population census.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MAX_DEPTH = 4  # how many exec/import hops from the hook the closure follows
MAX_FILES = 64  # how many closure members are read before the verdict goes unclassified
_MAX_BYTES = 1_000_000  # larger files are not read; they surface as an unread-member reason

#: Which invocation shapes are forbidden on a push path; each is (name, regex over one command string).
DENIED_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pytest", re.compile(r"(?<![\w.-])pytest(?![\w-])")),
    ("python -m unittest", re.compile(r"-m\s+unittest(?![\w-])")),
    ("tox/nox", re.compile(r"(?<![\w.-])(?:tox|nox)(?![\w-])")),
    ("package-manager test", re.compile(r"(?<![\w.-])(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?test(?![\w-])")),
    ("js test runner", re.compile(r"(?<![\w.-])(?:vitest|jest|mocha)(?![\w-])")),
    ("node --test", re.compile(r"(?<![\w.-])node\s+(?:-\S+\s+)*--test(?![\w-])")),
    ("git-lfs", re.compile(r"(?<![\w.-])git(?:\s+|-)lfs(?![\w-])")),
    ("coordinator-lfs-gate", re.compile(r"coordinator-lfs-gate")),
)

#: Which cheap static checks may sit on a push path: (name, closure-member path suffix, content marker).
#: A ``.py`` member's marker must appear in its module docstring; for any other member it may appear in
#: any closure member's text (the installed hook carries the sentinel block, not the checker).
ALLOWED: tuple[tuple[str, str, str], ...] = (
    ("size-guard", "bin/pre_push_size_guard.py", "size guard"),
    ("sdk-closure", "scripts/check-sdk-closure.mjs", "sdk-closure-guard"),
)

_LFS_SHAPES = frozenset({"git-lfs", "coordinator-lfs-gate"})
_LFS_PATTERN_RE = re.compile(r"(?<![\w-])filter\s*=\s*lfs(?![\w-])")
_LFS_JUSTIFICATION_RE = re.compile(r"^\s*#\s*lfs-justification:\s*(\S.*?)\s*$", re.IGNORECASE)
_LFS_PRE_PUSH_RE = re.compile(r"(?<![\w.-])git(?:\s+|-)lfs\s+pre-push(?![\w-])")

LFS_PRE_PUSH_MISSING = (
    "custom pre-push hook in an LFS repo never execs `git lfs pre-push`: pushes send LFS pointers only; "
    'exec `git lfs pre-push "$@"` from the hook and justify LFS in .gitattributes, '
    "or drop the filter=lfs patterns"
)


def _attr_lines(repo_root: Path) -> list[str]:
    return (_read(repo_root / ".gitattributes") or "").splitlines()


def _lfs_repo(repo_root: Path) -> bool:
    """True when the root ``.gitattributes`` has a non-comment ``filter=lfs`` pattern."""
    return any(not ln.lstrip().startswith("#") and _LFS_PATTERN_RE.search(ln) for ln in _attr_lines(repo_root))


def _lfs_finding(repo_root: Path) -> str | None:
    """None when the repo justifies LFS, else the finding text for an unjustified git-lfs hook."""
    lines = _attr_lines(repo_root)
    has_patterns = _lfs_repo(repo_root)
    has_reason = any(_LFS_JUSTIFICATION_RE.match(ln) for ln in lines)
    if has_patterns and has_reason:
        return None
    return (
        "git-lfs without LFS justification: justify LFS in .gitattributes "
        "(a filter=lfs pattern plus '# lfs-justification: <reason>') or drop it"
    )


@dataclass(frozen=True)
class Verdict:
    repo: Path
    hook: Path | None
    status: str
    reasons: tuple[str, ...]


# --- git config / hook resolution -------------------------------------------------------------

_SECTION_RE = re.compile(r"^\s*\[\s*([A-Za-z0-9.-]+)(?:\s+\"[^\"]*\")?\s*\]")
_KV_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9-]*)\s*=\s*(.*?)\s*$")


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > _MAX_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _parse_git_config(path: Path) -> tuple[str | None, bool]:
    """Return ``(core.hooksPath, has_include)`` for one git config file; (None, False) if unreadable."""
    text = _read(path)
    if text is None:
        return None, False
    section = ""
    hooks_path: str | None = None
    has_include = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        m = _SECTION_RE.match(line)
        if m:
            section = m.group(1).lower()
            if section in ("include", "includeif"):
                has_include = True
            continue
        kv = _KV_RE.match(line)
        if kv and section == "core" and kv.group(1).lower() == "hookspath":
            value = re.split(r"\s[#;]", kv.group(2), maxsplit=1)[0].strip()
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = value[1:-1]
            hooks_path = value or None
    return hooks_path, has_include


def _git_dir(repo_root: Path) -> Path | None:
    dot_git = repo_root / ".git"
    if dot_git.is_dir():
        return dot_git
    if dot_git.is_file():
        text = _read(dot_git) or ""
        for line in text.splitlines():
            if line.lower().startswith("gitdir:"):
                target = Path(line.split(":", 1)[1].strip())
                return target if target.is_absolute() else (repo_root / target).resolve()
    return None


def _common_dir(git_dir: Path) -> Path:
    """A linked worktree's config and hooks live in its common dir."""
    text = _read(git_dir / "commondir")
    if text and text.strip():
        target = Path(text.strip())
        return target if target.is_absolute() else (git_dir / target).resolve()
    return git_dir


def _global_configs() -> list[Path]:
    home = os.path.expanduser("~")
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    return [Path(xdg) / "git" / "config", Path(home) / ".gitconfig"]  # ascending git precedence: last wins


def _hooks_dir(repo_root: Path) -> tuple[Path | None, list[str]]:
    """The effective hooks dir and any reasons the config could not be trusted."""
    git_dir = _git_dir(repo_root)
    if git_dir is None:
        return None, []
    common = _common_dir(git_dir)
    reasons: list[str] = []
    hooks_path, local_include = _parse_git_config(common / "config")
    if local_include:
        reasons.append(f"{common / 'config'}:1: config uses include/includeIf (not followed)")
    if hooks_path is None:
        for cfg in _global_configs():
            value, has_include = _parse_git_config(cfg)
            if has_include:
                reasons.append(f"{cfg}:1: config uses include/includeIf (not followed)")
            if value is not None:
                hooks_path = value
    if hooks_path is None:
        return common / "hooks", reasons
    expanded = Path(os.path.expanduser(hooks_path))
    return (expanded if expanded.is_absolute() else repo_root / expanded), reasons


def resolve_pre_push(repo_root: Path) -> Path | None:
    """The repo's ``pre-push`` hook file per git-dir, ``core.hooksPath`` and global config, else None."""
    hooks_dir, _ = _hooks_dir(repo_root)
    if hooks_dir is None:
        return None
    hook = hooks_dir / "pre-push"
    return hook if hook.is_file() else None


# --- exec closure -----------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[^\s'\"`;|&()<>=,{}\[\]]+")
#: Which named files are data, never executed: lockfiles, configs and docs a hook may read but not run.
_DATA_SUFFIXES = frozenset({".json", ".yaml", ".yml", ".toml", ".lock", ".md", ".txt", ".cfg", ".ini"})
_VAR_PREFIX_RE = re.compile(r"^\$\{?\w+\}?")


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _path_targets(text: str, member: Path, repo_root: Path) -> list[Path]:
    found: list[Path] = []
    for tok in _TOKEN_RE.findall(text):
        cands = {tok, _VAR_PREFIX_RE.sub("", tok), tok.lstrip("/"), _VAR_PREFIX_RE.sub("", tok).lstrip("/")}
        for cand in cands:
            if not cand or cand in (".", ".."):
                continue
            for base in (repo_root, member.parent):
                try:
                    p = Path(cand) if Path(cand).is_absolute() else base / cand
                    if p.suffix.lower() in _DATA_SUFFIXES or p.name.endswith("-lock.yaml"):
                        continue
                    if p.is_file() and _under(p, repo_root):
                        found.append(p.resolve())
                except (OSError, ValueError):
                    continue
    return found


def _module_files(parts: list[str], search_dirs: list[Path], repo_root: Path) -> list[Path]:
    found: list[Path] = []
    for base in search_dirs:
        target = base.joinpath(*parts)
        for cand in (target.with_suffix(".py"), target / "__init__.py"):
            if cand.is_file() and _under(cand, repo_root):
                found.append(cand.resolve())
    return found


def _import_targets(tree: ast.AST, member: Path, repo_root: Path) -> list[Path]:
    dirs: list[Path] = []
    cur = member.resolve().parent
    root = repo_root.resolve()
    while True:
        dirs.append(cur)
        if cur == root or root not in cur.parents:
            break
        cur = cur.parent
    if root not in dirs:
        dirs.append(root)
    found: list[Path] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found += _module_files(alias.name.split("."), dirs, repo_root)
        elif isinstance(node, ast.ImportFrom):
            base_dirs = dirs
            if node.level:
                anchor = member.resolve().parent
                for _ in range(node.level - 1):
                    anchor = anchor.parent
                base_dirs = [anchor]
            mod = node.module.split(".") if node.module else []
            if mod:
                found += _module_files(mod, base_dirs, repo_root)
            for alias in node.names:
                found += _module_files(mod + [alias.name], base_dirs, repo_root)
    return found


def _is_python(path: Path, text: str) -> bool:
    return path.suffix == ".py" or text.startswith("#!") and "python" in text.split("\n", 1)[0]


def _str_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return None


def _python_strings(tree: ast.AST) -> list[tuple[int, str]]:
    """String payloads of call arguments and list/tuple literals; docstrings and comments never appear."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for arg in [*node.args, *(k.value for k in node.keywords)]:
                s = _str_value(arg)
                if s is not None:
                    out.append((arg.lineno, s))
        elif isinstance(node, (ast.List, ast.Tuple)):
            parts = [_str_value(e) for e in node.elts]
            if any(p is not None for p in parts):
                out.append((node.lineno, " ".join("_" if p is None else p for p in parts)))
    return out


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def _hits_in(text: str) -> list[str]:
    return [name for name, rx in DENIED_SHAPES if rx.search(text)]


def _strip_comments(text: str) -> list[tuple[int, str]]:
    lines = []
    for n, line in enumerate(text.splitlines(), 1):
        s = line.lstrip()
        if s.startswith(("#", "//", "/*", "*")) and not s.startswith("#!"):
            continue
        lines.append((n, line))
    return lines


@dataclass
class _Scan:
    hits: list[tuple[int, str]]
    targets: list[Path]
    docstring: str
    text: str
    lfs_pre_push: bool = False


def _scan(path: Path, repo_root: Path) -> _Scan | None:
    text = _read(path)
    if text is None:
        return None
    if _is_python(path, text):
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            tree = None
        if tree is not None:
            hits: list[tuple[int, str]] = []
            targets: list[Path] = []
            lfs_pp = False
            for lineno, s in _python_strings(tree):
                lfs_pp = lfs_pp or bool(_LFS_PRE_PUSH_RE.search(s))
                hits += [(lineno, h) for h in _hits_in(s)]
                targets += _path_targets(s, path, repo_root)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "pytest" for a in node.names):
                    hits.append((node.lineno, "import pytest"))
                elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "pytest":
                    hits.append((node.lineno, "import pytest"))
                elif isinstance(node, ast.Call) and _dotted(node.func).startswith("pytest."):
                    hits.append((node.lineno, "pytest.main"))
            targets += _import_targets(tree, path, repo_root)
            return _Scan(hits, targets, ast.get_docstring(tree) or "", text, lfs_pp)
    hits = [(n, h) for n, line in _strip_comments(text) for h in _hits_in(line)]
    targets = _path_targets("\n".join(line for _, line in _strip_comments(text)), path, repo_root)
    lfs_pp = any(_LFS_PRE_PUSH_RE.search(line) for _, line in _strip_comments(text))
    return _Scan(hits, targets, "", text, lfs_pp)


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def exec_closure(hook: Path, repo_root: Path) -> list[Path]:
    """The hook plus the repo-local files it execs or imports, bounded by MAX_DEPTH and MAX_FILES."""
    return _closure(hook, repo_root)[0]


def _closure(hook: Path, repo_root: Path) -> tuple[list[Path], dict[Path, _Scan], list[str]]:
    scans: dict[Path, _Scan] = {}
    reasons: list[str] = []
    order: list[Path] = []
    seen = {hook.resolve()}
    frontier = [hook]
    depth = 0
    while frontier:
        nxt: list[Path] = []
        for member in frontier:
            order.append(member)
            scan = _scan(member, repo_root)
            if scan is None:
                reasons.append(f"{_rel(member, repo_root)}:1: closure member unreadable or over size limit")
                continue
            scans[member] = scan
            for target in scan.targets:
                if target in seen:
                    continue
                if depth + 1 > MAX_DEPTH:
                    reasons.append(f"{_rel(member, repo_root)}:1: closure bound: depth > {MAX_DEPTH}")
                    break
                if len(seen) >= MAX_FILES:
                    reasons.append(f"{_rel(member, repo_root)}:1: closure bound: more than {MAX_FILES} files")
                    break
                seen.add(target)
                nxt.append(target)
        frontier = nxt
        depth += 1
    return order, scans, list(dict.fromkeys(reasons))


# --- verdicts ---------------------------------------------------------------------------------


def _allowed_name(scans: dict[Path, _Scan], repo_root: Path) -> str | None:
    for name, suffix, marker in ALLOWED:
        for path, scan in scans.items():
            if _rel(path, repo_root).endswith(suffix):
                if path.suffix == ".py":
                    haystack = scan.docstring
                else:
                    haystack = "\n".join(s.text for s in scans.values())
                if marker.lower() in haystack.lower():
                    return name
    return None


def classify(repo_root: Path) -> Verdict:
    """Classify one repo's pre-push hook as none, allowed, violation or unclassified."""
    hooks_dir, config_reasons = _hooks_dir(repo_root)
    hook = hooks_dir / "pre-push" if hooks_dir is not None else None
    if hook is not None and not hook.is_file():
        hook = None
    if hook is None:
        status = "unclassified" if config_reasons else "none"
        return Verdict(repo_root, None, status, tuple(config_reasons))
    _, scans, bound_reasons = _closure(hook, repo_root)
    lfs_finding = _lfs_finding(repo_root)
    violations = [
        f"{_rel(path, repo_root)}:{line}: {lfs_finding if shape in _LFS_SHAPES and lfs_finding else shape}"
        for path, scan in scans.items()
        for line, shape in scan.hits
        if not (shape in _LFS_SHAPES and lfs_finding is None)
    ]
    has_lfs_pre_push = any(s.lfs_pre_push for s in scans.values())
    if _lfs_repo(repo_root) and not bound_reasons and not has_lfs_pre_push:
        violations.append(f"{_rel(hook, repo_root)}:1: {LFS_PRE_PUSH_MISSING}")
    if violations:
        return Verdict(repo_root, hook, "violation", tuple(violations))
    untrusted = [*config_reasons, *bound_reasons]
    if untrusted:
        return Verdict(repo_root, hook, "unclassified", tuple(untrusted))
    name = _allowed_name(scans, repo_root)
    if name:
        return Verdict(repo_root, hook, "allowed", (f"{_rel(hook, repo_root)}:1: allowlisted {name}",))
    if has_lfs_pre_push and _lfs_finding(repo_root) is None:
        return Verdict(repo_root, hook, "allowed", (f"{_rel(hook, repo_root)}:1: allowlisted justified-lfs",))
    return Verdict(
        repo_root, hook, "unclassified", (f"{_rel(hook, repo_root)}:1: no allowlisted check in closure",)
    )


# --- fleet ------------------------------------------------------------------------------------

_MIRROR_RE = re.compile(r"^publish\.mirrors\.[^.]+\.path$")


def fleet_repos() -> dict[str, Path]:
    """Registered ``repos.*`` and ``publish.mirrors.*.path`` roots, deduplicated by resolved path."""
    import tomllib

    from _engine_root import _flatten_registry, _settings_home_registry_dir

    reg_dir = _settings_home_registry_dir()
    out: dict[str, Path] = {}
    seen: set[Path] = set()
    for name in ("registry.local.toml", "registry.toml"):
        try:
            with (reg_dir / name).open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        for key, value in _flatten_registry(data).items():
            if not (key.startswith("repos.") or _MIRROR_RE.match(key)):
                continue
            if not isinstance(value, str) or not value.strip():
                continue
            try:
                resolved = Path(value).resolve()
            except OSError:
                continue
            if resolved in seen or key in out:
                continue
            seen.add(resolved)
            out[key] = Path(value)
    return out


def sweep(repos: dict[str, Path] | None = None) -> list[Verdict]:
    """Classify every fleet repo."""
    return [classify(root) for root in (fleet_repos() if repos is None else repos).values()]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--sweep" not in args:
        print("usage: _pre_push_policy.py --sweep", file=sys.stderr)
        return 2
    verdicts = sweep()
    bad = 0
    for v in verdicts:
        if v.status == "none":
            continue
        if v.status in ("violation", "unclassified"):
            bad += 1
        extra = f" (+{len(v.reasons) - 1} more)" if len(v.reasons) > 1 else ""
        print(f"{v.repo}: {v.status}: {v.reasons[0] if v.reasons else ''}{extra}")
    print(f"pre-push fleet sweep: {bad} violations, {len(verdicts)} repos scanned")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
