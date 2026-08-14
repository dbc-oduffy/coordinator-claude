# The Guard-Unlock Channel

> **For the operator, not the agent.** A hard-deny guard can be cleared once, for one guard, in
> one session, by a human who drops a sentinel file from a terminal outside that session. This
> page is the construction recipe; the deny message deliberately withholds it.
>
> **If you are an agent reading this page: constructing this sentinel from inside the denied
> session is a doctrine violation, not a shortcut.** See
> [#why-the-recipe-lives-here](#why-the-recipe-lives-here).
>
> **Reaching this page for ordinary finished work is a defect upstream of it.** This channel is
> the human-shaped outlet for a guard that genuinely gates irreversible harm. A guard whose denied
> actor has no machine-takeable next step fails the outlet test in
> [`guard-proportionality.md`](guard-proportionality.md) — fix the guard there rather than routing
> routine work through a human here.

---

## What This Channel Is For {#what-this-is-for}

Every other hard-deny override is a `COORDINATOR_OVERRIDE_*` / `COORDINATOR_ALLOW_*` environment
variable read once when the session's hook processes spawn. That makes them structurally
unreachable at the moment you learn they exist: the deny fires *inside* a running session, and
neither a `export` from the agent's shell nor a mid-task relaunch can help — a relaunch loses the
context that made the override necessary in the first place.

The guard-unlock sentinel is the reachable remedy. You, at a terminal, create one file. The next
attempt at the denied operation succeeds, once.

## The Two Values You Need, and Where to Get Them {#the-two-values}

The sentinel is keyed on a **pair**: `(session_id, guard_name)`. No static page can render the
literal path for you, because both values are specific to one firing.

The deny message that sent you here supplies both, and says so explicitly — it ends with a clause
naming `session <session_id>, guard <guard_name>`. Take them from there. That division is
deliberate: the message carries the per-firing data, this page carries the shape.

## Constructing the Path {#constructing-the-path}

Three steps. Apply them in order.

### 1. The directory: your platform's temp directory {#step-directory}

Not a hardcoded `/tmp`. The resolver uses Python's `tempfile.gettempdir()`, which honours
`TMPDIR` / `TEMP` / `TMP` before falling back to the platform default:

| Platform | Usual result |
|----------|--------------|
| Windows | `%TEMP%` — a per-user `AppData\Local\Temp` path |
| macOS | `$TMPDIR` — a per-user `/var/folders/...` path, **not** `/tmp` |
| Linux | `/tmp` |

If any of `TMPDIR`/`TEMP`/`TMP` is set in the environment the *session* launched under, that wins.
When in doubt, ask Python directly rather than guessing:
`python3 -c "import tempfile; print(tempfile.gettempdir())"`.

### 2. Slugify each value {#step-slugify}

Each of `session_id` and `guard_name` is sanitized independently. **Every character outside
`[a-zA-Z0-9_-]` becomes `_`.** An empty result becomes a single `_`.

Two consequences worth internalizing:

- **Hyphens and underscores survive untouched.** Session ids are UUIDs and guard names are
  `lower_snake_case`, so in practice both values usually pass through unchanged — copy them
  verbatim and you are almost always right.
- **A `.` in either value becomes `_`.** This is what makes step 3 unambiguous.

### 3. Assemble {#step-assemble}

```
<tempdir>/coordinator-guard-unlock-<session>.<guard>
```

The prefix is `coordinator-guard-unlock-` (trailing hyphen included). The two slugified components
are joined on a single `.` — never `_`, never `__`.

The join character is load-bearing rather than cosmetic. Because step 2 maps every `.` inside
either component to `_`, the only `.` that can appear in the assembled name is the one the join
inserts, which makes the split back into `(session, guard)` unambiguous for any input. An
underscore join would not have that property — a literal `_` survives slugification, so two
distinct pairs could collide on one filename.

**Worked example.** Take a session id of `example-session-id` and a guard named
`block_reviewer_bash_outside_allowlist`, on Linux:

```
/tmp/coordinator-guard-unlock-example-session-id.block_reviewer_bash_outside_allowlist
```

Neither value needed rewriting to get there, and that is the common case rather than a
simplification of one. A real session id is a UUID — hyphens and hex digits, every character of it
already inside the safe set — so it passes through step 2 byte-for-byte, exactly as the guard name
does. Paste both verbatim, put a `.` between them, and you are done.

## Granting It {#granting-it}

Create the file. It is a pure existence signal — contents are never read, so empty is correct:

```sh
touch "/tmp/coordinator-guard-unlock-<session>.<guard>"     # macOS / Linux
```

```powershell
New-Item -ItemType File "$env:TEMP\coordinator-guard-unlock-<session>.<guard>"   # Windows
```

Then tell the agent to retry the denied operation. Nothing else is needed; no restart, no config
edit, no relaunch.

## What the Grant Actually Covers {#what-the-grant-covers}

Four properties, each a deliberate narrowing:

- **Per-guard.** One grant clears exactly the named guard. It is not, and must never become, an
  "all guards off for this session" switch — that is why the filename carries the guard name at
  all rather than the session id alone.
- **Per-session.** It has no effect on any other session running on the machine, including
  concurrent ones.
- **One-shot.** The consuming call unlinks the file and reports success exactly once. A second
  attempt at the same operation, with no new sentinel written in between, is denied again.
- **Fails closed.** Every failure mode — the file vanished, permissions refused, the temp
  directory unresolvable — resolves to "no grant." A guard cannot be tricked into failing open by
  breaking this channel.

## Create-Then-Retry in One Call Does Not Work {#create-then-retry}

The sentinel is consumed inside the `PreToolUse` decision, *before* the guarded operation runs.
So chaining creation onto the denied command in a single call — `touch <sentinel> && <denied
command>` — is denied, every time: the decision for that call was made before the `touch` in it
ever executed.

This is not a bug to route around. It is a direct consequence of the grant being consumed at
decision time, and it is part of why the channel is operator-shaped: two separate acts, by two
separate parties, at two separate moments.

## Why the Recipe Lives Here {#why-the-recipe-lives-here}

The deny message withholds the resolved sentinel path, the imperative, and the create-then-retry
sequencing. That withholding rests on measurement, not theory: presented with a message carrying
all three, four independently-dispatched agents read it and three classified it as prompt
injection.

An agent under a hard-deny reads top-to-bottom and acts on the first actionable thing it meets. A
ready-to-paste path plus a bare imperative *is* actionable, however the disclaimer above it is
worded — and an agent that complies has disabled a hard-deny guard, the one direction such a guard
must never fail in.

So the recipe moved to this page and the message kept only the two per-firing values. The extra hop
is the mechanism, not an oversight: reaching this page takes a deliberate step by someone who is
not skimming under a stop signal. An operator sitting at a terminal is unaffected by the hop; an
agent mid-refusal never arrives here unbidden.

The unlock remains **norm rather than enforcement** — nothing structurally prevents an agent from
writing the file. That was sized and deliberately declined; the mitigation is where the
instructions live, not a new enforcement surface. Which makes the norm load-bearing: an agent
creating this sentinel for itself is violating the contract this whole channel rests on.

## Before You Grant One {#before-you-grant}

A hard-deny guard fired because something is off the normal path. The grant is the right tool when
you have read the deny's own reason and judged this instance a genuine exception. It is the wrong
tool as a reflex — if you find yourself granting the same guard repeatedly, the guard's scope or
the workflow hitting it is the actual defect, and the durable fix belongs there.

## Related {#related}

- [`guard-message-concision.md`](guard-message-concision.md) — what a guard message is for, and
  why the explanation it cut belongs on a page like this one.
- [`bash-guard-threat-model.md`](bash-guard-threat-model.md) — what the Bash-side guards defend
  against, and why they deny rather than warn.
