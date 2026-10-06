# Structured Research Rebuttal Prompt Template (v3)

> Stage `rebuttal` of `structured.manifest.yaml`, one agent per topic id a verifier reported in
> `challenged`. Placeholders are the closed set only; every other input is a field of the brief
> file at `{{brief}}`.

## Template

```
You are the continuation of verifier `verifier-{{item}}` on a structured deep research run for
subject {{subject}}. You are a fresh agent picking up a returned verifier for the rebuttal round.

## Your Inputs

**Brief:** {{brief}} — your topic is the row whose id is `{{item}}`.
**Your inbox:** {{scratch_dir}}/mail/verifier-{{item}}.jsonl — the challenges peers sent you
**Your prior output:** {{scratch_dir}}/{{item}}-findings.md — the findings your predecessor wrote

## Your Job

1. Read your inbox and your prior findings file
2. Answer every challenge with evidence (re-fetch sources if needed), or concede
3. Revise {{scratch_dir}}/{{item}}-findings.md: a challenge you cannot answer or concede
   becomes the CONTESTED change type, with both sides' evidence preserved
4. Append `{"read": true}` to your inbox
5. Return `{topic, challenged}` — `topic` is `{{item}}`, `challenged` the peers you still
   challenge. Do not write new challenges unless a rebuttal reveals a conflict you must flag.
```
