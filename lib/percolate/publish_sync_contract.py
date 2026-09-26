"""coordinator/lib/percolate/publish_sync_contract.py — would a round refuse
this override?

The one question this module answers, AST-only: given a `publish_sync.py`
source text, would `check_publish_sync_contract` (`coordinator/bin/publish.py`,
the round-time `inspect`-based twin of the same bar) refuse it at dispatch
time? `accepted_keywords`/`would_refuse` mirror that guard's obligations
exactly — same modes, same bare-wrapper rule, same `load_ignore` check — but
read the source with `ast.parse` instead of importing and calling
`inspect.signature`, because a caller here (the seam-parity test) is
checking an override it must never execute: another repo's `publish_sync.py`
is arbitrary code, and importing it to read a signature runs that code, in a
test, on a box running 50-70 peer sessions. `check_publish_sync_contract`
itself is exempt from that constraint — it already has the module imported
to call it — so it stays on `inspect.signature` unchanged; this module is
the AST-only twin for callers that must not import.

Stdlib plus `.publish_modes` only — nothing else, so this stays a leaf a
test can import cheaply and without a percolate-engine bootstrap.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .publish_modes import PUBLISH_MODES


def accepted_keywords(source: str, symbol: str) -> "tuple[bool, set[str], bool]":
    """`(defined, accepted_keyword_names, is_bare_var_wrapper)` for `symbol`.

    A `**kwargs` catch-all reports as a bare wrapper only when it is the
    function's ONLY parameter shape, matching `check_publish_sync_contract`'s
    own rule: a bare `(*args, **kwargs)` passes a superficial check and still
    fails at runtime, so it must not read as acceptance here either.
    """
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != symbol:
            continue
        args = node.args
        named = {a.arg for a in args.args} | {a.arg for a in args.kwonlyargs}
        named |= {a.arg for a in args.posonlyargs}
        has_var_kw = args.kwarg is not None
        is_bare = not named and (has_var_kw or args.vararg is not None)
        if has_var_kw and not is_bare:
            # A real signature that also carries `**kwargs` absorbs anything;
            # the round-time guard's `bind_partial` accepts that too.
            return True, named | {"**"}, False
        return True, named, is_bare
    return False, set(), False


def would_refuse(override_path: Path) -> "list[str]":
    """The reasons a round would refuse this override, empty when it would
    not. Mirrors `check_publish_sync_contract`'s obligations in the order that
    guard checks them, minus the run-scoping — a template or a root is checked
    against EVERY entry point, because we cannot know which modes a future
    round's rows will dispatch."""
    reasons: "list[str]" = []
    source = override_path.read_text(encoding="utf-8", errors="replace")
    for descriptor in PUBLISH_MODES:
        if descriptor.entry_point is None:
            continue
        defined, accepted, is_bare = accepted_keywords(source, descriptor.entry_point)
        if not defined:
            reasons.append(f"does not define {descriptor.entry_point!r}")
            continue
        if is_bare:
            reasons.append(
                f"{descriptor.entry_point!r} is a bare (*args/**kwargs) wrapper"
            )
            continue
        if "**" in accepted:
            continue
        missing = sorted(set(descriptor.bind_kwargs) - accepted)
        if missing:
            reasons.append(
                f"{descriptor.entry_point!r} does not accept {missing} "
                f"(mode {descriptor.wire_name!r})"
            )
    defined, accepted, is_bare = accepted_keywords(source, "load_ignore")
    if not defined:
        reasons.append("does not define 'load_ignore'")
    elif is_bare:
        reasons.append("'load_ignore' is a bare (*args/**kwargs) wrapper")
    return reasons
