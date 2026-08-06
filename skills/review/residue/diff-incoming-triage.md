---
segment_id: diff-incoming-triage
surface: diff
class: protected
order: 60
---

- _Performative-agreement urge?_ ("you're absolutely right!", "great catch!", "thanks for catching that") _(`--surface diff`)_
  → STOP. Delete the urge. State the fix factually.

**`--surface diff` — executor brief out-of-scope reminder.** When building an executor brief from these findings, include this constraint: Removing/weakening production safeguards to satisfy pre-existing test mocks is OUT OF SCOPE. Tests follow production; surface the conflict instead.

- _Premise / hypothesis question?_ (reviewer challenges the artifact's framing or motivating hypothesis, or claims a bug/gap exists where the artifact is correct) _(`--surface diff`)_
  → Read the cited code at the cited line, not the reviewer's paraphrase. Confirm or revise premise either way.

- _Worker Dispatch Recommendations block present in reviewer output?_ _(`--surface diff`)_
  → On diff reviews: all four workers are in scope (`test-evidence-parser`, `security-audit-worker`, `dep-cve-auditor`, `doc-link-checker`) — reviewers name only the ones that fire on this diff. If the recommendation names `test-evidence-parser`, the EM runs the recommended test invocation first, captures stdout/stderr to a file, and dispatches the worker with that captured path — never the command itself.
