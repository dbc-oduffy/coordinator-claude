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

## Close

The scouts `next_action` carries `require_grounding: true`. `research.close` at tier scouts
refuses a run whose `grounding.md` is absent or empty, grades a claim `ungrounded` or
`contradicted`, rules a contradiction `invented`, or grades no claim of a digest. It builds
`digest.md` from the sorted `digest-*.md` bodies followed by `## Grounding` and `grounding.md`.
`probe-*.md` is never archived. `grounding.md` holds one `## digest-<slug>.md` section per digest
with claim lines `- **<grounded|ungrounded|contradicted>** <claim> — <evidence>` at line start,
and one `## Contradictions` section of `- **<real|invented>** <ruling>` lines.

## CLI and sizing

`--ask` is repeatable and every `--ask` is one question. `--target web|repo=PATH|local=PROBE` is
repeatable and binds to the preceding `--ask`. `--split | --combine` are mutually exclusive. The
sizing carries `research.question_mode` and `research.question_targets[]`, written by
`sizing-assemble --research-question-mode` and `--research-question-target n=source[:ref]`
(repeatable; an index repeats for a list).
