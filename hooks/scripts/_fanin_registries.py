"""The fan-in layer, enumerated once.

Seven dispatchers carry other hooks' handlers in a `REGISTRY`-shaped tuple
rather than each handler holding its own `hooks.json` entry
(`state/audits/2026-08-16-doe-spawn-totality-kill-list.md` -- one interpreter for
N guards, the whole point of the fan-in): `sessionstart-dispatch.py`,
`sessionstart-async-dispatch.py`, `stop-dispatch.py`, `preuse-write-dispatch.py`,
`postuse-stop-family-dispatch.py`, `preuse-bash-dispatch.py`, and
`preuse-agent-dispatch.py`. A reader that only walks `hooks.json` therefore sees
the DISPATCHER and none of the guards behind it, and cannot tell a folded guard
from a deleted one.

That blind spot has already produced two live defects: `x-effective-delivery`
reported the first three dispatchers as bare `direct` rows, under-reporting
delivered guards to the engine plane's duplication detector; and the hook
registration roster recorded `session-start-repair-prepare-commit-msg-hook.py`
as retired-because-complete when it was in fact carried by the async fan-in.
A third reader, `population_scan`, needs the union of every carrier to compute
its Category-A ceiling and has nowhere else to get it. This module is the ONE
enumeration all three now read, so a guard cannot be carried in one reader's
view and absent in another's, and no fourth reader gets to grow its own copy.

Negative-spec: this module does NOT execute any guard, does not read
`hooks.json` (which dispatcher is REGISTERED is that file's question, and its
readers' -- this one answers only what each dispatcher CARRIES), and imports
nothing outside the stdlib and this directory's own sibling hook-scripts
(a reviewed convention -- see `test_hook_stdlib_only_contract.py`'s own
docstring, which names its stdlib-only assertion withdrawn and does not test
this module).

Two carriers hold their guard rows one hop away from the dispatcher itself,
in a sibling in-process runner module the dispatcher only imports a
private-named alias of (`preuse-write-dispatch.py` -> `_guard_runner.py`'s
PUBLIC `REAL_GUARD_REGISTRY`; `postuse-stop-family-dispatch.py` ->
`_stop_family_runner.py`'s PUBLIC `REAL_STOP_FAMILY_REGISTRY`). This module
reads those runner modules' own public names directly rather than reaching
through the dispatcher's private alias -- the runner module IS the source of
truth for what it carries, and its registry is already public where it is
actually defined. Their guard rows carry `module_path`, not `filename`; this
module derives `filename` as `Path(module_path).name`.

`preuse-bash-dispatch.py` has no separate runner module -- `_BASH_GUARD_REGISTRY`
is defined, and is underscore-private, directly inside the dispatcher file. The
enrolling chunk's own brief calls for a public accessor there instead of
reaching through that underscore, but that brief's declared `writes:` scope
names only THIS file -- adding one to `preuse-bash-dispatch.py` is out of
scope for the chunk that landed this enrollment. Recorded as a deviation, not
silently resolved: this module reads `_BASH_GUARD_REGISTRY` directly via
`getattr` (same mechanism `carried_guards()` already uses for every other
carrier's registry attribute) until a chunk whose scope covers
`preuse-bash-dispatch.py` adds the sanctioned public accessor.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Callable

_SCRIPTS = Path(__file__).resolve().parent

FANIN_DISPATCHERS = {
    "sessionstart-dispatch.py": "SessionStart",
    "sessionstart-async-dispatch.py": "SessionStart",
    "stop-dispatch.py": "Stop",
    "preuse-write-dispatch.py": "PreToolUse",
    "postuse-stop-family-dispatch.py": "PostToolUse",
    # `_CARRIER_SOURCES`, and the two must stay in step: it is a PreToolUse
    # engine's chain. Listing it here without a `_CARRIER_SOURCES` entry raises
    "preuse-agent-dispatch.py": "PreToolUse",
}


def load_dispatcher(filename: str):
    path = _SCRIPTS / filename
    spec = importlib.util.spec_from_file_location(
        "_fanin_" + filename.replace("-", "_").removesuffix(".py"), path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load fan-in dispatcher {filename}")
    module = importlib.util.module_from_spec(spec)
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rows_direct(rows) -> "list[tuple[str, str]]":
    """Row shape already carrying `.module_key`/`.filename` directly --
    `sessionstart-dispatch.py`, `sessionstart-async-dispatch.py`,
    `stop-dispatch.py`, `preuse-agent-dispatch.py`'s `REGISTRY`, and
    `preuse-bash-dispatch.py`'s `_BASH_GUARD_REGISTRY` (read directly, not
    through a public accessor -- see the module docstring's "out of scope
    for this chunk" note)."""
    return [(row.module_key, row.filename) for row in rows]


