#!/usr/bin/env python3
"""Generate a ranked repository map for LLM context injection.

Parses git-tracked files using tree-sitter (TypeScript, TSX, JSX, Python, C++)
with stdlib fallbacks (Markdown, JSON, Shell). Builds a cross-file reference
graph, ranks files by PageRank centrality + git activity, and renders a
token-budgeted Markdown map.

Supports .repomapignore for project-specific exclusions, task-scoped maps
with --task/--focus-files for contextual narrowing, and UE project detection
with regex-based C++ parsing for UCLASS/USTRUCT/UFUNCTION signatures,
include-graph centrality, and dual-parse mode (regex defs + tree-sitter refs).
"""

import argparse
import ast
import fnmatch
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# tree-sitter (optional — graceful fallback to stdlib parsers)
_TS_AVAILABLE = False
try:
    from tree_sitter import Query, QueryCursor
    from tree_sitter_language_pack import get_language, get_parser
    _TS_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# File filtering
# ---------------------------------------------------------------------------

MAX_LINES_FOR_PARSING = 10_000

# Scoring profiles for different repo types.
# Each profile specifies weights for score components and a centrality cap.
# "infra" mirrors the original hardcoded weights (git activity heavy).
# "code" emphasizes structural centrality for code-heavy repos.
# "balanced" is the new default — blends both signals.
SCORING_PROFILES = {
    "infra": {
        "recency": 0.35, "frequency": 0.25, "centrality": 0.30,
        "size_inv": 0.10, "centrality_cap": 0.40,
    },
    "code": {
        "recency": 0.10, "frequency": 0.10, "centrality": 0.65,
        "size_inv": 0.15, "centrality_cap": 0.80,
    },
    "balanced": {
        "recency": 0.20, "frequency": 0.15, "centrality": 0.50,
        "size_inv": 0.15, "centrality_cap": 0.65,
    },
}

EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "build", "dist"}

# High-signal files that should appear near the top of the map regardless of
# git recency.  Inspired by Aider's filter_important_files() but focused on
# what a dispatched LLM agent most needs to orient itself.

# Files that are only important at the repo root — not nested copies.
# e.g., README.md is important at root but not docs/foo/README.md.
ROOT_ONLY_IMPORTANT = {
    "README.md", "README", "README.rst", "README.txt",
    "CLAUDE.md", "ARCHITECTURE.md", "CONTRIBUTING.md",
}

IMPORTANT_FILES = {
    # Build / packaging
    "pyproject.toml", "setup.py", "setup.cfg", "package.json",
    "Cargo.toml", "go.mod", "Makefile", "CMakeLists.txt",
    # Containerisation
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    # CI / CD
    ".github/workflows",  # prefix match handled in is_important_file()
    # Config / environment
    ".env.example", ".gitignore",
}

# UE-specific important file patterns (glob syntax, checked when UE mode active)
UE_IMPORTANT_PATTERNS = {
    "Source/*/DIRECTORY.md",
    "Source/*/*.Build.cs",
}


def load_repomapignore(project_root: Path) -> list[str]:
    """Load .repomapignore patterns from project root."""
    ignore_path = project_root / ".repomapignore"
    if not ignore_path.exists():
        return []
    patterns = []
    for line in ignore_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def filter_repomapignore(files: list[str], patterns: list[str]) -> list[str]:
    """Filter files using .repomapignore patterns.

    Supports:
    - Directory patterns (trailing /): "vendor/" matches "vendor/foo/bar.py"
    - Glob patterns: "*.jsonl" matches any .jsonl file
    - Basename matching: "fix_*.py" matches "fix_something.py" at any depth
    """
    if not patterns:
        return files

    def is_ignored(rel_path: str) -> bool:
        # Normalize to forward slashes for consistent matching
        normalized = rel_path.replace("\\", "/")
        for pattern in patterns:
            # Directory pattern: "vendor/" matches any file under vendor/
            if pattern.endswith("/"):
                prefix = pattern.rstrip("/")
                if "*" in prefix or "?" in prefix:
                    # Glob-style directory pattern: match each path component prefix
                    # e.g., "control/plugin/*/Packaged/" matches
                    #        "control/plugin/Foo/Packaged/bar.cpp"
                    parts = normalized.split("/")
                    prefix_parts = prefix.split("/")
                    n = len(prefix_parts)
                    for i in range(len(parts) - n + 1):
                        segment = "/".join(parts[i : i + n])
                        if fnmatch.fnmatch(segment, prefix):
                            return True
                else:
                    if normalized.startswith(prefix + "/") or normalized == prefix:
                        return True
            # Glob pattern — match against full path and basename
            elif fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(
                os.path.basename(normalized), pattern
            ):
                return True
        return False

    return [f for f in files if not is_ignored(f)]


def is_important_file(rel_path: str, ue_mode: bool = False) -> bool:
    """Check if a file is high-signal infrastructure worth surfacing early.

    When ue_mode is True, also matches UE-specific patterns (*.uproject at root,
    Source/*/DIRECTORY.md, Source/*/*.Build.cs).
    """
    name = os.path.basename(rel_path)
    # Root-only files: only important when at the repo root (no path separator)
    if name in ROOT_ONLY_IMPORTANT:
        return "/" not in rel_path and "\\" not in rel_path
    if name in IMPORTANT_FILES:
        return True
    # Prefix matches for directory-scoped patterns
    for pattern in IMPORTANT_FILES:
        if rel_path.startswith(pattern):
            return True
    # UE-specific patterns
    if ue_mode:
        norm = rel_path.replace("\\", "/")
        # .uproject at root only
        if "/" not in norm and norm.endswith(".uproject"):
            return True
        for pattern in UE_IMPORTANT_PATTERNS:
            if fnmatch.fnmatch(norm, pattern):
                return True
    return False


def _apply_profile_injection(
    ranked: list[str], profile: str, ue_mode: bool,
) -> list[str]:
    """Reorder ranked files based on profile's important-file injection policy.

    - infra: all important files front-injected
    - balanced: root-level orientation files only (README, CLAUDE.md, etc.)
    - code: no injection — pure score-based ranking
    """
    if profile == "infra":
        important = [f for f in ranked if is_important_file(f, ue_mode)]
        rest = [f for f in ranked if not is_important_file(f, ue_mode)]
        return important + rest
    elif profile == "balanced":
        root_orient = [f for f in ranked
                       if os.path.basename(f) in ROOT_ONLY_IMPORTANT
                       and "/" not in f and "\\" not in f]
        rest = [f for f in ranked if f not in set(root_orient)]
        return root_orient + rest
    # profile == "code": no injection
    return ranked


