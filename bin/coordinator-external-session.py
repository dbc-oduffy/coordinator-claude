#!/usr/bin/env python3
"""Codex lifecycle bridge: engine registration and audience-specific context.

SubagentStart carries the parent's session ID; it never writes a host binding.
No child process is spawned. Installed hook deadlines bound best-effort delivery.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        event = args[args.index('--event') + 1]
        root = Path(args[args.index('--engine-root') + 1])
        if event not in ('SessionStart', 'SessionEnd', 'SubagentStart', 'UserPromptSubmit', 'PostToolUse', 'Stop', 'SubagentStop', 'PreCompact', 'PostCompact') or not root.is_absolute():
            raise ValueError('published engine root and lifecycle event are required')
        if not (root / 'coordinator_core' / '_engine_stamp').read_bytes():
            raise ValueError('published engine stamp is empty')
        if not (root / 'coordinator_core' / 'session' / 'external_registry.py').is_file():
            raise ValueError('published engine lacks session.external_registry')
        if event != 'SessionEnd' and not (root / 'coordinator_core' / 'host_hooks' / 'session_context.py').is_file():
            raise ValueError('published engine lacks host_hooks.session_context')
        if event not in ('SessionStart', 'SubagentStart', 'SessionEnd') and not (root / 'coordinator_core' / 'host_hooks' / 'codex_lifecycle.py').is_file():
            raise ValueError('published engine lacks host_hooks.codex_lifecycle')
        sys.path.insert(0, str(root))
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError('hook payload must be an object')
        payload['hook_event_name'] = event
        from coordinator_core.session import external_registry
        try:
            if event == 'SessionEnd':
                external_registry.unregister(payload.get('session_id'), payload=payload)
            elif event == 'SessionStart' and not payload.get('agent_id'):
                external_registry.register_current(payload)
        except Exception as exc:
            sys.stderr.write(f'external session registration unavailable: {type(exc).__name__}: {exc}\n')
        result = {}
        if event != 'SessionEnd':
            from coordinator_core.host_hooks.session_context import context
            if event in ('SessionStart', 'SubagentStart'):
                result = context(payload, dict(os.environ))
            else:
                from coordinator_core.host_hooks.codex_lifecycle import handle
                result = handle(payload, dict(os.environ))
        sys.stdout.write(json.dumps(result) + '\n')
        return 0
    except (Exception, SystemExit) as exc:
        sys.stderr.write(f'external session context unavailable: {type(exc).__name__}: {exc}\n')
        sys.stdout.write('{}\n')
        return 0


if __name__ == '__main__':
    if any(_a in ("-h", "--help") for _a in __import__("sys").argv[1:]):
        print("usage: coordinator-external-session [-h]\nprint the external session context (hook-driven bridge; takes no arguments)")
        raise SystemExit(0)
    raise SystemExit(main())
