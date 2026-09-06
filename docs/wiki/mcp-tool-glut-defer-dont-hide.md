# MCP tool glut: defer, don't hide

> The negative spec for a recurring instinct — when an MCP server exposes 30, 50, 170 tools, hide
> most of them from the EM and let a dispatched specialist reach the rest. That shape is not
> implementable, and the version of it that *is* implementable was built, shipped, and deleted.
>
> Source: `cross-repo/archive/2026-07-27-project-rag-em-mcp-tool-glut-deferred-visibility.md`
> (project-rag-em, read against `example-game-workbench-repo` HEAD).
> Mechanism detail: `mcp-topology.md § 3`.

---

## The rule

**A subagent's tool surface only ever narrows relative to the session that dispatched it.** An
agent's `tools:` frontmatter is an allowlist over what the parent could already reach — there is
no mechanism by which a dispatched specialist reaches a tool the EM could not have reached. So
the intuitive design *"the EM sees 4 tools, the researcher sees 50"* has no implementation. The
only reachable shape is:

> The EM sees all 50 as **deferred names**; the worker is **allowlisted** to the 50 and instructed
> to use them.

**The load-bearing half of that rule is a property of the transport: stdio MCP carries no client
identity.** A server answering `tools/list` cannot tell which principal is asking — EM or
dispatched specialist, they are the same connection. Every consequence below follows from that one
fact, and it is the reason no amount of server-side cleverness produces a per-principal surface.
Independently re-proved by example-game-repo 2026-07-30: frontmatter `tools:` filters against the inherited
pool, and inline `mcpServers:` did not spawn a second connection in Claude Code 2.1.220, tested
with and without `--strict-mcp-config`.

## Why hiding is the wrong lever anyway

The harness registers every MCP server's tools **by name** and defers their schemas until
`ToolSearch` surfaces intent. Names are cheap: example-game-repo serves **170 tools in ~740 tokens**,
roughly **4 tokens per tool**. A 50-tool server therefore costs the EM about **200 tokens** of
always-on context. Server-side hiding trades a functioning specialist tier for a rounding error.

*(Figure provenance: example-game-repo's own measurement, taken from their docs rather than independently
re-measured — treat the per-name cost as small-and-bounded, not as a load-bearing constant. The
open question the memo left — whether deferral is unconditional or kicks in above some surface
size — is now pinned: it is unconditional. See § Turning servers back on.)*

## The worked example — example-game-repo's thin mode

Example-game-repo built server-side hiding (`DynamicToolManager.applyThinMode()`), shipped it, and
**deleted it**. The reason: hiding tools at the server level prevented
subagents from discovering them via `ToolSearch`, which made every domain agent non-functional for
MCP work.

**That specific gap has since been closed, and closing it does not revive hiding.** example-game-repo added
`search_tools` on 2026-06-17 — ranked, intent-aware discovery over tools and their action enums,
computed server-side, independent of advertisement — paired with `execute_domain_tool`, which
dispatches against the full registry by string and never consults the advertised list. A principal
that cannot see a name can still find the tool and call it.

Read that carefully, because it cuts the other way from how it first reads. The bypass that makes
hiding survivable for the specialist is available to **every** principal, the EM included — the
server cannot tell them apart. So the discovery-breakage argument is genuinely retired for a server
built this way, and what replaces it is worse for the hiding case, not better: hiding now enforces
nothing on anyone. See § Hiding cannot enforce.

**Beware the stale evidence trail.** Docs asserting thin mode as live and permanent long outlived
the code — including decision records stamped `Accepted`, one of them titled *Thin Mode
Permanence*. That stale text is what seeded project-rag's wrong premise in the first place. A
doctrine page written off those docs inherits the error — read the live code, not the marketing.
(Two file:line trails previously cited here did not reproduce at example-game-repo's current HEAD and
have been dropped; the surviving cluster is example-game-repo's to retire and they have committed to it. The
transferable lesson is the shape, not the paths: **a decision record titled *Permanence*, still
marked Accepted, describing a mechanism deleted four months ago is the most citable wrong-premise
source a tree can hold.** Retiring the mechanism and retiring its ratification are two jobs.)

