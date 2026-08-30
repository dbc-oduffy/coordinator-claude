# Security review — block-destructive-rm.sh false-positive fix (Part A + B)

Reviewer: coordinator:code-reviewer (security/bypass lens). Verdict: **BLOCKED** — the fix closes real false-positives but introduces NEW false-negative bypasses (caught by the pre-fix `\brm\b` scan). Must harden, not narrow, before shipping.

## EM dispositions (hardening design — apply all)

The principle: Part A (heredoc strip) is correct; keep it, fix its terminator handling. Part B must COVER the wrapped/grouped forms the broad scan caught, while still excluding rm-as-DATA (quoted-arg in a non-shell-invoker, glob substring, heredoc body).

- **F1/F2/F6/F7 (group/quote/negation openers — P1 bypass):** Before applying `_RM_CMD_RE` to each segment, iteratively strip leading noise: whitespace and any of `(` `{` `$(` `\` `'` `"` `!`. Then check command position. This catches `(rm -rf x)`, `{ rm -rf x; }`, `\rm`, `'rm'`, `"rm"`, `! rm`. Also make the separator split treat `(` `{` `)` `}` as boundaries so grouped commands segment cleanly.
- **F4 (exec/nice/nohup prefixes — P1 bypass):** Add `exec`, `nice`, `nohup` to the `_RM_CMD_RE` prefix alternation (alongside `sudo|command|time`). (`ionice -c 3 rm` takes a flag+value — acceptable to leave as a documented residual, or handle via the shell-invoker fallback if simple.)
- **F5 (env without VAR=val — P1 bypass):** Add an `env[[:space:]]+` arm (env directly invoking a command, no assignment) in addition to the existing `env VAR=val` arm.
- **F3 + F4-eval (shell-invoker wrappers — P1 bypass, the most realistic):** When a segment's command word is a shell invoker (`bash`/`sh`/`zsh`/`dash`) with `-c`, OR is `eval`, fall back to a BROAD `\brm\b` scan of that segment (the quoted command is executed, so broad detection is correct here). This re-catches `bash -c 'rm -rf x'` and `eval 'rm -rf x'`. NOTE: this intentionally does NOT broad-scan non-invokers like `grep "...rm..."` — only shell-invokers get the broad fallback, preserving the false-positive fix.
- **F8 (Part A heredoc terminator mismatch — P1 regression):** The awk word regex `[A-Za-z_][A-Za-z0-9_]*` misses terminators with `-`/`.`/etc. (`<<END-OF-FILE` → awk traps in heredoc mode forever, eats a real trailing `rm`). Fix: match the terminator as `[^[:space:]"'`]+` (any non-space/non-quote run) for the unquoted form. ADD FAIL-SAFE: if awk reaches END still inside a heredoc (unterminated), discard the awk output and PRESERVE the original `$CMD` (fail safe — a stuck stripper must never silently allow).
- **F9 (no bypass test coverage — P2):** Add one DENY-expected test per bypass shape: `{ rm -rf workdir; }`, `(rm -rf workdir)`, `bash -c 'rm -rf workdir'`, `sh -c 'rm -rf workdir'`, `eval 'rm -rf workdir'`, `exec rm -rf workdir`, `nice rm -rf workdir`, `nohup rm -rf workdir`, `env rm -rf workdir`, `\rm -rf workdir`, `'rm' -rf workdir`, `"rm" -rf workdir`, `! rm -rf workdir`, and the hyphenated-heredoc case `cat > x <<END-OF-FILE\nhello\nEND-OF-FILE\nrm -rf workdir`. Keep ALL existing ALLOW cases passing (heredoc body, `grep "how to rm files"`, `ls *rm*`, `grep ... ; ls *rm*`).
- **F10 (nit):** `env ... =+ ...` → use a single `=`.
- **F11 (nit):** `echo "$SEG"` → `printf '%s\n' "$SEG"` in the per-segment check.
- **F12 (P2, pre-existing):** `for tok in $AFTER` glob-expands against hook cwd — wrap the token loop in `set -f` / `set +f` (noglob), or use `read -ra`. Worth fixing while here.

## MANDATORY verification:
0 failed, with ALL new DENY bypass cases denying and ALL prior ALLOW false-positive cases still allowing. Zero existing DENYs may regress.

---

## Second-pass review (post-hardening) — dispositions

2nd review confirmed F1-F8 closed + heredoc fail-safe sound, but found 3 surviving P1 bypass classes:
- **Wrapper-with-flags** (`sudo -u root rm`, `env -i rm`, `nice -n 10 rm`): prefix-keyword regex arms only matched `keyword+ws+rm`; any flag between escaped.
- **`env` flagged forms**: F5 landed bare `env rm` but not `env -i`/`env -u X`.
- **Computed verb** (`$(which rm) -rf x`, backtick `` `which rm` ``): inner verb unrecognized.

**Fix (structural, applied):** added an execution-wrapper CLASS check to `_rm_is_rm_segment`. If the segment's command word is a known wrapper (`sudo command time exec nice nohup env ionice timeout stdbuf which type`), match a whole-TOKEN `rm`/`*/rm` anywhere after it (boundaries: whitespace + `( ) { }` + backtick) — flag-agnostic, so wrapper flags can't shield rm. Whole-token (not substring) preserves the quoted-data false-positive fix (`sudo grep "rm" f` still ALLOWs). Added backtick to opener-peel. Bare `which rm`/`command -v rm`/`type rm` carry no target → still ALLOW. Updated KNOWN-limitations to document genuine residuals (no-literal-target `xargs rm`/`find -exec`; function/alias-hidden rm; wrapper outside the set) — fail-open, adversarial-not-confabulation.

**Verification:** suite 74/0 (12 new 2nd-pass cases); live smoke confirmed every reproducer (`sudo -u root rm`, `env -i rm`, `nice -n 10 rm`, `$(which rm)`, backtick) DENYs and every false-positive guard (`which rm`, `command -v rm`, `type rm`, `sudo grep "rm"`) ALLOWs.

---

## Third-pass hardening (2026-07-10) — override incantation + peer-contest awareness

Cross-repo incident (accepted): in a shared worktree, an EM ran `rm` on untracked files belonging to a LIVE PEER session's in-progress, already-reviewed work. The hook correctly BLOCKED the delete — but (a) the deny message *printed the bypass incantation* `export COORDINATOR_ALLOW_RM=1` directly in the denial text, which an eager agent read as a sanctioned next step, and (b) `COORDINATOR_ALLOW_RM=1` was a blanket, non-session-aware early-return, so setting it then deleted the peer's untracked work with no git recovery path (no blob/reflog/stash/snapshot for untracked content).

**(1) Deny messages no longer print the override incantation.** `_RM_OVERRIDE_HINT` (the file-scope constant holding the `export COORDINATOR_ALLOW_RM=1` text) is removed, along with every interpolation site. Design principle: design-as-offers (lead the operator to the *recoverable* path, never print the escape hatch where it reads as an instruction) — matching the shape the claim-dir guard already modeled. The untracked-work deny now closes with a `git stash push -u` offer (`-u` includes untracked; `stash pop` restores) and a line reserving irreversible deletion for "genuinely disposable, self-authored, uncontested paths." The `.git`-store and subshell-unverifiable denies simply drop the hint tail — no replacement offer needed (deleting `.git` is never legitimate; the subshell case's fix is "resolve to a literal path", already stated). The env var itself still works — it is just never advertised in-band.

**(2) The override is now concurrent-session-aware for UNTRACKED targets only.** The blanket `[[ "$COORDINATOR_ALLOW_RM" == "1" ]] && return 0` early-return is replaced with a captured `_RM_OVERRIDE` flag threaded through the rest of `check_destructive_rm`. At the untracked-work branch, a new helper `_rm_peer_claim_of <tgt_abs> <root>` is consulted BEFORE the override is honored: it echoes the session id of a LIVE peer coordinator session (`.git/coordinator-sessions/<sid>/touched.txt`) whose touched-path set overlaps the target (equal to, nested under, or containing the target's repo-relative path). If a peer claim is found, the hook denies with `BLOCKED (not overridable): ... claimed by LIVE peer session <sid> ...` — this deny fires REGARDLESS of `COORDINATOR_ALLOW_RM`, closing exactly the incident's failure mode. If no peer claims the target, the override is honored as before (`continue`, i.e. allow). Liveness resolution prefers canonical `cs_live_session_ids` (at review time `lib/coordinator-session.sh`; the bash hook this review covers is retired and its Python successor, `preuse-bash-dispatch.py`, does not source that lib, deleted 2026-07-22, session-family-repoint C4a); when a peer sid is outside that scan's coverage (no `meta.json`) it degrades to a 30-minute `touched.txt` mtime heuristic as a backstop, never as the primary signal.

The three OTHER deny sites (subshell-unverifiable, claim-dir, `.git`-store) explicitly PRESERVE their pre-2026-07-10 override-bypass behavior (`continue`/fall-through on `_RM_OVERRIDE == 1`) — peer-contest hardening was scoped to the untracked-work branch only, per spec.

**KNOWN residuals — deliberately left for a possible P1:**
- The override still bypasses the `.git`-store / claim-dir / subshell-unverifiable denials unconditionally (out of scope for this pass — those targets are either never-legitimate-to-delete or already-unverifiable, not "possibly a live peer's work").
- No `coordinator-quarantine`-style verb exists yet (move-to-quarantine instead of delete-or-stash); `git stash push -u` is offered as the interim recoverable path and covers the recoverability need.
- `COORDINATOR_ALLOW_RM` remains session-WIDE (env-var scoped to the whole hook invocation), not per-path-tokenized — an override still applies to every untracked target in a multi-target `rm`, it is simply now individually gated per-target by the peer-claim check rather than blanket-honored.

**Verification:** suite 81/0 (5 new peer-contest cases: override-bypass-when-uncontested, override-refused-when-peer-claims [deny + message names peer sid], peer-claim-denies-even-without-override, stale-peer-does-not-contest, no-coordinator-sessions-dir-behaves-as-before).
