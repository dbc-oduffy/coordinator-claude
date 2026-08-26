"""Single source of publish-mode vocabulary (AC1,
docs/plans/2026-08-10-repo-cut-the-fourth-mode-and-the-table.md, chunk C1).

Before this module, six sites across `publish.py`, `publish_sync.py`, and
`ensure_required_targets.py` each hard-coded their own copy of "which modes
exist" and "which modes are mirror-like" as a literal tuple or a
`mode == "mirror"` string comparison. Adding a mode meant finding and
updating every copy by hand; missing one is exactly the kind of fail-open a
`repo-cut` fourth mode would hit silently (state/audits/2026-08-05-first-
full-payload-identity-findings.md Group E, and the `check_publish_sync_
contract` global-bind hazard the plan's AC7 names).

This module declares one `PublishModeDescriptor` per mode and derives every
consumer-facing tuple/constant from that table, so a consumer asks a
question of the table instead of restating a literal.

Four modes are declared: `mirror`, `flat-mirror`, `manifest`, and
`repo-cut`. Note that the four derived accessors below are all keyed on
`is_mirror_like`, so `repo-cut` — which is not mirror-like — is absent from
every one of them by construction. That is deliberate, and it is not the
whole story: a `repo-cut` row needs its own outer-gate arm in
`publish.py::process_target`, and anything wanting `repo-cut` in a CLI
choice set needs an accessor keyed on something other than mirror-like-ness
(dispatchability, or bootstrap-bearing). Widening `mirror_like_wire_names()`
to cover it is the wrong fix twice over: it would break the byte-for-byte
equality pins that are this refactor's regression net, and it would route a
mode through the mirror dispatcher, re-arming in a new place the fail-open
`MirrorDispatchModeError` exists to close.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PublishModeDescriptor:
    """One publish mode's dispatch properties.

    `bind_kwargs` is this descriptor's OWN declared contract — the exact
    kwarg set `check_publish_sync_contract` must bind against `entry_point`
    for THIS mode, never a single dict shared across every entry point
    (AC7: a global bind aborts every publish run the instant one mode's
    entry point can't bind against it). `sync_mirror` and `sync_flat_mirror`
    diverge on exactly one kwarg (`renamed_dir_names`) — that divergence is
    represented here per-descriptor, not as a second hard-coded check
    layered on top of a shared dict.
    """

    wire_name: str
    is_mirror_like: bool
    entry_point: str | None
    bind_kwargs: dict[str, object] = field(default_factory=dict)
    accepts_renamed_dir_names: bool = False
    #: Whether this mode's entry point takes `sweep_top_level_orphans` — the
    #: per-row opt-in that lets a destination top-level FILE absent from the
    #: source be deleted (`publish_sync._sweep_mirror_top_level_orphans`).
    #: `sync_mirror` only: `sync_flat_mirror` has always swept its top-level
    #: files unconditionally and needs no flag to be told to, and the two
    #: non-mirror-like modes have no sweep at all. Declared here for the same
    #: reason `accepts_renamed_dir_names` is — the two mirror-like entry points
    #: diverge on it, and `check_publish_sync_contract` binds each descriptor's
    #: own `bind_kwargs` against its own entry point rather than one shared set.
    accepts_sweep_top_level_orphans: bool = False
    is_bootstrap_bearing: bool = False


# The `mirror` mode's wire name as an importable constant. Site 5
# (`ensure_required_targets.py::_find_mirror_row`) is a NAMED-ROW lookup for
# the single `coordinator-claude|mirror` row, not a mode-vocabulary
# consumer — it imports this constant and keeps its equality test exact;
# it must never be widened into a mirror-like predicate (Problem-table
# site 5, plan AC2).
MIRROR_WIRE_NAME = "mirror"

_MIRROR_DESCRIPTOR = PublishModeDescriptor(
    wire_name=MIRROR_WIRE_NAME,
    is_mirror_like=True,
    entry_point="sync_mirror",
    bind_kwargs={
        "copy_file": None,
        "renamed_dir_names": None,
        "sweep_top_level_orphans": False,
        "renamed_file_names": None,
    },
    accepts_renamed_dir_names=True,
    accepts_sweep_top_level_orphans=True,
    is_bootstrap_bearing=False,
)

_FLAT_MIRROR_DESCRIPTOR = PublishModeDescriptor(
    wire_name="flat-mirror",
    is_mirror_like=True,
    entry_point="sync_flat_mirror",
    bind_kwargs={"copy_file": None},
    accepts_renamed_dir_names=False,
    is_bootstrap_bearing=False,
)

_MANIFEST_DESCRIPTOR = PublishModeDescriptor(
    wire_name="manifest",
    is_mirror_like=False,
    entry_point=None,
    bind_kwargs={},
    accepts_renamed_dir_names=False,
    is_bootstrap_bearing=False,
)

# `repo-cut` is a one-shot bootstrap-bearing mode, not mirror-like: it
# stands up a fresh destination repo (chunk C7b) rather than projecting a
# payload into an existing one, so it is deliberately absent from
# `mirror_like_wire_names()` / `mirror_entry_points()` /
# `argparse_mode_choices()` / `dest_bootstrap_parametrize_wire_names()` (all
# of which are `is_mirror_like`-keyed). Its dispatch arm and bootstrap
# implementation are chunk C7b's, in `publish.py` — this row exists so C7b
# has a table entry to dispatch off of, not to route it through any
# mirror-like consumer. Its source precondition (AC11) is pre-existing
# engine behaviour in `_git_materialize_ref` (`publish.py`): a
# `repo-cut` source that is not inside a git work tree is refused via
# `run_pre_sync_gates`'s `GitMaterializeError` handling before this
# descriptor's entry point is ever reached.
_REPO_CUT_DESCRIPTOR = PublishModeDescriptor(
    wire_name="repo-cut",
    is_mirror_like=False,
    entry_point="sync_repo_cut",
    # Declares `dry_run` rather than an empty dict: `check_publish_sync_contract`
    # binds this set against the real `sync_repo_cut` signature, and an empty
    # set binds vacuously — every possible signature satisfies it, so a drift
    # would NOT fail closed and AC7 would be satisfied in name only.
    bind_kwargs={"dry_run": False},
    accepts_renamed_dir_names=False,
    is_bootstrap_bearing=True,
)

# Declared order matters only for the derived accessors below, which
# preserve it so today's literal tuples reproduce byte-for-byte.
PUBLISH_MODES: tuple[PublishModeDescriptor, ...] = (
    _MIRROR_DESCRIPTOR,
    _FLAT_MIRROR_DESCRIPTOR,
    _MANIFEST_DESCRIPTOR,
    _REPO_CUT_DESCRIPTOR,
)

_BY_WIRE_NAME: dict[str, PublishModeDescriptor] = {
    descriptor.wire_name: descriptor for descriptor in PUBLISH_MODES
}


def descriptor_for(wire_name: str) -> PublishModeDescriptor | None:
    """Look up a mode's descriptor by its wire name, or `None` if unknown."""
    return _BY_WIRE_NAME.get(wire_name)


def mirror_like_wire_names() -> tuple[str, ...]:
    """Site 1 (`publish.py::process_target`'s outer gate,
    `if target.mode in ("mirror", "flat-mirror")`) and site 4
    (`publish_sync.py::main`'s argparse `choices=`) both read this."""
    return tuple(d.wire_name for d in PUBLISH_MODES if d.is_mirror_like)


def mirror_entry_points() -> tuple[str, ...]:
    """Site 3's `_MIRROR_ENTRY_POINTS = ("sync_mirror", "sync_flat_mirror")`."""
    return tuple(
        d.entry_point for d in PUBLISH_MODES if d.is_mirror_like and d.entry_point
    )


def argparse_mode_choices() -> tuple[str, ...]:
    """Site 4's `p.add_argument("mode", choices=("mirror", "flat-mirror"))`."""
    return mirror_like_wire_names()


def dest_bootstrap_parametrize_wire_names() -> tuple[str, ...]:
    """Site 6's `MIRROR_MODES = ("mirror", "flat-mirror")`, the tuple
    `test_publish_dest_bootstrap_git_ancestor.py` parametrizes over.

    Deliberately not named `test_*`: pytest collects `test_`-prefixed
    callables, and a production accessor carrying that prefix reads as a
    test case to every future reader and to any lint or coverage config
    keyed on the same convention.
    """
    return mirror_like_wire_names()