def _rows_via_module_path(rows) -> "list[tuple[str, str]]":
    """Row shape carrying `.module_key`/`.module_path` instead of a bare
    filename -- `_guard_runner.REAL_GUARD_REGISTRY` and
    `_stop_family_runner.REAL_STOP_FAMILY_REGISTRY`."""
    return [(row.module_key, Path(row.module_path).name) for row in rows]


#: four dispatchers whose own `REGISTRY`-shaped attribute is directly usable;
_CARRIER_SOURCES: "dict[str, tuple[str, str, Callable]]" = {
    "sessionstart-dispatch.py": ("sessionstart-dispatch.py", "REGISTRY", _rows_direct),
    "sessionstart-async-dispatch.py": ("sessionstart-async-dispatch.py", "REGISTRY", _rows_direct),
    "stop-dispatch.py": ("stop-dispatch.py", "REGISTRY", _rows_direct),
    "preuse-agent-dispatch.py": ("preuse-agent-dispatch.py", "REGISTRY", _rows_direct),
    # `preuse-bash-dispatch.py` is DELIBERATELY ABSENT and must not be re-added: it carries no
    # became a pure relay. A carrier entry here would resolve `_BASH_GUARD_REGISTRY` on a module
    "preuse-write-dispatch.py": ("_guard_runner.py", "REAL_GUARD_REGISTRY", _rows_via_module_path),
    "postuse-stop-family-dispatch.py": (
        "_stop_family_runner.py", "REAL_STOP_FAMILY_REGISTRY", _rows_via_module_path,
    ),
}


def carried_guards(filename: str):
    """`[(module_key, guard_filename), ...]` for one dispatcher, in REGISTRY order.

    Order is preserved because it is load-bearing for `sessionstart-dispatch.py`
    (`guard-hook-generation-self-probe.py` runs last by contract).

    `filename` names the DISPATCHER (a `FANIN_DISPATCHERS` key), never the
    sibling runner module a carrier's rows might actually live in -- that
    indirection is `_CARRIER_SOURCES`'s concern, not the caller's.
    """
    spec = _CARRIER_SOURCES.get(filename)
    if spec is None:
        raise AttributeError(f"{filename} is not an enrolled fan-in carrier")
    source_filename, attr_name, extractor = spec
    source = load_dispatcher(source_filename)
    attr = getattr(source, attr_name, None)
    if attr is None:
        raise AttributeError(
            f"{source_filename} exposes no {attr_name} -- not a fan-in carrier"
        )
    rows = attr() if callable(attr) else attr
    return extractor(rows)


def all_carried_guards():
    seen = {}
    for dispatcher in FANIN_DISPATCHERS:
        for _, guard_filename in carried_guards(dispatcher):
            if guard_filename in seen:
                raise ValueError(
                    f"{guard_filename} is carried by both {seen[guard_filename]} and "
                    f"{dispatcher} -- double delivery, not a naming collision"
                )
            seen[guard_filename] = dispatcher
    return seen
