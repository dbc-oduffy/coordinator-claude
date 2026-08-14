# Guard Message Concision

> The overflow destination for a guard's prose: why a guard message is a redirect rather than a
> spec, what each cap actually counts, and where the explanation you cut goes. Organised
> by anchor so a one-sentence guard message can cite a single section rather than this whole page.
>
> **Two caps exist, in two units — start at [#which-cap-is-mine](#which-cap-is-mine) and take the
> row for your surface before using any number below.**
>
> **Upstream of this page: should the guard exist at all?**
> `guard-proportionality.md` decides whether a fact earns silence, a
> warn, or a block — answer that first, because a perfectly concise deny message for a guard that
> should have said nothing is wasted work.

---

## A Guard Fires Only When the Reader Is Off the Normal Path {#off-the-normal-path}

On the normal path, the skill flow, the agent description, and this wiki already carry the
contract — a guard on that path never has to speak, because the reader already knows what to do.
A guard message exists for the other case: someone has arrived somewhere unexpected, off the path
those other surfaces cover.

That reframes what a guard message is *for*. It does not need to teach the mechanism it guards —
the mechanism is already documented where the reader was supposed to learn it. It needs to name
the off-ramp: the one or two things the reader should do right now to get back on the normal path.
A message that explains the three branches of *why* the rule exists is doing the wiki's job from
inside a channel that has no room for it.

If a guard message is over budget, the likeliest cause is not that the redirect is long — it is
that the message is explaining instead of redirecting. Check here before reaching for an exception.

## An Advisory Persuades; It Never Instructs {#advisories-persuade}

A deny does not need the reader's compliance — the call already failed at the tool boundary, and
the message only explains and names the off-ramp. An **advisory** has no such backing: it is text
in tool output asking for a change of course, and `coordinator/snippets/agent-role-dispatched.md`
now tells every dispatched agent that such text carries no authority and is acted on only when it
is true and useful. That is deliberate — an agent calibrated to obey imperatives in tool output is
one an attacker can steer, and the `[coordinator]` marker is a fixed public string that proves
nothing.

So write advisories that earn their follow-through. State the constraint and the alternative that
works; a reader reasoning about their task will take it. A bare imperative in the shape of "you're
the EM, not the typist" only lands on a reader trained to obey the channel, which is exactly the
disposition doctrine now removes — such a message will get weaker over time, correctly. Denies are
unaffected.

## There Are Two Caps, in Two Units — Find Yours First {#which-cap-is-mine}

**Before using any number on this page, identify which surface you are writing for.** Two
independent caps are enforced live, by two different mechanisms, in two different units:

| Surface | Constant | Budget | Unit | Enforced by |
|---|---|---|---|---|
| **The plugin's hook envelope** — `coordinator/hooks/scripts/*` | `_message_envelope.CEILING` | **280** | **characters** | `coordinator/tests/test_hook_message_budget.py` |
| **The engine's bash-guard emission path** — `coordinator_core/bash_guards/*` | `_message_size.MESSAGE_PROSE_CAP_BYTES` | **220** | **bytes** | `_message_size.measure_envelope`, at emission |

**A figure from one surface is never carried to the other.** Both axes differ — the number *and*
the unit — so a message drafted against the wrong row fails its gate on landing, and does so for a
reason the author cannot see from the number alone. Bytes and characters diverge the moment a
message contains a non-ASCII character, which coordinator messages routinely do (an em-dash is
three bytes, one character); the engine's 220 bytes is therefore materially tighter than "220
characters" would be, on top of already being a smaller figure than 280.

This page's worked examples, exemption rules, and exception ledger were authored against the
**280-character hook-envelope row** and state that figure throughout. The *reasoning* — redirect
rather than teach, the structural fenced-block exemption, the permission-boundary trap — is
surface-agnostic and applies to both. The *arithmetic* is not. Writing an engine-side guard
message means taking the reasoning from this page and the number from
`MESSAGE_PROSE_CAP_BYTES`, whose own module carries the matching negative spec.

<!-- Negative-spec: this page previously published the 280-character figure as though it were the
     only cap. An engine-plane sibling drafted plan copy against it and caught the divergence only
     at port time; that copy would have failed the engine's live gate on landing. A reader on
     either surface must be able to find their own number here. Do not collapse the table back to
     a single figure. -->

## What the Cap Counts (hook envelope: 280 characters) {#what-the-cap-counts}

The budget on this surface is **280 characters of prose** — deliberately sized to one tweet, because that is the
recognised unit for one-thought-length, and because two sentences at working density fit inside it
with room to spare. A **fenced, copy-pasteable runnable block is structurally exempt** and is never
counted against the cap. That exemption is structural, not textual: it applies to a block carried
as its own field in the message-composition contract, not to any block of prose a hook happens to
wrap in triple backticks — a mechanism that could not tell the difference would let any hook hide
arbitrary length inside a fence, which defeats the cap rather than serving it.

The reason for exempting the block at all: a message sometimes has a duty-of-care obligation to
hand the reader a ready-to-run alternative — copy-pasteable text that costs characters no matter
how it is phrased. A cap that charged the block against the same 280 would push every message that
carries one down to something too thin to be useful, undoing exactly the work a runnable
alternative is there to do. One sentence of diagnosis plus one runnable line satisfies the cap and
the duty-of-care obligation at the same time; neither has to be sacrificed for the other.

## Worked Exemplar {#worked-exemplar}

A ~1,544-character guard message became this, unchanged in effect:

> `review-integrator applies a reviewer sidecar; name one, or dispatch coordinator:enricher instead — that is the agent for amending a plan body.`

142 characters. Both remedies survive — apply the sidecar, or use the right agent instead — and
what was cut is the three-branch explanation of *why* the contract exists, which belongs on a page
like this one rather than in the channel that fires only when something has already gone wrong.
The rewrite was not an arithmetic squeeze against a target; it reads as ordinary writing because a
redirect naturally lands short once the teaching is removed from it.

## The Trap: Compression Must Keep the Rule's Permission Boundary Intact {#compression-versus-deletion}

A rule's operativeness is a property of what it forbids or permits, never a property of how many
words it takes to say so. Compressing a message toward the cap is safe; deleting or thinning the
part of a rule that states its permission boundary is not a compression — it is turning a
forbidden action into one that reads as permitted, silently, because the message says nothing
about the boundary at all.

This is the one place where "make it shorter" and "make it correct" can point in different
directions, so hold the boundary fixed and compress everything else around it. If a message cannot
be brought under budget without weakening what it forbids, that is a case for relocating the rest
of the explanation here, not for cutting the boundary itself.

## Escape Hatches and Overrides Relocate, They Never Disappear {#escape-hatches-relocate}

An override key, an environment kill-switch, or a documented bypass path is exactly the kind of
detail a shortened message has no room to restate in full. When a message is tightened toward the
cap, that detail moves to this wiki rather than being dropped — a reader who needs the override
should be able to follow the message's pointer here and find it, not lose it to a shortened
message that fails to carry it. A guard message losing its only stated escape hatch is a
regression, not a trim, even when the resulting message is well within budget.

---

## Doctrine-surface Bash-write guard: carve-outs and remedies {#doctrine-surface-bash-write-guard-carve-outs-and-remedies}

This guard is the Bash-surface twin of the doctrine admission gate that governs a small set of
always-on governed doctrine files. The admission gate only ever sees `Write`/`Edit`/`MultiEdit`
tool calls; this guard closes the same gap for a shell redirect, an in-place editor, a `tee`, an
interpreter payload, or a heredoc that writes one of those files without ever going through the
admission gate at all.

It classifies by **write sink**, not by the mere presence of shell punctuation anywhere in the
command: a governed filename mentioned in one stage of a `;`-joined command does not poison an
unrelated stage elsewhere in the same line, and a plain read (`cat`/`grep`/`head`/`tail`/`wc`/
`git show`, no redirect) is never blocked, even chained with an unrelated command. When a payload
arrives through an interpreter, `eval`, `xargs`, or a dynamically assembled path, this guard cannot
reliably tell a read from a write, so it fails closed on that shape rather than guessing.

### If the denial looks commit-shaped

A `git commit`/`git add`, or one of the scoped-commit wrapper family, does not write the governed
file's content at all -- it writes the object store and the index. If this guard still denied the
command, a genuine redirect, `tee`, or interpreter marker sits somewhere outside the commit message
itself. Use the pathspec form instead of reaching for Write/Edit -- Write/Edit cannot produce a
commit, so that advice is never the fix for this shape:

```
git commit -m '...' -- <path>
```

### If the real write target IS one of the governed files

Use the Write or Edit tool for that change instead of Bash. The admission gate this guard pairs
with only evaluates growth through those tools, and it will name the disposition (or the demote
target) the addition needs before it lands.

### If the governed filename is only quoted prose, not the write target

A guard that scans for a governed identifier anywhere in a command cannot always tell "this
filename is the destination path" apart from "this filename is quoted content being written
somewhere else" -- for example, a finding's prose, or a commit-message excerpt, that happens to
name a governed file while the command's real destination is a different, unrelated path. This
guard cannot safely make that distinction (quote-stripping to find out would also hide a genuine
write disguised the same way), so it fails closed either way.

The fix is doctrine, not detection: use the Edit tool directly on the real destination instead of
a Bash redirect, heredoc, or interpreter payload. Edit operates on the file you actually intend to
change and never goes through this guard's Bash-command classification at all. This is the
documented default for persisting a finding to an already-provisioned sidecar file -- see
`coordinator/snippets/findings-self-persist-sentinel.md`.

### The authorization-grant CLI carve-out

A CLI that grants, reads, or checks authorization for a governed-doctrine change takes a note
as one of its arguments, and that note almost always names the governed file it authorizes -- the
natural shape of an authorization note, not an edge case. That CLI's own write target is always
its internal grant record, never the governed file itself, for every one of its subcommands, so
this guard recognizes its invocation shape and does not deny on the strength of a governed filename
appearing inside the note alone. A genuine redirect or `tee` riding alongside that same invocation
still denies -- only the CLI's own expected indirection is exempted, not an actual write smuggled
into the same command.

## review-integrator sidecar intake -- what the guard is redirecting you away from {#review-integrator-sidecar-intake}

`review-integrator` applies a reviewer's findings to an artifact strictly from files on disk: a
findings sidecar plus the artifact path(s), never findings pasted inline into the dispatch prompt.
A sufficiently confident, concretely-specified brief -- real file paths, verified measurements,
unambiguous instructions -- can walk straight through a prose-only stop; that observed failure mode
is why a mechanical guard now enforces this at dispatch time instead of relying on prose alone.

A dispatch satisfies the guard iff its prompt text NAMES a sidecar path shaped like
`state/subagent-share/<session>/<key>.md` AND that exact path exists on disk.
Everything else denies: inline findings with no sidecar path at all, a path that is named but not
yet on disk (stale citation, or the reviewer was never actually dispatched to provision it), or a
real sidecar that exists on disk but was never named in THIS dispatch's prompt (see the
closed-rationalization-hole note below).

