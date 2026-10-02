# Perforce provider seam — the frontmatter slots a plugin layers first-class Perforce onto

<!-- Purpose: the contract a plugin conforms to when it layers Perforce capability onto the
     coordinator's second-class floor. Example-game-repo is the first provider (first-class Perforce owner).
     NOT a place to widen the p4 verb fence, NOT a registry of p4 commands, NOT a submit gate —
     the gate belongs to the provider's own tool. -->

This is the seam a plugin conforms to when it layers submit, asset checkout, locks, streams, or
anything Unreal-shaped onto the coordinator's Perforce floor (`coordinator/docs/wiki/portability/perforce-second-class.md`).

## Where the slot values live

In the repo's own `coordinator.local.md` frontmatter, beside the `vcs_mirror: p4` marker, as
`p4_submit_tool` and `p4_checkout_tool`, written by `p4.register_workspace`. A key that is absent
is an empty slot.

There is no plugin-root scan and no loader: the coordinator reads a file it already reads, and
this document is the whole seam — the same shape `project-rag` layers through, a producer-contract
doc rather than a runtime extension point. The slot values' shape — two key names and one
`mcp__<server>__<tool>` regex — is normative here, not pinned by any machine-readable schema.

## The slots

| Slot | Empty (no provider) | Filled |
|---|---|---|
| `submit_tool` | Submit is refused: "no Perforce submit provider installed". | The agent calls the named tool with the session changelist number. |
| `checkout_tool` | The checkout-before-edit guard denies a binary or `+l` target and says to route the change to the editor. | The same deny names this tool as the way to open the file. |

**A slot names a fully qualified MCP tool** (`mcp__<server>__<tool>`), invoked as a **direct MCP
tool call** — never a by-name dispatcher — because a direct call is what fires the harness's
human-confirmation prompt on a tool that declares it; a by-name route would refuse such a tool and
fail closed. The confirmation gate is the provider's and only the provider's.

**Submit takes the changelist number and the repo key as input.** The coordinator reads `p4_change`
from the session read contract below and passes it as an integer `changelist`. The field is a
decimal string on disk; parsing it is the caller's step, and the caller never parses provider output
to find the number instead. It passes `repo_key` in the same call: every identity key is named
`p4.<repo_key>.*`, so a provider without the key cannot reach identity at all, and an MCP server
need not be running anywhere near the repo it is submitting for. A provider never derives the key
from its own cwd, a stream path or a client name.

**A submit provider owns the shelf and the renumbering.** The coordinator's push leaves the
changelist both opened and shelved, and Perforce refuses a submit from that state either way. The
provider is what deletes or reverts the shelf, submits, and resyncs; the coordinator never does.
Submitting renumbers the changelist whenever a higher one exists, so a provider records the number
the server returned (`oldChange` in `-ztag` output names the old one) — nothing may keep treating
the pre-submit number as live.

**Submit is user-bound always, and client-bound for the numbered-changelist path.** The session
changelist belongs to the machine-local `p4.<repo_key>.user` and to the client that opened the
files. Another user is refused whatever the route, superuser included, and `submit` has no `-f`.
`submit -c <n>` is refused from any other client of the same user. Only `submit -e <n>` — the shelf
path, and only once the owning client has released the files with `revert -k` — works from a
second client of that user. A provider that cannot run as the owning user fails loud rather than
reassigning ownership.

## Session read contract (stable for providers)

A provider reads these facts; it never re-derives them. The session fields come from the engine op
`p4.session_state`, which is the read surface — no consumer imports a reader module or parses
`meta.json` itself.

| Fact | Where | Written by |
|---|---|---|
| Is this a Perforce workspace? | `vcs_mirror: p4` in the repo's `coordinator.local.md` frontmatter | `p4.register_workspace`, run by the `/repo-setup` Perforce step |
| The workspace's registry key | `p4_repo_key` in the same frontmatter — the `<repo_key>` every machine-local key below is named with, and a required param of `p4.session_state` | `p4.register_workspace`, at registration |
| Session changelist number | `p4_change` — a **decimal string**, e.g. `"12345"` — in `<git-common-dir>/coordinator-sessions/<session-id>/meta.json`. It names the *pending* changelist and goes stale the moment anyone submits it. | the engine, on first p4-gated write or push |
| Git HEAD when that changelist was minted | `p4_base_sha` in the same `meta.json` | the engine, at the same moment |
| Time of the last `shelve -r` of that changelist | `p4_shelved_at` (ISO-8601 UTC), absent until the first shelve | the engine, on each successful push shelve |
| Git HEAD at that shelve | `p4_shelved_sha` — equal to HEAD means the shelf is current and the push's p4 leg no-ops | the engine, at the same moment |
| Server, user, client | machine-local `p4.<repo_key>.port`, `.user`, `.client` | `p4.register_workspace`, run by the `/repo-setup` Perforce step |
| The **client's** root | machine-local `p4.<repo_key>.client_root` — what a provider opening its own p4 connection wants | `p4.register_workspace`, from the matched `Root`/`AltRoots` entry |
| The **git repo's** root | machine-local `p4.<repo_key>.repo_root` — what a caller wanting this repo wants | `p4.register_workspace`, at the same moment |

