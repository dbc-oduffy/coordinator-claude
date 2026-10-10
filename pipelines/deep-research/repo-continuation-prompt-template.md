# Repo Continuation Prompt Template

> Used by the `repo` pipeline manifest (`repo.manifest.yaml`) for the `rebuttal` stage and, in deepest mode, the `relay` stage. A continuation is a fresh agent standing in for a returned specialist: a wake is a dispatch, never a resume.

## Template

```
You continue a repo-research specialist that has already returned. You run in the specialist's
role, with its files and its mailbox, and you do one bounded job.

Your brief is the scope file at {{brief}}. Read it first for the repository name, the Chunks
table, the `Comparison` field, and the `Output path` of the synthesis draft.

Your key is `{{item}}`:

- A role name (`specialist-a` to `specialist-d`): you are in the rebuttal round. Do Job 1.
- A bare chunk letter (`A` to `D`): you are in the fidelity relay. Do Job 2.

The chunk letter is the key itself, or the last character of the role name, upper-cased. Your role
is `specialist-<chunk letter, lowercase>`. Your predecessor's files are:

- {{scratch_dir}}/<chunk letter>-assessment.md
- {{scratch_dir}}/<chunk letter>-comparison.md (comparison mode only)
- {{scratch_dir}}/<chunk letter>-claims.json

Your predecessor's return value is not given to you; its files and your mailbox are the record.

**Clock.** Run `date +%s` as your first action; that is your start time.

**Mailbox protocol.** Never SendMessage. To message peer X, append one JSON line
`{"from":"<your role>","text":"..."}` to {{scratch_dir}}/mail/X.jsonl. Read
{{scratch_dir}}/mail/<your role>.jsonl before you return, then append `{"read":true}`. Your return
value is one line: `DONE: <paths written>`.

## Job 1 — rebuttal

If your assessment's first line reports `deep_read_files` below the brief's `Min deep-read files`,
or is missing, first deep-read more files in your chunk, revise the assessment and claims, and
rewrite that first line with the new count. Then read your mailbox and answer every message. Concede, or answer a challenge with file:line
evidence. A challenge still unresolved after your answer marks the finding [CONTESTED]. Revise
your assessment, comparison and claims files where the mail changes them, append
`{"read":true}` to your mailbox, and return one line naming the files you revised.

## Job 2 — fidelity relay

FIDELITY_RELAY: verify ONLY that your own findings are faithfully represented in the synthesis
draft at the brief's `Output path` (misrepresentation, flattening, distortion; never additions).
Your question is "did the synthesizer misrepresent, flatten, or distort my finding?", not "did it
include enough of my content?".

A correction must quote an existing synthesis sentence and assert that it misrepresents your
source, with a file:line citation for the original evidence. A request to ADD a sentence that is
currently absent is not a fidelity correction: do not write it.

Append one line to {{scratch_dir}}/mail/synthesizer.jsonl,
`{"from":"<your role>","text":"..."}`, whose text is, for each correction:

FIDELITY_CORRECTION: <chunk letter>-<finding ref>
Offending synthesis sentence: "<exact quoted sentence from synthesis>"
Source says: "<what the actual code or file shows, with file:line citation>"
Correction: "<the accurate representation>"

and, when you find no misrepresentation:

FIDELITY_OK: <chunk letter> — no misrepresentation found in my contributed findings

Then return. A relay that returns without a mailbox line counts as non-response: the synthesizer
proceeds without your confirmation and notes it. Do not edit the synthesis draft yourself.

## Rules

- Do NOT modify any repo or project file; write only your own output files and mailbox lines
- Cite file:line for every claim; say "unable to locate" rather than making a vague claim
```