If you have hit this guard, there are three ways forward, in order of likelihood:

- **This is plan-body maintenance, not reviewer-findings application.** Dispatch
  `coordinator:enricher` instead -- review-integrator applies a reviewer's sidecar findings, it
  does not author or maintain plan bodies.
- **This genuinely is reviewer findings.** Re-dispatch the reviewer instead: sidecar provisioning
  auto-creates a sidecar at spawn (`state/subagent-share/<session>/<key>.md`), and that path is
  what this dispatch needs to name.
- **Defect-recovery only** -- a reviewer already ran and its output was lost from the sidecar:
  write the reviewer's verbatim output into the already-provisioned sidecar path, then re-dispatch
  review-integrator naming that exact path in the prompt.

### `state/plan-sidecars/` is never the answer here, even for a `staff-eng-review`-lens plan review

A persona's findings on a PLAN can look, at a glance, like they belong next to the plan-pipeline
lens sidecars (`state/plan-sidecars/<plan-stem>.prior-art-check.md` and siblings) -- they don't.
`state-placement-law.md`'s two rows are explicit about the split: `state/plan-sidecars/` is
reserved for exactly four plan-derivable, D0/Z2-relocated, UNREAPED-BY-DESIGN lens emitters
(prior-art-check, plan-coverage-check, docs-check, external-pattern) whose whole purpose is
cross-run continuity at a fixed plan-derived path. `staff-eng-review` (and every other persona
finding, code review included) stays session-keyed at `state/subagent-share/<session>/<key>.md`,
the one home the typed-sidecar contract gives it, reaped on an age/liveness floor once its
content folds into a consuming
artifact -- a fundamentally different lifecycle than the unreaped lens sidecars. A persona findings
sidecar that lands under `state/plan-sidecars/` didn't move because the guard's regex is narrow; it
moved because provisioning put it in the wrong family. Widening `_SIDECAR_PATH_RE` to also admit
`state/plan-sidecars/` would fix the symptom by erasing that reap-lifecycle distinction -- resist
it. The fix is re-dispatching (or re-provisioning) the persona so its findings land at its own
auto-provisioned `state/subagent-share/` path, not teaching the guard to accept the wrong family.

