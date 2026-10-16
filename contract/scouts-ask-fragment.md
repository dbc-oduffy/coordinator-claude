# Scouts-ask fragment

`scouts-ask-fragment.json` is the contract for a multi-question `/coordinator:research` ask on the
scouts class: question cap, split/combine modes, per-question targets, the `ask.md` section
grammar, manifest lists and flags, output names, the local-probe allowlist, and the close
parameter. DoE owns the rule; the engine reads it and never re-derives it, on the
`pm-gate-signal-fragment` precedent.

## Cap and mode

`max_questions` (8) bounds parallel scouts per ask and equals the scout stage's `max_concurrent`.
`split` (default) emits one slug per question; `combine` emits the single slug `combined`, whose
`## combined` section carries every question.

## Targets

Each question carries `targets[]` of `{source, ref}` with `source` in `web | repo | local`. `web`
takes no ref. `repo` refs a path: `.` is the firing repo root, an absolute path is another
checkout. `local` refs a probe id from `probe_allowlist`. A question with no targets gets
`default_targets`: web plus repo `.`.

## ask.md grammar

After the ask text, one `## <slug>` section per list item: the question text, a `Targets:` line,
then one `- <source>` or `- <source>: <ref>` bullet per target.

## Lists, flags, outputs

List `questions` holds the slugs. List `probes` holds the slugs of questions with a `local` target
(in combine mode, `combined` when any question has one). Flag `local_probe` is true when `probes`
is non-empty. Outputs: `digest-<slug>.md` per scout, `probe-<slug>.md` per probe, `grounding.md`
once.

## Probe allowlist

Three probe ids, each with a literal command per OS (`macOS`, `Windows`, `Linux`), run verbatim
with its output filter in the same pipeline, so the probe agent's tool output never holds a
secret. A probe reports names, keys and sizes, never a value. A probe id outside the list is
refused at emit. `{ref}` in a command is the target's ref.

## Close

The scouts `next_action` carries `require_grounding: true`. `research.close` at tier scouts
refuses a run whose `grounding.md` is absent or empty, and builds `digest.md` from the sorted
`digest-*.md` bodies followed by `## Grounding` and `grounding.md`. `probe-*.md` is never
archived.

## CLI and sizing

`--ask` is repeatable; `--split | --combine` are mutually exclusive; `--question-target
<n>=<source>[:<ref>]` is repeatable with `n` 1-based. The sizing carries `research.question_mode`
and `research.question_targets[]`, written by `sizing-assemble --research-question-mode` and
`--research-question-target`.