## What a worker agent actually buys you

The framing *"this worker exists so the EM never carries the tool surface"* is off by one, and the
off-by-one matters when someone generalises from it — it points at a gate that hides tools, which
is the move example-game-repo reverted. The EM loads the deferred names either way, cheaply. The real wins
are four, none of them about the tool list:

1. **Schema containment** — the EM never loads ~25 full tool *schemas* into its own window.
2. **Output containment** — the multi-call read loop and its raw output happen in the subagent's
   context and come back as a conclusion.
3. **Resident-instruction savings** — the worker carries domain operating instructions the EM does
   not need resident.
4. **The specialist does the job better.** The worker carries domain priming the EM does not have —
   engine-version caveats, mode-routing rules, the habit of verifying API claims against a corpus
   instead of training data. An EM that calls the domain tool directly skips all of it and produces
   **worse output, not merely more expensive output**.

The first three are containment — all about what the EM avoids *carrying*. The fourth is quality,
and it is categorically different in one respect that decides everything downstream: **it is the
only win that depends on the dispatch actually happening.** Containment accrues whenever the worker
is used; quality is forfeited every time it is bypassed. So the fourth win is the only one with an
enforcement question attached, and it is where the hide-the-tools instinct regenerates each time —
someone notices that prose is the only thing holding the routing, and reaches for the server.

Design accordingly: the answer to tool glut is **more worker agents plus routing prose**, with
**no gating at the MCP layer**. Where advisory routing is genuinely not enough, the gate goes one
layer up — § Hiding cannot enforce.

## Hiding cannot enforce — the affordance argument, and why it fails

The strongest case for server-side hiding is not cost. It is **discipline**: an EM sees a tool in
the list, thinks *"oh cool, I'll do that,"* and does it itself instead of dispatching the
specialist that exists to do it properly. Routing prose is advisory; it loses at the margin, more
often under time pressure and as tool counts grow. The wish is to make the routing table the only
path rather than the recommended one. **That failure mode is real** — it is the fourth win above
being forfeited — and this page previously argued only against the cost framing, which left the
affordance framing looking like an open carve-out. It is not one. Adjudicated 2026-07-30 at the
request of a sibling repo that drafted exactly this plan and blocked it themselves.

**Server-side hiding cannot deliver enforcement, for a structural reason, in any repo, under any
design.** The MCP server is the one layer in the stack that cannot see who is calling. With no
client identity on the connection, hiding is necessarily *uniform across principals*, which leaves
exactly two settings and no third:

- **Total** — no bypass. The specialist cannot reach the tool either, and the specialist tier
  breaks. This is example-game-repo's April, and it broke *despite* a shakedown across four projects.
- **Bypassed** — a discovery endpoint plus an invoke-by-string endpoint, so the specialist still
  works. But those endpoints answer the EM identically. The wrong path is now two calls instead of
  one, taken by a principal that can trivially make both.

So a hiding mechanism is either broken or non-binding, and the very repair that rescues it from the
first state delivers it into the second. **An eager EM is not deterred by a speed bump it can see
the far side of** — and `search_tools` is *designed* to show it the far side. The affordance
argument does not survive its own mechanism.

This is why the negative spec below covers the enforcement framing and not only the cost framing.
The two bans are one ban: don't put a gate where the gate cannot see the principal.

### Where the gate goes instead

Enforcement is available — one layer up, where the principal **is** legible.

**A `PreToolUse` hook payload carries a top-level `agent_id` that is present only when the caller
is a dispatched subagent, and absent for the main session.** That is a direct, proven principal
discriminator, and coordinator already ships deny-guards and nudge-suppressors keyed on exactly it
(`block_subagent_archive_write`, `block_em_hand_edit_pending_review_integration`,
`suggest_sonnet_research`). So the rule *"this domain tool is reachable by the specialist and
denied to the EM"* is directly implementable **today**, per-repo, with a hook and a test — no wire
change, no thin mode, no shakedown of every domain agent, and it is a genuine gate rather than a
bump, because the EM has no bypass in the way it has one around a hidden tool.

