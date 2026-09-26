"""Shared gate for creating a session's directory under the session hub.

The hub is `<git common dir>/coordinator-sessions/`. A directory directly
under it is either a per-session hub directory named for a live session's id,
or one of the fixed store directories (`logs`, `decisions`, `memo-claims`,
`no-session`, ...) that the engine and hooks share. Nothing else belongs
there: the reaper collects per-session directories by walking that level, and
peer-claim adjudication reads it to enumerate live peers.

Several hooks keep per-session state -- cursors, PID locks, dedup markers,
calibration sentinels -- under their own `<hub>/<session_id>/`. Each one is a
hub-directory creator, and a hook is driven with whatever `session_id` its
payload carries: a benchmark, probe, or test supplies a synthetic one. Gated
only on a path-traversal charset check, every such invocation minted a hub
directory that no registrar claimed and no reaper collects, indistinguishable
from a live peer by inspection. 176 accumulated in this repo's hub before the
first creator was gated.

`session_id_is_real` is the shape gate: a real Claude Code `session_id` is a
uuid4, checked locally with no I/O, and it holds in every install.

NEGATIVE SPEC -- THIS IS NOT AN EXISTENCE GATE, AND MUST NOT BECOME ONE. The
obvious alternative ("only write into a hub directory some registrar already
claimed") is wrong here: the registrar that creates it,
`hooks.session_heartbeat`, round-trips the control-plane engine, so an
install without that engine has no claimed directory for any session and an
existence gate would silence every gated hook's per-session state at once.
Shape is checked locally and needs nothing installed.

STANDING LIMIT, NOT A DEFECT. The gate is uuid4-shaped, so a caller that
mints a non-UUID session id -- which the documented contract still permits --
gets no per-session hub directory. The fixed store directories, `no-session`
among them, are deliberately non-UUID and are created by their own owners,
never through this seam.
"""

import os
import re

_SESSION_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def session_id_is_real(session_id: object) -> bool:
    return isinstance(session_id, str) and bool(_SESSION_UUID_RE.match(session_id))


def ensure_session_dir(
    session_dir: "str | os.PathLike[str]", session_id: object
) -> bool:
    if not session_id_is_real(session_id):
        return False
    try:
        os.makedirs(os.fspath(session_dir), exist_ok=True)
    except (OSError, TypeError, ValueError):
        return False
    return True