### The closed rationalization hole

This guard deliberately checks "named in this dispatch's prompt AND present on disk" -- never
"present on disk" alone. A "some sidecar exists somewhere under
`state/subagent-share/<session>/`" fallback would silently re-open a failure mode already observed
in the field: a dispatcher treating an unrelated pre-existing sidecar as a correction order against
it, simply because one happened to exist on disk. Resist adding one even as a convenience for a
genuinely-provisioned-but-unnamed sidecar -- the correct remedy in that case is to name the path in
the dispatch prompt, not for the guard to go find it on the dispatcher's behalf.

## Unnamed Explore Dispatch: Cost and Guarantee {#unnamed-explore-dispatch-cost-and-guarantee}

When the EM dispatches a doctrine-carrying agent (any `subagent_type` other than `Explore`/
`Plan` -- the two the harness itself exempts from booting the full doctrine corpus) for work whose
prompt reads as read-only-shaped, an **unnamed** `Explore` dispatch is the cheaper choice: it
skips the full doctrine-corpus boot entirely. In one measured repo the boot cost was roughly 45k+
tokens for the doctrine-carrying dispatch versus 17.6k for the unnamed `Explore` dispatch -- the
gap size varies by repo, but the direction does not.

**Why it must stay unnamed, specifically.** Naming an `Explore` dispatch (passing a `name: "..."`
argument in the `Agent` call) does not merely cost more -- it changes what the dispatch actually
is. A named dispatch discards the harness's built-in `Explore` definition and rebuilds the child
from the main-loop prompt builder instead, and the `Edit`/`Write` denial that makes `Explore`
safe for recon lives inside that discarded built-in definition, not in the main-loop prompt
builder. A named `Explore` dispatch is therefore **not actually read-only** -- it is a
doctrine-carrying dispatch wearing the cheaper name, and recommending one would be actively wrong
advice, not merely a worse deal. The offer only ever recommends the unnamed form.

**When the offer does not apply.** `Explore` (named or not) carries no `Edit`/`Write` tool at
all. If the work at hand needs to write a sidecar, a file, or any other artifact, this offer is
not the right tool regardless of naming -- dispatch the doctrine-carrying agent the work actually
needs.

**Detection is conservative by design.** The offer fires only when the dispatch prompt carries a
find/locate/search/survey-class signal AND no write-shaped instruction anywhere in the prompt --
a single write verb present anywhere disqualifies the offer outright, with no negation-scrubbing.
A missed offer costs nothing; a wrong one, on genuinely write-shaped work, costs the reader's
trust in every future offer from this hook.

The offer is shown at most once per session -- a repeat qualifying dispatch in the same session
stays silent.

## Workflow model-guard: override hatches and PM gate {#workflow-model-guard-override-hatches-and-pm-gate}

This guard sits on the EM's own Workflow launch (never a subagent's nested dispatch) and fires
only in one narrow condition: the EM's main loop is running on an Opus-tier model AND the launched
Workflow script contains at least one `agent(` call with no `model:` override. Every un-modeled
`agent()` call then silently inherits the Opus session model, running that worker at roughly 4x
the cost of an explicit `model: 'sonnet'`, with no other visible signal in the script or the tool
output.

### The fix, first

Add `model: 'sonnet'` to every `agent()` call in the script (or `model: 'sonnet', effort: 'low'`
for a mechanical fan-out step). This is always the first thing to try, and it fully resolves the
guard on its own -- no override is needed for the common case of an oversight.

### If Opus is genuinely intended for these agents

Running a worker on Opus is a deliberate, gated decision, not a default -- name the reason and
get approval before overriding this guard for that agent.

### Two override hatches, functionally equivalent, reachable at different times

1. **Environment variable** -- `COORDINATOR_OVERRIDE_WORKFLOW_MODEL_GUARD=1`, set before the
   session's process launches. This is env-only: a shell `export` run from inside an
   already-running session does not mutate that process's own inherited environment, so this hatch
   is reachable only from a pre-launch shell or a non-interactive/CI invocation, never mid-session.

2. **Repo-root sentinel file** -- `touch <repo-root>/.coordinator-override-workflow-model-guard`.
   This is the session-reachable equivalent of the environment variable: a live session can create
   this file mid-run to disarm the guard, which the environment variable cannot do once the process
   has already started. Its blast radius is the whole repo -- it disarms this guard for every
   Workflow launch while the file exists, including any concurrent peer session on a shared
   branch -- so use it deliberately, and remove it once the intentional Opus dispatch is done.

### Detection scope and known limitations

This guard fires only when: the tool is a `Workflow` call (not a subagent's nested dispatch, not a
saved-workflow launch by `name:` -- those carry no script contents in the payload and are out of
scope), the session model is detected as Opus-tier (an undetectable or non-Opus session always
fails open, silent allow), and at least one real `agent(` call site exists with zero call sites
carrying their own `model:` key. Partial coverage -- some call sites modeled, some not -- is never
denied, only advised, since mixed tiering across agents can be intentional.

The `agent(`/`model:` count is a string-and-comment-aware parse of the script text, not a full JS
parser: it correctly ignores `agent(`-shaped substrings inside string literals, template-literal
interpolation, and comments, and correctly attributes `model:` per call site (not as a whole-script
substring count). It does not model JS regex literals as a distinct token class, and a call site
whose argument list is unbalanced (truncated or malformed) is treated as an unparseable detection
failure -- attributed toward neither the deny nor the advisory count, consistent with this guard's
overall bias toward failing open rather than wedging a legitimate launch on a parse edge case.

## Autonomous-mode AskUserQuestion nudge {#autonomous-mode-askuserquestion-nudge}

While an autonomous run is active, an `AskUserQuestion` call halts the run until
the (away) requester returns — the most expensive action available to that run. This
nudge exists because an excellent diagnosis that ends in a blocking ask feels
like diligence but is exactly the anti-pattern autonomous mode is designed to
prevent: break-class findings are fix-by-default, and the fix approach is
yours to decide. Decide, dispatch, log the alternatives considered where they will
persist, and inform the eventual reader in a status line — do not
stop the run to ask permission for a decision that was already yours to make.

