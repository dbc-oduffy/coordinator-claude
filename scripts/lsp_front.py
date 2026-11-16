"""Box-level uni-server LSP front: one daemon answers `initialize` locally and routes to lazy backends.

Clients (the lsp_launch stub) bridge stdio to this daemon over 127.0.0.1. The front caches each
backend's real capabilities, answers `initialize` with their union, routes every request by file
extension (language) and longest-prefix root, and starts, reaps and respawns backends individually.
A backend crash errors only that backend's pending requests; the front and the other backends stay up.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse
from urllib.request import url2pathname

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import lsp_front_backends as fb  # noqa: E402
import lsp_share  # noqa: E402

FRONT_KEY = "lsp-front"
CAPS_FILE = "capabilities.json"
INIT_TIMEOUT_S = 60.0
ROUTE_BACKEND = "backend"
_JSONRPC = "2.0"
_INTERNAL_ERROR = -32603

DEFAULT_CAPABILITIES = {
    "textDocumentSync": {"openClose": True, "change": 1},
    "hoverProvider": True,
    "definitionProvider": True,
    "referencesProvider": True,
    "documentSymbolProvider": True,
    "workspaceSymbolProvider": True,
}

# Request method -> the server capability that gates it; an unlisted method is never gated.
METHOD_CAPABILITY = {
    "textDocument/hover": "hoverProvider",
    "textDocument/definition": "definitionProvider",
    "textDocument/declaration": "declarationProvider",
    "textDocument/typeDefinition": "typeDefinitionProvider",
    "textDocument/implementation": "implementationProvider",
    "textDocument/references": "referencesProvider",
    "textDocument/documentSymbol": "documentSymbolProvider",
    "textDocument/documentHighlight": "documentHighlightProvider",
    "textDocument/completion": "completionProvider",
    "textDocument/signatureHelp": "signatureHelpProvider",
    "textDocument/codeAction": "codeActionProvider",
    "textDocument/rename": "renameProvider",
    "textDocument/prepareRename": "renameProvider",
    "textDocument/formatting": "documentFormattingProvider",
    "textDocument/rangeFormatting": "documentRangeFormattingProvider",
    "textDocument/foldingRange": "foldingRangeProvider",
    "textDocument/prepareCallHierarchy": "callHierarchyProvider",
    "textDocument/prepareTypeHierarchy": "typeHierarchyProvider",
    "textDocument/semanticTokens/full": "semanticTokensProvider",
    "textDocument/inlayHint": "inlayHintProvider",
    "workspace/symbol": "workspaceSymbolProvider",
}

# Server requests the front answers itself with a null result.
_LOCAL_NULL_SERVER_REQUESTS = (
    "client/registerCapability",
    "client/unregisterCapability",
    "window/workDoneProgress/create",
)


def uri_to_path(uri: object) -> Optional[str]:
    """Filesystem path of a file: URI; None for any other scheme or a non-string."""
    if not isinstance(uri, str):
        return None
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return url2pathname(parsed.path)


def path_to_uri(path: "str | Path") -> str:
    return Path(path).absolute().as_uri()


def _norm(path: "str | Path") -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _contains(root: str, path: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _merge_lists(a: list, b: list) -> list:
    out = list(a)
    for item in b:
        if item not in out:
            out.append(item)
    return out


def _merge_dict(a: dict, b: dict) -> dict:
    out = dict(a)
    for key, value in b.items():
        if key not in out or out[key] in (None, False):
            out[key] = value
        elif isinstance(out[key], list) and isinstance(value, list):
            out[key] = _merge_lists(out[key], value)
        elif isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _merge_dict(out[key], value)
    return out


def _sync_change(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, dict) and isinstance(value.get("change"), int):
        return value["change"]
    return 0


def _union_sync(caps_list: "list[dict]") -> dict:
    """Open/close always on; the lowest non-zero change kind so every backend can follow."""
    kinds = []
    for caps in caps_list:
        change = _sync_change(caps.get("textDocumentSync"))
        if change > 0:
            kinds.append(change)
    return {"openClose": True, "change": min(kinds) if kinds else 1}


def union_capabilities(caps_list: "list[dict]") -> dict:
    """Union of server capability sets. positionEncoding is dropped: backends run the utf-16 default."""
    out: dict = {}
    for caps in caps_list:
        for key, value in caps.items():
            if key in ("textDocumentSync", "positionEncoding"):
                continue
            if key not in out or out[key] in (None, False):
                out[key] = value
            elif isinstance(out[key], dict) and isinstance(value, dict):
                out[key] = _merge_dict(out[key], value)
    out["textDocumentSync"] = _union_sync(caps_list)
    return out


def _utf16_index(line: str, units: int) -> int:
    seen = 0
    for i, ch in enumerate(line):
        if seen >= units:
            return i
        seen += 2 if ord(ch) > 0xFFFF else 1
    return len(line)


def _offset(lines: "list[str]", pos: dict) -> int:
    line = max(0, min(int(pos.get("line", 0)), len(lines) - 1))
    base = sum(len(row) + 1 for row in lines[:line])
    return base + _utf16_index(lines[line], int(pos.get("character", 0)))


def apply_change(text: str, change: dict) -> str:
    """One LSP content change applied to text: a rangeless event replaces it, a ranged one splices."""
    rng = change.get("range")
    if not rng:
        return change.get("text", "")
    lines = text.split("\n")
    start = _offset(lines, rng["start"])
    end = _offset(lines, rng["end"])
    return text[:start] + change.get("text", "") + text[end:]


def _config_value(options: dict, section: Optional[str]) -> object:
    if not section:
        return options or None
    node: object = options
    for part in section.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _default_argv(spec: "fb.BackendSpec") -> "list[str]":
    return [shutil.which(spec.argv[0]) or spec.argv[0], *spec.argv[1:]]


class _Agg:
    """Fan-out of one uri-less client request over several backends; replies when every part is in."""

    def __init__(self, cid: int, mid: object, parts: int) -> None:
        self.cid, self.mid, self.remaining, self.results = cid, mid, parts, []


class Backend:
    """One backend language-server process and the requests in flight to it."""

    def __init__(self, key: str, spec: "fb.BackendSpec") -> None:
        self.key = key
        self.spec = spec
        self.proc: Optional[subprocess.Popen] = None
        self.write_lock = threading.Lock()
        self.pending: "dict[int, tuple]" = {}
        self.caps: Optional[dict] = None
        self.folders: "list[str]" = []
        self.init_sid = 0
        self.init_event = threading.Event()
        self.ready = threading.Event()
        self.dead = False
        self.last_used = 0.0

    def write(self, obj: dict) -> bool:
        proc = self.proc
        if proc is None or proc.stdin is None or self.dead:
            return False
        try:
            with self.write_lock:
                proc.stdin.write(lsp_share.encode_message(obj))
                proc.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    def supports(self, method: str) -> bool:
        gate = METHOD_CAPABILITY.get(method)
        if gate is None or self.caps is None:
            return True
        return self.caps.get(gate) not in (None, False)


class Front:
    """The uni-server: client multiplexer, capability union, router and backend pool."""

    def __init__(
        self,
        runtime: Path,
        mode: str = fb.DEFAULT_BACKEND,
        idle_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
        resolve: Optional[Callable[[str, str], Optional["fb.BackendSpec"]]] = None,
        argv_for: Callable[["fb.BackendSpec"], "list[str]"] = _default_argv,
        route_by_kind: Optional[Callable[[str, dict], str]] = None,
        external_routes: Optional["dict[str, Callable[[str, dict], object]]"] = None,
    ) -> None:
        self.runtime = Path(runtime)
        self.mode = mode
        self.idle_seconds = fb.idle_seconds() if idle_seconds is None else idle_seconds
        self.clock = clock
        self.resolve = resolve or (lambda language, root: fb.resolve_spec(language, root, self.mode))
        self.argv_for = argv_for
        self.route_by_kind = route_by_kind or (lambda method, params: ROUTE_BACKEND)
        self.external_routes = external_routes or {}
        self.port = 0
        self.stopped = threading.Event()
        self._lock = threading.RLock()
        self._listener: Optional[socket.socket] = None
        self._clients: "dict[int, lsp_share._Peer]" = {}
        self._roots: "dict[int, list[str]]" = {}
        self._client_caps: Optional[dict] = None
        self._next_cid = 0
        self._next_sid = 0
        self._backends: "dict[str, Backend]" = {}
        self._docs: "dict[str, dict]" = {}
        self._srv_reqs: "dict[str, tuple[Backend, object]]" = {}
        self._caps_cache: "dict[str, dict]" = self._load_caps()
        self._idle_since = clock()

    @property
    def registry_path(self) -> Path:
        return self.runtime / f"{FRONT_KEY}.json"

    # ---- lifecycle -------------------------------------------------------------------------

    def start(self) -> int:
        """Open the listener and publish the registry entry; returns the port. No backend starts here."""
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(16)
        self.port = self._listener.getsockname()[1]
        self.runtime.mkdir(parents=True, exist_ok=True)
        tmp = self.registry_path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"pid": os.getpid(), "port": self.port, "mode": self.mode}), encoding="utf-8")
        os.replace(tmp, self.registry_path)
        threading.Thread(target=self._accept_loop, daemon=True).start()
        return self.port

    def run_forever(self, poll_s: Optional[float] = None) -> None:
        self.start()
        poll = poll_s if poll_s is not None else max(0.2, min(5.0, self.idle_seconds / 2))
        while not self.stopped.wait(poll):
            self.tick()

    def tick(self) -> bool:
        """Reap idle backends; stop the front once no client has been connected for the idle window."""
        self.reap_idle()
        with self._lock:
            idle = not self._clients and self.clock() - self._idle_since >= self.idle_seconds
        if idle:
            self.shutdown()
        return self.stopped.is_set()

    def reap_idle(self) -> "list[str]":
        """Stop every backend with nothing in flight that has been unused for the idle window."""
        now = self.clock()
        with self._lock:
            victims = [
                b for b in self._backends.values()
                if not b.dead and not b.pending and now - b.last_used >= self.idle_seconds
            ]
        for backend in victims:
            self._stop_backend(backend)
        return [b.key for b in victims]

    def shutdown(self) -> None:
        with self._lock:
            if self.stopped.is_set():
                return
            self.stopped.set()
            clients = list(self._clients.values())
            self._clients.clear()
            backends = list(self._backends.values())
        for backend in backends:
            self._stop_backend(backend)
        for peer in clients:
            peer.close()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
        try:
            current = json.loads(self.registry_path.read_text(encoding="utf-8"))
            if current.get("pid") == os.getpid():
                self.registry_path.unlink()
        except (OSError, ValueError):
            pass

    def backend_keys(self) -> "list[str]":
        with self._lock:
            return sorted(k for k, b in self._backends.items() if not b.dead)

    # ---- capability cache ------------------------------------------------------------------

    def _load_caps(self) -> "dict[str, dict]":
        try:
            data = json.loads((self.runtime / CAPS_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _store_caps(self, slot: str, caps: dict) -> None:
        with self._lock:
            self._caps_cache[slot] = caps
            snapshot = dict(self._caps_cache)
        try:
            self.runtime.mkdir(parents=True, exist_ok=True)
            tmp = self.runtime / f"{CAPS_FILE}.{os.getpid()}.tmp"
            tmp.write_text(json.dumps(snapshot), encoding="utf-8")
            os.replace(tmp, self.runtime / CAPS_FILE)
        except OSError:
            pass

    def local_capabilities(self) -> dict:
        """Union of the cached real capabilities; a language with no cache contributes the default set."""
        with self._lock:
            cache = dict(self._caps_cache)
        slots = [spec.cache_slot for spec in fb.backend_table(self.mode).values()]
        sets = [cache.get(slot) or DEFAULT_CAPABILITIES for slot in slots]
        sets += [caps for slot, caps in cache.items() if slot not in slots]
        return union_capabilities(sets)

    # ---- client side -----------------------------------------------------------------------

    def _accept_loop(self) -> None:
        while not self.stopped.is_set():
            try:
                sock, _ = self._listener.accept()
            except OSError:
                return
            with self._lock:
                self._next_cid += 1
                cid = self._next_cid
                peer = lsp_share._Peer(sock)
                self._clients[cid] = peer
                self._roots[cid] = []
            threading.Thread(target=self._client_loop, args=(cid, peer), daemon=True).start()

    def _client_loop(self, cid: int, peer: "lsp_share._Peer") -> None:
        reader = peer.sock.makefile("rb")
        try:
            while True:
                msg = lsp_share.read_message(reader)
                if msg is None:
                    break
                self.handle_client_message(cid, msg)
        except OSError:
            pass
        finally:
            self._drop_client(cid)

    def _drop_client(self, cid: int) -> None:
        closes: "list[tuple[Backend, str]]" = []
        with self._lock:
            peer = self._clients.pop(cid, None)
            self._roots.pop(cid, None)
            for uri in list(self._docs):
                doc = self._docs[uri]
                if cid in doc["holders"]:
                    doc["holders"].discard(cid)
                    if not doc["holders"]:
                        del self._docs[uri]
                        live = self._live(doc.get("opened_on"))
                        if live is not None:
                            closes.append((live, uri))
            if not self._clients:
                self._idle_since = self.clock()
        if peer is not None:
            peer.close()
        for backend, uri in closes:
            backend.write({
                "jsonrpc": _JSONRPC, "method": "textDocument/didClose", "params": {"textDocument": {"uri": uri}},
            })

    def _live(self, backend: Optional[Backend]) -> Optional[Backend]:
        with self._lock:
            if backend is not None and not backend.dead and self._backends.get(backend.key) is backend:
                return backend
        return None

    def _reply(self, cid: int, mid: object, result: object = None, error: Optional[dict] = None) -> None:
        with self._lock:
            peer = self._clients.get(cid)
        if peer is None:
            return
        msg: dict = {"jsonrpc": _JSONRPC, "id": mid}
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result
        peer.send(msg)

    def handle_client_message(self, cid: int, msg: dict) -> None:
        method = msg.get("method")
        mid = msg.get("id")
        if method is None:
            self._client_response(msg)
            return
        if mid is None:
            self._client_notification(cid, method, msg.get("params") or {}, msg)
            return
        params = msg.get("params") or {}
        if method == "shutdown":
            self._reply(cid, mid, None)
        elif method == "initialize":
            self._initialize(cid, mid, params)
        else:
            self._request(cid, mid, method, params, msg)

    def _initialize(self, cid: int, mid: object, params: dict) -> None:
        roots = []
        for folder in params.get("workspaceFolders") or []:
            path = uri_to_path(folder.get("uri"))
            if path:
                roots.append(os.path.normpath(path))
        if not roots:
            path = uri_to_path(params.get("rootUri")) or params.get("rootPath")
            if path:
                roots.append(os.path.normpath(path))
        with self._lock:
            self._roots[cid] = roots
            if self._client_caps is None:
                caps = json.loads(json.dumps(params.get("capabilities") or {}))
                (caps.get("general") or {}).pop("positionEncodings", None)
                self._client_caps = caps
        self._reply(cid, mid, {"capabilities": self.local_capabilities(), "serverInfo": {"name": "lsp-front"}})

    def _client_response(self, msg: dict) -> None:
        with self._lock:
            entry = self._srv_reqs.pop(msg.get("id"), None)
        if entry is not None:
            backend, orig = entry
            backend.write({**msg, "id": orig})

    # ---- routing ---------------------------------------------------------------------------

    def root_for(self, cid: int, path: str) -> str:
        """Longest-prefix announced root containing path; the file's own directory when none does."""
        norm = _norm(path)
        with self._lock:
            roots = list(self._roots.get(cid, ()))
        best = ""
        for root in roots:
            if _contains(_norm(root), norm) and len(root) > len(best):
                best = root
        return best or os.path.normpath(os.path.dirname(path))

    def _locate(self, cid: int, uri: object) -> "Optional[tuple[str, str, fb.BackendSpec, str]]":
        path = uri_to_path(uri)
        if path is None:
            return None
        language = fb.language_for_path(path)
        if language is None:
            return None
        root = self.root_for(cid, path)
        spec = self.resolve(language, root)
        if spec is None:
            return None
        return language, root, spec, fb.backend_key(spec, root)

    @staticmethod
    def _uri_of(params: dict) -> Optional[str]:
        uri = (params.get("textDocument") or {}).get("uri") or params.get("uri")
        return uri if isinstance(uri, str) else None

    def _request(self, cid: int, mid: object, method: str, params: dict, msg: dict) -> None:
        kind = self.route_by_kind(method, params)
        if kind != ROUTE_BACKEND and kind in self.external_routes:
            try:
                self._reply(cid, mid, self.external_routes[kind](method, params))
            except Exception as exc:  # noqa: BLE001 - an external route must not take the front down
                self._reply(cid, mid, error={"code": _INTERNAL_ERROR, "message": f"{kind} route failed: {exc}"})
            return
        if method == "workspace/symbol":
            self._workspace_symbol(cid, mid, msg)
            return
        uri = self._uri_of(params)
        if uri is None:
            self._reply(cid, mid, None)
            return
        target = self._locate(cid, uri)
        if target is None:
            self._reply(cid, mid, None)
            return
        _, root, spec, key = target
        backend = self._ensure_backend(spec, root, key, cid)
        if backend is None:
            self._reply(cid, mid, error={"code": _INTERNAL_ERROR, "message": f"backend {spec.name} unavailable"})
            return
        if not backend.supports(method):
            self._reply(cid, mid, None)
            return
        self._sync_doc(backend, uri)
        self._forward_request(backend, cid, mid, msg)

    def _forward_request(self, backend: Backend, cid: int, mid: object, msg: dict) -> None:
        with self._lock:
            self._next_sid += 1
            sid = self._next_sid
            backend.pending[sid] = ("client", cid, mid)
            backend.last_used = self.clock()
        if not backend.write({**msg, "id": sid}):
            with self._lock:
                backend.pending.pop(sid, None)
            self._reply(cid, mid, error={"code": _INTERNAL_ERROR, "message": f"backend {backend.spec.name} exited"})

    def _workspace_symbol(self, cid: int, mid: object, msg: dict) -> None:
        with self._lock:
            targets = [b for b in self._backends.values() if not b.dead and b.supports("workspace/symbol")]
        if not targets:
            self._reply(cid, mid, None)
            return
        agg = _Agg(cid, mid, len(targets))
        for backend in targets:
            with self._lock:
                self._next_sid += 1
                sid = self._next_sid
                backend.pending[sid] = ("agg", agg)
                backend.last_used = self.clock()
            if not backend.write({**msg, "id": sid}):
                with self._lock:
                    backend.pending.pop(sid, None)
                self._agg_part(agg, None)

    def _agg_part(self, agg: _Agg, result: object) -> None:
        with self._lock:
            if isinstance(result, list):
                agg.results.extend(result)
            agg.remaining -= 1
            done = agg.remaining == 0
        if done:
            self._reply(agg.cid, agg.mid, agg.results or None)

    # ---- client notifications --------------------------------------------------------------

    def _client_notification(self, cid: int, method: str, params: dict, msg: dict) -> None:
        if method == "workspace/didChangeWorkspaceFolders":
            self._change_folders(cid, params)
        elif method == "textDocument/didOpen":
            self._did_open(cid, params)
        elif method == "textDocument/didClose":
            self._did_close(cid, params)
        elif method == "textDocument/didChange":
            self._did_change(params, msg)
        elif method in ("textDocument/didSave", "textDocument/willSave"):
            self._forward_doc_notification(self._uri_of(params), msg)
        elif method == "workspace/didChangeWatchedFiles":
            with self._lock:
                targets = [b for b in self._backends.values() if not b.dead]
            for backend in targets:
                backend.write(msg)
        elif method == "$/cancelRequest":
            self._cancel(cid, params)
        # initialized, exit, didChangeConfiguration, $/setTrace and the rest stop here.

    def _change_folders(self, cid: int, params: dict) -> None:
        event = params.get("event") or {}
        with self._lock:
            roots = self._roots.setdefault(cid, [])
            for folder in event.get("removed") or []:
                path = uri_to_path(folder.get("uri"))
                if path and os.path.normpath(path) in roots:
                    roots.remove(os.path.normpath(path))
            for folder in event.get("added") or []:
                path = uri_to_path(folder.get("uri"))
                if path and os.path.normpath(path) not in roots:
                    roots.append(os.path.normpath(path))

    def _did_open(self, cid: int, params: dict) -> None:
        td = params.get("textDocument") or {}
        uri = td.get("uri")
        target = self._locate(cid, uri)
        if target is None:
            return
        _, root, spec, key = target
        with self._lock:
            doc = self._docs.get(uri)
            first = doc is None
            if first:
                doc = {
                    "holders": set(), "text": td.get("text", ""), "version": td.get("version", 0),
                    "languageId": td.get("languageId", ""), "key": key, "opened_on": None,
                }
                self._docs[uri] = doc
            doc["holders"].add(cid)
        backend = self._ensure_backend(spec, root, key, cid)
        if backend is not None:
            self._sync_doc(backend, uri)

    def _sync_doc(self, backend: Backend, uri: str) -> None:
        """Send didOpen for uri to backend unless this very process already holds it."""
        with self._lock:
            doc = self._docs.get(uri)
            if doc is None or doc["opened_on"] is backend or doc["key"] != backend.key:
                return
            doc["opened_on"] = backend
            item = {"uri": uri, "languageId": doc["languageId"], "version": doc["version"], "text": doc["text"]}
        backend.write({"jsonrpc": _JSONRPC, "method": "textDocument/didOpen", "params": {"textDocument": item}})

    def _did_close(self, cid: int, params: dict) -> None:
        uri = self._uri_of(params)
        with self._lock:
            doc = self._docs.get(uri)
            if doc is None:
                return
            doc["holders"].discard(cid)
            if doc["holders"]:
                return
            del self._docs[uri]
            live = self._live(doc.get("opened_on"))
        if live is not None:
            live.write({
                "jsonrpc": _JSONRPC, "method": "textDocument/didClose", "params": {"textDocument": {"uri": uri}},
            })

    def _did_change(self, params: dict, msg: dict) -> None:
        uri = self._uri_of(params)
        with self._lock:
            doc = self._docs.get(uri)
            if doc is None:
                return
            for change in params.get("contentChanges") or []:
                doc["text"] = apply_change(doc["text"], change)
            doc["version"] = (params.get("textDocument") or {}).get("version", doc["version"])
            live = self._live(doc.get("opened_on"))
            if live is not None:
                live.last_used = self.clock()
        if live is not None:
            live.write(msg)

    def _forward_doc_notification(self, uri: Optional[str], msg: dict) -> None:
        with self._lock:
            doc = self._docs.get(uri) if uri else None
            live = self._live(doc.get("opened_on")) if doc else None
        if live is not None:
            live.write(msg)

    def _cancel(self, cid: int, params: dict) -> None:
        with self._lock:
            for backend in self._backends.values():
                for sid, entry in backend.pending.items():
                    if entry[0] == "client" and entry[1] == cid and entry[2] == params.get("id"):
                        backend.write({
                            "jsonrpc": _JSONRPC, "method": "$/cancelRequest", "params": {**params, "id": sid},
                        })
                        return

    # ---- backends --------------------------------------------------------------------------

    def _ensure_backend(self, spec: "fb.BackendSpec", root: str, key: str, cid: int) -> Optional[Backend]:
        """The live backend for key, started (and its open documents replayed) when none is."""
        with self._lock:
            backend = self._backends.get(key)
            creator = backend is None or backend.dead
            if creator:
                backend = Backend(key, spec)
                self._backends[key] = backend
        if creator:
            try:
                self._start_backend(backend, root)
            except Exception:  # noqa: BLE001 - a backend that will not start is reported per request
                self._discard(backend)
                backend.ready.set()
                return None
            backend.ready.set()
            self._replay_docs(backend)
        else:
            backend.ready.wait(INIT_TIMEOUT_S + 5)
            if backend.dead or backend.caps is None:
                return None
            self._ensure_folder(backend, root)
        backend.last_used = self.clock()
        return backend

    def _discard(self, backend: Backend) -> None:
        backend.dead = True
        with self._lock:
            if self._backends.get(backend.key) is backend:
                del self._backends[backend.key]
        proc = backend.proc
        if proc is not None and proc.poll() is None:
            proc.kill()

    def _start_backend(self, backend: Backend, root: str) -> None:
        spec = backend.spec
        env = {**os.environ, **spec.env} if spec.env else None
        backend.proc = subprocess.Popen(
            self.argv_for(spec),
            cwd=root if os.path.isdir(root) else None,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=lsp_share._no_console(),
        )
        backend.folders = [path_to_uri(root)]
        threading.Thread(target=self._server_loop, args=(backend,), daemon=True).start()
        with self._lock:
            self._next_sid += 1
            backend.init_sid = self._next_sid
            client_caps = self._client_caps or {}
        params = {
            "processId": os.getpid(),
            "rootUri": backend.folders[0],
            "workspaceFolders": [{"uri": u, "name": os.path.basename(uri_to_path(u) or u)} for u in backend.folders],
            "capabilities": client_caps,
            "initializationOptions": spec.init_options or None,
        }
        backend.write({"jsonrpc": _JSONRPC, "id": backend.init_sid, "method": "initialize", "params": params})
        if not backend.init_event.wait(INIT_TIMEOUT_S) or backend.caps is None:
            raise RuntimeError(f"{spec.name} did not initialize")
        self._store_caps(spec.cache_slot, backend.caps)
        backend.write({"jsonrpc": _JSONRPC, "method": "initialized", "params": {}})

    def _replay_docs(self, backend: Backend) -> None:
        with self._lock:
            uris = [u for u, d in self._docs.items() if d["key"] == backend.key]
        for uri in uris:
            self._sync_doc(backend, uri)

    def _ensure_folder(self, backend: Backend, root: str) -> None:
        uri = path_to_uri(root)
        with self._lock:
            if uri in backend.folders:
                return
            backend.folders.append(uri)
        backend.write({
            "jsonrpc": _JSONRPC,
            "method": "workspace/didChangeWorkspaceFolders",
            "params": {"event": {"added": [{"uri": uri, "name": os.path.basename(root)}], "removed": []}},
        })

    def _stop_backend(self, backend: Backend) -> None:
        """Retire a backend (reap or front exit): its documents are replayed to a successor."""
        with self._lock:
            if self._backends.get(backend.key) is backend:
                del self._backends[backend.key]
            already = backend.dead
            backend.dead = True
        proc = backend.proc
        if already or proc is None or proc.poll() is not None:
            return
        try:
            with backend.write_lock:
                proc.stdin.write(lsp_share.encode_message({"jsonrpc": _JSONRPC, "id": "front-shutdown", "method": "shutdown"}))
                proc.stdin.write(lsp_share.encode_message({"jsonrpc": _JSONRPC, "method": "exit"}))
                proc.stdin.flush()
        except (OSError, ValueError):
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass

    def _server_loop(self, backend: Backend) -> None:
        proc = backend.proc
        try:
            while True:
                msg = lsp_share.read_message(proc.stdout)
                if msg is None:
                    break
                self.handle_server_message(backend, msg)
        except (OSError, ValueError):
            pass
        self._backend_died(backend)

    def _backend_died(self, backend: Backend) -> None:
        """Error only this backend's pending ids; the entry goes so the next request respawns it."""
        with self._lock:
            backend.dead = True
            if self._backends.get(backend.key) is backend:
                del self._backends[backend.key]
            pending, backend.pending = backend.pending, {}
            for rid in [r for r, (b, _) in self._srv_reqs.items() if b is backend]:
                del self._srv_reqs[rid]
        backend.init_event.set()
        for entry in pending.values():
            if entry[0] == "client":
                self._reply(entry[1], entry[2], error={
                    "code": _INTERNAL_ERROR, "message": f"backend {backend.spec.name} exited",
                })
            elif entry[0] == "agg":
                self._agg_part(entry[1], None)

    # ---- server messages -------------------------------------------------------------------

    def handle_server_message(self, backend: Backend, msg: dict) -> None:
        method = msg.get("method")
        mid = msg.get("id")
        if method is None:
            self._server_response(backend, mid, msg)
        elif mid is not None:
            self._server_request(backend, mid, method, msg)
        else:
            self._server_notification(backend, method, msg)

    def _server_response(self, backend: Backend, mid: object, msg: dict) -> None:
        if mid == backend.init_sid and backend.caps is None and not backend.init_event.is_set():
            result = msg.get("result")
            if isinstance(result, dict):
                backend.caps = result.get("capabilities") or {}
            backend.init_event.set()
            return
        with self._lock:
            entry = backend.pending.pop(mid, None)
        if entry is None:
            return
        if entry[0] == "agg":
            self._agg_part(entry[1], msg.get("result"))
            return
        _, cid, orig = entry
        out = {k: v for k, v in msg.items() if k in ("jsonrpc", "result", "error")}
        out["id"] = orig
        with self._lock:
            peer = self._clients.get(cid)
        if peer is not None:
            peer.send(out)

    def _server_request(self, backend: Backend, mid: object, method: str, msg: dict) -> None:
        def answer(result: object) -> None:
            backend.write({"jsonrpc": _JSONRPC, "id": mid, "result": result})

        if method == "workspace/configuration":
            options = backend.spec.init_options or {}
            items = (msg.get("params") or {}).get("items") or []
            answer([_config_value(options, item.get("section")) for item in items])
            return
        if method in _LOCAL_NULL_SERVER_REQUESTS:
            answer(None)
            return
        if method == "workspace/workspaceFolders":
            answer([{"uri": u, "name": os.path.basename(uri_to_path(u) or u)} for u in backend.folders])
            return
        with self._lock:
            target = self._clients.get(min(self._clients)) if self._clients else None
            rid = None
            if target is not None:
                self._next_sid += 1
                rid = f"lspfront-{self._next_sid}"
                self._srv_reqs[rid] = (backend, mid)
        if target is None:
            answer(None)
        else:
            target.send({**msg, "id": rid})

    def _server_notification(self, backend: Backend, method: str, msg: dict) -> None:
        params = msg.get("params") or {}
        if method == "textDocument/publishDiagnostics":
            with self._lock:
                doc = self._docs.get(params.get("uri"))
                peers = [self._clients[c] for c in (doc["holders"] if doc else ()) if c in self._clients]
        else:
            if method == "$/progress" and "token" in params:
                msg = {**msg, "params": {**params, "token": f"{backend.spec.name}:{params['token']}"}}
            with self._lock:
                peers = list(self._clients.values())
        for peer in peers:
            peer.send(msg)