These two are not interchangeable and the difference is not hypothetical: a client `Root` may be a
parent directory holding several projects, so taking one where the other is meant fails silently in
exactly that layout, both values being real directories.

Identity is machine-local because a client name belongs to one machine and a user to one person.
Neither is ever written to a tracked file. `p4_repo_key` is the opposite and so lives in tracked
frontmatter: it is the same minted identity on every box, and putting it machine-local would make
the key needed to read the machine-local store unreachable without already having it. A provider launching its own Perforce server connection
(for example p4mcp) takes identity from these keys instead of keeping a second copy.

A provider reads these keys through the `machine-local` CLI, never by path: `machine-local get
p4.<repo_key>.port` for one key, `machine-local dump` for a batch read of all of them in one
process rather than one per key. `machine-local has <key>` exits 0 when the key is set, 1 when
unset, and 2 on operational failure — the 2 is what distinguishes "no such key" from "could not
read the store." `machine-local path` prints the backing file, but the path is not the interface:
it moves with the settings home. A provider that must also work with no coordinator installed
treats the binary not resolving as "no coordinator identity" and falls back to its own discovery.

`p4_change` names a pending changelist. If a human submits or deletes it, the engine mints a fresh
one on next use and rewrites the field. A provider reads the field at call time and never caches it
across calls.

## Registration

**Registration is invocable by any surface, and that is the seam.** The engine op
`p4.register_workspace {repo_root, repo_key, port, user, client}` — plus optional
`p4_submit_tool` / `p4_checkout_tool` — is the only sanctioned writer of the `p4.<repo_key>.*` row.
It is not EM-only: cockpit registers a Perforce workspace through its own desktop affordance and
calls this op rather than writing the machine-local store directly, which would fork the surface
and rot on the next shape change. `/repo-setup`'s Perforce step is the human-facing path over the
same op, not a second mechanism.

The op writes the marker, `p4_repo_key`, the machine-local identity, `.p4ignore` listing `.git/`, and a `* -text`
line-ending pin so Perforce's `LineEnd` is the only converter. It confirms the client before
writing: `Root` or `AltRoots` must *contain* the repo and `Host` must match, and where it doesn't,
the caller picks — the op never guesses. No caller passes a client root: the git repo lives inside
the workspace by construction, so a second parameter for a fact the op already verifies would be a
second source of truth with no tiebreaker. Note that containment is not equality — a client `Root`
may be a parent directory holding several projects, so `p4.<repo_key>.client_root` is not
interchangeable with `p4.<repo_key>.repo_root`.

**Identity has two paths, not one.** The caller supplies `{port, user, client}` directly —
that is the registering surface's path. P4CONFIG discovery is the other, for a caller that has a
workspace but not the values, and it is honoured only inside this one call.

**`repo_key` is cockpit's minted registry identity and is validated for shape only** — single
slash, lowercase, e.g. `p4-studio/game-main`. Never derive one from a directory name, a stream
path or a client name. Cockpit's rule is resolve-first, mint-last, derive-never, and their resolver
declining to match is a refusal to admit the workspace, not licence to invent a key.

Until the op lands in the engine, registration is unavailable. Never hand-write the marker. A
marker with no machine-local row fails every p4-gated op with a typed `p4_workspace_unregistered`,
and never falls back to ambient `P4*` environment variables.

## Validation and failure

- A slot value that is not of the `mcp__<server>__<tool>` form is not a tool name. The agent does
  not call it and says so; it never falls back to a by-name dispatcher or a shell-out.
- A repo names at most one tool per slot, because the slot is a frontmatter key. There is no
  multi-provider arbitration to get wrong.
- A named tool the MCP server does not expose fails at call time, as an ordinary missing-tool
  error. Nothing pre-validates it.

## What a provider cannot do

- **Widen the p4 verb fence.** No slot key adds an allowed verb. A provider works over MCP,
  and the fence (which sees only Bash and PowerShell) never observes that. A deny-fence a plugin
  could widen would be a route around it.
- **Change the floor.** The session changelist, the marker, reconcile-then-shelve on push, and the
  checkout-before-edit guard for text files belong to the coordinator.
- **Run in a git-only repo.** Every slot is read only behind the `vcs_mirror: p4` marker. A repo
  without it reads no slot and pays nothing.