Four constraints on doing it, none optional:

- **Deny, don't hide.** The tool stays on the wire and stays visible. The EM that reaches for it
  gets a denial naming the agent to dispatch instead. Visible-and-refused teaches the routing;
  invisible teaches nothing and gets rediscovered.
- **Write it as an offer, per global doctrine's design-as-offers rule.** The denial's payload is
  *"dispatch `X` for this"* — the alternative first, the violation second.
- **Fail open.** A guard that cannot resolve the principal allows. A false stand-down beats a false
  denial on a tool the specialist needs.
- **Prove it fires for the agent types you actually dispatch.** Whether `PreToolUse` fires for
  *harness built-in* subagent types is not established; for coordinator-registered agents it is
  shipped and proven. Test through the real dispatcher, not by introspection.

**Reach for this only past the threshold the convention below already names, and only after the
routing prose has demonstrably failed** — a hook deny is a real gate with real blast radius, and
most tool glut needs a routing table, not a fence.

## Per-MCP-server convention (past ~15 tools)

1. A **Tier-1 table** in the owning repo's `CLAUDE.md` naming the handful of tools worth calling
   inline — framed as *"don't delegate what takes 5 seconds."*
2. A **worker agent** covering the rest of the surface, with the domain instructions resident in
   its prompt. Breadth has three shapes, not two — pick by whether the worker's remit is
   **bounded** or **open-ended**, never by default:
   - **Bounded remit** (a fixed pipeline over a known tool subset) — a narrow `tools:` allowlist
     plus a graduated `ToolSearch` bootstrap, the `atlassian-worker` shape.
   - **Open-ended remit** (free-form questions that may legitimately reach the whole surface) —
     **omit `tools:` from frontmatter entirely** rather than hand-enumerate it. Enumeration is
     both a resident cost (the array is echoed into the agent listing every session, § Turning
     servers back on) and a rot vector — a hand-maintained literal with nothing checking it
     against the live registry silently caps the worker below the growing surface as new tools
     land. Omitting `tools:` also lifts the ceiling on `Write`/`Edit`/`NotebookEdit`/dispatch, so
     pair it with an explicit in-prompt guardrail restating what the worker may NOT do (no edit,
     no commit, Bash restricted to read-only commands, etc.) rather than relying on the array to
     carry that restriction.
   - **"Allowlisted to the full surface"** (enumerate every tool) is the shape to avoid for a
     growing surface — it pays the enumeration rot cost of the bounded shape without the
     narrowness that makes that cost worth it.
   *(Discriminator and omit-`tools:` shape contributed by project-rag-em,
   cross-repo/inbox/2026-07-28-project-rag-em-project-rag-agent-tool-surface-reference-implementation.md,
   as the reference implementation of `project-rag-researcher`/`project-rag-context-builder`. The
   omit-vs-enumerate resident-token delta and whether an MCP server's `instructions` block is
   resident are both explicitly **unmeasured** on their side as of that memo — do not treat either
   as settled here.)*
3. **Routing prose** pointing everything else at that worker. In coordinator this is the agent's
   own `description:` field (the harness surfaces it at dispatch-selection time) — coordinator
   keeps no separate `agent-routing-table.md` artifact; example-game-repo does, and either discharges the
   requirement.
4. **Past a few dozen tools, make the routing a checked artifact rather than prose.** Give every
   tool an **owning agent**, generated from a small category→agent seed plus per-tool overrides
   rather than hand-maintained, with a regenerate-and-diff drift test. Where the server offers
   discovery, have it return the owner with each hit — so a lookup answers *"who do I dispatch"*
   rather than *"what do I call."* This is the discharge for routing prose: hand-maintained prose
   over a 170-tool surface rots silently, and a generated map with a drift test cannot. It needs no
   hiding, no gating, and is compatible with the full surface staying on the wire. *(Mechanism
   contributed by example-game-repo-em, 2026-07-30, alongside the ruling in § Hiding cannot enforce.)*

