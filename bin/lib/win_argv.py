"""win_argv — the single Windows-safe argv tokenizer for `coordinator/bin/`.

Consumers: `coordinator/bin/coordinator-ceremony-hook.py` (the commit hot
path) and `coordinator/bin/refresh-plugin-live-install.py`. Both already
insert `coordinator/bin/lib` onto `sys.path` before importing this module,
so no new bootstrap step is needed at either call site.

Negative-spec — leaf-clean import constraint: this module imports ONLY
``shlex`` from the standard library, and it must never import anything
else, ever. That is the entire reason it exists as a standalone leaf module
rather than living in `coordinator_core`: `coordinator_core/session/core.py`
imports `psutil` at module level, and any import path that reaches this
tokenizer through `coordinator_core` would drag that 83-module transitive
chain onto the ceremony hook's hot-path import budget
(`coordinator_core/benchmarks/import-budget-manifest.json`). Adding any
import here — including another `coordinator/bin/lib` sibling — risks
recreating that trap one hop removed. If a future change needs this module
to depend on something else, that dependency choice must re-measure the
import graph against the manifest, not assume leaf-cleanliness still holds.
"""
from __future__ import annotations

import shlex


def win_safe_shlex_split(cmd_str: str) -> list[str]:
    """``shlex.split`` equivalent that does not mangle backslashes.

    Bare ``shlex.split`` (POSIX mode) treats ``\\`` as a C-style escape
    character, so a Windows-authored drive-letter path with backslash
    separators (illustrative example, not a real path: a drive letter,
    colon, then ``Users``, ``bob``, ``tools``, ``refresh.exe`` joined by
    backslashes) is silently stripped down to the same segments joined with
    no separator at all. That mangled path then surfaced verbatim in a
    caller's WARN/error diagnostic, misattributing a path the operator
    never typed.

    ``posix=False`` is NOT the fix and is NOT used here: it also stops
    stripping the surrounding quote characters from a quoted token
    (``"hello world"`` splits to the literal 4-char token ``"hello`` plus
    ``world"``, quotes retained), regressing the argv-only contract's
    quoted-token handling that existing callers/tests rely on (e.g. the
    ceremony hook's secret-redaction test's quoted URL).

    This keeps posix quote-stripping/whitespace-splitting semantics while
    disabling backslash escape processing, so backslash path separators
    pass through untouched. Equivalence with ``shlex.split`` holds only for
    input containing NO backslash: whitespace splitting, quote stripping,
    and unbalanced-quote ``ValueError``\\ s all match in that case. Once a
    backslash is present, behaviour diverges in BOTH directions, because
    ``escape=""`` makes a backslash a literal character always — never an
    escape — which changes which quote characters are seen as delimiters. A
    backslash cannot be both an escape and a path separator, and this repo
    is Windows-first, so this divergence is the deliberate tradeoff. Two
    concrete illustrations: ``"a\\"b"`` raises here (the backslash is not
    consumed as an escape, so the middle ``"`` closes the quote after just
    ``a``, leaving the trailing ``b"`` as unbalanced) where ``shlex.split``
    returns ``['a"b']``; and ``"unterminated\\"`` returns the token
    ``['unterminated\\\\']`` here (the two literal ``"`` characters pair up
    as an ordinary open/close with the backslash preserved as a plain char
    in between) where ``shlex.split`` raises ``ValueError`` on the same
    input, because there it treats ``\\"`` as an escaped, non-closing
    quote and so sees only one closing quote short.

    Negative-spec — the one deliberate tokenization divergence: a backslash
    can be an escape character or a path separator, never both, and this
    repo is Windows-first. So a POSIX-style escaped space (``a\\ b``) is NO
    longer one token ``a b``; it tokenizes as ``a\\`` and ``b``. An operator
    escaping spaces that way must quote the value instead (``"a b"``), which
    works identically on both platforms.
    """
    lexer = shlex.shlex(cmd_str, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    return list(lexer)
