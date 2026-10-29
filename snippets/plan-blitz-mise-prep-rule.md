<!-- Read directly by the plan-blitz planner brief; not a synced snippet, no embedding. -->

FOUR DECLARATIONS, because the next ceremony is gated on them. The plan you write is fired by a
hands-off run with no human in the loop, and its entry gate refuses a plan that leaves any of
these undeclared. "Nothing to declare" is itself a declaration — an EMPTY value is a claim a
reader can check; an ABSENT key is one nobody can see. Declare all four:

  1. `writes:` ON EVERY SPINE ROW. The wave-builder decides what can run in parallel from the
     rows' write sets, and cannot decide it for a row that declares none. A row that writes
     nothing declares `writes: []`.

  2. `census:` IN FRONTMATTER — every COUNTED premise the plan rests on, as
     `question` + `command` + `result`. The command is the point: a count in prose can only
     be believed or not, while a count with the query that produced it can be re-asked of HEAD at
     fire time, which is what an undercount needs in a world where planning runs waves ahead of
     execution. Do not restate the spine's own file count here. A plan resting on no counted
     premise declares `census: []`.
     The prep gate refuses any `command` outside the allowed form your charter quotes; a count
     that needs a program is a tracked read-only script the command names by path.

  3. `external_gate[].requires:` ON EVERY UNCLEARED GATE. A blocker owned by another repo is a
     declared gate, never a sentence in the body. `requires: landed-work` means wait for them —
     the row is withheld and the plan still certifies. `requires: commit-in-owner-repo` means
     write into their tree — a commit dispatched under per-session PM assent, as its own act; that
     row is withheld too and the plan still certifies. The two read identically in prose and are
     released by different acts, which is why the field exists. A row whose declared paths leave
     this repo and carries no gate at all is refused.

  4. `prime_exit_criterion:` AT EVERY SIZE, S and XS included — `statement` plus
     `derived_from`. It answers the one question a driver cannot answer against a task list:
     how do I know this is finished. A `falsifier` sub-object stays proportional to size and is
     not required here.
     When present it nests UNDER `prime_exit_criterion` (never a top-level `falsifier:`), and
     its `baseline_ref` is a bare commit sha — no branch, date, or prose around it.

     WHICH FILE `derived_from` NAMES, when this wave sized you: the wave's
     `em-size-review.md`, rather than the baton's `.sizing.md`, whenever a review exists. The
     `.sizing.md` is the scout's PROPOSAL. Where the EM overrode it, that file states the size
     and the reasoning that were overturned, in its opening lines, with nothing in it saying so —
     so a reader who follows it gets a confident answer that is the opposite of your plan's
     premise. Both are openable and the schema admits both; only this rule tells them apart.

TWO MORE FRONTMATTER KEYS the gate reads as undeclared when ABSENT, whatever the scaffold emitted:

  - `anchor_premises:` — each load-bearing premise as `{id, claim, check: {command, expect}}`, or
    `anchor_premises: []` when the plan rests on none.
  - `register_claims:` — `{sizing, rows, pins}` when the sizing carries a requirement_register;
    omit it only when the sizing has none.

Add them to the plan's frontmatter if the generator did not.

Declare what is true. A `census: []` on a plan that counted something, or a gate omitted because
naming it looked like extra work, is a false claim in a machine-checked field — worse than the
absence, because it certifies.
