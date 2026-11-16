"""Backend table, TypeScript version router, version pins and rollback-key readers for the LSP front.

The table is language-neutral data: {language: spawn spec, root-keying rule, capability cache slot}.
`native` is ty (Python) and tsgo (TypeScript) with typescript-language-server for roots tsgo
cannot serve; `pooled` is today's pyright + typescript-language-server (the rollback). Nothing
here spawns a process; the front (`lsp_front.py`) and the launcher read these decisions.
"""
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import lsp_share  # noqa: E402

FRONT_KEY = "lsp.front"
BACKEND_KEY = "lsp.front_backend"
DEFAULT_FRONT = "on"
DEFAULT_BACKEND = "native"
BACKENDS = ("native", "pooled")

PINS_PATH = _HERE / "lsp_front_pins.json"
LSP_JSON_PATH = _HERE.parent / ".lsp.json"

# Backend idle window; the front reaps a backend after this many seconds without a request.
IDLE_SECONDS = lsp_share.IDLE_SECONDS
IDLE_ENV = lsp_share.IDLE_ENV

TSLS_MAX_SERVER_MEMORY = 3072
_PYRIGHT_ENV = {"NODE_OPTIONS": "--max-old-space-size=2048"}

# Root-keying rules: how many backend processes serve a language's roots.
KEY_SHARED = "shared"  # one process, every root as a workspace folder
KEY_PER_VERSION = "per-version"  # one process per resolved TypeScript version
KEY_PER_ROOT = "per-root"  # one process per root

EXTENSION_LANGUAGE = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "typescript",
    ".jsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".mjs": "typescript",
    ".cjs": "typescript",
}

# (argv) -> (returncode, stdout); the machine-local runner signature lsp_launch uses.
Runner = Callable[[Sequence[str]], "tuple[int, str]"]


@dataclass(frozen=True)
class BackendSpec:
    """How to start one backend and how the front keys and caches it."""

    name: str  # ty | tsgo | tsls | pyright
    language: str  # python | typescript
    argv: tuple[str, ...]
    keying: str
    cache_slot: str  # capability-cache key; same-named specs share one cached capability set
    init_options: dict = field(default_factory=dict)
    env: dict = field(default_factory=dict)


def load_pins(path: Optional[Path] = None) -> dict:
    """The pinned {ty, tsgo, tsgo_lib, tsls} versions from lsp_front_pins.json."""
    data = json.loads((path or PINS_PATH).read_text(encoding="utf-8"))
    missing = [k for k in ("ty", "tsgo", "tsgo_lib", "tsls") if not isinstance(data.get(k), str)]
    if missing:
        raise ValueError(f"lsp_front_pins.json is missing {missing}")
    return data


def _argv_after_dashes(args: Sequence[str]) -> Optional[list[str]]:
    if "--" not in args:
        return None
    tail = list(args[list(args).index("--") + 1:])
    return tail or None