This is the **design-as-offers** shape from global doctrine: lead with the better path, not with a
block. What produces the routing behaviour is prompt-layer — *"the EM routes to specialists
because it's the higher-quality path, not because tools are hidden"*
(`plugin/example-game-repo-control/CLAUDE.md:24`).

## Turning servers back on — what it actually costs

Deferral is the harness's default posture and it is **not size-gated**. Observed directly in a
DoE-claude session on 2026-07-27 with six MCP servers connected — Asana (~37 tools), Gmail (16),
Google Calendar (9), Google Drive (8), Cockpit (4), context7 (2) — **every one of them registered
name-only**, schemas withheld until `ToolSearch`. A 2-tool server defers exactly like example-game-repo's
170-tool one. Built-in tools (`WebFetch`, `WebSearch`, `Task*`, `Cron*`, `Monitor`) defer on the
same mechanism, so this is a harness-wide posture, not an MCP special case. There is no
`settings.json` key that turns it on or off; nothing needs configuring to get it.

**So "enable the server" does not mean "load 50 schemas."** But three costs *are* always-on, and
they are the ones to check before re-enabling a server fleet-wide:

| Cost | Defers? | Magnitude |
|---|---|---|
| Tool **names** | — | ~4 tokens each (example-game-repo's figure). Not separately itemized by `/context` — it falls inside the system-prompt line. A 50-tool server ≈ 200 tokens. Ignorable. |
| Tool **schemas** | **yes** | Zero until `ToolSearch`. This is the whole win, and it is measurable — see below. |
| Server **`instructions` block** | **no** | Fully resident, every session, unbounded, author-controlled. Cockpit, example-game-repo, project-rag, notebooklm and context7 all ship one; example-game-repo's is a ~25-line routing table. **Believed to be the real per-server variable cost** — a 50-tool server with no instructions block should be cheaper than a 4-tool server with a long one. **Not yet measured** — see the caveat below. |
| An agent's `tools:` **array** | **no** | Echoed verbatim into the resident agent-type listing, and this row *is* counted in the total. Measured: `coordinator:atlassian-worker` 176 tokens, `drive-worker` 174, all 33 coordinator agents 7.7k. So a worker costs about as much resident as the ~26-tool deferred surface it fronts — worth it for the three wins, but not free, and not a place to allowlist speculatively. |

Two consequences that are easy to get backwards:

- **Judge a server by its `instructions` block, not its tool count.** Tool count is the number
  everyone quotes and the one that barely matters. (Pending the measurement caveat below — this is
  the standing hypothesis, not yet a confirmed fact.)
- **Audit for duplicate registrations.** The same server registered twice pays twice for
  everything and creates call-site ambiguity. Observed 2026-07-27: `cockpit` (2.84k) and
  `claude.ai Cockpit` (2.85k) were both live, same four tools, same instructions block injected
  twice.
- **A broad worker allowlist buys back part of what deferral saved.** It is still worth it — the
  worker's wins are schema containment, output containment, and resident-instruction savings, all
  of which are larger — but a worker allowlisted to 50 tools "just in case" is paying resident
  tokens for reach it never uses. Allowlist what the agent's own instructions actually reference
  (this is the `AGENT-MCP-TOOL-ADOPTION` gate's rule, arrived at from the other direction).

### The measured answer — 397k held off the wire

A DoE-claude session on 2026-07-27, measured with `/context` before and after enabling ten MCP
servers mid-session (~292 tools):

| Category | context7 only | all servers |
|---|---|---|
| System prompt | 6.5k | 6.5k |
| System tools | 15.3k | 15.3k |
| Custom agents | 7.7k | 7.7k |
| Memory + Skills | 22.3k | 22.3k |
| Messages | 117.7k | 143.5k |
| **MCP tools (deferred)** | **1.4k** | **396.9k** |

**Every resident category is unchanged.** The only growth is Messages, and that was the `/context`
output itself being read into the conversation — not MCP. Meanwhile the deferred row went to
**396.9k**: ~1.4k of schema per tool, 40% of a 1M window, roughly 2× a 200k one, all of it held
off the wire and still reachable via `ToolSearch`.

That is the number to quote. "~4 tokens per name" is the cost side; **397k** is the saving side,
and it is the one that decides whether a fleet runs with MCP on.

Concentration matters as much as the total. Rough per-server split of that 396.9k: example-game-repo-control
**~290k (73%)** — its five `manage_widget_*` tools are ~7k *each* — then Asana 38.5k, project-rag
~21k, Gmail 13.3k, notebooklm 13.2k, Calendar 8.8k, Cockpit 5.7k, Drive 4.0k, context7 1.9k. One
server can dominate the whole surface, so a per-server audit beats a fleet-wide policy.

**What this run did NOT measure.** The servers were enabled *mid-session*, which delivers their
`instructions` blocks into the message stream rather than the system prompt — system prompt stayed
at 6.5k across both readings. So the instructions-block cost claimed in the table above remains
**unmeasured**, not confirmed. Measuring it needs a fresh session started with the servers already
connected, comparing system-prompt size.

### Reading `/context` — the deferred rows are NOT in the total

This is the part that misleads on first read. `/context` reports deferred tools on their own rows
(`MCP tools`, `System tools (deferred)`) with what look like alarming numbers — a DoE-claude
session on 2026-07-27 showed **1.4k for two context7 tools** (523 + 892), i.e. ~700 tokens each.
Read naively that says deferral costs ~700 tokens per tool and the whole doctrine collapses.

**Check the arithmetic before believing it.** In that same session the itemized categories summed
to the reported total on their own:

```
system prompt 6.5k + system tools 15.3k + custom agents 7.7k
  + memory 17.2k + skills 5.1k + messages 117.7k  =  169.5k  ≈  total 168.9k
```

The deferred rows — 1.4k MCP and 17.8k system — are **excluded** from that sum. Including them
would give 188.7k, which is not the reported figure. So those numbers are the **counterfactual**:
what the schemas *would* cost if they were not deferred. In that session deferral was holding
**17.8k of built-in tool schemas alone** off the wire, for a surface the EM could still reach at
any time via `ToolSearch`.

Two rules follow:

- **Never quote a deferred row as a cost.** It is a saving, stated in the units of the thing
  avoided. Anyone reading it as spend will conclude MCP is expensive and start disabling servers —
  which is where the hide-the-tools instinct comes from in the first place.
- **The measurement that decides a re-enable is the delta in the *summed* categories**, before and
  after, not the deferred row. Run `/context` with the server off, enable it, restart, run it
  again, and compare the lines that add up to the total. That is the discharge for this section —
  it is repo- and account-specific, and the numbers above are a snapshot, not a constant.

- **Do not build server-side tool hiding**, in any repo, under any name — **including as an
  enforcement or affordance-shaping mechanism, not only as a cost-saving one.** The enforcement
  framing is the harder-to-refuse version and it is barred too: a server that cannot see the
  principal cannot gate one. If a plan proposes hiding under any framing, this page is the
  refutation; § Hiding cannot enforce and § Where the gate goes instead say what to build instead.
- **Do not write a session-start assertion that a `deferred` server's tools are absent from the
  active tool surface.** Deferred tools are *present by name* by design; that assertion would fail
  on every correctly-configured session, and "fixing" it means rebuilding thin mode.
- **Do not justify a worker agent by "the EM avoids loading the tool surface."** Use the four wins
  above instead. Note this bars an argument about what the EM *loads*; it does not bar the fourth
  win, which is about the EM *reaching for the wrong thing* and is a legitimate justification —
  they are genuinely different claims and only the first is refuted here.

## Related

- `mcp-topology.md` — the typed load-posture declaration; § 3 carries the harness deferral
  mechanism and the plugin-subagent `mcpServers` limitation.
- `tool-registry-vs-routing.md` — the agent-side analog: array presence is not adoption.
- `per-project-plugin-gating.md` — what `enabledPlugins` actually suppresses (agents/skills, not a
  user-scope server's tools).
