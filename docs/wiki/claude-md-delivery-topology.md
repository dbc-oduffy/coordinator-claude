# CLAUDE.md delivery topology — what actually reaches whom

> This wiki exists because a previous account of this topology was wrong in a way that survived
> for months, propagated into plans and probe agents, and cost a roadmap its central design. Read
> this before reasoning about doctrine placement, boot cost, or what a subagent knows.

## The one-sentence correction

**There is exactly one always-on fleet-wide doctrine surface: `~/.claude/CLAUDE.md`.**
`coordinator/CLAUDE.md` is not a second one. It never was.

## What each surface actually is

| Surface | Reaches | When | Publishes OSS? |
|---|---|---|---|
| `~/.claude/CLAUDE.md` | **Every session in the fleet, and every dispatched subagent** except built-in `Explore`/`Plan` | At boot, and again after every compaction | No — it is personal |
| repo-root `CLAUDE.md` (e.g. `DoE-claude/CLAUDE.md`) | Sessions whose cwd is that repo, **and their subagents** | At boot | No |
| `coordinator/CLAUDE.md` | **Only DoE-claude sessions, and only after something Reads a file under `coordinator/`** | Lazily, not at boot | **No — absent from the publish allowlist** |
| `coordinator/templates/CLAUDE.md.tmpl`, `templates/postures/*.md` | **Nobody at runtime.** Percolation artifacts for external consumers | n/a | **Yes** — this is the distribution doctrine |

> **The meta-repo local-doctrine file this table used to list as a row (`CLAUDE.local.md`) no
> longer exists — it has been retired fleet-wide, not merely folded for one repo.** Both its
> tracked and derived `~/.claude`-side copies, and the install step that regenerated them, are
> deleted. It structurally loaded only for a session whose cwd was `~/.claude` itself, which
> nothing spawns for work any more — so, despite older descriptions of it as a live per-repo
> personal layer, it was never a real per-agent doctrine multiplier. Do not cite it as a current
> surface.

## The myth, and why it was sticky

The claim — stated in this repo's own `CLAUDE.md`, `claude-md-surfaces.md`, and
the OSS template we ship to strangers — was that `coordinator/CLAUDE.md` is *"delivered live as
plugin project-instructions"* / *"fleet-wide via `--plugin-dir`"*.

**It is false.** Delivery is ordinary **nested-CLAUDE.md lazy loading**: `coordinator/` is a child
directory of the repo root, and Claude Code loads a child-directory `CLAUDE.md` only when it reads
a file in that directory. Established by five parallel probes plus a live cross-repo verification
from a `claude-klabauter` session with the plugin confirmed loaded — a verbatim-recall probe for a
string unique to `coordinator/CLAUDE.md` returned NOT-PRESENT (commit `3c342db0`).

Three consequences, in severity order:

1. **No sibling-repo session has ever received coordinator doctrine.**
2. **Even in DoE-claude it is absent at boot**, arriving only after an incidental `coordinator/` Read.
3. **Nested CLAUDE.md does not survive `/compact`** the way a project-root file does.

### Why it survived so long

- **Our own doctrine asserted it.** Three separate always-loaded files stated the mechanism as
  fact. Anyone checking read the assertion, not the behaviour.
- **Convergence was not confidence.** Two independent probe agents *both* concluded "the plugin
  delivers it" — because both had read our doctrine and inherited the false prior. A yes/no
  question produced a confabulated "yes" from both. **What separated them was a verbatim-quote
  discriminator**: asking an agent to *recite a unique string* from the file, rather than asking
  whether it had the file. Use that shape when probing what is in a context window.
- **It was never falsifiable from inside DoE-claude.** Here, a `coordinator/` Read happens early
  and often, so the file *is* usually present by the time anyone looks — the failure is only
  visible from a sibling repo, or at boot before the first Read.

## Consequences you must not re-derive

- **`coordinator/CLAUDE.md` is not a low-cost sanctuary to move doctrine into.** It was briefly
  designed as one — put EM/PM-relational doctrine there because it's "EM-only and paid ×1." That
  design is wrong: a file that is absent at boot, invisible to siblings, and lost on compaction is
  not a safe home for load-bearing doctrine. You would trade a correctness regression for an
  amplification win.
