"""Invariant core and strictest-story fallback for the environment switch.

Spec backlink: state/handoffs/2026-09-06_210003_roadmap-cloudem-04.md
(roadmap cloud-em-2026-09-06, cluster C14). Research backlink:
state/roadmap/cloud-em-2026-09-06/research-corpus/invariant-core-and-strictest-default.md.

This module is the safety half of the environment-switch mechanism: the
enumerated core no composed story may omit (`CORE_RULE_IDS`,
`validate_story`, `register_story`), and the fallback story returned when
the machine cannot tell which environment it is in
(`resolve_environment_story`, `STRICTEST_STORY`).

Mirrors `_posture.py`'s RESOLUTION SHAPE -- a module-level docstring naming
every failure path, one named constant as the sole fallback target, and a
resolver function that is the enforcement point and never raises -- and
INVERTS its endpoint. `_posture.py` fails open to "precision" because
posture answers *what surfaces* to an already-trusted local operator: the
safeguard itself never changes, so degrading all the way to "change
nothing" is safe by construction. This module answers a different
question -- *what is true here*, i.e. which rules apply at all -- and an
unrecognised environment must fail toward the story that keeps every rule,
never toward the one a local operator would find least intrusive. Fail-open
there is fail-closed here: the two mechanisms share a shape and resolve to
opposite ends of their respective spectra, and that inversion is the entire
point of this file existing separately from `_posture.py` rather than
extending it.

Resolution is a LADDER, not six independent switches, and the difference
is load-bearing enough to state before the modes are listed. The rungs are:
run `probe` under a bounded timeout, else read the sentinel, else resolve
the recovered id against the registry, else the registry name against the
admitted-story set. Each mode below terminates at `STRICTEST_STORY` when no
LOWER RUNG ANSWERS -- not unconditionally. A probe that times out beside a
readable sentinel resolves via that sentinel, and that is deliberate: the
question this module answers is "can the machine tell where it is", and a
sentinel that answers means it can. A timed-out probe is not evidence that
an independent detection source is wrong. `test_ladder_probe_timeout_falls_
through_to_a_readable_sentinel` pins this so it stays a decision rather than
drifting into an accident.

The six independently reachable failure modes, each detected at its own
step, each terminating at `STRICTEST_STORY` and never at any other value:

  1. **Detection fails** -- the environment-identification step itself
     raises or cannot decide. Caught at the top of
     `resolve_environment_story`'s body, the same way `_posture.py`'s
     frontmatter-parse step failing returns before rung 1 ever produces a
     value.
  2. **Registry unreadable** -- the environment-id -> story registry file
     is missing, unreadable, or unparseable. Named as ONE class (mirroring
     `_posture.py`'s "missing file, unreadable file, unparseable content"
     grouping) via `_ResolutionFailure`, caught internally and never
     propagated out of the resolver.
  3. **Sentinel missing** -- the on-disk marker asserting "this is
     environment X" is absent. Falls through exactly like `_posture.py`'s
     rung-2 identity-file read: absence terminates at the fallback, not at
     a laxer default.
  4. **Probe times out** -- an active disambiguation probe (network,
     filesystem, or caller-supplied) is given an explicit bounded timeout;
     an unbounded probe is itself a hang, not a resolution step.
  5. **Unknown environment id** -- the registry resolves to a story name
     that was never admitted via `register_story`. Handled by the
     admitted-story lookup returning nothing, not by a separate enum
     check: the registry of admitted stories IS the enum, so there is no
     second list to fall out of sync with it.
  6. **Torn write** -- a registry or story artifact caught mid-write
     (partially written, truncated, or otherwise structurally broken) is
     treated as case 2, "registry unreadable" -- never as a partial story
     to interpret. A half-composed story must never be read as if it were
     a smaller, valid one.

`resolve_environment_story` NEVER raises and NEVER returns `None` -- every
one of the six paths above returns `STRICTEST_STORY`. `validate_story` and
`register_story` are the opposite of fail-open by design: they DO raise,
because enforcement failing loudly is the whole point (a warning is not a
remediation for a silent core omission -- see the `warn-is-not-a-
remediation-for-silent-skip` lesson cited in the research corpus §4).

WHAT A COMPOSED STORY'S `rule_ids` ARE ACCOUNTED AGAINST: a non-strictest
story's `rule_ids` is built from
`state/audits/2026-09-06-doctrine-rule-class-register.yaml`, an
ENVIRONMENT-PREMISE extraction, not a doctrine census. A rule absent from
the register carries no environment-scoped premise captured there -- it does
not mean no rule exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

# the failure that reaches it. A `_FAIL_CLOSED_` prefix would name the
STRICTEST_STORY_NAME = "strictest"

#   story omits this member. Its ENFORCEMENT MODE is venue-conditional and
CORE_RULE_IDS: frozenset[str] = frozenset(
    {"naked-python-mandate", "cross-repo-write-gating"}
)


@dataclass(frozen=True)
class Story:
    """One composed environment story: a name, its prose, and the set of
    rule ids it carries. `rule_ids` is the accounting surface `validate_story`
    checks against `CORE_RULE_IDS` -- prose is never parsed to infer coverage."""

    name: str
    prose: str
    rule_ids: frozenset[str] = field(default_factory=frozenset)


class CoreOmissionError(Exception):
    """Raised by `validate_story`/`register_story` when a story's
    `rule_ids` do not cover `CORE_RULE_IDS`. Names each missing member --
    never a bare "invalid story" -- so the caller sees exactly which core
    rule the story dropped."""


class _ResolutionFailure(Exception):
    pass


class ProbeTimeoutError(Exception):
    pass


_STRICTEST_PROSE = (
    "Every rule in the doctrine corpus applies, in full, with no omission "
    "and no environment-scoped exception. Code is authored for every host "
    "this fleet runs on, not only the one producing the diff. Every "
    "cross-repo write is gated exactly as if a reviewer with full context "
    "will read it, because that is always true of a change destined for "
    "review. Nothing here is relaxed on the theory that some party is "
    "absent; where presence cannot be told, the rule stays."
)

STRICTEST_STORY = Story(
    name=STRICTEST_STORY_NAME,
    prose=_STRICTEST_PROSE,
    rule_ids=CORE_RULE_IDS,
)

_registry: dict[str, Story] = {}


def validate_story(story: Story) -> None:
    """Raise `CoreOmissionError` naming each missing core member, or return
    silently if `story.rule_ids` is a superset of `CORE_RULE_IDS`. This is
    the enforcement point: it raises rather than warns, because a story
    that silently omits a core rule and one that does not are
    indistinguishable from the outside once both simply run."""
    missing = CORE_RULE_IDS - story.rule_ids
    if missing:
        raise CoreOmissionError(
            f"story {story.name!r} omits core rule(s): {sorted(missing)!r}"
        )


def register_story(story: Story) -> None:
    validate_story(story)
    _registry[story.name] = story


def _read_registry_entry(registry_path: str, environment_id: str) -> Optional[str]:
    try:
        with open(registry_path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError as exc:
        raise _ResolutionFailure(str(exc)) from exc
    except UnicodeDecodeError as exc:
        raise _ResolutionFailure(str(exc)) from exc

    prefix = environment_id + ":"
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
            if not value:
                raise _ResolutionFailure(
                    f"torn registry entry for {environment_id!r}"
                )
            return value
    return None


def _read_sentinel(sentinel_path: str) -> str:
    try:
        with open(sentinel_path, "r", encoding="utf-8") as handle:
            content = handle.read().strip()
    except OSError as exc:
        raise _ResolutionFailure(str(exc)) from exc
    if not content:
        raise _ResolutionFailure(f"empty sentinel at {sentinel_path!r}")
    return content


def resolve_environment_story(
    *,
    registry_path: Optional[str] = None,
    sentinel_path: Optional[str] = None,
    probe: Optional[Callable[[], str]] = None,
    probe_timeout_s: float = 2.0,
) -> Story:
    """Resolve the environment story for this session.

    Order: run `probe` (if given) under a bounded timeout to detect the
    environment id; if no probe is given or it fails/times out, fall back
    to reading `sentinel_path`; resolve the recovered environment id
    against `registry_path` to a story name; look the name up in the
    registry admitted via `register_story`.

    NEVER raises and NEVER returns `None` -- every one of the six failure
    modes named in the module docstring returns `STRICTEST_STORY`. Callers
    importing this module get the fail-CLOSED contract unconditionally, not
    just for the guarded I/O paths -- any other exception raised anywhere in
    this body is also caught and answered with `STRICTEST_STORY`.

    `probe_timeout_s`: bounded wall-clock budget for `probe`. An unbounded
    probe is itself a hang, not a resolution step, so `probe` is always run
    through a timeout wrapper regardless of the value passed here.
    """
    try:
        environment_id = None

        if probe is not None:
            try:
                environment_id = _run_probe_with_timeout(probe, probe_timeout_s)
            except Exception:
                environment_id = None

        if environment_id is None:
            if sentinel_path is None:
                return STRICTEST_STORY
            environment_id = _read_sentinel(sentinel_path)

        if registry_path is None:
            return STRICTEST_STORY

        story_name = _read_registry_entry(registry_path, environment_id)

        if story_name is None:
            return STRICTEST_STORY

        story = _registry.get(story_name)
        if story is None:
            return STRICTEST_STORY

        validate_story(story)
        return story
    except Exception:
        return STRICTEST_STORY


def _run_probe_with_timeout(probe: Callable[[], str], timeout_s: float) -> str:
    import threading

    result: list[str] = []

    def _target() -> None:
        try:
            result.append(probe())
        except Exception:  # pragma: no cover - result stays empty, same as a timeout
            pass

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout_s)

    if not result:
        raise ProbeTimeoutError(f"probe exceeded {timeout_s}s or returned no value")
    return result[0]
