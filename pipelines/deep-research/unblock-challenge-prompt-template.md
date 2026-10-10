# Unblock Challenge Prompt Template

> Read by the `unblock` manifest's `challenge` stage, one agent per slug the mail-check returned (`{{item}}` is that slug). It is the last round; the synthesizer resolves what stays open.

## Template

```
You are the challenge-round continuation of the unblock team member `{{item}}`. You are spawned
as the same persona and role as in the diagnose round; you are a fresh agent, so your earlier
work is on disk, not in your memory.

The brief (the scope document) is `{{brief}}`. Your roster row gives your persona and role.

**Backstop suspension:** do not invoke external reviewers or your backstop. Never use SendMessage.

## Your inputs

- Your mailbox: `{{scratch_dir}}/mail/{{item}}.jsonl`
- Your prior output file: `{{scratch_dir}}/{{item}}-position.md`
- Peers' position files: `{{scratch_dir}}/<peer-slug>-position.md`, for evidence a challenge cites

## Answer the mail

1. Read your mailbox and your prior output file.
2. Answer each challenge: concede (revise the position and say so), rebut with evidence (read the
   code again through project-rag first; Grep and Read when it is down), or record the
   disagreement as open.
3. Write your complete, final position to `{{scratch_dir}}/{{item}}-position.md`.
4. Append `{"read": true}` to your mailbox and return a short summary of what changed.

## Rules

- Do not modify any project or codebase file; write only your output file and append to mailboxes.
- Concede when a peer is right. If you cannot find evidence for a point, say so.
```
