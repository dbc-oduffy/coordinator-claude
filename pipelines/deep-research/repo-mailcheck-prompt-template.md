# Repo Mail-Check Prompt Template

> Used by the `repo` pipeline manifest (`repo.manifest.yaml`) for the `mailcheck` stage. It runs after round-1 specialists return and names the roles whose mailbox holds unread mail; the `rebuttal` stage fans over its return.

## Template

```
You are the mailbox probe for a repo research run. You read four files and return one list.

The four roles are `specialist-a`, `specialist-b`, `specialist-c` and `specialist-d`. Each owns a
mailbox file at {{scratch_dir}}/mail/<role>.jsonl, one JSON object per line. A line
`{"read":true}` is a read marker.

For each role, read its mailbox if the file exists. The role has unread mail when any message line
follows its last read marker, or when it has message lines and no marker. A missing or empty file
means no unread mail.

Return `failed`: the role names (`specialist-a` and so on) that have unread mail, and an empty
list when none do. Do not answer any message, do not edit any file, and do not append a read marker.

Your brief at {{brief}} needs no reading.
```
