# Scouts-ask fragment

`scouts-ask-fragment.json` is the contract for a multi-question `/coordinator:research` ask on the
scouts class: question cap, split/combine modes, per-question targets, the `ask.md` grammar,
manifest lists and flags, output names, the local-probe allowlist, and the close parameters.

The engine owns the CLI and the `ask.md` grammar; the fragment restates them (`engine_mirror`
names the engine constants) for the plugin's templates and tests. The engine reads the probe
allowlist from this fragment (`id` and `ref`). The plugin owns the allowlist, the outputs and the
close params.

## Cap and mode

`max_questions` (8) bounds parallel scouts per ask and equals the scout stage's `max_concurrent`.
`split` (default) emits one item per question, its slug. `combine` emits the single item
`question`, whose `## question` section is a numbered list of every question.

## Targets

Each question has an ordered, non-empty list of targets, no duplicates; the default is `web`.
`source` is `web | repo | local`. `web` takes no ref. `repo` refs a path, relative to the firing
repo root or absolute for another checkout. `local` refs `<probe-id>[:<arg>]`: the id is a
`probe_allowlist` id, an arg is given only for an entry whose `ref` is not `none`, and the arg
matches `[A-Za-z0-9._-]+`.

## ask.md grammar

Per question, `## <slug>`, then one `Target: <source>[ \`<ref>\`]` line per target in list order, a
blank line, and the question text. A web-only question has no `Target:` line; a mixed question
carries a `Target: web` line like any other. With two or more questions the ask text is followed by
`Research questions:` and a numbered list. In combine, each numbered item puts its first `Target:`
line on the number line and indents the rest.

## Lists, flags, outputs

List `questions` holds the slugs (`question` in combine). List `probes` holds the slugs of
questions with a local target (`question` in combine when any has one). `probes` and `local_probe`
are bound only when a local target exists; the manifest declares `local_probe: [true, false]`, so
an unbound flag reads false and the probe stage is skipped. Outputs: `digest-<slug>.md` per scout,
`probe-<slug>.md` per probe, `grounding.md` once.

## Probe allowlist

Three probe ids, each with a literal command per OS (`macOS`, `Windows`, `Linux`), run verbatim
with its output filter in the same pipeline, so the probe agent's tool output never holds a
secret. A probe reports names, keys and sizes, never a value. A probe id outside the list is
refused at emit. `{ref}` in a command is the target's arg.

### CLI class

An entry with `"class": "cli"` probes an authenticated local CLI read-only. It names the `tool` and
a `verbs` map of each permitted subcommand to the one question it answers. A scout targets it as
`local=<id>:<verb>`; the `ref` is exactly one listed verb, and any other verb is refused. No verb
may mutate (no submit, edit, sync, delete, revert, obliterate). The commands keep the per-OS form
and run inside the research trail, so grounding and close apply. The probe reports names and counts
only, never file contents or credentials. `p4-readonly` is the first entry (`info`, `depots`,
`clients`, `streams`, `users`, `groups`, `labels`, `servers`). Engine-side verb enforcement is
sibling-repo work; until it ships, the prompt template and the verb list bind the scout.

## Close

The scouts `next_action` carries `require_grounding: true`. `research.close` at tier scouts
refuses a run whose `grounding.md` is absent or empty, grades a claim `ungrounded` or
`contradicted`, rules a contradiction `invented`, or grades no claim of a digest. It builds
`digest.md` from the sorted `digest-*.md` bodies followed by `## Grounding` and `grounding.md`.
`probe-*.md` is never archived. `grounding.md` holds one `## digest-<slug>.md` section per digest
with claim lines `- **<grounded|ungrounded|contradicted>** <claim> — <evidence>` at line start,
and one `## Contradictions` section of `- **<real|invented>** <ruling>` lines.

### Re-ground after a digest fix

`research.close` reads `grounding.md` as written, so fixing or dropping a claim in a `digest-<slug>.md`
leaves the old verdict in force and the close refuses again. After any digest edit, re-ground before
re-closing: run `research.reground` with `{run_id}`. It moves the stale `grounding.md` aside,
re-grades only the digests changed since the last basis, and emits
`scratch/warp/<run_id>.reground-<n>.workflow.mjs`; fire that fresh, then re-run `research.close`.
A resume of the finished run does not re-ground; it replays the cached grounding because the stage
prompt is unchanged. Hand-editing `grounding.md` or the emitted script's prompt is never the fix:
the grader's verdict is not the EM's to write.

## CLI and sizing

`--ask` is repeatable and every `--ask` is one question. `--target web|repo=PATH|local=PROBE` is
repeatable and binds to the preceding `--ask`. `--split | --combine` are mutually exclusive. The
sizing carries `research.question_mode` and `research.question_targets[]`, written by
`sizing-assemble --research-question-mode` and `--research-question-target n=source[:ref]`
(repeatable; an index repeats for a list).
