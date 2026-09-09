"""DoE-side selection seam for the environment-switch mechanism.

Spec backlink: docs/plans/2026-09-07-compose-the-environment-story-and-select.md
(chunk C3, roadmap cloud-em-2026-09-06). This module is the SECOND splice
site alongside `_posture.py`'s -- same shape (a marker-delimited managed
section rendered by the engine's `render_posture_overlay`), a different
marker pair, and a resolver that answers a different question. It supplies
`_environment_story.resolve_environment_story` with the two paths it needs
(`registry_path`, `sentinel_path`) and hands back the `Story` it resolves.
It does not re-implement resolution, and does not re-decide any of the six
failure modes that function already owns -- see its own module docstring
for the ladder and the six named modes. Making that function unreachable
from here is this chunk's own failure, not a case to degrade around.

THE INVERSION -- read side by side with `_posture.py`, stated here because
the difference IS the safety argument. `_posture.py` answers *what
surfaces to an already-trusted local operator*, and fails OPEN: every
unreadable/unparseable/absent-key/out-of-enum condition resolves to
"precision", the most cautious posture, which changes NOTHING about
whether a safeguard fires -- fail-open is safe there only because the
safeguard itself is invariant across every posture value. This module
answers *what is true here at all* -- which rules even apply -- and an
unrecognised environment must fail CLOSED, toward `STRICTEST_STORY`, which
OMITS NOTHING. The two mechanisms share a ladder shape and resolve to
opposite ends of their respective spectra on purpose: a posture that failed
toward its least cautious value would be silently permissive, and a story
that failed toward its most permissive member would silently drop rules no
one decided to drop. Neither file may borrow the other's anchor.

THE MARKER-NAME HAZARD -- see the constants below, and this plan's
Anti-scope for the fixture-verified writeup: the engine's
`render_posture_overlay._swap` drops every marker line after the first
`MARKER_START` it meets, so two pairs of the SAME marker name lose their
second pair silently. This module's marker pair is a distinct name from
`coordinator:posture` for exactly that reason.

NO PRODUCTION CALLER, BY DESIGN AND NOT YET BY OVERSIGHT -- stated here so
the next reader does not have to re-derive it from a fruitless grep. The
consumer is engine-plane: `render_posture_overlay` splices a marker pair it
hardcodes, so nothing renders THIS pair until the engine gains a second
render target. That shape is not a guess -- it is the answer
`state/roadmap/cloud-em-2026-09-06/peer-team-asks.md` row 5 came back with,
read from the engine source. Until that lands, the callers are this
module's two test files. What makes the module worth its bytes meanwhile is
the marker-name constraint below, which has no other home and whose failure
mode is silent.

WHAT WOULD RETIRE THIS FILE: the engine declining a second render target, or
the environment-switch mechanism being answered some other way. Either makes
this a gravestone, not a refactor -- there is nothing here to salvage but
the hazard note.

Import-light, stdlib-only, no `subprocess`, no third-party import, no
module-level file I/O -- mirrors `_environment_story.py`'s own constraints,
because this module is reached at session start like every sibling hook
script in this directory.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, Optional

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _environment_story import (  # noqa: E402
    STRICTEST_STORY,
    Story,
    resolve_environment_story,
)

# Imported for its module-level side effect only: `_environment_stories`
# calls `_environment_story.register_story(EPHEMERAL_CLOUD_VM_STORY)` at
# import time, admitting `"ephemeral-cloud-vm"` into the same in-process
# registry `resolve_environment_story` looks names up against. Nothing in
# this module references a name from it directly -- the registration is
# the only thing needed, and it is the reason this import exists at all
# rather than being left to whichever caller happens to import that module
# first. `noqa: F401` because the import is deliberately side-effect-only;
# not wrapped in try/except like the `_engine_root` imports elsewhere in
# this directory, because a missing `_environment_stories` here is a
# partial deploy of THIS SAME BATON's own two chunks, not the
# cross-repo-engine-absent case those other wrappers guard against.
import _environment_stories  # noqa: F401,E402


# ---------------------------------------------------------------------------
# Marker constants -- the splice site for the composed story's prose.
#
# MUST NOT reuse `coordinator:posture` (or any other already-spliced marker
# name). This is not a style preference: the engine's
# `render_posture_overlay._swap` sets a `printed_block` flag on the FIRST
# `MARKER_START` line it meets in a target file and drops every marker line
# after it -- so a file carrying two pairs of the SAME marker name has its
# SECOND pair (start line, body, and end line) silently deleted: exit 0, no
# warning, no error, nothing raised. Verified by executing that module
# against a two-pair fixture; filed P1 against the engine and unpinned by
# any test there as of this writing. A future edit that "simplifies" these
# two constants down to `coordinator:posture` would reintroduce exactly
# that silent-deletion path. See this plan's Anti-scope for the full
# writeup: docs/plans/2026-09-07-compose-the-environment-story-and-select.md
MARKER_START = "<!-- coordinator:environment-story:start -->"
MARKER_END = "<!-- coordinator:environment-story:end -->"

#: Filenames under the resolved settings-home (see `_resolve_settings_home`
#: below) an operator populates to select a story for this box. Not
#: committed into the repo -- `coordinator/templates/environment-registry.
#: example` is the template an operator copies and edits; see that file's
#: own header comment for the format and the real path.
_REGISTRY_FILENAME = "environment-registry"
_SENTINEL_FILENAME = "environment-sentinel"


def _resolve_settings_home() -> str:
    """Resolve the coordinator-claude settings-home root as a plain string
    path, built entirely with `os.path.join` (Windows-safe, no literal
    `/`).

    Precedence, bit-for-bit the same as every other self-contained hook
    script in this directory that resolves settings-home on its own (see
    `session-start-announce-job-mode.py::resolve_settings_home`,
    `pickup-autofire.py`, `mise-autofire.py`): an explicit
    `COORDINATOR_SETTINGS_HOME` override is used AS-IS; otherwise
    `CLAUDE_HOME` (or `HOME`) joined with the fixed
    `.coordinator-claude-settings` suffix. Each hook script in this
    directory carries its own copy of this precedence rather than sharing
    one import, matching this directory's own stated single-file-module
    convention -- this module's copy is no exception."""
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return override
    base = os.environ.get("CLAUDE_HOME") or os.path.expanduser("~")
    return os.path.join(base, ".coordinator-claude-settings")


