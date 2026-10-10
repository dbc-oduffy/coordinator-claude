"""coordinator/lib/doctrine_status.py -- read a doctrine page's `status:`
frontmatter value and check it against the closed vocabulary contract.

Purpose: `coordinator/contract/doctrine-status-vocabulary.json` closes the
`status:` field at exactly five values (`active`, `deprecated`, `distilled`,
`shipped`, `stub`) after C1's 82-page repair. Nothing previously checked a
page's value against that contract -- a ninth spelling could land tomorrow
and nothing would notice. This module is the read-and-check half; the CLI
at `coordinator/bin/check-doctrine-status.py` is the exit-code half.

`load_vocabulary` raises `ValueError` for a contract that parses as JSON
but is shaped wrong (missing `vocabulary` key, or a non-list-of-strings
value) -- the CLI routes this, alongside `json.JSONDecodeError`, to its
exit-2 "unusable contract" path.

THREE PAGE CLASSES ARE SILENT, BY DESIGN. 675 pages carry no frontmatter at
all; 48 carry frontmatter but no `status:` key. Absence is never a
violation -- this is the frontmatter-backfill rejection
(`docs/plans/2026-08-30-doctrine-governance-tier-2.md` Anti-scope), enforced
mechanically here rather than left as a convention a future editor could
violate by accident. Only a page that HAS a `status:` key with a value
outside the contract's vocabulary is a violation.

Frontmatter parsing reuses `coordinator/lib/agent_frontmatter.py:split_frontmatter`
rather than adding a fourth private splitter -- three unshared copies already
existed in this tree per this chunk's dispatch brief, and a fourth is the
defect the brief calls out by name.

Negative-spec: no CLI, no output formatting, no exit codes, no directory
walk caching -- pure functions over paths/text returning structured
results, so a caller (the CLI, or a test) can assert on data. No staleness,
no git history, no second unrelated concern sharing this module -- the
earlier draft's `doctrine_governance.py` bundled two unrelated things and
needed a third chunk to reunite them; this module is deliberately narrow.

Spec: `docs/plans/2026-08-30-doctrine-governance-tier-2.md`, chunk C2.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# coordinator/lib/doctrine_status.py -> coordinator/lib -> coordinator -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENT_FRONTMATTER_PATH = REPO_ROOT / "coordinator" / "lib" / "agent_frontmatter.py"


def _load_agent_frontmatter():
    """Load `agent_frontmatter.py` by file location, not a dotted package
    import -- `coordinator/` carries no `__init__.py` in this tree, and
    every existing consumer of this sibling module (e.g.
    `test_agent_tools_no_phantom_tools.py`) loads it the same way."""
    # Bare "agent_frontmatter" is a process-global
    # sys.modules slot with no namespacing; key by resolved path so an
    # unrelated module registered under the same bare name can never be
    # silently substituted. The spec is created UNDER THAT SAME KEY, not
    # under the bare name: `@dataclass` resolves `sys.modules[cls.__module__]`,
    # so a module whose __name__ disagrees with its registry key crashes at
    # class-creation time with a bare AttributeError.
    cache_key = f"agent_frontmatter@{_AGENT_FRONTMATTER_PATH}"
    if cache_key in sys.modules:
        return sys.modules[cache_key]
    spec = importlib.util.spec_from_file_location(cache_key, _AGENT_FRONTMATTER_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[cache_key] = mod
    spec.loader.exec_module(mod)
    return mod


split_frontmatter = _load_agent_frontmatter().split_frontmatter
CONTRACT_PATH = REPO_ROOT / "coordinator" / "contract" / "doctrine-status-vocabulary.json"
WIKI_ROOT = REPO_ROOT / "coordinator" / "docs" / "wiki"

STATUS_LINE = re.compile(r"^status:\s*(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class StatusFinding:
    """One page's `status:` verdict.

    `has_status` is False for both silent classes (no frontmatter, and
    frontmatter without a `status:` key) -- callers branch on `has_status`
    first and never inspect `value` when it is False.
    """

    path: Path
    has_status: bool
    value: "str | None"
    is_violation: bool


def load_vocabulary(contract_path: Path = CONTRACT_PATH) -> tuple[str, ...]:
    """The closed vocabulary from the contract file, as an ordered tuple.

    Raises `FileNotFoundError`/`json.JSONDecodeError` unmodified on a
    missing or malformed contract -- a caller with an unusable contract
    cannot silently treat every value as valid. Also raises `ValueError`
    if the contract parses as JSON but its shape is unusable: no
    `vocabulary` key, or a `vocabulary` value that isn't a list of
    strings.

    A contract that is valid JSON but has no `vocabulary` key (or has it
    as a non-list) raises ValueError, so the CLI reports the documented
    exit 2 for an unusable contract rather than an uncaught traceback.
    """
    data = json.loads(contract_path.read_text(encoding="utf-8"))
    if "vocabulary" not in data:
        raise ValueError(f"contract at {contract_path} has no \"vocabulary\" key")
    vocabulary = data["vocabulary"]
    if not isinstance(vocabulary, list) or not all(isinstance(v, str) for v in vocabulary):
        raise ValueError(
            f"contract at {contract_path} has a \"vocabulary\" value that is not "
            "a list of strings"
        )
    return tuple(vocabulary)


def extract_status(text: str) -> "str | None":
    """The frontmatter `status:` value, or `None` if the page has no
    frontmatter or has frontmatter without a `status:` key.

    Bounded to the frontmatter block between the leading `---` fences --
    a naive whole-file `status:` search over-reports because body prose
    (a code block, a sentence describing the field itself) can also match.
    """
    frontmatter, _body = split_frontmatter(text)
    if not frontmatter:
        return None
    match = STATUS_LINE.search(frontmatter)
    if match is None:
        return None
    return match.group(1).strip().strip("'\"")


def check_page(path: Path, vocabulary: Iterable[str]) -> StatusFinding:
    """Read one page and classify it against `vocabulary`.

    Never raises on the two silent classes; a page this function cannot
    read (permissions, encoding) is the caller's problem to surface, not
    one this function papers over -- read errors propagate. The CLI
    catches `UnicodeDecodeError` specifically and routes it to exit 2
    naming the unreadable file, so it never collides with exit 1's
    "unlisted status value" contract.
    """
    text = path.read_text(encoding="utf-8")
    value = extract_status(text)
    if value is None:
        return StatusFinding(path=path, has_status=False, value=None, is_violation=False)
    vocab = tuple(vocabulary)
    return StatusFinding(
        path=path,
        has_status=True,
        value=value,
        is_violation=value not in vocab,
    )


def iter_wiki_pages(wiki_root: Path = WIKI_ROOT) -> "list[Path]":
    """Every `.md` file under `wiki_root`, sorted for deterministic output."""
    return sorted(wiki_root.rglob("*.md"))
