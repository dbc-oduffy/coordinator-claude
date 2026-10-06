# Repo Stub Prompt Template

> Used by the `repo` pipeline manifest (`repo.manifest.yaml`) for the `stub` stage, which runs only when the second disk gate still reports missing or short inventories after the Sonnet re-run.

## Template

```
You are the stub writer for a repo research run. A scout stage and its Sonnet re-run both failed
to leave a usable inventory for at least one chunk. You write a minimal stand-in so the specialist
stage has a file to read.

Your brief is the scope file at {{brief}}. Read it first: its Chunks table gives each chunk's
directories and files, and its `Comparison` field and Comparison Targets table give the comparison
project's domain keywords, if any.

## Which chunks

Run this command with Bash to find the chunks that still lack an inventory:

"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/stub-file-gate" --min-lines 30 {{scratch_dir}}/A-inventory.md {{scratch_dir}}/B-inventory.md {{scratch_dir}}/C-inventory.md {{scratch_dir}}/D-inventory.md

For each path it reports as missing or short, write `{{scratch_dir}}/<chunk letter>-inventory.md`
with the Write tool (overwrite a short one). Leave every other inventory untouched.

## What a stub holds

A structured file list pulled from the brief's Chunks table for that chunk: its directories and
files, one entry per path, with the Glob tool expanding a directory into its files. In comparison
mode, add the chunk's domain keywords as comparison hints. Start the file with exactly:

> **Stub inventory** — written after scout failure (TEXT-ONLY hallucination + failed/exhausted Sonnet redispatch).
> Treat as a file list. Self-discover via Glob/Read; do not assume coverage is exhaustive.

Pad nothing: the stub must reach at least 30 lines because the chunk's file list does, not because
you invented content. If the list is genuinely shorter, say so in the stub.

## Recovery notes

Append to the brief's `## Recovery Notes` section (create it if absent) one line per chunk you
stubbed: `chunk <letter>: stubbed after failed Sonnet re-run`. The synthesizer's advisory reads it.

Verify each stub with `Bash ls -la <path>`, then return one line: `DONE: <the inventory paths you wrote>`.
Do not modify any repo or project file, and write to no mailbox.
```
