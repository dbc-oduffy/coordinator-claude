# `claude --print` Subprocess Contract

Reference notes for every coordinator harness, skill, or command that invokes `claude --print` as a CLI subprocess. These are not style preferences — they are correctness rules that produce silent failures when violated.

---

## Tool sandboxing

**Subprocess `claude --print` runs ignore `--allowedTools` for built-ins.**

Write, Edit, and Bash are not suppressible via flags. A subprocess invoked with `--allowedTools Read,Glob,Grep` can still write files. Flag-based sandboxing of CLI subprocesses is a false sense of security.

To control output destination or behavior, write the constraint into the prompt explicitly:

> "Write your output to `<absolute path>` and nothing else. Do not create any other files."

Prompt-level direction is the only reliable mechanism for destination control in CLI subprocesses.

---

## Six-item invocation contract

Every `claude --print` subprocess dispatch must satisfy all six of the following:

1. **No `--cwd` flag.** The CLI does not support `--cwd`. Change directory via subshell instead:
   ```bash
   (cd "$target_dir" && claude --print ...)
   ```

2. **Pass Windows-native drive-lettered paths in prompts** when the CWD may be on a different drive than the target file. Unix-style `/x/path` variants break cross-drive resolution. Use `X:/path/to/file` form in the prompt body.

3. **Pipe large prompts via stdin; never use `-p "$big_string"`.** Shell argument limits silently truncate prompts at 50KB+. For any prompt that may exceed that threshold — research prompts, enriched stubs, multi-section briefs — use:
   ```bash
   claude --print < prompt.md
   ```

4. **Prefer `--print --disable-slash-commands` over `--bare` for naked-baseline runs.** `--bare` requires `ANTHROPIC_API_KEY` set in the environment and skips OAuth. `--disable-slash-commands` achieves the same stripped baseline without the credential dependency.

5. **Use `--output-format json` for exact token/cost telemetry.** Plain text output drops token and cost fields entirely.

6. **Read token and cost data from the JSON envelope's `usage` key, not top-level fields.** The correct extraction paths are:
   - `usage.input_tokens`
   - `usage.output_tokens`
   - `total_cost_usd`

   Top-level `input_tokens` / `output_tokens` fields, if present, are unreliable and should not be used for accounting.