def default_registry_path() -> str:
    """The registry path this module supplies to `resolve_environment_story`
    when no caller override is given. Not a literal baked into the
    resolver itself -- `resolve_environment_story` takes `registry_path` as
    a parameter and never assumes one, per this plan's
    no-single-machine-assumptions brightline; this function is where a
    default gets to live instead."""
    return os.path.join(_resolve_settings_home(), _REGISTRY_FILENAME)


def default_sentinel_path() -> str:
    """The sentinel path this module supplies to `resolve_environment_story`
    when no caller override is given. Same non-literal reasoning as
    `default_registry_path` above."""
    return os.path.join(_resolve_settings_home(), _SENTINEL_FILENAME)


def resolve_selected_story(
    *,
    registry_path: Optional[str] = None,
    sentinel_path: Optional[str] = None,
    probe: Optional[Callable[[], str]] = None,
    probe_timeout_s: float = 2.0,
) -> Story:
    """Resolve the environment story for this session through the real
    seam: fill in the two default paths this module owns when the caller
    does not override them, then delegate everything else -- probing,
    reading, registry lookup, and every one of the six failure modes -- to
    `_environment_story.resolve_environment_story` unchanged. This function
    adds no resolution logic of its own; it exists only to own the two
    default paths and the marker constants above.

    NEVER raises and NEVER returns `None`, by the same guarantee the
    delegated call already carries: every failure mode terminates at
    `STRICTEST_STORY`."""
    if registry_path is None:
        registry_path = default_registry_path()
    if sentinel_path is None:
        sentinel_path = default_sentinel_path()
    return resolve_environment_story(
        registry_path=registry_path,
        sentinel_path=sentinel_path,
        probe=probe,
        probe_timeout_s=probe_timeout_s,
    )
