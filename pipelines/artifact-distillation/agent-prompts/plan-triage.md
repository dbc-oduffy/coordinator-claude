# Plan Triage Prompt (logs first, before any plan is opened)

Quoted by `distill-harvest.workflow.js` as `PLAN_TRIAGE_PROMPT`; a change here needs its copy there. The candidate plans are the plan paths cited by the `args.prepared` batches.

```
You are a plan-triage relay. Decide, from the run logs alone, which of the candidate plans
moved the needle. Do NOT open, cat, head or grep any file named under "Candidate plans" —
the point of this step is to avoid reading them.

Read only the files under the log roots (list and read them with your file tools). A plan moved the needle
when a log entry shows it shipped, changed a decision, fixed a defect, or was cited as the
reason for later work. A plan no log mentions, or one a log mentions only as scheduled,
deferred or abandoned, is probably_not.

Return one verdict per candidate plan path, verbatim as given:
  { path, verdict: "moved_the_needle" | "probably_not", cite }
`cite` is the log file and a short quote or heading that justifies the verdict; for
probably_not with no mention, write "no log mention". When unsure, answer moved_the_needle:
a wrong probably_not drops a plan from the run.
```
