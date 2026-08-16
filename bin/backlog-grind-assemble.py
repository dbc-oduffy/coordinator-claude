# backlog-grind-assemble — CLI trampoline over claude-klabauter
# coordinator_core.backlog_grind_assemble (the cadence-parameterized
# computed-skill assembler replacing the five duplicated backlog-grind
# spines: bug-blitz, mise-en-place, bug-sweep, debt-triage, dogfood).
# Direct-import variant (template-variant #1, mirrors coordinator/bin/
# pickup-assemble and baton-assemble): a plain in-process function call
# after resolving CLAUDE_KLABAUTER_ROOT, no cc_invoke/IPC hop.
#
# Contract: DoE-claude coordinator/docs/wiki/computed-skills.md
# Spec backlink: docs/plans/2026-07-26-backlog-grind-computed-frontage.md,
# chunk C5
# Registration seam: a new engine capability registers by shipping a thin
# bin/ trampoline over an in-process coordinator_core module — same shape as
# every other direct-import CLI in this tree (pickup-assemble, baton-assemble,
# archive-stamp-cli).
#
# Subcommands:
#   brief <cadence> [--run-id <run-id>]
#     Computes and returns the decision object for the named cadence
#     ("bug-blitz" | "mise-en-place" | "bug-sweep" | "debt-triage" |
#     "dogfood"). READ-ONLY — mutates nothing. Dispatched to
#     coordinator_core.backlog_grind_assemble.main() (C3's own entrypoint),
#     which receives this trampoline's argv VERBATIM — flags are parsed
#     there, never mirrored here, so a new brief flag needs no edit to this
#     file. (The pre-2026-08-04 comment here advertised `--decisions`/
#     `--json`; neither was ever implemented by `main()`, which silently
#     ignored them. Unrecognized tokens are now a usage error.)
#     `--run-id` names which run of the asking surface is asking — for
#     mise-en-place, the `state/mise-inventory/<run-id>.md` record whose
#     range the Phase-6 verdict is computed over. Ratified 2026-08-04
#     (cross-repo/inbox/2026-08-04-doe-claude-em-mise-run-id-carrier-env-
#     breaks-windows.md) as a FLAG rather than an environment variable:
#     `VAR=value command` is not a line cmd.exe parses, so an env carrier is
#     unreachable through backlog-grind-assemble.cmd — the Windows P0 path.
#   mint-run-id <cadence>
#     Mints a fresh run identity for the named cadence and prints it as a
#     single JSON object carrying `run_id` and `inventory_path` (the latter
#     repo-relative, `state/mise-inventory/<run_id>.md`, on every platform
#     -- never machine-absolute). READ-ONLY -- and specifically NEVER
#     creates `state/mise-inventory/` itself: that directory's ABSENCE is
#     `readers_mise`'s own Phase-0-vs-Phase-6 self-gate, so minting the
#     directory into existence would flip every Phase-0 run into looking
#     like Phase 6. Today only `mise-en-place` claims this verb; a cadence
#     no reader claims is a usage error (exit 2) naming the cadence, never
#     an exit-0 mint. The minted id is a flag/stdout carrier only, same as
#     `--run-id` above -- never an environment variable (the `cmd.exe`
#     rationale spelled out for `--run-id` above applies verbatim). The
#     caller passes the minted value straight back as
#     `brief mise-en-place --run-id <minted>`. Dispatched to
#     coordinator_core.backlog_grind_assemble.main() (C1's own
#     `_main_mint_run_id` dispatch), which receives this trampoline's argv
#     VERBATIM -- the verb's own FLAGS are parsed there and need no mirror
#     here. The verb NAME is a different matter: `main()` below carries
#     both a subcommand allowlist and a dispatch chain ending in a bare
#     `main_drop` fallthrough, so a new subcommand needs BOTH edited.
#     Allowlisting alone routes the new verb into `drop` -- exit 0, drop's
#     payload, silently wrong. Observed 2026-08-04 while adding this verb;
#     `TestTrampolineDispatchRouting` now pins every allowlisted
#     subcommand to its intended callee so the next one fails loudly.
#   apply <cadence> [--session-id <id>] [--decisions <json>]
#     Recomputes the brief and executes its directives[] through the closed
#     dispatch table. MUTATING. Dispatched to
#     coordinator_core.backlog_grind_assemble.apply.main_apply() (C4's own
#     entrypoint) — a sibling module to the `brief`-only `main()` above, not
#     the same function; see that module's own docstring for why apply/drop
#     live apart from brief.
#   drop <cadence> [--session-id <id>]
#     AC4's inverse subcommand. backlog-grind-assemble carries no
#     claim/artifact-lifecycle state to release — a deliberate, documented
#     no-op returning success, provided for interface parity with
#     pickup_assemble/baton_assemble's own drop(). Dispatched to
#     coordinator_core.backlog_grind_assemble.apply.main_drop().
#
# Exit codes (locally scoped to this CLI, NOT inherited — see the contract's
# own § Exit-code contract):
#   0 — OK.
#   1 — business failure.
#   2 — usage error (malformed arguments, malformed --decisions JSON,
#       unrecognized subcommand).
#   3 — transport failure (CLAUDE_KLABAUTER_ROOT unresolvable, coordinator_core import
#       failure, or no enclosing git worktree) — this trampoline's own
#       transport failure, distinct from any business exit code.

# --- routing half: this file is now a thin shim over entry_point_shim.run_target ---
from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from entry_point_shim import run_target  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_target("backlog-grind-assemble", sys.argv[1:]))
