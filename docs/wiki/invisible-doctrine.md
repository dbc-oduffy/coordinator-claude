# Invisible doctrine — the north star for the coordinator rebuild

> The organizing ambition behind the computed-skills frontage rollout, the skills-carry-no-code
> extirpation, and the dispatch-seam rebuild. Those three tracks look like separate cleanups.
> They are one idea applied at three altitudes, and this page is that idea.
>
> **Audience: the person CHANGING the system**, not the person using it. That distinction is
> itself part of the doctrine (§ Nobody reads this while acting), so read this at design time —
> when scoping a baton, writing a contract, or deciding what a surface should look like. It is
> deliberately not written to be recalled mid-ceremony, because nothing should have to be.
>
> Spec backlinks: `docs/decisions/DR-090-the-unit-of-extraction-is-the-mechanical-step.md`;
> `docs/wiki/computed-skills.md` (the contract); `docs/wiki/coordinator-tripwires.md §
> SKILL-NARRATES-PROCEDURE`. Origin: the DR-090 alignment session.

## The north star, in one paragraph

<!-- First computed frontage of the programme, named in the sizing-lobby core session: -->
<!-- "routing you can no longer do wrong, not a rule you must remember." The paragraph -->
<!-- below is that framing's durable statement. -->
**Coordinator should stop being a system you comply with and become one you cannot easily do
wrong.** Every rule we write is a small failure — it means we shipped a surface that permits the
mistake and then asked a human or a model to remember not to make it. The target state is that
the correct path is also the easiest path, so nobody experiences a choice, and the rule is never
encountered as a rule at all. When this works you will not notice it working. That is the point,
and it is also why it is hard to sell: nobody thinks about the sound team when the mix is good.

## How we got here — six escalating realizations

Each one looked like the whole answer at the time. Each was a special case of the next.

1. **The fence.** A multi-line command payload pasted into a `SKILL.md` makes the *EM the
   transport*: it reads the block and retypes it into a shell. The defect is not the payload's
   language — text handed to bash could equally be handed to python. It is that code living in a
   markdown fence is invisible to every gate we own: unlintable, untestable, uncountable. Cured by
   `SKILLS-CARRY-NO-CODE`.

2. **The step.** Killing fences was not enough, because a numbered prose sequence of single-line
   invocations passes that gate and is the same defect. *"Stage these paths, then commit them as
   one unit, and say whether this was a first run or a refresh"* has zero branches and is entirely
   mechanical. The unit of extraction is the mechanical **step**, not the mechanical **branch** —
   branching is one species of step; sequencing is another. Cured by DR-090.

3. **The reader.** Sharper still: that step explains `git commit` to a frontier model that has
   known how to commit since pretraining. It is not merely badly factored, it is a *tutorial
   written for the wrong reader*. What a surface keeps is context the reader **cannot** have —
   this repo's policy, this ceremony's ordering constraint, this gate. Never procedure it already
   has. The same defect appears one level up when an EM writes a dispatch brief restating a
   subagent's own job description back to it.

4. **The artifact.** And then: nobody reads any of the above while acting. A rule that must be
   recalled has already failed, however well written. The rule must be discharged by the shape of
   the thing in the operator's hands.