def _lsp_json_entry(name: str, path: Optional[Path]) -> dict:
    try:
        data = json.loads((path or LSP_JSON_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entry = data.get(name) if isinstance(data, dict) else None
    return entry if isinstance(entry, dict) else {}


def native_table() -> dict[str, BackendSpec]:
    """Language -> ty / tsgo spec. The tsls fallback is `tsls_spec`, chosen per root."""
    return {
        "python": BackendSpec(
            name="ty", language="python", argv=("ty", "server"), keying=KEY_SHARED, cache_slot="python:ty"
        ),
        "typescript": BackendSpec(
            name="tsgo",
            language="typescript",
            argv=("tsgo", "--lsp", "--stdio"),
            keying=KEY_SHARED,
            cache_slot="typescript:tsgo",
        ),
    }


def tsls_spec(root: Optional[Path] = None, lsp_json: Optional[Path] = None) -> BackendSpec:
    """typescript-language-server, one process per resolved TypeScript version.

    argv comes from the `.lsp.json` typescript entry's tail after `--` so the pooled rollback and
    the fallback never drift; `tsserver.path` pins the process to the root's own typescript copy.
    """
    entry = _lsp_json_entry("typescript", lsp_json)
    argv = _argv_after_dashes(entry.get("args", [])) or ["typescript-language-server", "--stdio"]
    init = dict(entry.get("initializationOptions") or {"maxTsServerMemory": TSLS_MAX_SERVER_MEMORY})
    init.setdefault("maxTsServerMemory", TSLS_MAX_SERVER_MEMORY)
    version = typescript_version(root) if root is not None else None
    if root is not None and version is not None:
        lib = typescript_lib_dir(root)
        if lib is not None:
            init["tsserver"] = {"path": str(lib)}
    return BackendSpec(
        name="tsls",
        language="typescript",
        argv=tuple(argv),
        keying=KEY_PER_VERSION,
        cache_slot=f"typescript:tsls:{version or 'bundled'}",
        init_options=init,
    )


def pooled_table(lsp_json: Optional[Path] = None) -> dict[str, BackendSpec]:
    """Rollback table: today's pyright and typescript-language-server argv from `.lsp.json`."""
    py_entry = _lsp_json_entry("pyright", lsp_json)
    py_argv = _argv_after_dashes(py_entry.get("args", [])) or ["pyright-langserver", "--stdio"]
    return {
        "python": BackendSpec(
            name="pyright",
            language="python",
            argv=tuple(py_argv),
            keying=KEY_SHARED,
            cache_slot="python:pyright",
            env=dict(py_entry.get("env") or _PYRIGHT_ENV),
        ),
        "typescript": tsls_spec(None, lsp_json),
    }


def backend_table(mode: str = DEFAULT_BACKEND, lsp_json: Optional[Path] = None) -> dict[str, BackendSpec]:
    """The language table for a `lsp.front_backend` value."""
    if mode == "pooled":
        return pooled_table(lsp_json)
    return native_table()


def language_for_path(path: "str | Path") -> Optional[str]:
    """Language the front routes `path` to, by extension; None when no backend serves it."""
    return EXTENSION_LANGUAGE.get(Path(str(path)).suffix.lower())


def typescript_lib_dir(root: "str | Path") -> Optional[Path]:
    """`<nearest node_modules>/typescript/lib` for root, or None."""
    pkg = _typescript_package(root)
    if pkg is None:
        return None
    lib = pkg.parent / "lib"
    return lib if lib.is_dir() else None


def _typescript_package(root: "str | Path") -> Optional[Path]:
    """Nearest `node_modules/typescript/package.json` at or above root (Node resolution order)."""
    start = Path(root)
    for directory in (start, *start.parents):
        candidate = directory / "node_modules" / "typescript" / "package.json"
        if candidate.is_file():
            return candidate
    return None


def typescript_version(root: "str | Path") -> Optional[str]:
    """The root's resolved TypeScript version string, or None when it has no typescript install."""
    pkg = _typescript_package(root)
    if pkg is None:
        return None
    try:
        version = json.loads(pkg.read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None
    return version if isinstance(version, str) and version else None


_MAJOR_MINOR = re.compile(r"^\s*v?(\d+)\.(\d+)")


def major_minor(version: Optional[str]) -> Optional[str]:
    """`"5.9.3"` -> `"5.9"`; None for an unparseable value."""
    m = _MAJOR_MINOR.match(version or "")
    return f"{m.group(1)}.{m.group(2)}" if m else None


def select_ts_backend(root: "str | Path", pins: Optional[dict] = None) -> str:
    """`"tsgo"` when the root's typescript major.minor equals the pinned tsgo lib, else `"tsls"`.

    tsgo ships one bundled lib and cannot honour a root's own typescript, so any other version
    (and a root with no readable typescript install) goes to typescript-language-server.
    """
    pins = pins or load_pins()
    resolved = major_minor(typescript_version(root))
    return "tsgo" if resolved is not None and resolved == major_minor(pins["tsgo_lib"]) else "tsls"


def resolve_spec(
    language: str, root: "str | Path", mode: str = DEFAULT_BACKEND, pins: Optional[dict] = None
) -> Optional[BackendSpec]:
    """The backend spec serving `language` for `root` under `mode`; None for an unserved language."""
    if language == "typescript" and (mode == "pooled" or select_ts_backend(root, pins) == "tsls"):
        return tsls_spec(root)
    return backend_table(mode).get(language)


def backend_key(spec: BackendSpec, root: "str | Path") -> str:
    """Process identity: roots with equal keys share one backend process."""
    if spec.keying == KEY_PER_ROOT:
        return f"{spec.cache_slot}@{os.path.normcase(os.path.normpath(str(root)))}"
    return spec.cache_slot


def idle_seconds(environ: Optional[dict] = None) -> float:
    """Backend idle-reap window: `LSP_SHARE_IDLE_SECONDS` when set, else the lsp_share default."""
    env = os.environ if environ is None else environ
    try:
        return float(env.get(IDLE_ENV) or IDLE_SECONDS)
    except ValueError:
        return float(IDLE_SECONDS)


def _runner(runner: Optional[Runner]) -> Runner:
    if runner is not None:
        return runner
    import lsp_launch  # lazy: lsp_launch imports this module

    return lsp_launch._default_runner


def _read_key(key: str, runner: Optional[Runner]) -> Optional[str]:
    rc, out = _runner(runner)(["get", key])
    return out.strip().lower() if rc == 0 else None


def front_enabled(runner: Optional[Runner] = None) -> bool:
    """`lsp.front`: False only when it reads exactly `off`; unset, a failed read or any other value is on."""
    return _read_key(FRONT_KEY, runner) != "off"


def front_backend(runner: Optional[Runner] = None) -> str:
    """`lsp.front_backend`: `pooled` only when it reads exactly `pooled`; else `native`."""
    return "pooled" if _read_key(BACKEND_KEY, runner) == "pooled" else DEFAULT_BACKEND