def get_git_tracked_files(project_root: Path) -> list[str] | None:
    """Return list of git-tracked file paths relative to project_root, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return [f for f in result.stdout.strip().splitlines() if f]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def is_binary_file(path: Path) -> bool:
    """Check if a file is binary by attempting UTF-8 decode of its first 8KB."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        chunk.decode("utf-8")
        return False
    except (UnicodeDecodeError, OSError):
        return True


def count_lines(path: Path) -> int:
    """Count lines in a file. Returns 0 on error."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# UE project detection
# ---------------------------------------------------------------------------


def detect_ue_project(project_root: Path) -> bool:
    """Check for .uproject at project root (root-level only).

    Known limitation: Subdirectory .uproject files are not detected.
    """
    return any(project_root.glob("*.uproject"))


def detect_ue_api_macros(project_root: Path, files: list[str]) -> dict[str, str]:
    """Scan Source/*/*.Build.cs to find API export macros per module.

    Returns dict mapping source directory prefix (forward-slash) to API macro.
    E.g., {"Source/MyModule/": "MYMODULE_API"}
    """
    macros = {}
    for rel in files:
        norm = rel.replace("\\", "/")
        m = re.match(r"^Source/(\w+)/\w+\.Build\.cs$", norm)
        if m:
            module = m.group(1)
            macros[f"Source/{module}/"] = module.upper() + "_API"
    return macros


def get_api_macro_for_file(rel_path: str, module_macros: dict[str, str]) -> str | None:
    """Get the API export macro for a file based on its module directory."""
    norm = rel_path.replace("\\", "/")
    for prefix, macro in module_macros.items():
        if norm.startswith(prefix):
            return macro
    return None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def parse_python(path: Path) -> list[str]:
    """Extract structural info from a Python file using ast.parse."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        print(f"  warn: syntax error in {path}: {e}", file=sys.stderr)
        return []

    entries = []

    # Collect imports
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])

    # Collect top-level classes and functions with signatures
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(_unparse_safe(b) for b in node.bases)
            base_str = f"({bases})" if bases else ""
            entries.append(f"class {node.name}{base_str}")
            # Methods within the class
            for item in ast.iter_child_nodes(node):
                if isinstance(item, ast.FunctionDef) or isinstance(
                    item, ast.AsyncFunctionDef
                ):
                    sig = _format_func_sig(item)
                    entries.append(f"  {sig}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = _format_func_sig(node)
            entries.append(sig)

    if imports:
        entries.append(f"Imports: {', '.join(sorted(imports))}")

    return entries


def _unparse_safe(node) -> str:
    """Unparse an AST node to string, with fallback."""
    try:
        return ast.unparse(node)
    except Exception:
        return "..."


def _format_func_sig(node) -> str:
    """Format a function/async function definition signature."""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = []
    for arg in node.args.args:
        ann = f": {_unparse_safe(arg.annotation)}" if arg.annotation else ""
        args.append(f"{arg.arg}{ann}")
    returns = f" -> {_unparse_safe(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({', '.join(args)}){returns}"


def parse_markdown(path: Path) -> list[str]:
    """Extract headings and frontmatter key-value pairs from Markdown."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    entries = []
    lines = text.splitlines()

    # Frontmatter extraction (single-line key: value between --- fences)
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                # Extract key-value pairs from frontmatter
                for fm_line in lines[1:i]:
                    m = re.match(r"^([a-zA-Z_-]+):\s*(.+)$", fm_line)
                    if m:
                        key, value = m.group(1), m.group(2).strip().strip('"\'')
                        # Truncate long values
                        if len(value) > 80:
                            value = value[:77] + "..."
                        entries.append(f"{key}: {value}")
                break

    # Headings (h1-h3)
    for line in lines:
        m = re.match(r"^(#{1,3})\s+(.+)$", line)
        if m:
            entries.append(f"{'#' * len(m.group(1))} {m.group(2).strip()}")

    return entries


def parse_json_file(path: Path) -> list[str]:
    """Extract top-level keys and their value types from JSON."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []

    if not isinstance(data, dict):
        return [f"Root type: {type(data).__name__}"]

    entries = []
    for key, value in data.items():
        type_name = type(value).__name__
        if isinstance(value, list):
            type_name = f"list[{len(value)}]"
        elif isinstance(value, dict):
            type_name = f"dict[{len(value)} keys]"
        entries.append(f"{key}: {type_name}")

    return entries


def parse_shell(path: Path) -> list[str]:
    """Extract function definitions from shell scripts."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    entries = []
    for line in text.splitlines():
        # function name() or function name {
        m = re.match(r"^\s*function\s+(\w+)", line)
        if m:
            entries.append(f"function {m.group(1)}")
            continue
        # name() {
        m = re.match(r"^(\w+)\s*\(\)\s*\{", line)
        if m:
            entries.append(f"function {m.group(1)}")

    return entries


PARSERS = {
    ".py": parse_python,
    ".md": parse_markdown,
    ".json": parse_json_file,
    ".sh": parse_shell,
}


# ---------------------------------------------------------------------------
# UE C++ parser (regex-based state machine)
# ---------------------------------------------------------------------------


def parse_cpp_ue(path: Path, api_macro: str | None = None) -> list[str]:
    """Extract UE C++ structural info using regex-based two-line lookahead.

    Handles:
    - UCLASS() -> class Name (Parent)
    - USTRUCT() -> struct Name
    - UENUM() -> enum Name
    - UFUNCTION(BlueprintCallable) -> fn Name(params) -> ReturnType
    - DECLARE_DYNAMIC_MULTICAST_DELEGATE* -> delegate Name
    - UE_DECLARE_GAMEPLAY_TAG_EXTERN -> tag Name
    - Bare <MODULE>_API classes (no preceding macro)

    For .h files only — .cpp files return empty list (no redundant declarations).

    Args:
        path: Path to the source file.
        api_macro: Module-specific API macro (e.g., "MYPROJECT_API").
                   If None, matches any *_API pattern.
    """
    if path.suffix.lower() == ".cpp":
        return []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = text.splitlines()
    entries = []

    # Build API macro regex fragment
    api_pat = re.escape(api_macro) if api_macro else r"\w+_API"

    # Single-line construct patterns
    _re_delegate = re.compile(
        r"DECLARE_DYNAMIC_MULTICAST_DELEGATE\w*\(\s*(\w+)"
    )
    _re_gameplay_tag = re.compile(
        rf"(?:{api_pat}\s+)?UE_DECLARE_GAMEPLAY_TAG_EXTERN\(\s*(\w+)"
    )
    _re_bare_class = re.compile(
        rf"^class\s+{api_pat}\s+(\w+)"
    )

    # Macro detection patterns
    _re_uclass = re.compile(r"\bUCLASS\s*\(")
    _re_ustruct = re.compile(r"\bUSTRUCT\s*\(")
    _re_uenum = re.compile(r"\bUENUM\s*\(")
    _re_ufunction = re.compile(r"\bUFUNCTION\s*\(")

    # Declaration line patterns (applied on the line AFTER the macro)
    _re_class_decl = re.compile(
        rf"class\s+(?:{api_pat}\s+)?(\w+)(?:\s*:\s*public\s+(\w+))?"
    )
    _re_struct_decl = re.compile(
        rf"struct\s+(?:{api_pat}\s+)?(\w+)"
    )
    _re_enum_decl = re.compile(
        r"enum\s+class\s+(\w+)"
    )
    _re_func_decl = re.compile(
        r"^\s*(?:(?:static|virtual|inline|FORCEINLINE|UFUNCTION\(\))\s+)*"
        r"([\w:*&<>\s]+?)\s+"
        r"(\w+)\s*\("
        r"([^)]*)\)"
    )

    pending_macro: str | None = None
    pending_macro_text: str = ""
    prev_line_had_uclass_macro = False

    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ---------------------------------------------------------------
        # Single-line constructs (no state machine needed)
        # ---------------------------------------------------------------
        m = _re_delegate.search(stripped)
        if m:
            entries.append(f"delegate {m.group(1)}")
            i += 1
            prev_line_had_uclass_macro = False
            continue

        m = _re_gameplay_tag.search(stripped)
        if m:
            tag_name = m.group(1).replace("_", ".")
            entries.append(f"tag {tag_name}")
            i += 1
            prev_line_had_uclass_macro = False
            continue

        # ---------------------------------------------------------------
        # Pending macro: we are waiting for the declaration line
        # ---------------------------------------------------------------
        if pending_macro is not None:
            # Skip blank lines while waiting
            if not stripped:
                i += 1
                continue

            if pending_macro == "UCLASS":
                m = _re_class_decl.search(stripped)
                if m:
                    class_name = m.group(1)
                    parent = m.group(2)
                    if parent:
                        entries.append(f"class {class_name} ({parent})")
                    else:
                        entries.append(f"class {class_name}")
                pending_macro = None
                pending_macro_text = ""
                prev_line_had_uclass_macro = True
                i += 1
                continue

            elif pending_macro == "USTRUCT":
                m = _re_struct_decl.search(stripped)
                if m:
                    entries.append(f"struct {m.group(1)}")
                pending_macro = None
                pending_macro_text = ""
                prev_line_had_uclass_macro = False
                i += 1
                continue

            elif pending_macro == "UENUM":
                m = _re_enum_decl.search(stripped)
                if m:
                    entries.append(f"enum {m.group(1)}")
                pending_macro = None
                pending_macro_text = ""
                prev_line_had_uclass_macro = False
                i += 1
                continue

            elif pending_macro == "UFUNCTION":
                if "BlueprintCallable" in pending_macro_text or "BlueprintPure" in pending_macro_text:
                    m = _re_func_decl.match(line)
                    if m:
                        ret_type = m.group(1).strip()
                        func_name = m.group(2)
                        params = m.group(3).strip()
                        entries.append(f"fn {func_name}({params}) -> {ret_type}")
                    else:
                        # Simpler fallback: just extract the function name
                        m2 = re.search(r"(\w+)\s*\(", stripped)
                        if m2 and m2.group(1) not in {"UFUNCTION", "UCLASS", "USTRUCT", "UENUM"}:
                            entries.append(f"fn {m2.group(1)}(...)")
                pending_macro = None
                pending_macro_text = ""
                prev_line_had_uclass_macro = False
                i += 1
                continue

        # ---------------------------------------------------------------
        # Detect new macro openings
        # ---------------------------------------------------------------

        if _re_ufunction.search(stripped):
            macro_text = stripped
            j = i
            paren_idx = macro_text.index("(")
            while ")" not in macro_text[paren_idx:] and j + 1 < n:
                j += 1
                macro_text += " " + lines[j].strip()
            pending_macro = "UFUNCTION"
            pending_macro_text = macro_text
            prev_line_had_uclass_macro = False
            i = j + 1
            continue

        if _re_uclass.search(stripped):
            macro_text = stripped
            j = i
            open_count = macro_text.count("(") - macro_text.count(")")
            while open_count > 0 and j + 1 < n:
                j += 1
                macro_text += " " + lines[j].strip()
                open_count = macro_text.count("(") - macro_text.count(")")
            pending_macro = "UCLASS"
            pending_macro_text = macro_text
            prev_line_had_uclass_macro = False
            i = j + 1
            continue

        if _re_ustruct.search(stripped):
            pending_macro = "USTRUCT"
            pending_macro_text = stripped
            prev_line_had_uclass_macro = False
            i += 1
            continue

        if _re_uenum.search(stripped):
            pending_macro = "UENUM"
            pending_macro_text = stripped
            prev_line_had_uclass_macro = False
            i += 1
            continue

        # ---------------------------------------------------------------
        # Bare API-exported class (no preceding UCLASS macro)
        # ---------------------------------------------------------------
        if not prev_line_had_uclass_macro:
            m = _re_bare_class.match(stripped)
            if m:
                entries.append(f"class {m.group(1)}")

        prev_line_had_uclass_macro = False
        i += 1

    return entries


# ---------------------------------------------------------------------------
# tree-sitter enhanced parsing
# ---------------------------------------------------------------------------

# Extension to tree-sitter language name mapping
TS_LANG_MAP = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "cpp",  # Assume C++ for headers — tree-sitter-cpp handles C subset
    ".hpp": "cpp",
}

# Directory containing .scm query files
_QUERY_DIR = Path(__file__).parent / "treesitter-queries"


class TreeSitterParser:
    """tree-sitter based parser with stdlib fallback.

    Extracts both definitions and references from source files.
    Falls back to PARSERS dict when tree-sitter is unavailable or
    the language is not supported.
    """

    def __init__(self):
        self._parsers: dict[str, object] = {}  # lang -> tree_sitter.Parser
        self._queries: dict[str, object] = {}  # lang -> Query
        if _TS_AVAILABLE:
            self._load_queries()

    def _load_queries(self) -> None:
        """Load .scm query files for all supported languages."""
        if not _QUERY_DIR.is_dir():
            return
        for scm_file in _QUERY_DIR.glob("*.scm"):
            lang_name = scm_file.stem  # e.g., "python" from "python.scm"
            try:
                language = get_language(lang_name)
                query_source = scm_file.read_text(encoding="utf-8")
                query = Query(language, query_source)
                self._queries[lang_name] = query
                self._parsers[lang_name] = get_parser(lang_name)
            except (LookupError, Exception) as e:
                print(f"  warn: tree-sitter query load failed for {lang_name}: {e}",
                      file=sys.stderr)

    def parse(self, path: Path, ext: str) -> tuple[list[str], list[str]]:
        """Parse a file, returning (definitions, references).

        Uses tree-sitter if available for this language, otherwise falls
        back to stdlib parsers (which return definitions only, refs=[]).
        """
        lang_name = TS_LANG_MAP.get(ext)

        # Try tree-sitter path
        if _TS_AVAILABLE and lang_name and lang_name in self._queries:
            try:
                return self._parse_treesitter(path, lang_name)
            except Exception as e:
                print(f"  warn: tree-sitter parse failed for {path}: {e}",
                      file=sys.stderr)
                # Fall through to stdlib

        # Stdlib fallback — definitions only
        stdlib_parser = PARSERS.get(ext)
        if stdlib_parser:
            return (stdlib_parser(path), [])

        return ([], [])

    def parse_refs_only(self, path: Path, ext: str) -> list[str]:
        """Parse a file for references only (UE mode — defs come from regex parser).

        Returns references list. Falls back to empty list if tree-sitter unavailable.
        """
        lang_name = TS_LANG_MAP.get(ext)
        if not (_TS_AVAILABLE and lang_name and lang_name in self._queries):
            return []
        try:
            _, refs = self._parse_treesitter(path, lang_name)
            return refs
        except Exception:
            return []

    def _parse_treesitter(self, path: Path, lang_name: str) -> tuple[list[str], list[str]]:
        """Parse using tree-sitter. Returns (definitions, references)."""
        source_bytes = path.read_bytes()
        parser = self._parsers[lang_name]
        tree = parser.parse(source_bytes)
        query = self._queries[lang_name]

        cursor = QueryCursor(query)
        captures = cursor.captures(tree.root_node)
        # captures is dict[str, list[Node]] in tree-sitter 0.25.x

        defs = []
        refs = []

        for capture_name, nodes in captures.items():
            for node in nodes:
                text = node.text.decode("utf-8", errors="replace").strip()
                if not text:
                    continue

                if capture_name == "def.name":
                    defs.append(text)
                elif capture_name == "ref.name":
                    refs.append(text)

        return (defs, refs)


# ---------------------------------------------------------------------------
# Git-based ranking
# ---------------------------------------------------------------------------


def get_git_log_data(
    project_root: Path, files: list[str]
) -> dict[str, dict]:
    """Get git recency and frequency data for files.

    Returns dict mapping filepath to {last_change_days: float, commits_90d: int}.
    """
    now = datetime.now(timezone.utc)
    result = {}

    # Get last change date per file using a single git log call
    try:
        log_output = subprocess.run(
            [
                "git", "log", "--format=%H %aI", "--name-only",
                "--diff-filter=ACDMR", "--since=365 days ago",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if log_output.returncode != 0:
            return result
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return result

    file_set = set(files)
    last_change = {}
    commits_90d: dict[str, int] = {}
    current_date = None

    for line in log_output.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Commit line: hash + ISO date
        if " " in line and len(line.split()[0]) == 40:
            parts = line.split(" ", 1)
            try:
                current_date = datetime.fromisoformat(parts[1])
            except (ValueError, IndexError):
                current_date = None
            continue
        # File name line
        if line in file_set and current_date:
            if line not in last_change:
                last_change[line] = current_date
            days_ago = (now - current_date).total_seconds() / 86400
            if days_ago <= 90:
                commits_90d[line] = commits_90d.get(line, 0) + 1

    for f in files:
        days = 365.0  # default: old
        if f in last_change:
            days = max(0.0, (now - last_change[f]).total_seconds() / 86400)
        result[f] = {
            "last_change_days": days,
            "commits_90d": commits_90d.get(f, 0),
        }

    return result


def get_filesystem_ranking(project_root: Path, files: list[str]) -> dict[str, dict]:
    """Fallback ranking using filesystem modification time."""
    now = datetime.now(timezone.utc).timestamp()
    result = {}
    for f in files:
        p = project_root / f
        try:
            mtime = p.stat().st_mtime
            days = max(0.0, (now - mtime) / 86400)
        except OSError:
            days = 365.0
        result[f] = {"last_change_days": days, "commits_90d": 0}
    return result


def compute_scores(
    ranking_data: dict[str, dict],
    line_counts: dict[str, int],
    ref_centrality: dict[str, float] | None = None,
    profile: str = "balanced",
) -> dict[str, float]:
    """Compute composite score for each file using a named scoring profile.

    Profile weights are read from SCORING_PROFILES. With a reference graph,
    centrality is capped at profile["centrality_cap"] fraction of the total
    score to prevent centrality from dominating git-activity signals. Without
    a reference graph, centrality weight is redistributed proportionally among
    the remaining components.
    """
    p = SCORING_PROFILES[profile]
    use_refs = ref_centrality is not None and len(ref_centrality) > 0
    scores = {}

    for f, data in ranking_data.items():
        # Recency: exponential decay, half-life ~14 days
        recency = math.exp(-0.05 * data["last_change_days"])

        # Frequency: log-scaled commits in 90 days
        freq = math.log1p(data["commits_90d"]) / math.log1p(50)
        freq = min(freq, 1.0)

        # Size: inverse — smaller files score higher
        lines = line_counts.get(f, 100)
        size_inv = 1.0 / (1.0 + math.log1p(lines / 100))

        if use_refs:
            centrality = ref_centrality.get(f, 0.0)
            # Base score WITHOUT centrality
            base_score = (recency * p["recency"] + freq * p["frequency"]
                         + size_inv * p["size_inv"])
            # Centrality contribution, capped
            cap = p["centrality_cap"]
            centrality_part = centrality * p["centrality"]
            # Derived from: centrality_part / (base_score + centrality_part) <= cap
            max_centrality = base_score * (cap / (1.0 - cap))
            centrality_part = min(centrality_part, max_centrality)
            scores[f] = base_score + centrality_part
        else:
            # No reference graph — redistribute centrality weight proportionally
            non_cent = p["recency"] + p["frequency"] + p["size_inv"]
            if non_cent > 0:
                scores[f] = (recency * p["recency"] / non_cent
                            + freq * p["frequency"] / non_cent
                            + size_inv * p["size_inv"] / non_cent)
            else:
                scores[f] = 0.0

    return scores


# ---------------------------------------------------------------------------
# Cross-file reference graph
# ---------------------------------------------------------------------------


def _symbol_edge_weight(symbol: str, def_count: int) -> float:
    """Compute edge weight for a symbol reference.

    Long project-specific identifiers (camelCase/snake_case, 8+ chars) get
    boosted. Private symbols (underscore prefix) and generic/overloaded
    symbols (defined in 5+ files) get dampened. Multiple definitions split
    the weight via inverse square root.
    """
    weight = 1.0

    # Long identifiers with naming conventions = project-specific
    if (len(symbol) >= 8
        and symbol != symbol.upper()  # exclude ALL_CAPS_CONSTANTS
        and ("_" in symbol  # snake_case
             or any(c.isupper() for c in symbol[1:]))  # camelCase/PascalCase
    ):
        weight *= 10.0

    # Private symbols
    if symbol.startswith("_"):
        weight *= 0.1

    # Generic/overloaded symbols
    if def_count >= 5:
        weight *= 0.1

    # Multiple definitions: spread weight
    if def_count > 1:
        weight /= math.sqrt(def_count)

    return weight


def build_reference_graph(
    parsed_defs: dict[str, list[str]],
    parsed_refs: dict[str, list[str]],
) -> dict[str, dict[str, float]]:
    """Build file-to-file reference graph with weighted edges.

    Returns: {source_file: {target_file: weighted_edge_sum}}

    Algorithm:
    1. Build symbol -> defining files index from all definitions
    2. For each file's references, look up which file defines that symbol
    3. Create edge with weight computed by _symbol_edge_weight() — long
       project-specific identifiers contribute more than generic ones
    """
    # Symbol index: symbol_name -> list of defining files
    # Multiple files may define the same symbol (e.g., `main`, `setup`, `Config`)
    symbol_index: dict[str, list[str]] = {}
    for filepath, defs in parsed_defs.items():
        if not defs and not parsed_refs.get(filepath, []):
            continue  # No structural signal — don't add to graph
        for symbol in defs:
            symbol_index.setdefault(symbol, []).append(filepath)

    # Build weighted edges
    graph: dict[str, dict[str, float]] = {}
    for filepath, refs in parsed_refs.items():
        edges = graph.setdefault(filepath, {})
        for ref in refs:
            targets = symbol_index.get(ref, [])
            if not targets:
                continue
            w = _symbol_edge_weight(ref, len(targets))
            for target in targets:
                if target != filepath:  # No self-edges
                    edges[target] = edges.get(target, 0.0) + w

    return graph


def pagerank(
    graph: dict[str, dict[str, float]],
    damping: float = 0.85,
    iterations: int = 20,
) -> dict[str, float]:
    """Simplified PageRank on dict-based directed graph.

    Returns: {file: score} rank-normalized to (0, 1].
    Rank-based normalization distributes signal evenly across all files,
    avoiding collapse when one file is an extreme outlier.
    """
    # Collect all nodes (sources and targets)
    nodes = set(graph.keys())
    for targets in graph.values():
        nodes.update(targets.keys())

    n = len(nodes)
    if n == 0:
        return {}

    scores = {node: 1.0 / n for node in nodes}

    # Build reverse graph for efficient iteration
    in_edges: dict[str, list[tuple[str, float]]] = {node: [] for node in nodes}
    out_degree: dict[str, float] = {node: 0.0 for node in nodes}
    for src, targets in graph.items():
        total_weight = sum(targets.values())
        out_degree[src] = total_weight
        for tgt, weight in targets.items():
            in_edges[tgt].append((src, weight))

    for _ in range(iterations):
        new_scores = {}
        for node in nodes:
            rank_sum = sum(
                scores[src] * (weight / out_degree[src])
                for src, weight in in_edges[node]
                if out_degree[src] > 0
            )
            new_scores[node] = (1 - damping) / n + damping * rank_sum
        scores = new_scores

    # Rank-based normalization: convert absolute scores to rank percentiles
    sorted_nodes = sorted(scores.keys(), key=lambda nd: scores[nd])
    return {node: (rank + 1) / n for rank, node in enumerate(sorted_nodes)}


# ---------------------------------------------------------------------------
# Include graph centrality (UE projects)
# ---------------------------------------------------------------------------

_ENGINE_HEADER_PREFIXES = {
    "CoreMinimal.h",
    "Engine/",
    "Components/",
    "GameFramework/",
    "Kismet/",
    "UObject/",
    "Containers/",
    "Math/",
    "HAL/",
    "Misc/",
    "GameplayTagContainer.h",
    "Stats/Stats.h",
}


def _is_engine_header(include_path: str) -> bool:
    """Return True if this include is an engine/external header to skip."""
    for prefix in _ENGINE_HEADER_PREFIXES:
        if include_path == prefix or include_path.startswith(prefix):
            return True
    if include_path.endswith(".generated.h"):
        return True
    return False


def build_include_graph(project_root: Path, files: list[str]) -> dict[str, float]:
    """Build C++ include graph and return normalized in-degree centrality.

    Scans .h and .cpp files for #include "..." directives, resolves them to
    project-relative paths, and computes in-degree centrality in [0.0, 1.0].

    Resolution order:
    1. Path as-is relative to project_root (#include "FDM/DGFDMTypes.h")
    2. Relative to the including file's directory (#include "DGFDMTypes.h")
    3. Skip if neither resolves (engine/external header)
    """
    re_include = re.compile(r'#include\s+"([^"]+)"')
    file_set = {f.replace("\\", "/") for f in files}
    in_degree: dict[str, int] = {}

    for rel in files:
        ext = Path(rel).suffix.lower()
        if ext not in (".h", ".cpp"):
            continue

        full = project_root / rel
        if not full.is_file():
            continue

        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel_norm = rel.replace("\\", "/")
        rel_dir = str(Path(rel_norm).parent).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""

        for m in re_include.finditer(text):
            inc = m.group(1)
            if _is_engine_header(inc):
                continue

            # Resolution 1: as-is relative to project root
            candidate = inc.replace("\\", "/")
            if candidate in file_set:
                in_degree[candidate] = in_degree.get(candidate, 0) + 1
                continue

            # Resolution 2: relative to including file's directory
            if rel_dir:
                candidate2 = (rel_dir + "/" + inc).replace("\\", "/")
            else:
                candidate2 = inc.replace("\\", "/")
            try:
                candidate2 = str(Path(candidate2)).replace("\\", "/")
            except Exception:
                pass
            if candidate2 in file_set:
                in_degree[candidate2] = in_degree.get(candidate2, 0) + 1

    if not in_degree:
        return {}

    max_deg = max(in_degree.values())
    if max_deg == 0:
        return {}

    return {f: in_degree.get(f.replace("\\", "/"), 0) / max_deg for f in files}


def _blend_centralities(
    include_centrality: dict[str, float] | None,
    pagerank_centrality: dict[str, float] | None,
    all_files: list[str],
) -> dict[str, float] | None:
    """Blend include-graph and PageRank centrality via max() per file.

    Returns None if neither source has data. Otherwise returns a dict
    mapping each file to max(include_score, pagerank_score).
    """
    if not include_centrality and not pagerank_centrality:
        return None

    blended: dict[str, float] = {}
    for f in all_files:
        inc_v = include_centrality.get(f, 0.0) if include_centrality else 0.0
        pr_v = pagerank_centrality.get(f, 0.0) if pagerank_centrality else 0.0
        val = max(inc_v, pr_v)
        if val > 0:
            blended[f] = val

    return blended if blended else None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def file_content_hash(path: Path) -> str:
    """SHA-256 hash of file content."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def load_cache(cache_path: Path) -> dict:
    """Load parse cache from JSON file."""
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_cache(cache_path: Path, cache: dict):
    """Save parse cache atomically."""
    os.makedirs(cache_path.parent, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=cache_path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
        os.replace(tmp_path, cache_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Token budget fitting
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Estimate token count: word_count * 1.3."""
    return int(len(text.split()) * 1.3)


def render_file_entry(rel_path: str, entries: list[str], max_entries: int = 20) -> str:
    """Render a single file's map entry as Markdown.

    Caps at max_entries definitions per file at render time with (+N more) suffix.
    Full parse is preserved in cache for task-scoped maps with higher caps.
    """
    lines = [f"## {rel_path}"]
    if len(entries) > max_entries:
        for entry in entries[:max_entries]:
            lines.append(f"- {entry}")
        lines.append(f"- (+{len(entries) - max_entries} more)")
    else:
        for entry in entries:
            lines.append(f"- {entry}")
    return "\n".join(lines)


def budget_fit(
    ranked_files: list[tuple[str, list[str]]], budget: int
) -> list[tuple[str, list[str]]]:
    """Select files that fit within the token budget, in rank order.

    Uses iterative addition rather than binary search — simpler and adequate
    since we process in rank order and stop when full.
    """
    selected = []
    header = "# Repository Map\nGenerated: ... | Files: ... | Budget: ...\n\n"
    current_tokens = estimate_tokens(header)

    for rel_path, entries in ranked_files:
        entry_text = render_file_entry(rel_path, entries)
        entry_tokens = estimate_tokens(entry_text)

        # Allow ~30% overshoot on the last entry
        if current_tokens + entry_tokens > budget * 1.3 and selected:
            break

        selected.append((rel_path, entries))
        current_tokens += entry_tokens

    return selected


# ---------------------------------------------------------------------------
# Task-scoped selective loading
# ---------------------------------------------------------------------------


def compute_focus_boosts(
    focus_files: list[str],
    task_context: str,
    ref_graph: dict[str, dict[str, int]],
    all_files: list[str],
) -> dict[str, float]:
    """Compute score boost multipliers based on task focus.

    Boost tiers:
    - Files in focus_files: x5.0
    - Files 1-hop from focus_files in reference graph: x2.5
    - Files 2-hops from focus_files: x1.5
    - Files whose paths appear in task_context: x2.0
    - All other files: x1.0 (no boost)

    Boosts are multiplicative — a file that's both 1-hop and mentioned in
    task_context gets max(2.5, 2.0) = 2.5, not 2.5 * 2.0.
    """
    boosts: dict[str, float] = {}

    # Exact focus files
    focus_set = set(focus_files)
    for f in focus_files:
        boosts[f] = 5.0

    # Build reverse graph for backward walks
    reverse_graph: dict[str, set[str]] = {}
    for src, targets in ref_graph.items():
        for tgt in targets:
            reverse_graph.setdefault(tgt, set()).add(src)

    # 1-hop: files that import focus files (reverse) or are imported by focus files (forward)
    one_hop = set()
    for f in focus_set:
        # Forward: files that f references
        for tgt in ref_graph.get(f, {}):
            if tgt not in focus_set:
                one_hop.add(tgt)
        # Reverse: files that reference f
        for src in reverse_graph.get(f, set()):
            if src not in focus_set:
                one_hop.add(src)

    for f in one_hop:
        boosts[f] = max(boosts.get(f, 1.0), 2.5)

    # 2-hop: files one hop from 1-hop files
    two_hop = set()
    for f in one_hop:
        for tgt in ref_graph.get(f, {}):
            if tgt not in focus_set and tgt not in one_hop:
                two_hop.add(tgt)
        for src in reverse_graph.get(f, set()):
            if src not in focus_set and src not in one_hop:
                two_hop.add(src)

    for f in two_hop:
        boosts[f] = max(boosts.get(f, 1.0), 1.5)

    # Task context: extract path-like tokens and match against known files
    if task_context:
        path_tokens = re.findall(r'[\w/.\\-]+\.[\w]+', task_context)
        for token in path_tokens:
            # Normalize separators
            token_normalized = token.replace("\\", "/")
            for f in all_files:
                if token_normalized in f or f.endswith(token_normalized):
                    boosts[f] = max(boosts.get(f, 1.0), 2.0)

    return boosts


def generate_task_scoped_map(
    project_root: Path,
    budget: int,
    task_context: str,
    focus_files: list[str],
    cache_dir: Path,
    output_path: Path,
    profile: str = "balanced",
) -> None:
    """Generate a repo map scoped to a specific task step.

    Same pipeline as generate_repomap() but with score boosting based on
    task context and focus files. The reference graph enables neighborhood
    discovery — files structurally related to the focus files get boosted.
    """
    project_root = project_root.resolve()

    # Reuse the standard pipeline for steps 1-4
    git_files = get_git_tracked_files(project_root)
    is_git = git_files is not None

    if is_git:
        files = git_files
    else:
        files = []
        for root, dirs, filenames in os.walk(project_root):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for fn in filenames:
                full = Path(root) / fn
                rel = str(full.relative_to(project_root))
                files.append(rel)

    if not files:
        print("  warn: no files found", file=sys.stderr)
        return

    # Apply .repomapignore filtering
    ignore_patterns = load_repomapignore(project_root)
    if ignore_patterns:
        before = len(files)
        files = filter_repomapignore(files, ignore_patterns)
        print(
            f"  .repomapignore: {before - len(files)} files excluded, "
            f"{len(files)} remaining",
            file=sys.stderr,
        )

    # Filter
    valid_files = []
    line_counts = {}
    for rel in files:
        full = project_root / rel
        if full.is_symlink():
            valid_files.append(rel)
            line_counts[rel] = 0
            continue
        if not full.is_file():
            continue
        if is_binary_file(full):
            continue
        lc = count_lines(full)
        line_counts[rel] = lc
        valid_files.append(rel)

    # Detect UE project
    ue_mode = detect_ue_project(project_root)
    ue_module_macros: dict[str, str] = {}
    if ue_mode:
        ue_module_macros = detect_ue_api_macros(project_root, valid_files)

    # Parse (read-only on cache — piggybacks on standard map's cache, does not write)
    cache_path = cache_dir / "cache.json"
    cache = load_cache(cache_path)
    parsed_defs: dict[str, list[str]] = {}
    parsed_refs: dict[str, list[str]] = {}
    ts_parser = TreeSitterParser()

    for rel in valid_files:
        full = project_root / rel
        ext = full.suffix.lower()

        if full.is_symlink() or line_counts.get(rel, 0) > MAX_LINES_FOR_PARSING:
            parsed_defs[rel] = []
            parsed_refs[rel] = []
            continue

        has_parser = ext in TS_LANG_MAP or ext in PARSERS
        if not has_parser:
            parsed_defs[rel] = []
            parsed_refs[rel] = []
            continue

        content_hash = file_content_hash(full)
        # UE mode uses separate cache namespace
        cache_prefix = "ue:" if (ue_mode and ext in (".h", ".cpp")) else ""
        cache_key = f"{cache_prefix}{rel}:{content_hash}"

        if cache_key in cache and cache_key != "_version":
            cached = cache[cache_key]
            if isinstance(cached, dict) and "defs" in cached:
                defs, refs = cached["defs"], cached["refs"]
            else:
                defs, refs = (cached, []) if isinstance(cached, list) else ([], [])
        elif ue_mode and ext in (".h", ".cpp"):
            # UE mode: regex parser for defs, tree-sitter for refs only
            api_macro = get_api_macro_for_file(rel, ue_module_macros)
            defs = parse_cpp_ue(full, api_macro)
            refs = ts_parser.parse_refs_only(full, ext)
        else:
            defs, refs = ts_parser.parse(full, ext)

        parsed_defs[rel] = defs
        parsed_refs[rel] = refs

    # NOTE: No save_cache() call — task-scoped maps are read-only on the cache
    # to avoid clobbering entries from the standard map generation.

    # Build reference graph (tree-sitter symbol refs)
    ref_graph: dict[str, dict[str, float]] = {}
    pagerank_centrality = None
    if any(parsed_refs.values()):
        ref_graph = build_reference_graph(parsed_defs, parsed_refs)
        if ref_graph:
            pagerank_centrality = pagerank(ref_graph)

    # Include-graph centrality (UE projects)
    include_centrality = None
    if ue_mode:
        include_centrality = build_include_graph(project_root, valid_files)

    # Blend centralities
    blended_centrality = _blend_centralities(
        include_centrality, pagerank_centrality, valid_files
    )

    # Compute base scores
    if is_git:
        ranking_data = get_git_log_data(project_root, valid_files)
    else:
        ranking_data = get_filesystem_ranking(project_root, valid_files)

    scores = compute_scores(ranking_data, line_counts, blended_centrality, profile)

    # Apply focus boosts
    boosts = compute_focus_boosts(focus_files, task_context, ref_graph, valid_files)
    for f in scores:
        scores[f] *= boosts.get(f, 1.0)

    # Sort, budget-fit, render (same as standard)
    ranked = sorted(valid_files, key=lambda f: scores.get(f, 0), reverse=True)

    ranked = _apply_profile_injection(ranked, profile, ue_mode)

    ranked_with_entries = [(f, parsed_defs.get(f, [])) for f in ranked]
    selected = budget_fit(ranked_with_entries, budget)

    # Render with task-scoped header
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    focus_str = ", ".join(focus_files[:5])
    if len(focus_files) > 5:
        focus_str += f" (+{len(focus_files) - 5} more)"
    header = (
        f"# Repository Map (task-scoped)\n"
        f"Generated: {now_str} | Files: {len(selected)}/{len(valid_files)} | "
        f"Budget: {budget} tokens\n"
        f"Focus: {focus_str}\n"
    )

    sections = [header]
    for rel_path, entries in selected:
        sections.append(render_file_entry(rel_path, entries))

    output_text = "\n\n".join(sections) + "\n"

    os.makedirs(output_path.parent, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=output_path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(output_text)
        os.replace(tmp_path, output_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    boosted_count = sum(1 for b in boosts.values() if b > 1.0)
    actual_tokens = estimate_tokens(output_text)
    print(
        f"Task-scoped map written to {output_path}\n"
        f"  {len(selected)}/{len(valid_files)} files, ~{actual_tokens} tokens "
        f"(budget: {budget}), {boosted_count} files boosted"
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def generate_repomap(
    project_root: Path,
    budget: int,
    cache_dir: Path,
    output_path: Path,
    profile: str = "balanced",
) -> None:
    """Main entry point: parse, rank, budget-fit, render, write."""

    project_root = project_root.resolve()

    # 1. Get file list
    git_files = get_git_tracked_files(project_root)
    is_git = git_files is not None

    if is_git:
        files = git_files
    else:
        print("  info: not a git repo, using filesystem walk", file=sys.stderr)
        files = []
        for root, dirs, filenames in os.walk(project_root):
            # Prune excluded dirs
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for fn in filenames:
                full = Path(root) / fn
                rel = str(full.relative_to(project_root))
                files.append(rel)

    if not files:
        print("  warn: no files found", file=sys.stderr)
        return

    # 1b. Apply .repomapignore filtering
    ignore_patterns = load_repomapignore(project_root)
    if ignore_patterns:
        before = len(files)
        files = filter_repomapignore(files, ignore_patterns)
        print(
            f"  .repomapignore: {before - len(files)} files excluded, "
            f"{len(files)} remaining",
            file=sys.stderr,
        )

    # 2. Filter: skip binary, symlinks
    valid_files = []
    line_counts = {}
    for rel in files:
        full = project_root / rel
        if full.is_symlink():
            valid_files.append(rel)  # include by path only
            line_counts[rel] = 0
            continue
        if not full.is_file():
            continue
        if is_binary_file(full):
            continue
        lc = count_lines(full)
        line_counts[rel] = lc
        valid_files.append(rel)

    # 2b. Detect UE project
    ue_mode = detect_ue_project(project_root)
    ue_module_macros: dict[str, str] = {}
    if ue_mode:
        ue_module_macros = detect_ue_api_macros(project_root, valid_files)
        print(
            f"  UE project detected: {len(ue_module_macros)} module(s) "
            f"({', '.join(ue_module_macros.values())})",
            file=sys.stderr,
        )

    # 3. Parse files (with caching)
    cache_path = cache_dir / "cache.json"
    cache = load_cache(cache_path)
    new_cache = {}
    parsed_defs: dict[str, list[str]] = {}
    parsed_refs: dict[str, list[str]] = {}
    ts_parser = TreeSitterParser()

    # Cache version migration: v1 stored flat lists, v2 stores {defs, refs}
    cache_version = cache.get("_version", 1)

    for rel in valid_files:
        full = project_root / rel
        ext = full.suffix.lower()

        # Symlinks or very large files: path only
        if full.is_symlink() or line_counts.get(rel, 0) > MAX_LINES_FOR_PARSING:
            parsed_defs[rel] = []
            parsed_refs[rel] = []
            continue

        # Check if any parser can handle this extension
        has_parser = ext in TS_LANG_MAP or ext in PARSERS
        if not has_parser:
            parsed_defs[rel] = []
            parsed_refs[rel] = []
            continue

        content_hash = file_content_hash(full)
        # UE mode uses separate cache namespace to avoid stale defs from
        # tree-sitter being served when regex parser is expected
        cache_prefix = "ue:" if (ue_mode and ext in (".h", ".cpp")) else ""
        cache_key = f"{cache_prefix}{rel}:{content_hash}"

        if cache_key in cache and cache_key != "_version":
            cached = cache[cache_key]
            if isinstance(cached, dict) and "defs" in cached:
                # v2 cache entry
                defs, refs = cached["defs"], cached["refs"]
            else:
                # v1 cache entry (flat list) — treat as defs-only
                defs, refs = (cached, []) if isinstance(cached, list) else ([], [])
        elif ue_mode and ext in (".h", ".cpp"):
            # UE mode: regex parser for defs, tree-sitter for refs only.
            # Tree-sitter @def.name captures are DISCARDED in UE mode to
            # prevent duplicate/conflicting entries (e.g., bare "ADGDronePawn"
            # vs rich "class ADGDronePawn (APawn)").
            api_macro = get_api_macro_for_file(rel, ue_module_macros)
            defs = parse_cpp_ue(full, api_macro)
            refs = ts_parser.parse_refs_only(full, ext)
        else:
            defs, refs = ts_parser.parse(full, ext)

        new_cache[cache_key] = {"defs": defs, "refs": refs}
        parsed_defs[rel] = defs
        parsed_refs[rel] = refs

    new_cache["_version"] = 2
    # Evict stale cache entries (only keep current files)
    save_cache(cache_path, new_cache)

    # 4. Build reference graph (tree-sitter symbol refs)
    ref_graph: dict[str, dict[str, float]] = {}
    pagerank_centrality = None
    if any(parsed_refs.values()):
        ref_graph = build_reference_graph(parsed_defs, parsed_refs)
        if ref_graph:
            pagerank_centrality = pagerank(ref_graph)

    # 4b. Build include-graph centrality (UE projects)
    include_centrality = None
    if ue_mode:
        include_centrality = build_include_graph(project_root, valid_files)

    # 4c. Blend centralities: max(include, pagerank) per file
    blended_centrality = _blend_centralities(
        include_centrality, pagerank_centrality, valid_files
    )

    # 5. Rank
    if is_git:
        ranking_data = get_git_log_data(project_root, valid_files)
    else:
        ranking_data = get_filesystem_ranking(project_root, valid_files)

    scores = compute_scores(ranking_data, line_counts, blended_centrality, profile)

    # Sort by score descending
    ranked = sorted(valid_files, key=lambda f: scores.get(f, 0), reverse=True)

    ranked = _apply_profile_injection(ranked, profile, ue_mode)

    ranked_with_entries = [(f, parsed_defs.get(f, [])) for f in ranked]

    # 6. Budget fit
    selected = budget_fit(ranked_with_entries, budget)

    # 7. Render
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = (
        f"# Repository Map\n"
        f"Generated: {now_str} | Files: {len(selected)}/{len(valid_files)} | "
        f"Budget: {budget} tokens\n"
    )

    sections = [header]
    for rel_path, entries in selected:
        sections.append(render_file_entry(rel_path, entries))

    output_text = "\n\n".join(sections) + "\n"

    # 8. Write atomically
    os.makedirs(output_path.parent, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=output_path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(output_text)
        os.replace(tmp_path, output_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    actual_tokens = estimate_tokens(output_text)
    ref_info = ""
    if pagerank_centrality:
        edge_count = sum(len(targets) for targets in ref_graph.values())
        ref_info = f", {len(ref_graph)} nodes/{edge_count} edges in ref graph"
    ue_info = ""
    if ue_mode:
        inc_count = sum(1 for v in (include_centrality or {}).values() if v > 0)
        ue_info = f", UE mode ({len(ue_module_macros)} modules, {inc_count} files with include refs)"
    print(
        f"Repository map written to {output_path}\n"
        f"  {len(selected)}/{len(valid_files)} files, ~{actual_tokens} tokens "
        f"(budget: {budget}){ref_info}{ue_info}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def find_git_root(start: Path) -> Path | None:
    """Find the git root directory from start path."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate a ranked repository map for LLM context."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root (default: git root or cwd)",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=4000,
        help="Token budget for the map (default: 4000)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Cache directory (default: <project>/.claude/repomap-cache/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: <project>/.claude/repomap.md)",
    )
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Task description for scoped map generation (enables task-scoped mode)",
    )
    parser.add_argument(
        "--focus-files",
        type=str,
        default=None,
        help="Comma-separated list of files to boost in task-scoped mode",
    )
    parser.add_argument(
        "--profile",
        choices=list(SCORING_PROFILES.keys()),
        default="balanced",
        help="Scoring profile: infra (git activity), code (centrality), balanced (default)",
    )

    args = parser.parse_args()

    # Resolve project root
    if args.project_root:
        project_root = args.project_root.resolve()
    else:
        git_root = find_git_root(Path.cwd())
        project_root = git_root if git_root else Path.cwd()

    if not project_root.is_dir():
        print(f"Error: {project_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    cache_dir = args.cache_dir or (project_root / ".claude" / "repomap-cache")

    if args.task or args.focus_files:
        # Task-scoped mode
        output_path = args.output or (project_root / ".claude" / "repomap-task.md")
        focus_files = []
        if args.focus_files:
            focus_files = [f.strip() for f in args.focus_files.split(",") if f.strip()]
        generate_task_scoped_map(
            project_root, args.budget, args.task or "", focus_files, cache_dir, output_path,
            args.profile,
        )
    else:
        # Standard mode
        output_path = args.output or (project_root / ".claude" / "repomap.md")
        generate_repomap(project_root, args.budget, cache_dir, output_path, args.profile)


if __name__ == "__main__":
    main()