5. **The seam.** Sharper still, and the one that cost two passes to see: building the artifact is
   not the same as the artifact reaching the operator's hands. `/pickup` did the first four things
   right — a compute layer (`pickup_assemble.brief()`) resolved classification and gate state
   server-side; a mutation layer (`apply.py`) existed to execute it; an auto-fire hook
   (`pickup-autofire.py`) was even written to call it automatically, gated correctly on
   `coast == clear AND judgment_points == []`. And it still didn't work, twice, because each piece
   was individually correct and never verified as one connected chain: the consuming `SKILL.md`
   kept ~230 lines of memo-`kind` adjudication prose the EM had to self-navigate regardless of
   `artifact.classification` (the compute existed; the *reader* never stopped reading the branch
   that didn't apply), and the auto-fire hook called a CLI subcommand (`pickup-assemble apply`)
   that was never built — so the hook silently no-op'd, by design (fail-open), which made the gap
   invisible instead of loud. Two more escalating failure modes past "the operator remembers":
   **the artifact was built but the consuming surface never stopped duplicating it** (SKILL.md
   still carries the branch the assembler already resolved), and **the wiring was designed and
   even called from the caller's side, but the callee was never finished** (an already-gated
   auto-fire hook calling a CLI verb that doesn't exist). Both read as "done" from inside the one
   piece you're looking at. Neither is done until you trace the artifact end-to-end and watch it
   actually arrive.

6. **The adventure.** The seam (#5) says trace the wire until the artifact reaches the operator's
   hands. The sharper form — the one the *third* pass on `/pickup` forced, after the first two
   built every layer and still missed — is that resolving which branch applies is only half the
   job. The assembler must **hand the operator the resolved branch, already assembled, and hand
   them nothing else.** A skill body that still carries *"if this is a memo … / if it's a
   spinoff … / if a peer is live on the branch …"* prose has not been thinned; it has been caught.
   **Deterministic if/else is code in a markdown fence at the logic level** — realization #1 one
   abstraction up. It branches on facts the engine already computed (`artifact.classification`,
   the claim state), so it *runs in code*, and what reaches the operator is its resolved output,
   never the branch table. The line-count of a skill body is therefore a real success criterion,
   not a vanity metric: 333 dense lines of branching prose is a failure by construction, because
   every branch in it was deterministic and belonged in the engine. Three consequences bind:
   - **Push the adventure; do not make them pull it.** The classification-appropriate guidance —
     *how* you run a memo versus a handoff baton — is injected into the operator's hands at fire
     time (the assembled brief, the auto-fire hook's `additionalContext`), keyed on the nature of
     the material in front of them. The operator never scrolls a rulebook to the section that
     applies; the section that applies is the only one they are shown. A static doc the operator
     must navigate to find their own case is a *pull*, and a pull is the rulebook defect intact.
   - **The surviving prose is the irreducible, non-branching action core — and nothing else.** For
     `/pickup` that is exactly: grab it if it is unclaimed, check first for a warning, do not grab
     it if it is claimed, and — the one genuine universal — how to drop a baton. If you take it,
     you run with it. Everything else was bloat wearing a rulebook's clothes. The mechanical test:
     a grep for branch-selection vocabulary in the skill body comes back empty, because every
     branch now lives where branches belong.
   - **Do not manufacture a judgment point out of noise** — the same defect inverted. The second
     pass surfaced *"a sibling handoff on this branch is held by a live peer — proceed or stand
     down?"* as an Opus-tier question, when nothing claimed *this* artifact and a shared tree is
     *always* noisy. Surfacing concurrency the operator can do nothing useful about is not
     assembling the adventure; it is the engine *inventing* a branch instead of a doc *carrying*
     one. Assemble only what genuinely gates (is *this* item claimed?) and what genuinely needs
     judgment (a memo's disposition); inject exactly that, and stay silent on the rest. An
     action-oriented operator is a feature to protect, not a risk to hedge.

   § Wu wei applies this same rule one notch further, to whether the invocation resolving the
   branch needs to exist at all.

## The discharge test

> **For every rule: what artifact discharges it? If the answer is "the operator remembers," the
> work is not finished.**

This is the single test to apply when scoping any conversion. Worked examples:

| Rule | What discharges it |
|---|---|
| never `git add -A` | the op does the commit — no git is typed, so nothing can be got wrong |
| pass the path, not the paraphrase | the sidecar arrives with disposition blanks; the path is already what's in hand |
| write thin briefs | fat agent definitions + an intake that takes a path — nothing left to write |
| extract the mechanical step | the assembler exists, so there is no step to narrate |
| don't misremember the CLI subcommand | the answer is already in the brief, so there is no name to recall |
| classify the pickup, then act on its class | the assembler resolves the class and injects only the applicable branch's guidance into the fired message — there is no branch for the operator to select, and no rulebook section for them to find |
| don't retire a form while a reader survives | the advance op re-derives consumers and refuses (`docs/plans/2026-07-25-cutover-state-machine.md`; `coordinator/docs/wiki/cutover-state-machine.md`) |
| don't remember which sidecar a review dispatch owns | one structural home, one mechanical guard — reviewer sidecar provisioning resolves the path and reconciles it against the mechanical guard, so there is no sentinel left to remember across the fleet's review dispatches (`2026-07-24-reviewer-sidecar-provisioning-reconciliation-7d4e70.md`) |

None of those require learning anything. The artifact's shape *is* the rule.

**Corollary — build the artifact before the tool.** The instinct is to reach for a CLI. Often the
artifact alone suffices: if a reviewer emits its findings sidecar with an empty disposition slot
under each finding, the operator fills blanks that are already in front of them — no command to
remember, no flag to learn — and what they are then holding is already the next agent's input. A
CLI becomes an accelerator for bulk cases, not the mechanism. Prefer the shape over the tool.

### The callsite discriminator

> **A write fired from inside an op that already runs at the trigger discharges the test. The same
> write as a CLI line in skill prose does not — the EM types it, so the EM must know it exists.**

The tell: a "discharged by" column naming an invocation rather than an artifact. Replacing a
hand-edit with a single-writer command is a real improvement and still leaves the operator
carrying the mechanism; the test grades what must be remembered, not how much better it got.
Correction: find the op already firing at that trigger and move the write inside it.

Applying this honestly will sometimes empty a workstream — the slate shrinks to doctrine plus a
walk and the plan becomes a memo to whoever owns the ops. Keeping callsites in prose to justify
the artifact is this test failing in the direction nobody flags, because the result still looks
like a plan with chunks in it.

## The act/disposition boundary — the discharge test's edge

> **A mechanism can enforce an act. It cannot install a disposition.**

Read literally, the discharge test says: mechanize everything, and where the answer is "the
operator remembers," the work is not finished. A zealous reader applying that literally to a
doctrine file concludes that because no guard enforces "voice disagreement rather than swallowing
it," that line is unfinished work, waiting for a mechanism to replace it. It cannot be finished
that way. This section names the bound the discharge test needs and does not state on its own —
not a caveat bolted onto the test, but the edge of its domain. Without it, the north star eats the
very content that most needs saying: relationship and posture prose, cut for being "merely
prose," on the theory that a future mechanism will absorb what it carries. No mechanism ever will.

**Why not.** A guard fires at the moment of a specific act — it can block a blanket `git add`, deny
a bash call, refuse an out-of-order dispatch. A wiki, a DR, a doctrine block is read only if
someone chooses to read it, or it is loaded and sits inert until the moment it's needed. Neither
of those is the same operation as making an agent *default* to something absent a reminder.
Defaults live only in what is loaded before the agent acts — not in what fires when it acts, and
not in what waits to be consulted. An act is a single crossing a mechanism can stand at and check.
A disposition is a standing inclination that has to already be there, unprompted, at every one of
the many moments nothing is checking. There is no artifact whose *shape* carries an inclination —
only ones whose shape carries a rule about a single act, and a disposition is not that.

**The practical inversion — this is what makes the boundary operational, not just true.**
Procedural prose ("commit this way", "run the fast test tier before commit") has many possible
homes: a guard, a hook, an op, a test — prose describing it is therefore its *weakest* available
carrier, worth keeping only until a mechanism replaces it (Tier 2 at best; see
`coordinator/docs/wiki/claude-md-authoring-and-boot-context.md § 13`). Relationship and posture
prose — how the EM talks to its human, what it defaults to when nobody is watching, when it
pushes back before complying — has exactly *one* possible home: always-loaded prose. So when a
loaded budget is tight, the correct edit is the opposite of the instinct that reaches first for
the soft-sounding paragraph: **procedural content is what goes, relationship content is what
stays.** The instinct to cut it first is optimizing for concreteness (it reads like busywork,
easy to point at and trim) instead of irreplaceability (nothing else in the system could have said
it). Trimming a doctrine file by removing what looks like filler and keeping what looks
technical gets this exactly backwards.

**Worked pair.** "Voice disagreement with the PM before complying, rather than swallowing the
objection and executing silently" (§ How to Escalate, `~/.claude/CLAUDE.md`) — and, similarly,
"default to dispatching a subagent rather than self-authoring the fix" (§ Engineering Remit) — are
dispositions: nothing fires at the moment an EM chooses silence over pushback, or a keystroke over
a dispatch call, because there is no discrete act to intercept — only a choice made or not made,
privately, before any tool call exists to check. Compare "commit with a scoped pathspec, never
`git add -A`": that is an act, and it is in fact mechanized — `coordinator_core.bash_guards.
block_blanket_git_add` denies the blanket form structurally. One of these pairs was rightly
converted to a guard and retired from prose (the discharge test, working as intended); the other
has no such conversion available and stays prose by necessity, not by neglect.

Verbosity in an EM's reply to the PM was long read as belonging with the second pair — a
continuous property of a finished artifact, with no keystroke a guard could stand at. That reading
held only as long as the carrier list stopped at "what the model composes." `MessageDisplay`
supplies a crossing the composition step never had: the render between a finished reply and what
the PM's screen shows. A guard standing there caps what crosses, the same structural move as
`block_blanket_git_add`, without installing a disposition at composition time — the model can
still compose 400 words; only what displays is capped. The carrier list above is therefore not
guard-vs-prose alone; it is every discrete crossing a mechanism can stand at, composition and
render alike, with prose reserved for what has no crossing at all.

## The Captain's Chair standard

The discharge test asks the question of a *rule*. Ask the same question of a *session*, moment to
moment, and it sharpens further: what does the operator actually do with their hands, right now?

**The captain just sits in the chair.** Picard never runs the sensor sweep — the bridge crew does,
then reports "Captain, we're being hailed", and the call gets made. Applied to an EM session: everything mechanical is
already done, and already narrated, before it reaches the operator. What reaches them is a
decision, never a task list.

**The test:** if the EM types a command in order to *find something out*, the system has already
failed — regardless of whether the command succeeds. A command is for acting on a decision already
put in front of the operator, never for going and getting one.

**Name the antipattern: homework.** Homework is any mechanical step the system could have
performed but instead handed to the operator to perform by hand — list a directory to find a
filename the system elided, retype a path, re-run a diff the engine already computed and then
discarded. Homework is a defect in the surface that assigned it. It is never a discipline failure
in the operator who did it, no matter how capably they did it.

**Homework is not only a step. A form is homework too.** The examples above are all *actions*,
which makes them easy to recognize and lets a subtler shape pass: a decision map, template, or
argument set the operator is asked to *populate* with facts the engine holds. A ceremony that
emits a forty-key template whose keys are `gross_loc`, `commit_count`, `surface_count`,
`deleted_paths`, `plan_path` has not asked the operator to decide anything — it has asked them
to transcribe. Each key is individually trivial, which is exactly why the shape survives review
that would have caught any one of them as a step. **The test is not "is this hard?" but "does
the operator supply this, or does the engine?"** Facts are computed and shown. They are never
requested. A template arrives populated, with the operator overriding what they disagree with,
or it should not arrive at all.

**Count the asks at a gate, not just the lines in a body.** § The adventure establishes skill-body
line-count as a real success criterion. The gate-side equivalent is the number of things the
operator must answer before the ceremony proceeds, and it fails differently: past a handful,
volume itself changes behaviour. A long list trains batch-answering, which is the posture in
which the two or three that genuinely needed thought get answered carelessly — so a surface with
twenty-five prompts is not "three good questions plus twenty-two cheap ones," it is a surface
where the three good ones do not get a real answer. Worse, operators skip it, and § Ergonomics
already concedes they are correct to. **A ceremony that gets bypassed is worse than one that
rubber-stamps**, because the rubber stamp at least leaves the mechanical half done.

The two failures cure together, and this is why they are one section rather than two. Trimming
the drudgery is not a cost paid to buy completion, and completion is not bought by making the
ceremony cheap: **the ceremony completes because what remains in front of the operator is the
handful of calls that are actually theirs.** So reject a fix that cuts the count while leaving
computable items in the set — the drudgery survives and so does the skipping — and equally reject
one that raises completion by letting the survivors go perfunctory.

The corpus exemplar: `/coordinator:pickup`, PM pasting a handoff path a terminal had visibly
elided. The assembler resolved exact paths only, failed closed with "could not resolve," and
pointed at the archive; the auto-fire hook duly delivered an empty decision object — no
directives, no judgment points, correctly wired and firing on nothing. The EM then hand-listed the
handoffs directory to find the real filename, re-ran the brief, re-ran apply, and hand-ran `sed`
on the plan and `git show` on a commit whose diff the engine had already computed and discarded.
Four manual steps, none of them judgment. The captain got up and worked the console.

**The tempting fix is a rule, and rejecting it is the whole point of this page.** *"EMs MUST pass
the full file path"* is exactly the failure mode the north star exists to reject — a rule is a
small failure, an admission that we shipped a surface permitting the mistake and then asked
someone to remember not to make it. It would not even have worked here: paths arrive by
copy-paste out of a terminal that elides them, and the operator frequently cannot see the full
path anywhere on screen to comply with the rule even if they remembered it.

**The corollary that generalizes:** input arriving in degraded form — elided, abbreviated, pasted
out of a lossy transcript — is the normal case, not operator error. The system absorbs it. Where
the degraded input is still unambiguous, resolve it and say what was resolved. Where it is
genuinely ambiguous, ask a real question with the candidates listed. What the system never does is
fail closed and hand the work back.

## Wu wei — the target invocation count is zero

The discharge test asks what artifact discharges a rule. This is the same rule from § The
adventure (realization #6) and § The discharge test, applied one notch further: not only must the
resolved branch reach the operator already assembled, the *invocation* that delivers it should
not need to exist at all. What's new here is a ranking, not a restatement.

**First-best: zero invocations.** A mechanism fires around the EM on the trigger that already
tells us the moment has arrived; the artifact is there when the EM arrives, and nothing is ever
typed to mint or close it. `pickup-autofire.py` is the fleet's working case: on `coast == clear
AND judgment_points == []` it calls the mutating apply half itself. `mise-autofire.py` and
`handoff-segment-inject.py` (`coordinator/hooks/hooks.json`, `UserPromptExpansion`) are the same
pattern at the same seam.

**Second-best, where an invocation is genuinely irreducible: one invocation, not many.** Collapse
the scripts a step would otherwise chain behind a single invocable entry point, so the operator
crosses one seam instead of narrating a sequence across several. A step that types `bin/A`, reads
its output, then types `bin/B` with a value pulled from that output has not been thinned by
naming both tools correctly — it has been caught wearing correct tool names. Merge A and B, or
give the EM one op that runs both.

**Third: a computed skill resolves the branch, it does not list the branches.** Same rule as
realization #6, applied to which skill fires at all rather than only what it says once it has —
`coordinator:sizing` routing to `plan` for both an S-sized change and an XXL one is not routing to
"the same job twice"; the delivered instruction must be the *resolved* one.

**Shipped, not proposed.** `coordinator/skills/handoff/residue/` (8 segments, `case:`/`order:`
keyed, hook-injected by `handoff-segment-inject.py`) and `coordinator/skills/review/residue/` (14
segments, retrieved by an assembler op scoped to the resolved `--surface`) are both live instances
of the third point: the reader never sees the full menu, only the segment set their own case
resolved to.

**The gap is real and it is the PM's own example.** `plan-outline-maker.py` does not exist in
either this repo or `claude-klabauter` — `coordinator/skills/plan/SKILL.md` still instructs the EM
to type the scaffolder rather than having it minted for them. The stamp-and-close family is the
same shape: `coordinator/skills/execute-plan/SKILL.md`'s `close-out-and-stamp` and
`coordinator/skills/workstream-complete/SKILL.md`'s `workstream-complete-assemble` are both
EM-typed invocations at a moment — chunk-work-complete, workstream-complete — a hook could equally
have fired on. Naming the gap does not close it; it is left as a known instance of the antipattern
this section states, for whoever next touches those surfaces. This is a live inventory, not a
permanent record — trim an entry the moment its surface closes rather than let it accrete.

**Worked example of the failure: `coordinator/skills/percolate/SKILL.md`.** 346 lines, with a
365-line sibling procedure file (`percolate-setup-procedure.md`), and 16 separate lines typing a
`bin/` invocation in the SKILL body alone. Percolate should be a trigger firing a script, with a little
prose residue left over — and the prose that survives should be judgment: when NOT to publish,
what a large DELETE count means. It should not be the sequence, because the sequence is exactly
the thing a mechanism can fire around the EM instead of asking them to type.

## A shipped recommendation is self-evidence

> **If the engine can defensibly recommend an answer, the question was never the operator's.**

§ The adventure names two failures at the judgment-point seam: inventing one out of noise, and —
under § What this does NOT mean — auto-resolving one that is genuine. Between them sits a third
that neither covers and that is by far the most common: **a point the engine can answer, and
often already does, presented as a question anyway.**

The tell is mechanical and needs no interpretation. If the emitted point carries a
`recommendation`, the engine has demonstrated that the answer is derivable from evidence it
holds. That demonstration is the demotion path. The point should have been a directive, and
carrying it as a judgment point with a suggested answer attached is the half-converted state —
the compute landed, the surface never stopped asking.

**A null recommendation is not proof of the opposite.** A point may ship no recommendation for
three quite different reasons, and only one of them is legitimate:

- **Genuine.** The evidence originates outside this engine — a sender's memo prose, a peer's
  commits, the operator's own unstated intent — or the answer is authorial or a real tradeoff.
  Leave it alone. The untrusted-gate constructors that structurally refuse a `recommendation`
  parameter are the standing example, and refusing it there is a design, not timidity.
- **Blocked computation.** The point is unresolved only because some input was not computed,
  where that input is itself computable. Asking the operator for arithmetic the engine declined
  to do is homework wearing a judgment point's costume.
- **Missing producer.** The engine names a data source that does not exist. This is honest — it
  is better than fabricating — but it is a gap to close, not a question to ask. A `reason` string
  that says "there is no producer anywhere in this codebase for X" has diagnosed itself.

So the audit question is never "does it ship a recommendation?" alone. It is: **for each point
that does not, which of the three is it?** Only the first survives.

### Applied by default is not "do not question the machine"

This rule removes an *ask*. It must not remove the *look*, and the difference is the whole design.
The target shape is the paperwork filed for you and shown to you, correctable where you disagree
— never a black box whose output you countersign. An operator who applies a recommendation they
can see is wrong has failed worse than the questionnaire did, because the questionnaire at least
made them look.

Two things keep this honest, and a conversion that drops either has built the wrong thing:

- **The receipt is legible and it is read.** What was applied, and on what evidence, arrives in a
  form an operator can scan in one pass and challenge. A receipt nobody can check is a rubber
  stamp with better manners.
- **Overriding is free.** No justification owed to anyone, no friction, no re-litigation. The
  moment an override costs more than acquiescence, § Ergonomics predicts what operators will do,
  and they will be correct to.

The engines are wrong sometimes, and the operator is the only one positioned to notice. The
session that wrote this section found four live defects in ceremony engines precisely because an
EM read the evidence strings instead of taking the emitted state at face value. **Removing
twenty questions is what buys the attention to catch the twenty-first.** That is the trade, and
if the attention does not get spent, the trade was not made.

### Tentativeness dressed as concision

The reason this recurs across passes is worth naming, because the failure is not laziness and
will not be fixed by trying harder.

Every conversion pass faces each candidate individually, and absent a standing rule the
conservative answer wins every time: keep the decision point, just in case. Nobody is ever
blamed for a question that turned out to be unnecessary. Meanwhile the deterministic predicate
gets rewritten as tighter prose rather than moved into the engine, and the tightening *reads as
progress* — the body got shorter, the branch table got cleaner. **A shorter branch table is still
a branch table**, and prose being well written is not a defence when the branch was computable.

Three tells, all greppable:

1. A surface that **self-labels a step** "mechanical checkpoint", "checkable count", or
   equivalent, and still hands it to the operator. It has already made the finding; it just did
   not act on it.
2. A predicate annotated **"not yet engine-computed"** and left in place. The annotation is the
   defect confessing itself and being filed rather than fixed.
3. A pass that **reduces the count** of asks without changing what kind of thing is asked. Twenty
   prompts becoming twelve is not a conversion; it is the same defect at lower volume.

And the corollary for anyone tempted to keep a gate because the operator might do the thing
badly: § The adventure already rules that *an action-oriented operator is a feature to protect,
not a risk to hedge*. Applied to gates, that means **do not build one priced for a contributor we
do not have.** A step that exists to stop a careless operator writing a lazy commit message, or
skipping a field, is priced for a junior human under deadline pressure. The crew here is diligent
and well-meaning by construction. Gate what genuinely gates; trust the rest.

## Ergonomics, not enforcement

The tempting next move after the discharge test is *"make the wrong thing unrepresentable."* That
is still constraint-thinking — it moves the wall rather than removing it.

**The real test is whether the right path is cheaper than the wrong one.** If recording a
disposition through a tool costs more keystrokes and more thought than typing a paragraph into a
brief, operators will route around it and they will be *correct to*. We would have built a wall
and called it a tool. Get the ergonomics right and unrepresentability stops being a goal: it
becomes a side effect of a shape good enough that nobody wants the other path. Nobody obeys
anything; they take the easy road, which happens to be the correct one.

This is why every baton in the frontage rollout carries an **Ergonomics AC** as a required field
rather than a prose reminder: *the new path costs fewer keystrokes and less thinking than the
shape it replaces; a technically-correct conversion that makes the right thing harder has FAILED.*
It is verified at the dogfood gate, because that is where it surfaces anyway.

The field is a field, not a sentence, for the same reason as everything else on this page — the
discharge test applied to itself.

## A prose guard is not a guard

A guard that asks a model to refuse work it is eager to do is advisory in practice, whatever its
wording claims — and emphasis does not fix it.

The corpus exemplar is a hard-stop intake precondition that is about as emphatic as prose gets
("this is a hard stop, not a soft preference… do not proceed under any circumstance, even if they
look complete"), which *documents its own non-determinism from a prior dogfood* and then failed
again on every dispatch in a later session. It is a well-written rule. It does not work, and no
rewrite will make it work.

Reach for the shape instead: an intake that takes a path cannot receive pasted content, and the
failure lands as a usage error at the boundary rather than a judgment call in the middle.

### Carve-out — irreversible harm stays a block

Ergonomics is the rule for friction, not for data loss. The floor guards against destructive
operations remain hard blocks, because there the cost of the wrong path is not wasted tokens. A
tutorialized brief wastes effort; it deletes nothing. Know which register you are in before
softening anything.

## Nobody reads this while acting

Doctrine surfaces and artifacts have different audiences, and conflating them is a category
error we have committed repeatedly:

- **DRs, wikis, tripwire entries, decision records** — for the person *changing* the system.
  Legitimate, necessary, and the right home for *why*.
- **The artifact in hand** — for the person *using* it. This is where behaviour actually comes
  from.

A `→ DR-NNN` pointer at the end of a constraint is a link nobody follows forty steps into a
ceremony. That does not make the DR wrong; it makes it the wrong *mechanism*. Write the reasoning
down, then go build the thing that means nobody needs it.

**The honest self-check when a doctrine session ends:** how much of what we produced was inert?
Prose that states a rule is necessary and it is also the weakest available fix. If a session
produces only documents, it has aligned on an ambition without moving toward it.

## The success metric

**Invisibility.** If this works, no future contributor writes a page explaining good brief
hygiene, or good commit hygiene, or how to sequence a ceremony's pre-steps — because none of
those will be experiences anyone has. The tell that we failed is the appearance of exactly such a
page: the front-of-house engineer explaining the monitor mix to the audience.

A useful inversion when reviewing a converted surface: *what did the operator have to know?* If
the answer is anything beyond their own intent, there is more to discharge.

## What this does NOT mean

- **Not the removal of judgment.** The operator's judgment pass is load-bearing and stays — it is
  what catches the finding that should not be applied as written. What gets removed is
  *transcribing* that judgment, not exercising it. An assembler narrows the search space; it does
  not decide.
- **Not thinner surfaces everywhere.** Agent definitions should be *fat* — durable,
  version-controlled, reviewable, loaded on every dispatch. Persona definitions in particular are
  legitimately long because the persona *is* the content. Thinness belongs in the ad-hoc,
  per-invocation surfaces (the brief), not the durable ones.
- **Not automation of the whole loop.** The goal is that mechanics do not stop for the operator
  and judgment does. A conversion that auto-resolves a genuine judgment point has failed in the
  opposite direction, and more dangerously — see the untrusted-probe confirmation gate in
  `computed-skills.md`, which must remain unresolved when no human is present.
- **Not a licence to delete provenance.** Accreted archaeology relocates to git history, a wiki,
  or a DR. Only *tutorial* prose — procedure the reader already has — is deleted outright, because
  it was never doctrine and nothing replaces it.

### The sizing/lobby limit

The conversion rule has a floor, and `coordinator:sizing` sits on it. Its own routing table
converted cleanly and completely — but that table is the only mechanically-shaped thing in the
surface. Roughly 7% of the skill's lines are the converted surface; the remaining ~82% is intake
prose: forming the estimate, deciding whether to probe, answering the provenance question
honestly, asking the PM. Those are **speech acts and inputs, not computations**, and no amount of
engine work converts them, because there is nothing computed on the other side to converge on.

Conversion of a judgment-heavy surface does not always shrink it. `sizing_assemble`'s conversion
*generated* a 59-line anti-anchoring guard, precisely because the engine cannot see whether an
estimate arrived pre-contaminated — that gap has to be covered by prose, not code. A converted
surface that grows is not evidence the conversion failed.

The shape this class of surface is *for* is a bank of probes in the torpedo tubes, fired at the
operator's will — not a directive. That distinction carries an engineering contract: a probe must
be cheap, independent, and side-effect-free — fire three, discard two, nothing changes on disk.
A directive exists to mutate state; a probe bank that mutates on invocation has stopped being a
probe bank and become an auto-apply engine nobody asked for. Probe output is evidence for the
operator's judgment, never a disposition on its own — `pickup_assemble`'s `closure_signals`,
explicitly documented as "never a verdict," is the fleet's working reference implementation of
that boundary.

## Applying it

When scoping any surface, in order:

1. **Census every mechanical step**, not only every decision branch.
2. For each, ask **what artifact discharges it.** "The operator remembers" is not an answer.
3. Ask **what the operator had to know** beyond their own intent. That residue is the work.
4. Check the **ergonomics AC**: is the new path cheaper than the old one? If not, it fails
   regardless of correctness.
5. Prefer **the artifact's shape** to a tool, and a tool to a rule. Reach for a rule only when
   the first two genuinely cannot carry it — and record that as a known gap, not a solution.
6. **Trace the seam end-to-end before calling it done** (§ The seam). Don't stop at "the compute
   layer resolves this correctly" or "the mutation layer can execute this correctly" — run the
   actual consuming path (the skill body, the hook, the caller) and confirm it (a) does not
   duplicate logic the compute layer already resolved, and (b) actually reaches and invokes the
   mutation layer, not a CLI verb that doesn't exist yet. A green unit test on the compute layer
   and a correct-looking hook are each necessary and NEITHER is sufficient — the check is whether
   the wire between them is live, verified by exercising it, not by reading both ends and
   assuming they meet in the middle.
7. **Assemble and push; never store-and-make-them-pull** (§ The adventure, realization #6). A
   converted skill body must carry no branch the engine already resolves — grep it for
   classification/branch-selection vocabulary and expect empty. The classification-appropriate
   guidance is *injected* into the operator's hands at fire time, keyed on the material, not left
   as a section they navigate to. And do not invent a judgment point out of noise the operator
   can do nothing about (concurrency on a shared tree, a peer holding an unrelated baton) — surface
   only what genuinely gates this item and what genuinely needs judgment. What survives as prose is
   the irreducible non-branching action core and the genuine universals, nothing more.