- **The amplified surface is the ~60 KB of global + repo `CLAUDE.md`.** Under fan-out dispatch
  that is paid per agent — an N-agent wave pays it N+1 times. `coordinator/CLAUDE.md` is not part
  of that multiplier. (The retired meta-repo local-doctrine file never belonged in this sum: it
  loaded only for a session whose cwd was `~/.claude` itself, which nothing spawns for work.)
- **The OSS distribution is `templates/`, not `coordinator/CLAUDE.md`.** If you are looking for
  "the doctrine our consumers get," it is `templates/CLAUDE.md.tmpl` plus
  `templates/postures/{default,precision,substrate-free}.md`, all in the allowlist at
  `setup/publish-targets.portable`. Those files are percolation artifacts and carry a
  `coordinator:percolate-only` sentinel block saying so; the block is stripped at publish time.

## The intended architecture

Ratified by the PM, 2026-07-27:

1. **One global `CLAUDE.md`** describing how the coordinator system works — written in **system
   terms** (there is an EM; there is a PM; dispatched agents are the EM's team), *not* in second
   person addressed to a role the reader may not hold.
2. **The main agent learns it is the EM from a hook** that fires only for the main session.
3. **Dispatched agents learn they are on the EM's team from the dispatch path** — the Agent-tool
   PreToolUse hook already appends to `tool_input.prompt` on every dispatch
   (`hooks/scripts/enforce-agent-dispatch-mode.py`, which documents itself as the **only**
   `updatedInput` emitter; any role-framing append goes *inside* it, not in a second hook).
4. **Repo-scoped context stays repo-scoped** — a repo's own `CLAUDE.md` says what
   that repo is for. Nothing shims a repo `CLAUDE.md` into the global one; if that is ever wanted it
   must be *built*, not assumed.
5. **The consumer distribution is derived from the global file**, not hand-maintained in parallel —
   with a real transform, because a personal global file contains personal and fleet-specific prose
   that a naive strip cannot separate.

### Why role-by-hook rather than role-by-file

Because it removes the defect instead of counterweighting it. The observed failure was a
`general-purpose` worker reporting that it was the EM, naming a human PM it would seek
authorization from, and claiming dispatch authority — at 8/10 self-rated confidence, *after*
locating the one line that identified it as a subagent and reasoning it away as boilerplate. No
agent detects this unprompted, and self-reported confidence runs **backwards** to correctness
(the persona that answered correctly rated itself 7/10; the generic worker that answered wrongly
rated itself 8/10).

A hook is the right channel because it is **already role-scoped by construction** — SessionStart
fires only for the main session; the Agent-tool PreToolUse fires only on dispatch. Neither can be
forgotten, neither needs an adoption campaign.

**But keep "the hook fires" and "an append is emitted" separate — they are not the same claim,
and conflating them is exactly the failure mode this section used to have.** The hook *invocation*
is unconditional: `hooks.json` registers a tool-name matcher (`Agent`) with no `subagent_type`
filter, so it runs for every dispatch regardless of agent type. The prompt *append*, however, is
not unconditional — it is produced only by the sidecar-notice and contract-block concerns, both
gated on an exact-string lookup against `subagent-sandbox-policy.yaml`'s `report_sidecar:` and
`contract_blocks:` lists. **`general-purpose`, `claude`, `Explore`, and `Plan` — the four types this
argument is about — appear in neither list.** The combined emit-gate
(`hooks/scripts/enforce-agent-dispatch-mode.py:527`) returns `0` with no `updatedInput` for all
four today. So on current disk, the dispatch hook sees every one of these agents and appends
nothing to any of them. An unconditional role-framing append that actually reaches this population
is a thing **to be built** — the architecture this section argues for, not a behaviour already
running. Full evidence: `state/audits/2026-07-27-explore-plan-hook-reach.md`.

**A second, separate claim about `Explore`/`Plan` needs its own downgrade — it was stated as fact
and is actually an unverified inference.** The claim that the dispatch append "reaches
`Explore`/`Plan`, where it is the only framing they get" stacks two things nobody has ever
checked: (1) that a plugin `PreToolUse` `Agent` hook runs at all for a harness *built-in*
`subagent_type`, as opposed to only for plugin-defined ones — undocumented either way, though the
official permissions syntax (`Agent(Explore)`) is circumstantial support that the permission layer
treats an Explore dispatch as an ordinary `Agent` tool call; and (2) that an `updatedInput` prompt
mutation, if produced, is actually honoured and delivered into a built-in's context. No probe has
tested either step. Treat "it reaches Explore/Plan" as inference, not observation, until someone
runs the recall-probe protocol in the audit's § 5.

**What *is* well-supported, and stays**: `Explore` and `Plan` are the one documented exemption from
ordinary CLAUDE.md injection. Anthropic's own docs state it three times verbatim ("Explore and Plan
skip your CLAUDE.md files… every other built-in and custom subagent loads both"; "there is no
frontmatter field or per-agent setting to change which agents skip them"), and a local probe (P2)
confirmed it empirically for `Explore` — zero CLAUDE.md files, no MEMORY.md, no agent listing, on a
zero-tool-use dispatch. `Plan`'s exemption rests on the doc statement alone; it has never been
probed locally. That asymmetry — Explore observed, Plan doc-only — is worth carrying honestly
rather than treating the pair as equally verified.

Contrast the alternatives that were considered and rejected: a mandatory snippet the dispatcher
must remember to append is the operator remembering, which
`docs/wiki/invisible-doctrine.md`'s discharge test rejects; and a coordinator-owned generic worker
agent cannot become the default, because **a plugin agent cannot shadow a harness built-in** —
plugin scope is lowest-priority and gets a `<plugin>:` scoped identifier.

## Suppression is not available — do not go looking

Official docs, verbatim: *"there is no frontmatter field or per-agent setting to change which
agents skip them."* GitHub #24773 proposed three opt-out shapes and was closed **"not planned."**
An internal `omitClaudeMd` flag exists in the shipped bundle but is reachable only by
binary-patching a minified build — unsupported, breaks on every update, not doctrine.

Related dead end: **`skills:` in agent frontmatter is an additive *preload***, not a listing
filter — *"This field controls which skills are preloaded, not which skills the subagent can
access."* Used to shrink a subagent's context it does the opposite. And plugin skills are
explicitly excluded from `skillOverrides`, so that lever does not reach coordinator's own skills.

## How to check this yourself

Do not ask an agent whether it has a file — it will confabulate. **Ask it to recite a string unique
to that file.** To test the boot-vs-lazy distinction, probe before anything has read the directory
in question. To test fleet reach, probe from a *sibling repo* session, not from DoE-claude.

## See also

- `state/audits/2026-07-27-explore-plan-hook-reach.md` — the per-claim verdict table (fires vs.
  appends vs. inference) behind the § Why role-by-hook corrections above. Read this before
  extending the append to `general-purpose`/`claude`/`Explore`/`Plan` — it also names the cheap
  quarantined probe that would settle the Explore/Plan inference.
- `docs/wiki/claude-md-surfaces.md` — the five-surface disambiguation. **Carried the falsified
  `--plugin-dir` claim; check it has been corrected before citing it.**
- `docs/wiki/invisible-doctrine.md` — the discharge test, which is why role-by-hook beats
  role-by-reminder.
- `docs/problems/2026-07-27-the-boot-envelope-is-paid-per-agent-and-.md` — the ratified problem-set.
  **Its Problem 8 states the falsified `--plugin-dir` mechanism**; the problem it names survives,
  its stated mechanism does not.
- `state/roadmap/boot-envelope/COORDINATOR-RESOLUTIONS.md` § Resolution 0 — the mid-flight
  falsification and what it invalidated.
- `docs/research/spike-verdicts/2026-07-27-boot-context-envelope.md` — the per-agent amplification
  evidence and the role-miscasting probes.