The one legitimate autonomous-mode ask is a genuinely irreversible external
action (a push, a PR, an external message, a data deletion) with no
pre-authorization, or a true no-correct-answer product fork — a case where two
or more reasonable people would land in different places and there is no
spec-authority basis to pick one. For exactly those cases, set
`COORDINATOR_AUTONOMOUS_ASK_OK=1` before the `AskUserQuestion` call to signal
that the ask is deliberate rather than a fallback around undone decision work.
This mirrors the fleet's established override convention
(`COORDINATOR_AGENT_FOREGROUND_OK=1`, and the `COORDINATOR_OVERRIDE_*` family)
— an environment variable set once, consciously, immediately before the call
it is meant to authorize.

This nudge fires only while an active autonomous run is in progress, and is
suppressed automatically for a subagent's own `AskUserQuestion` (a delegated
worker's ask is not the top-level run's own halting decision) and whenever the
run cannot be positively identified as autonomous. It is advisory only — it
never blocks the call, it only names the cheaper path.

## prompt-surface citations -- what the guard is redirecting you away from {#prompt-surface-citations}

`coordinator/{agents,skills,commands,snippets,pipelines}/` percolate: they run in sibling repos, on
other operators' machines, and in installs that ship only a deliberately sparse curated wiki seed.
A citation that resolves only in the clone you are editing from -- an internal plan, a decision
record, an archived spec, a cross-repo memo, a non-seed wiki page, or a bare internal-id-style
reference -- 404s for every one of those other readers. This guard is advisory (PM ruling): it
does not deny the write. The moment it introduces a NEW such citation into a
prompt surface, the guard attaches an `additionalContext` note naming the exit below; it is not
a blanket flag on the (much larger) set of legacy violations already sitting in the corpus
untouched. The actual enforcing gate is `coordinator/tests/test_prompt_surfaces_cite_resolvably.py`,
a ratchet whose baseline may not be regenerated to launder a new violation.

Two legitimate exits, in order of likelihood:

- **Inline it.** If the dispatched agent genuinely needs the content to do its job, put the content
  itself in the prompt surface instead of a pointer to where it lives in your clone.
- **Promote it to the OSS seed wiki allowlist.** If the target is genuinely further reading rather
  than load-bearing content, add it to the seed-wiki allowlist test's own list of admitted pages --
  a deliberate, ratified edit, not a quiet workaround -- and cite the promoted target via a
  settings-home-relative reference, never a bare repo-relative path (a repo-relative path is exactly
  the shape that resolves in your clone and nowhere else).

If neither exit is worth taking, the pointer was not load-bearing in the first place -- delete it
rather than leaving it for the next reader to trip over.

### Why this is a hard deny, not an advisory

The existing corpus carries a large body of legacy violations across many files -- re-flagging all
of them on every future edit would wedge nearly any touch to a governed prompt surface. This guard
instead denies only on the multiset difference between a file's citations before and after the
specific write in front of it: a legacy violation sitting untouched elsewhere in the file
contributes equally to both sides of that diff and never surfaces here. Only a citation this write
is the first to introduce (or a legacy one this write duplicates a second time) does. That is what
makes a hard deny the right call despite the size of the existing debt -- the guard's decision is
about this write's own new intent, never about the file's total pre-existing state.

## New-file zero-budget-ratchet remedies {#new-file-zero-budget-ratchet-remedies}

