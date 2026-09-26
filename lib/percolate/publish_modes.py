
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PublishModeDescriptor:

    wire_name: str
    is_mirror_like: bool
    entry_point: str | None
    bind_kwargs: dict[str, object] = field(default_factory=dict)
    accepts_renamed_dir_names: bool = False
    accepts_sweep_top_level_orphans: bool = False
    accepts_foreign_dir_names: bool = False
    is_bootstrap_bearing: bool = False


# (`ensure_required_targets.py::_find_mirror_row`) is a NAMED-ROW lookup for
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
    accepts_foreign_dir_names=True,
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

_REPO_CUT_DESCRIPTOR = PublishModeDescriptor(
    wire_name="repo-cut",
    is_mirror_like=False,
    entry_point="sync_repo_cut",
    bind_kwargs={"dry_run": False},
    accepts_renamed_dir_names=False,
    is_bootstrap_bearing=True,
)

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
    return _BY_WIRE_NAME.get(wire_name)


def mirror_like_wire_names() -> tuple[str, ...]:
    return tuple(d.wire_name for d in PUBLISH_MODES if d.is_mirror_like)


def mirror_entry_points() -> tuple[str, ...]:
    """Site 3's `_MIRROR_ENTRY_POINTS = ("sync_mirror", "sync_flat_mirror")`."""
    return tuple(
        d.entry_point for d in PUBLISH_MODES if d.is_mirror_like and d.entry_point
    )


def argparse_mode_choices() -> tuple[str, ...]:
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
