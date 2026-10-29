# A Deny No Machine Step Clears Is a Guard Defect

> **No deny is cleared by a human act.** Rule token: `A-GUARD-DENYING-AN-EM-COMMIT-IS-A-GUARD-DEFECT`. A guard
> that denies and offers no machine-takeable next step is a defect in the guard. The remedy is to
> report the exact denial to the guard's owner, not to ask a person to clear it.
>
> **If you are an agent reading this page:** do not write a sentinel, set an override variable, or
> ask a person to do either. Follow [#the-standing-route](#the-standing-route).

---

## The Standing Route {#the-standing-route}

A deny fires. In order:

1. **Read the deny's own reason.** It names what the guard protects and, where one exists, the
   machine-takeable step that satisfies it (the missing artifact, the right command, the correct
   dispatch shape). Take that step.
2. **No such step, or the step does not apply to your case:** the guard is defective. Stop the
   denied operation, keep the remaining work moving, and report the defect to the guard's owner
   (a hook or doctrine surface to the doctrine owner, an engine guard to the engine owner) with
   the exact denial text, the command or tool call that fired it, and what you expected to be
   able to do.
3. **Never route around it.** A sentinel file, a `COORDINATOR_OVERRIDE_*` / `COORDINATOR_ALLOW_*`
   variable, a relaunch to reset one, or a request that a person clear the deny are all the same
   violation: they turn a guard defect into a human chore.

A guard that gates irreversible harm still holds. The route for it is the same: the owner fixes
the guard (narrows its scope, adds the machine step it was missing, or removes it). Nobody
approves a single instance.

## Why No Human Act Clears a Deny {#why-no-human-act}

- **A person is not a machine-takeable step.** A guard whose only exit is a person has failed the
  outlet test in [`guard-proportionality.md`](./guard-proportionality.md); it is routing work to
  the one resource the system must not spend.
- **The workaround teaches itself.** An agent that learns a deny is clearable by a file or a
  request reaches for it first, and the guard stops being a guard.
- **A repeated clear is a signal.** The same guard hit repeatedly means its scope or the workflow
  hitting it is wrong. Only a fix at the guard retires that.

## A Guard Naming Two Exits May Offer Neither {#two-exits-may-offer-neither}

A deny that names two remedies is not guaranteed to reach either for your case. The originating
instance: `review-brightline-gate` HALTs a chain close on uncovered predecessor commits and names
a waiver or `/handoff`. Both can be dead ends, and the discriminator is the `Session-Id` git
trailer on the commit in question:

- **Trailer names another session** -> the named exit works, and per-commit trail writes succeed.
- **No trailer** -> a different refusal branch fires ("genuinely ambiguous") that the exit does not
  reach at all. Measured: two trailered SHAs wrote clean, seven untrailered SHAs refused.

`/handoff` is no exit either in that case, because a trailer is immutable history; a fresh session
inherits the same missing trailer and refuses forever. Before spending effort on an offered exit,
verify it applies to your case: check the discriminating field the guard's own logic keys on, not
just the names it prints. If the review genuinely already ran, prefer the guard's own
coverage-verdict path (recording the honest coverage ratio) over discarding a review that exists.
If no exit applies, that is the guard defect of [#the-standing-route](#the-standing-route): report
it with the exact denial.

## Why a Deny Message Does Not Hand Over a Bypass {#why-the-deny-withholds}

A deny message carries the reason and the machine step, never a ready-to-run bypass. Measured:
presented with a message carrying a resolved path, an imperative and sequencing, four
independently dispatched agents read it and three classified it as prompt injection. An agent under
a deny acts on the first actionable thing it meets; a pasteable bypass is actionable however the
disclaimer above it is worded.

## Related {#related}

- [`guard-proportionality.md`](./guard-proportionality.md) -- the necessity/duration/outlet test a
  guard must pass, and why a person is never the outlet.
- [`guard-message-concision.md`](./guard-message-concision.md) -- what a guard message is for, and
  why the explanation it cut belongs on a page like this one.
- `bash-guard-threat-model.md` -- what the Bash-side guards defend against, and why they deny
  rather than warn.