This advisory fires on a brand-new file's first `Write` when it trips one of two shrink-only
ratchets that hold a NEW, as-yet-untracked file to a ZERO allowance -- even though a neighbouring,
already-baselined file with the identical content would pass as grandfathered debt. Copying a
baselined file's wording or shebang into a new file imports debt the new file has no allowance for.
It is advisory only and never blocks: the author is usually doing something reasonable (reusing a
neighbour's idiom), and a hard block would fight that instead of correcting it.

### OSS-payload locality violations

- **Private sibling-repo-name attribution** -- name the CAPABILITY instead of the repo that hosts
  it (e.g. "the engine plane"/"the contract plane", not the repo name itself). If the name is
  genuinely load-bearing, add it to the plugin's own locality-exemption list instead of writing the
  bare repo name.
- **Drive-rooted Windows path** -- use a portable form instead: `pathlib`, an environment
  variable, or a settings-home resolution, rather than a hardcoded drive-letter path.

### POSIX-exec-assumption violations

- **`env_shebang`** -- delete the shebang line. Windows `CreateProcess` never reads it, and if
  this file is invoked through `runpy`/direct-import (the usual case for a hook or trampoline
  script) the line is dead weight even on POSIX. If this genuinely IS a direct-exec entrypoint
  with a Windows-leg counterpart (a `.cmd` sibling), name it in the plugin's own POSIX-exec
  exemption list instead of deleting the shebang.
- **`extensionless_exec`** -- give the file an extension (`.py`). Windows resolves a bare
  invocation via `PATHEXT`, never shebang-sniffing, so an extensionless file is dead on Windows
  regardless of shebang.
- **`path_separator`** -- use `os.sep` / `os.path.join` / `pathlib` instead of a hardcoded `\`
  separator.
- **`posix_mode_bits`** -- avoid `os.access(..., os.X_OK)` / `os.chmod` with an exec bit /
  `st_mode` exec-bit tests -- meaningless-to-lying on Windows.
- **`implicit_encoding`** -- add `encoding="utf-8"` to the `open()` call -- the default text
  encoding is locale-dependent on some platforms, not always UTF-8.

### Escape hatch

Set `COORDINATOR_NEW_FILE_RATCHET_NUDGE_OFF=1` to silence this advisory for an autonomous run.
This does not touch either ratchet itself -- it only silences the early warning; the full
test-tier run still catches the underlying violation regardless.

## Plan-persistence hook: idempotency, collision, and the subagent-review-artifact rule {#plan-persistence-check}

This hook fires once, after plan approval (never on a subagent's own internal plan-mode exit). It
copies the approved plan to a dated slug path under the host repo's own plans directory, stages it,
and never commits — committing from a hook child process would bypass every commit-safety check
downstream, so staging is as far as this hook goes.

**Idempotent re-fire.** If the same approval fires again against a target that already holds
byte-identical content, the hook is a silent no-op at the filesystem level: no re-write, no
re-stage, no duplicate plan-index entry. It is always safe to let this hook re-fire on an unchanged
plan.

**Collision policy — a documented refusal, not a silent drop.** If the target slug path already
exists with DIFFERENT content than the plan just approved, the hook does **not** overwrite it. This
is the one branch where the hook actively refuses a write it would otherwise perform; every other
guard in this hook is a silent no-op, and this one talks back precisely so the agent does not lose
the just-approved plan. Resolve the collision manually — compare the two files and choose a new
slug, or merge — before committing anything.

**Subagent review artifacts must be written to disk now, not later.** This is the reminder every
successful persist (and every idempotent re-fire) used to carry inline, verbatim:

> SUBAGENT REVIEW ARTIFACTS: If subagent reviews were part of this planning session, their outputs
> must be written to disk NOW. Agent outputs exist only in your context — if you do not write them,
> they are lost on compaction. Review artifacts are intermediate — write them straight to archive
> (not active folders). The plan document itself must incorporate ALL review findings unless the
> author believes they are in error or require further input.

And the closing note the successful-persist branch appended:

> The goal is a polished plan document, not review clutter.

Nothing here is optional or a suggestion: review-session outputs exist only in agent context, and a
hook-fired reminder is often the last chance to catch them before compaction discards them
irretrievably.

## Dispatch-suite guard: overrides and directory-breadth advisory {#dispatch-suite-guard-overrides-and-directory-breadth-advisory}

This guard sits on the dispatching EM's own Agent/Workflow call (never a subagent's nested
dispatch) and denies a dispatch prompt that hands a subagent a full/undetermined test-suite
invocation in imperative position -- a prompt that merely quotes or negates a suite command in
its authoring prose (e.g. explaining what NOT to run) is not denied.

### Three override hatches, in ascending order of blast radius

Prefer the first one that applies; the third is a named last resort, not a routine option.

1. **In-prompt marker** -- add a line, on its own, carrying a non-empty reason:

   `COORDINATOR-OVERRIDE-DISPATCH-SUITE-GUARD: <why this dispatch is safe>`

   This is the PREFERRED hatch, scoped to exactly the one dispatch carrying the marker. It is
   honored only in text the dispatching EM authored directly in that same tool call (an Agent
   `prompt`, or a Workflow inline `script`) -- never in text read from a `scriptPath` file on
   disk, since a file on a shared branch is attacker-influenceable by anyone with write access.
   The marker makes the suppression self-documenting to the subagent and to anyone reading the
   transcript.

2. **An environment variable**, `COORDINATOR_OVERRIDE_DISPATCH_SUITE_GUARD=1`, typed and
   EM-settable, same shape as the guard's sibling env overrides elsewhere in this plugin. It is
   NOT reachable mid-session -- a shell `export` inside a tool call does not mutate the running
   harness process's own environment, so a live session cannot set this on itself after boot. It
   remains meaningful for a non-interactive/CI invocation, where the process environment is set
   before the harness launches.

3. **A repo-root sentinel file**, `.coordinator-override-dispatch-suite-guard`. Its blast radius
   is the WHOLE REPO: it disarms this guard for every dispatch while it exists, and on a shared
   branch, for every concurrent peer session too. Reach for this only as a last resort -- other
   repos have already reported reaching for it on a single false-positive dispatch
   because the environment-variable hatch was unreachable mid-session and the in-prompt marker
   did not yet exist. That live pressure toward a posture worse than the guard itself is exactly
   what motivated adding the in-prompt marker hatch.

### If the match looks like a false positive

If the flagged text is ordinary prose that merely mentions a test-runner name and was never
meant as a command, that is a known limitation of the shared classifier this guard delegates to,
not something to reword your prompt around. Add the in-prompt marker to get past it for this one
dispatch, but also report the classifier defect upstream -- rewording the prompt to dodge the
guard is not the remedy for that case either.

### Remediation, absent an override

Remove the suite invocation from the dispatch prompt, or path-scope it to a Tier-T (file- and
node-id-scoped) subset before dispatching.

### Directory-breadth advisory (never a deny)

Separately from the deny above, this guard also watches for a dispatch prompt naming a
directory-scoped (rather than file/node-id-scoped) test-runner invocation in imperative position.
This is advisory only -- it never blocks the dispatch -- because a directory-scoped brief is
legitimate when the dispatching EM intends to verify that breadth itself after the dispatch
completes.

The reason it's worth flagging at all: a dispatched agent's own downstream precision guard
refuses a bare-directory positional outright (for a dispatched agent, Tier T is file-and-node-id
precision, not directory scope). Left directory-scoped, the dispatched agent will silently narrow
to whatever files or node ids it can construct on its own, run only that narrower set, and report
THAT run as green -- which is, by construction, narrower than whatever breadth the directory-scoped
brief actually named. Nothing tells the dispatching EM at authoring time that its brief is
unrunnable as written unless this advisory fires. Verifying the breadth actually named in the
brief is the dispatching EM's own job afterwards, not something the narrowed run establishes.

Name explicit file paths or test node ids in the dispatch prompt instead, to avoid the silent
narrowing entirely.

## Worktree ban: rationale, the sanctioned alternative, and the override {#worktree-ban-rationale}

### Why worktrees are banned in this fleet

Git worktrees degrade on Windows, a first-class target platform for this coordinator system, and
they don't scale to the concurrent-agent shape this system runs on: multiple sessions sharing one
working tree with scoped, disjoint file paths per agent is the load-bearing pattern, not a worktree
per dispatched agent. A worktree per agent reintroduces the sequential-grind / worktree-per-item
shape that pattern exists to rule out.

### The sanctioned alternative

Dispatch into the SAME working tree with scoped, disjoint file paths per agent -- this is the
fan-out shape this coordinator system is built around (scoped-parallel edit-only, with commits
serialized through the dispatching EM). If genuine branch-level isolation is required for a
specific piece of work, that is an escalation to the EM, and requires PM-level permission before
it is granted -- it is not something a session grants itself.

### The override -- a repo-root sentinel file, deliberately with no env-var leg

`<repo-root>/.coordinator-override-worktree-guard` suppresses the deny on entering a worktree.
Create it with `touch <repo-root>/.coordinator-override-worktree-guard` from inside a live
session. There is deliberately no environment-variable override for this guard, unlike most other
guards in this tree: a dispatched subagent can set an env var on itself before making a tool call,
which would let it silently grant itself the very override this guard exists to gate. A
session-reachable file, by contrast, is visible and removable by any other session sharing the
tree, and does not let a subagent unilaterally exempt itself.

### Why the deny message itself never names the sentinel file

The deny message a blocked agent sees leads with the sanctioned alternative and does not spell out
the override incantation. A deny message that hands over the exact bypass command in the moment an
agent is blocked reads as a sanctioned next step rather than a boundary, which defeats the point of
gating branch-level isolation behind EM/PM approval. The override exists and is documented here,
reachable by anyone who goes looking for it deliberately -- it is withheld only from the in-context
deny text itself, not from the doctrine that governs when it should be used.

## Derive Global Doctrine: Mirror and Fail Loud {#derive-global-doctrine-mirror-and-fail-loud}

This advisory (`derive-global-doctrine-live-copy.py`) fires when a tracked global-doctrine source
(the repo's own hand-authored copy of the operator's global instructions) may have drifted from
the LIVE copy the harness actually
loads at session start. Direction is always tracked -> live, never the reverse: the tracked file
is the authoring target, and the live copy is a derived mirror of it. Before this mechanism
existed, nothing performed that derivation automatically -- a human had to notice the mirror had
gone stale and copy the tracked file over the live one by hand. That is exactly the failure shape
this project's own north-star doctrine names: a rule whose only discharge is "the operator
remembers." This hook makes the derivation automatic instead.

### Why it also runs at session start, not only on a tracked-file write

A tracked source living in a shared-branch repo changes far more often via `git pull` / checkout /
merge / a teammate's commit than via a single edit tool inside one session -- none of those other
paths fire an edit-scoped event. A session-start check closes that gap: it re-compares tracked
against live every session, regardless of how the tracked file most recently changed.

### The dev-repo gate -- why this never touches a plain install's own config

The live copy this mirror writes to is the OPERATOR'S OWN personal global configuration. For
anyone running a plain install of this tooling with no local working copy of the tracked doctrine
source, the mirror has nothing to derive from and must never write to that operator's live config
at all. A repo-root sentinel file, present only in a genuine authoring checkout of this doctrine
and deliberately excluded from any published/installed copy of the tooling, is the gate: its
presence is checked FIRST, before any other input is even parsed, and its absence makes every
other branch of this mechanism a silent no-op by construction -- not a best-effort heuristic that
could degrade, but a hard precondition checked on every invocation path, including the session-start
path that carries no other identifying payload to fall back on.

### Fail-loud on the one path this mechanism owns

Silence is the correct, permanent behaviour when the live copy is already byte-identical to the
tracked source, or when the gate above did not match -- a check that only speaks on real drift
costs nothing to run on every session. But once the tracked source is confirmed to be the one this
mechanism owns, a read or write failure during the actual derivation is reported loudly rather than
swallowed: a bare "catch and ignore" here would silently reintroduce the exact staleness gap this
mechanism exists to close. This is the one place genuine failure must never be silent, even though
every other guard on the path (no match, source not readable-at-all, an unresolvable root) fails
open and silent by design.

### Manual remedy, if this mechanism is ever unavailable

Absent this automatic mirror entirely, the manual equivalent is a plain file copy of the tracked
doctrine source over the live config path the tooling loads at session start -- the same
tracked -> live direction described above, just performed by hand instead of automatically.

## derive-setup-copies.py: parity modes and remedies {#derive-setup-copies-parity-modes-and-remedies}

This advisory fires on a write matching one of a small canonical->derived pair table this hook
maintains -- files that live in two places in this repo (a canonical, repo-root source, plus an
install-template derived copy) with no code-level sync mechanism between them otherwise. Direction
is always canonical -> derived, never the reverse: a write to a derived copy is an edit to a
derived artifact, so this hook does not silently clobber it (that would destroy the operator's
work) and does not propagate it (that would promote a derived copy to canonical). It leaves the
edit in place and points at the canonical file to re-author in instead.

### The two parity modes

- **byte-copy** -- the derived copy should be byte-identical to canonical. On a canonical write,
  this hook copies canonical -> derived directly, and a direct write to the derived copy is never
  auto-reverted; it is simply lost the next time the canonical copy is touched, since the mirror
  always wins.
- **contract-only** -- this hook never rewrites the derived copy at all. Two different rows
  currently land here for two different reasons:
  - The install template's own resolver-ladder script is a **permanent, deliberate,
    hand-maintained divergence**: it keeps its own resolver ladder a live install needs, which a
    byte-copy would destroy. Parity is enforced on the public callable signature only, via a
    dedicated regression test -- an internal dev-tooling check, not a reader-facing artifact, so it
    is described here in prose rather than by path.
  - `percolate-hooks/README.md` is a **temporary, unreconciled divergence**: its two copies
    currently document two different eras of the percolate mechanism, and nobody has yet
    established which is correct. It sits in this row so a canonical write cannot silently destroy
    the diverged derived copy while that reconciliation is pending -- not because the divergence is
    sanctioned. This divergence is fleet-internal bookkeeping (not something an OSS reader can trace
    or needs to follow); it will be re-designated byte-copy once the two copies are reconciled.

### Fail-loud on owned paths

A read or write failure on a path this hook owns (canonical matched but the file could not be read,
or the derived copy could not be written) is reported loudly rather than silently swallowed -- a
bare "except Exception: pass" here would reintroduce the exact staleness gap this hook exists to
close. Every other case (path did not match any row, repo root undiscoverable) fails open and
silent by design, since this hook runs on every write in the session and silence on the common case
is required.

### Why the read/write-failure and contract-only-on-canonical-write messages dropped their inline paths

These composers used to print both the canonical and the derived path inline, and, on an OS-level
read/write failure, also let the underlying OS error repeat the same path a second time (a
"file not found"/"is a directory" message embeds the failing path in its own text). That
double-printing was the bulk of these sites' pre-conversion length. The fix keeps exactly one copy
of the relevant path -- riding the message envelope's fenced "alternative" slot, separate from the
counted prose -- and reads only the OS error's own short reason text (e.g. "No such file or
directory", "Is a directory") rather than its full message, since the path is already present via
the alternative slot and does not need restating.

The alternative path chosen differs by composer, matching "the file to look at next":

- **read failure**: the canonical file that could not be read -- the operator needs to know which
  canonical source is missing/unreadable to fix the underlying problem.
- **contract-only** and **write failure**: the derived file this write did NOT touch, that the
  operator may need to hand-edit or inspect.

**Measurement note for the next reader.** This hook's own measurement scenario resolves both paths
against a fresh temporary directory, so these sites' measured lengths vary with the OS temp-path
length on the machine that ran the measurement -- shorter on a machine with a shorter temp-path
prefix, but the prose-only portion (independent of any path) is the number that actually needs to
stay under the 280-char ceiling with margin to spare for a realistic in-repo path. These four sites
are also measured via a raw output-stream capture rather than the structured-message capture most
other sites on this page use, so unlike a site measured through that structured capture, the fenced
alternative block here is **not** exempt from what gets measured at this site -- the full rendered
text (prose + fenced path + wiki pointer) all counts. The conversion stays under 280 even so, but a
future edit that lengthens the prose further should re-measure against the rendered total, not
assume the alternative-slot exemption applies here.

## Run-report sidecar: why the notice is unconditional, not an offer {#sidecar-deliverable-notice}

`enforce-agent-dispatch-mode.py` appends a short notice to a dispatched subagent's prompt whenever
the engine plane's own provisioning hands back a `report_sidecar` path for that subagent's type. The
notice is deliberately unconditional -- every eligible dispatch gets it, every time -- not a
courtesy offer the agent can skip.

A prior decision governs a narrower question than it might look like: whether a sidecar gets
provisioned at all. Only subagent types on the `report_sidecar:` eligibility list in
`subagent-sandbox-policy.yaml` get one, so an ineligible type is never over-provisioned with an
empty doc it will never fill in. That decision never licensed skipping a sidecar that WAS
provisioned.

A later decision settled that explicitly: the sidecar is prescaffolded before the agent's first
tool call, and its required frontmatter fields (a divergence note, run observations, and so on) are
a deliverable of the dispatch, not optional prose the agent may leave blank. The notice reads as a
task ("fill this in"), not a maybe ("here's a place you could write notes if you want").

### The machine-readable marker line

Every notice carries a second, separate payload after the human-readable sentence: a literal
`sidecar_path: <path>` line, on its own line, newline-preceded. This is not part of the prose a
human reads for context -- it is a contract a consuming agent parses directly. `code-reviewer`'s own
HARD RULE step 1 keys off that exact line (not the surrounding sentence) to locate its own sidecar,
and the same shape is scanned for by this hook's own dedup guard (to detect a sidecar an
upstream fan-out dispatch already provisioned, and skip re-provisioning). Both consumers depend on
the marker's exact text and position surviving verbatim -- it is intentionally excluded from the
character-cap-counted prose field, and it does not belong inside a fenced "alternative" block
either (its trailing colon fails the alternative block's command/path shape check by design, since
it is a data marker, not a runnable remedy).

### The second emission site: named-dispatch strip

This hook has two distinct emission sites. The human-readable notice this section documents is
authored inside `enforce-agent-dispatch-mode.py` itself. The second site -- the advisory this hook
surfaces to a stripped named-dispatch child when it removes a `name:` key from a named `Explore`/
`Plan` dispatch -- is authored in a sibling shared helper this hook only imports and relays, and is
documented separately in [Named-dispatch strip](#named-dispatch-strip) below, since the text this
hook measures there is not text this hook authors. A comparable sibling advisory for the equivalent
foreground-dispatch strip remains unconverted and is a follow-up candidate, not addressed here.

## Named-dispatch strip: why `name:` is removed from Explore/Plan {#named-dispatch-strip}

`enforce-agent-dispatch-mode.py` strips a `name:` key from an `Agent`-tool dispatch when the
`subagent_type` is the built-in `Explore` or `Plan`. The computation itself lives in its own
shared, pure helper module -- imported by this hook and by a now-deregistered predecessor that
carried the same restricted-type / unknown-key / deny logic, so the logic is written once rather
than duplicated across both call sites. `enforce-agent-dispatch-mode.py` only imports the
computation and relays its returned message verbatim as part of its own single merged notice
(folded in alongside the worktree-isolation and foreground-reroute notes, in a fixed order, on the
same emission site described in [Run-report sidecar](#sidecar-deliverable-notice) above) -- it
authors no text of its own for this concern.

### Why naming Explore or Plan is costly

A `name:` field routes an `Agent` dispatch to a **teammate spawn**, which discards the built-in
agent definition entirely rather than layering a name onto it. For `Explore`/`Plan` specifically,
that means losing:

- the built-in's **read-only tool restriction** (a teammate spawn's `tools` falls back to `"*"`);
- the built-in's **own system prompt**;
- the mechanism that omits the ambient project-instructions corpus from the child's context (a
  teammate spawn includes it).

It also costs roughly **31k more tokens** than an unnamed dispatch of the same built-in.

### The remedy: strip, don't block

None of this is worth blocking the dispatch over. The guard proceeds with the dispatch **unnamed**
instead -- still read-only, still cheaper -- and surfaces a short advisory so the caller understands
why. If the caller genuinely needs teammate messaging (addressing the spawned agent by name later
in the session), the fix is to pick a `subagent_type` whose definition **survives** naming --
concretely, any non-built-in, non-plugin type -- rather than naming `Explore` or `Plan`.

### The fail-closed escape hatch this module owns

Once the dispatch is established as a named `Explore`/`Plan` dispatch, an **unrecognised**
dispatch-argument key, or any other internal failure while constructing the rewrite, returns a deny
result rather than silently falling through to the strip -- naming `Explore` or `Plan` discards its
read-only restriction, so this module fails **closed** rather than risk allowing that through on a
shape it does not recognise. There is no override key for this deny: the fix is to retry the
dispatch without `name:` (`Explore`/`Plan` are read-only and cheaper unnamed), or, again, to pick a
`subagent_type` whose definition survives naming if teammate messaging is genuinely required.

## OSS-payload locality -- what the guard is redirecting you away from {#oss-payload-locality}

`coordinator/`'s OSS payload (see `_oss_payload.py`) percolates outward to a publish-only mirror an
OSS reader installs with none of this fleet's private sibling-repo checkouts on disk. Two distinct
defect shapes trip this guard, and each has its own fix:

- **A private sibling-repo name as attribution prose.** A mention of a private sibling repo (for
  example, the name of the fleet's control-plane engine repo) used as ATTRIBUTION -- not a
  load-bearing wire value -- costs an OSS reader something real: the name means nothing to them and
  the reference is dead on arrival. The fix is to name the CAPABILITY the repo stands in for (e.g.
  "the engine's write-guard dispatch") rather than the repo hosting it. If the name is genuinely
  load-bearing -- a live fallback or wire-key match with nothing to substitute it with -- it belongs
  in the ratified table instead: add it to `IRREDUCIBLE_LITERALS` in
  `coordinator/hooks/scripts/_oss_operative_strings.py`, following the ENTRY CRITERION reasoning
  that file's own docstring asks for.
- **A drive-rooted Windows path.** Hardcoding a machine-specific value into shipped prose or code
  where a portable form was available. The fix is a portable form instead -- pathlib, an env var, or
  a settings-home resolution -- so the OSS payload never ships a machine-specific value.

### Why this is a hard deny, not an advisory

This guard denies only on the write's own NEW violations (see `new_violations()` in
`_prompt_surface_locality.py`) -- the same reasoning as the sibling prompt-surface citations guard.
A legacy violation sitting untouched elsewhere in the file contributes equally to both sides of the
before/after diff and never surfaces here; only a violation this write is the first to introduce (or
duplicates a second time) does. That is what makes a hard deny safe against the existing corpus
without wedging every future touch to an already-imperfect payload file.

## Initiative goals nudge remedies {#initiative-goals-nudge-remedies}

This advisory (`nudge-initiative-goals-ladder.py`) fires on a `Write` or `Edit` to a
`state/initiatives/*.yaml` file whose `goals` field is empty or absent, in a repo that already
has at least one goal file under `state/goals/`. It is advisory only and never blocks: an
initiative genuinely without goals is a normal, supported shape, and a hard block would fight
that instead of just prompting a second look.

### Attaching a goal

Use `coordinator-initiative attach` to tag one or more goals onto the initiative:

```
coordinator-initiative attach --goals <goal-id>[,<goal-id>...] state/initiatives/<initiative-id>.yaml
```

When the nudge names one or more candidate goal-ids, those are the best textual matches against
the initiative's `label`/`description` (or its filename stem, if neither is present) — attaching
the first one is usually the fastest path, but any of the named candidates, or a different goal
entirely, is a valid choice.

### If this initiative intentionally has no goals

Ignore the nudge — nothing is blocked, and no state changes as a result of the nudge firing. It
is a one-time offer surfaced on the write, not a recurring or escalating warning.

### Escape hatch

Set `COORDINATOR_INITIATIVE_GOALS_NUDGE_OFF=1` to silence this advisory for an autonomous run.
This does not remove or alter goal-tagging in any way — it only silences the offer; an initiative
written under this env var still has whatever `goals` field the write itself gave it.

### Degraded operation

If the candidate-goal-matching capability is unreachable (its host service can't be resolved
locally, or the match lookup itself fails), the nudge still fires — it simply omits the candidate
suggestions and falls back to the generic "this repo has goals, consider tagging one" text. This
degradation is deliberate: a nudge with no suggested candidates is still a valid, safe nudge, and
the hook never treats an unreachable matcher as a reason to stay silent or to crash.

## Workflow offer nudge {#workflow-offer-nudge}

This advisory (`nudge-multiwave-workflow.py`) fires on a `PreToolUse` `Agent` dispatch when the
EM hand-dispatches the Nth write-capable executor (or `review-integrator`/`enricher`) within a
rolling window — N defaults to 4 dispatches within 30 seconds. It is advisory only and never
blocks: the tool call it fired on always proceeds.

### What a background Workflow buys over hand-dispatch

A background Workflow survives your own compaction, encodes the wave gates a hand-dispatched
sequence has to track manually, and keeps each executor's output out of your context window
instead of accumulating there dispatch by dispatch. Your PM is happy to approve a Workflow where
it's a good fit for the work, and a Workflow is already pre-approved for `/execute-plan`
specifically — no separate PM sign-off is needed to use one there.

### When hand-dispatch is still the right call

If the work in front of you is genuinely ad-hoc parallel work rather than a multi-wave plan, a
run of hand-dispatched backgrounded agents is a legitimate way to do it — carrying on is fine.
You're the EM; the nudge is a prompt to double-check the fit, not a verdict that hand-dispatch was
wrong. Nothing about the dispatch that triggered the nudge is altered or blocked by it.

### Firing cadence

This nudge fires at most once per session. Once a `Workflow` tool call has been made in the
current session, the nudge never fires again for the remainder of that session, regardless of how
many further executors are hand-dispatched.

### Escape hatch

Set `COORDINATOR_OVERRIDE_MULTIWAVE_WORKFLOW=1` to suppress this advisory entirely for a session.
This does not change how any dispatch is routed — it only silences the offer.

## Pickup decision-report evidence tail: not a guard advisory, a decision-report render {#pickup-decision-report-evidence-tail}

**Read this before converting this site again.** The `render_additional_context` site inside
`pickup-autofire.py` is not the same kind of site as the rest of this page's Category-A
conversions. Every other site on this page composes a short, hook-authored ADVISORY sentence --
"here's what happened, here's the off-ramp" -- where the reader already has the mechanism from the
skill/agent/wiki and the guard only needs to name the exception. This site instead RELAYS the
actual content of a pickup decision back to the EM: narration and next-move guidance computed by
the engine plane, an EM-supplied prose note, and a droppable JSON evidence tail -- none of which is
boilerplate this hook invented to explain itself. Shrinking it is not the same move as shrinking a
static advisory.

### What actually changed

The only genuinely compressible thing here was the **evidence tail's default presence**. Before
this pass, the decision-report composer always built the `Evidence:\n{...}` JSON block, letting the
existing (much larger, ~10,000-char) context budget degrade ladder drop it under real budget
pressure. For a simple "everything's fine" decision (no open judgment points, no gate carrying
anything beyond a clear verdict), that JSON block is a byte-for-byte restatement of facts the
verdict line already states in prose -- it was never informative for that shape of decision, only
for a genuinely complex one.

A new informativeness check now skips composing the evidence segment entirely for that
non-informative case, rather than composing it and relying on the large budget ladder to drop it:
informative iff there is at least one open judgment point, or a gate carries a key beyond the
default, or the default gate itself carries a key beyond its verdict. This is a genuine
simplification, not a truncation -- nothing is cut off mid-sentence, no escape hatch or override key
existed on this segment to lose, and a decision that IS complex still gets its full evidence tail,
still droppable under the unchanged large-budget ladder if it's large.

### Why this is flagged, not just silently applied

This site was scoped into this page's write targets because an automated classifier saw a
guard-shaped context emission and marked it Category A alongside the rest. That classification is
correct in the mechanical sense (the text IS composed by this hook), but the 280-char guard-message
ceiling this page otherwise documents was calibrated against short off-ramp sentences, not against
a decision-report renderer that already has its own, separately-designed, separately-tested
much-larger budget contract. The fix applied here (suppressing a non-informative evidence tail) is
defensible on its own terms -- it removes redundant content, not operative content -- but it is a
genuine judgment call about what this site's job is, not a mechanical prose trim. A future reader
revisiting this site should treat its own large-budget ladder as this function's real budget
contract, and the 280-char ceiling as satisfied incidentally by the evidence-suppression fix rather
than by routing this function through the same single-message envelope every other Category-A site
on this page uses -- this renderer returns a hand-assembled multi-segment string by design
(narration/verdict/next-move/your-call/evidence, capable of covering more than one work item at
once, with its own truncation ladder), and forcing it through the single-message envelope shape
would be a worse fit than leaving it as its own renderer.
