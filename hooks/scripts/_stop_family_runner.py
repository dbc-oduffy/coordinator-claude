"""_stop_family_runner.py -- the in-process runner for the four Stop-family
PostToolUse write-path guards (C4b), implementing
`_stop_family_runner_contract.py` (the GOVERNING SURFACE) verbatim -- see
that module's numbered clauses for the authoritative statement of each
behaviour below.

Deliberately NOT built on top of `_guard_runner.py`'s internals (no shared
base class, no imported helper functions from that module) -- see
`_stop_family_runner_contract.py`'s own docstring for why this is a SIBLING
mechanism, not an extension: the aggregation problem (concatenate-all N
independent stderr-emitters into one combined stderr write + one exit code)
is different in kind from `_guard_runner.py`'s class-aware DENY-vs-
additionalContext combining, not a parametrisation of it. The two-stage
lazy-import shape (`_import_guard_module`/two-stage descriptor match) is
structurally similar by necessity -- both runners solve "N sibling scripts,
one process, don't pay every import" -- but is reimplemented here rather
than shared, so the two mechanisms can evolve independently without one
change rippling into an unrelated protocol.

Spec: docs/plans/2026-08-06-hook-spawn-fan-in-finish-and-extend.md § C4b.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _stop_family_runner_contract import (  # noqa: E402
    ENROLLED_GUARD_MODULES,
    STOP_FAMILY_SCOPE_DESCRIPTORS,
)
from _guard_runner_contract import GuardScopeDescriptor  # noqa: E402


@dataclass(frozen=True)
class RegisteredStopFamilyGuard:

    module_key: str
    module_path: str
    descriptor: GuardScopeDescriptor


class _ByteSink:
    """Binary-mode facade for `_BufferedTextCapture.buffer`: writes bytes straight
    through, UNMODIFIED, into the SAME ordered `io.BytesIO` the text channel's
    `write(str)` encodes into -- no decode, no round-trip at capture time. This is
    the byte-exactness half of the fix (the ordering half is: one shared sink, not
    two separately-accumulated buffers -- see `_BufferedTextCapture`'s own
    docstring). Byte-exactness matters here specifically because the two
    `nudge-*.py` guards route their emission through `_message_envelope.emit()`,
    which writes raw UTF-8 bytes via `sys.stderr.buffer.write()` PRECISELY to
    bypass Python's Windows text-mode CRLF translation (`project-orientation.py`'s
    `_w()` documents the same convention, review finding B-F3) -- a capture layer
    that decoded those bytes into a `str` mid-flight would still be lossless
    (UTF-8 decode/encode round-trips exactly), but the dispatcher-side RE-EMISSION
    this capture feeds must also avoid a text-mode `sys.__stderr__.write(str)`,
    or the CRLF translation this convention exists to avoid gets reintroduced one
    hop later. See `postuse-stop-family-dispatch.py`'s own emission site (already
    `sys.stderr.buffer.write(text.encode("utf-8"))`, not the text wrapper) for the
    other half of that guarantee."""

    def __init__(self, sink: "io.BytesIO") -> None:
        self._sink = sink

    def write(self, data: bytes) -> int:
        return self._sink.write(data)

    def flush(self) -> None:
        pass


class _BufferedTextCapture(io.StringIO):

    def __init__(self) -> None:
        super().__init__()
        self._bytes = io.BytesIO()
        self.buffer = _ByteSink(self._bytes)

    def write(self, s: str) -> int:
        self._bytes.write(s.encode("utf-8"))
        return len(s)

    def combined(self) -> str:
        return self.combined_bytes().decode("utf-8", "replace")

    def combined_bytes(self) -> bytes:
        return self._bytes.getvalue()

    def getvalue(self) -> str:
        return self.combined()


def _target_path_from_payload(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _import_guard_module(guard: RegisteredStopFamilyGuard):
    if guard.module_key in sys.modules:
        return sys.modules[guard.module_key]
    spec = importlib.util.spec_from_file_location(guard.module_key, guard.module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load guard module at {guard.module_path!r}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[guard.module_key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(guard.module_key, None)
        raise
    return module


def _invoke_stop_guard_main(main_fn: Callable[[], int], stdin_text: str) -> Tuple[int, str]:
    """Runs one guard's `main()` with stdin swapped and stderr captured
    (contract clause 3) -- mirrors `_guard_runner._invoke_guard_main`'s
    stdio-swap technique, but captures STDERR (this protocol's real
    channel) instead of stdout, and returns the RAW `(exit_code,
    stderr_text)` pair rather than translating into a verdict shape (there
    is only one shape here, so no translation step is needed).

    Captures via `_BufferedTextCapture`, not a plain `io.StringIO()`: the
    two `nudge-*.py` guards route their CHANNEL_STOP emission through
    `_message_envelope.emit()`, which deliberately writes via
    `sys.stderr.buffer.write()` (raw UTF-8 bytes, bypassing Python's
    Windows text-mode CRLF translation -- see that module's own docstring)
    rather than `sys.stderr.write()`. A plain `io.StringIO` has no
    `.buffer` attribute and raises `AttributeError` the instant such a
    guard fires -- the exact same gap `coordinator/tests/fixtures/
    hook-message-sweeps/message_measurement_harness.py`'s own
    `_BufferedTextCapture` class was built to close for its measurement
    harness; this reuses that same fix rather than rediscovering it.

    Catches `SystemExit` defensively (contract clause 1 says a guard's
    `main()` must not use it for control flow, but the runner never trusts
    that by assumption alone) -- an uncaught `SystemExit` is treated as
    `return 0` with whatever was captured on stderr up to that point, an
    ultra-conservative choice since no enrolled guard's `main()` actually
    calls `sys.exit()` internally (verified at authoring time by reading
    all four)."""
    stdin_buf = io.StringIO(stdin_text)
    stderr_buf = _BufferedTextCapture()
    old_stdin = sys.stdin
    exit_code = 0
    with contextlib.redirect_stderr(stderr_buf):
        sys.stdin = stdin_buf
        try:
            try:
                exit_code = main_fn()
            except SystemExit as exc:
                exit_code = exc.code if isinstance(exc.code, int) else 0
        finally:
            sys.stdin = old_stdin
    return exit_code, stderr_buf.combined()


def build_stop_family_entries(
    registry: Iterable[RegisteredStopFamilyGuard],
    raw_payload_text: str,
    payload: Any,
) -> List[Tuple[str, Callable[[], Tuple[int, str]]]]:
    target_path = _target_path_from_payload(payload)
    entries: List[Tuple[str, Callable[[], Tuple[int, str]]]] = []
    for guard in registry:
        if not guard.descriptor.matches(target_path):
            continue

        def _call(_guard: RegisteredStopFamilyGuard = guard) -> Tuple[int, str]:
            module = _import_guard_module(_guard)
            main_fn = getattr(module, "main")
            return _invoke_stop_guard_main(main_fn, raw_payload_text)

        entries.append((guard.module_key, _call))
    return entries


def run_stop_family_guards(
    entries: Iterable[Tuple[str, Callable[[], Tuple[int, str]]]],
    skipped_out: Optional[List[str]] = None,
) -> Tuple[int, str]:
    """The pure aggregation core (contract clauses 4 + 5): CONCATENATE-ALL,
    never first-fires-wins. Every entry that raises `BaseException`
    (clause 5's exception isolation -- deliberately this broad, mirroring
    `_guard_runner.run_guards`) has its name appended to `skipped_out` and
    the batch continues; `skipped_out` defaults to a fresh list.

    Returns `(combined_exit_code, combined_stderr_text)`:
      - `combined_exit_code` is `2` if ANY entry returned `2`, else `0`.
      - `combined_stderr_text` is every FIRED entry's captured stderr text
        (exit code `2` only), joined with a blank line between each, in
        entry order -- never just the first."""
    if skipped_out is None:
        skipped_out = []

    fired_texts: List[str] = []
    any_fired = False

    for name, fn in entries:
        try:
            exit_code, text = fn()
        except BaseException:
            skipped_out.append(name)
            continue

        if exit_code == 2:
            any_fired = True
            if text:
                fired_texts.append(text.rstrip("\n"))

    combined_exit = 2 if any_fired else 0
    combined_text = "\n\n".join(fired_texts)
    return combined_exit, combined_text


#: `_stop_family_runner_contract.ENROLLED_GUARD_MODULES` names, each paired
#: with its descriptor from `STOP_FAMILY_SCOPE_DESCRIPTORS` (imported, never
REAL_STOP_FAMILY_REGISTRY: Tuple[RegisteredStopFamilyGuard, ...] = tuple(
    RegisteredStopFamilyGuard(
        module_key=name.replace("-", "_").replace(".py", ""),
        module_path=str(Path(_HOOKS_DIR) / name),
        descriptor=STOP_FAMILY_SCOPE_DESCRIPTORS[name],
    )
    for name in ENROLLED_GUARD_MODULES
)


def run_registered_stop_family_guards(
    registry: Iterable[RegisteredStopFamilyGuard],
    raw_payload_text: str,
    payload: Any,
    skipped_out: Optional[List[str]] = None,
) -> Tuple[int, str]:
    entries = build_stop_family_entries(registry, raw_payload_text, payload)
    return run_stop_family_guards(entries, skipped_out=skipped_out)
