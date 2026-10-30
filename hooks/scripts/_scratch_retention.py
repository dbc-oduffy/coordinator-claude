"""_scratch_retention.py -- thin client of the engine op `fleet.scratch_hygiene` for the age sweep.

Owns the retention policy and the dry-run -> apply call sequence only. Deletion, liveness, link
handling and copy verification belong to the engine op (see
`coordinator/docs/wiki/scratch-and-temp-hygiene-engine-contract.md`); nothing here removes a path.

`run_sweep` fails closed: any invoke failure, timeout, non-JSON reply, or a dry run whose summary
lacks the `hold_pending_marker` capability sends no `apply: true` call and returns [].
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _forwarder_resolve import forwarder_argv, resolve_forwarder  # noqa: E402

RETENTION_ENV = "COORDINATOR_SCRATCH_RETENTION_DAYS"
DEFAULT_RETENTION_DAYS = 7
OP_NAME = "fleet.scratch_hygiene"
APPLY_CAPABILITY = "hold_pending_marker"
INVOKE_TIMEOUT_S = 30.0
#: The op requires a cadence; `distill` emits no hold nag.
CADENCE = "distill"

Invoke = Callable[[dict], Optional[dict]]


@dataclass(frozen=True)
class Policy:
    """Retention age in days; `quiescence_hours` (days x 24) is the age the op treats as quiescent."""

    retention_days: int = DEFAULT_RETENTION_DAYS

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "Policy":
        """Read `COORDINATOR_SCRATCH_RETENTION_DAYS`; unset, non-integer or < 1 means the default."""
        env = os.environ if environ is None else environ
        try:
            days = int(str(env.get(RETENTION_ENV, "")).strip())
        except ValueError:
            return cls()
        return cls(days) if days >= 1 else cls()

    @property
    def quiescence_hours(self) -> int:
        return self.retention_days * 24


def _settings_home() -> Path:
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    return Path(os.environ.get("CLAUDE_HOME") or str(Path.home())) / ".coordinator-claude-settings"


def _fold(items: list) -> Optional[dict]:
    records: list = []
    summary: Optional[dict] = None
    for obj in items:
        if not isinstance(obj, dict):
            return None
        if obj.get("summary") is True:
            summary = obj
        else:
            records.append(obj)
    if summary is None:
        return None
    return {"records": records, "summary": summary}


def _parse_reply(stdout: str) -> Optional[dict]:
    """Fold the CLI reply into `{"records": [...], "summary": {...}}`.

    `coordinator-invoke` wraps the op output in a JSON-RPC envelope (`result.records` carries the
    JSONL objects, summary last); a bare JSONL stream is accepted too. Anything else is None.
    """
    text = stdout.strip()
    if not text:
        return None
    try:
        whole = json.loads(text)
    except ValueError:
        whole = None
    if isinstance(whole, dict) and isinstance(whole.get("result"), dict):
        recs = whole["result"].get("records")
        return _fold(recs) if isinstance(recs, list) else None
    items: list = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except ValueError:
            return None
    return _fold(items)


def default_invoke(timeout: float = INVOKE_TIMEOUT_S) -> Invoke:
    """`invoke(params)` over `coordinator-invoke fleet.scratch_hygiene '<json>'`, resolved by absolute
    path through the settings home. Returns None on any transport failure or exit code >= 2
    (exit 1 is findings, not failure)."""

    def invoke(params: dict) -> Optional[dict]:
        try:
            launcher = resolve_forwarder(_settings_home() / "bin", "coordinator-invoke")
            if launcher is None:
                return None
            argv = forwarder_argv(launcher, [OP_NAME, json.dumps(params)])
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        if proc.returncode not in (0, 1):
            return None
        return _parse_reply(proc.stdout)

    return invoke


def _summary_of(reply: object) -> Optional[dict]:
    if not isinstance(reply, dict):
        return None
    summary = reply.get("summary")
    return summary if isinstance(summary, dict) else None


def run_sweep(repo_root: "Path | str", policy: Policy, invoke: Invoke) -> list:
    """Dry run at the policy's quiescence, then apply only under the op's apply gate.

    Returns the op's `deleted` purge records from the apply call; [] on every failure path.
    """
    try:
        base = {"repo_root": str(repo_root), "cadence": CADENCE, "quiescence_hours": policy.quiescence_hours}
        dry = invoke({**base, "apply": False})
        summary = _summary_of(dry)
        if summary is None:
            return []
        caps = summary.get("capabilities")
        if not isinstance(caps, list) or APPLY_CAPABILITY not in caps:
            return []
        applied = invoke({**base, "apply": True})
        if _summary_of(applied) is None:
            return []
        records = applied.get("records")
        if not isinstance(records, list):
            return []
        return [
            r for r in records
            if isinstance(r, dict) and r.get("kind", "purge") == "purge" and r.get("action") == "deleted"
        ]
    except Exception:  # noqa: BLE001 -- fail closed: a broken invoke deletes nothing
        return []