# ---- daemon spawn and client connect ------------------------------------------------------


def default_runtime() -> Path:
    import lsp_launch  # lazy: lsp_launch imports this module's sibling table

    return lsp_launch.share_runtime().parent / "lsp-front"


def _spawn_front(runtime: Path) -> None:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--serve", "--runtime", str(runtime)]
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | lsp_share._no_console()
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, cwd=str(runtime), **kwargs)


def ensure_front(runtime: Path, wait_s: float = lsp_share.SPAWN_WAIT_S) -> Optional[socket.socket]:
    """A connected socket to the box's front, spawning it under a spawn lock when none is live.

    lsp_share.ensure_daemon cannot start this daemon (it spawns lsp_share.py itself), so the same
    lock-and-spawn protocol runs here on lsp_share's primitives.
    """
    runtime = Path(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    lock = runtime / f"{FRONT_KEY}.lock"
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        sock = lsp_share._try_connect(runtime, FRONT_KEY)
        if sock is not None:
            return sock
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > lsp_share.LOCK_STALE_S:
                    lock.unlink()
            except OSError:
                pass
            time.sleep(0.1)
            continue
        except OSError:
            return None
        os.close(fd)
        try:
            sock = lsp_share._try_connect(runtime, FRONT_KEY)
            if sock is not None:
                return sock
            try:
                (runtime / f"{FRONT_KEY}.json").unlink()
            except OSError:
                pass
            _spawn_front(runtime)
            while time.monotonic() < deadline:
                sock = lsp_share._try_connect(runtime, FRONT_KEY)
                if sock is not None:
                    return sock
                time.sleep(0.1)
            return None
        finally:
            try:
                lock.unlink()
            except OSError:
                pass
    return None


def connect(runtime: Optional[Path] = None) -> Optional[int]:
    """Proxy this process's stdio to the box's front; None when no front could be reached."""
    sock = ensure_front(runtime or default_runtime())
    if sock is None:
        return None
    return lsp_share.bridge(sock, sys.stdin.buffer, sys.stdout.buffer)


def _main(args: "list[str]") -> int:
    runtime = None
    if "--runtime" in args:
        at = args.index("--runtime") + 1
        if at >= len(args):
            print("lsp_front: --runtime needs a directory", file=sys.stderr)
            return 2
        runtime = Path(args[at])
    runtime = runtime or default_runtime()
    if "--serve" in args:
        mode = os.environ.get("LSP_FRONT_MODE") or fb.DEFAULT_BACKEND
        Front(runtime, mode=mode if mode in fb.BACKENDS else fb.DEFAULT_BACKEND).run_forever()
        return 0
    if "--connect" in args:
        return 0 if connect(runtime) is not None else 1
    print("usage: lsp_front.py --serve|--connect [--runtime <dir>]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
