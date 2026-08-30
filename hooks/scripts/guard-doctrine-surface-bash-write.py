"""PreToolUse(Bash) hook: close the Bash escape from the C7 doctrine
admission gate (`check-claude-md-size.py`, registered on
``Write|Edit|MultiEdit`` only).

THE DEFECT THIS CLOSES: the admission gate that governs
``_claude_md_ledger.GOVERNED_AUTHORING_SURFACES`` (unjustified growth of
always-on doctrine) only ever sees the ``Write``/``Edit``/``MultiEdit`` tool
names. A shell redirect (``cat > file``, ``printf >> file``, ``tee``), an
interpreter payload (``python3 -c "open(p,'w').write(...)"``, ``sed -i``,
``perl -i``), or a heredoc writes a governed surface with the admission gate
never firing at all. This hook is the mirror-image guard on the Bash
surface, following the same paired-guard idiom already established in this
fleet for ``docs/plans/**`` -- ``coordinator_core.write_guards.
block_subagent_plan_body_write`` (Write/Edit/MultiEdit) is paired with
``coordinator_core.bash_guards.block_subagent_plan_body_bash_write`` (Bash)
in the control-plane engine repo; this hook is that same pairing shape
applied to the C7 admission gate instead, authored plugin-side (not
engine-side) because the C7 predicate itself is plugin-resident permanently
(same reasoning ``check-claude-md-size.py``'s own docstring gives for why the
admission-gate leg does not fold into the engine).

DETECTION STRATEGY -- deny by the WRITE SINK, not by the presence of shell
punctuation anywhere in the command. An earlier revision of this hook denied
the whole command whenever a governed identifier and a write/indirection
marker both appeared ANYWHERE in the command text, with no requirement that
the marker be anywhere near the mention. That closed the bypass but also
denied ordinary multi-stage read pipelines that happened to mention a
governed surface in one stage and an unrelated tool (e.g. ``python3 -m
pytest ...`` for an unrelated test run) in another -- observed directly:
``ls ...; wc -c CLAUDE.md ...; python3 -m pytest ... -q`` was denied purely
because ``python3`` appeared somewhere in the same ``;``-joined command as
``CLAUDE.md``, even though neither stage touched the other. A guard that
blocks routine reads gets disabled or ``!``-prefixed by the first person it
annoys, and a disabled guard protects nothing -- so this revision keys off
the SINK:

  1. GOVERNED-IDENTIFIER MENTION (unchanged fast path). Build the
     identifier set from every ``_claude_md_ledger.GOVERNED_AUTHORING_
     SURFACES`` entry: its full repo-relative POSIX path AND its bare
     basename. If NONE of these identifiers appears, PATH-SEGMENT-BOUNDARY-
     ANCHORED (see ``_mentions_governed_identifier`` -- the character
     immediately before and after the match, if any, must not be
     ``[A-Za-z0-9]``, so ``CLAUDE.md`` matches bare, quoted, or preceded by
     ``/``, a backslash, whitespace, ``=``, ``(``, a backtick, ``;``, ``>``,
     but a longer
     basename that merely ENDS in the same characters -- ``dotclaude.md``
     containing ``claude.md`` -- does not), anywhere in the command text,
     the command cannot be directed at a governed surface by any means this
     hook can see -> ALLOW immediately (the overwhelming majority of Bash
     calls never mention a governed surface at all).

  2. TOP-LEVEL SEGMENTATION. The command is split into segments at
     top-level ``;``, ``&&``, ``||``, ``|``, and newline -- "top-level"
     meaning outside single/double quotes and outside ``(...)``/``$(...)``
     grouping, so a pipe or semicolon embedded in a quoted argument (e.g.
     ``sed 's/a;b/c/'``) does not fracture a single command. Each segment
     is then classified independently: a segment that does not itself
     mention a governed identifier cannot deny the command on its own,
     regardless of what marker it contains -- this is what lets
     ``wc -c CLAUDE.md`` and an unrelated ``python3 -m pytest ...`` coexist
     in one ``;``-joined command without the ``python3`` mention leaking
     into the ``CLAUDE.md`` verdict.

  3. PER-SEGMENT SINK CLASSIFICATION. A segment that DOES mention a
     governed identifier is denied if it also contains, in that SAME
     segment: a write marker (``>``/``>>`` that is not fd-duplication
     (``2>&1``) or a ``/dev/null`` target, ``tee``, an in-place editor
     (``sed -i``/``perl -i``), ``cp``/``mv``/``install``/``dd``/
     ``truncate``, a write-mode ``open(...)``/``.write(``/``.write_text(``/
     ``.write_bytes(`` call), OR an indirection marker (an interpreter
     invocation (``python``/``python3``/``perl``/``ruby``/``node``), a
     ``sh``/``bash``/``zsh -c`` subshell, ``eval``, ``xargs``, a backtick,
     or a ``$(...)`` command substitution) -- inside an interpreter payload
     or a dynamically-assembled command this hook cannot reliably prove a
     mention is a read, so it fails CLOSED rather than guessing (unchanged
     posture from the prior revision; see point 5).

  4. CROSS-SEGMENT VARIABLE-ASSIGNMENT INDIRECTION (the one deliberate
     exception to per-segment scoping). ``SURFACE="coordinator/snippets/
     em-operating-doctrine.md"; echo "..." > "$SURFACE"`` never mentions the
     governed identifier in the same segment as the write marker -- the
     mention is in the assignment, the write is against the *variable* two
     segments later. If a segment is (or opens with) a shell variable
     assignment (``NAME=...``) whose value mentions a governed identifier,
     the WHOLE command is checked for a write marker (not scoped to that
     one segment) -- this is "command assembly from a variable", one of the
     shapes the dispatch brief names as genuinely unclassifiable and
     required to stay denied. This is deliberately broader than point 3
     (whole-command write-marker scan, not segment-scoped) because once a
     variable carries a governed path, this hook has no way to know which
     later segment(s) dereference that variable.

  5. THE FAIL-CLOSED POSTURE (unchanged). Per the dispatch brief: "when a
     payload arrives through an interpreter or command-assembly indirection
     you CANNOT reliably distinguish a read from a write, so DENY that
     shape by construction rather than trying to parse it." This hook does
     not attempt to determine whether a ``python3 -c`` payload mentioning a
     governed identifier is actually reading or actually writing it --
     once an interpreter/indirection marker AND a governed-identifier
     mention are BOTH present in the same segment (or via point 4's
     variable-assignment exception), the shape is denied unconditionally.
     Ambiguity about the PATH (a dynamically assembled path, ``eval``,
     ``xargs``, backticks/``$(...)`` producing the path) still fails
     closed; ambiguity about mere punctuation elsewhere in the command
     (an unrelated pipe stage, ``2>&1``, ``2>/dev/null``) must not.

  6. READ-SHAPE CARVE-OUT (unchanged in spirit, now sink-scoped). A segment
     that mentions a governed identifier but contains no write or
     indirection marker (``cat``, ``head``, ``grep``, ``wc``, ``git show/
     log/diff/status/cat-file``, ``less``, ``more``, ``sort``, ``uniq``,
     ``diff``, ``md5``/``shasum``, ``ls``, ``stat``, ``file``, or any other
     non-write-shaped inspection) is treated as a read and ALLOWED, even
     when chained via ``|``/``;``/``&&`` with other segments that mention
     unrelated tools -- reads cannot corrupt the governed surface
     regardless of tool, and a pipeline whose SINK is read-only (e.g.
     ``git show HEAD:CLAUDE.md | wc -c``) must not be denied merely because
     an upstream or downstream stage exists. A pipe whose SINK targets a
     governed surface (``... | tee CLAUDE.md``) is still denied -- that
     sink segment mentions the identifier and contains ``tee``.

  7. GIT CONTENT-SAFE SUBCOMMAND CARVE-OUT. A segment whose command is
     ``git`` with a subcommand that cannot modify working-tree file content
     (``commit``, ``add``, ``log``, ``show``, ``diff``, ``status``,
     ``cat-file``, ``tag``, ``notes``, ``rev-parse``, ``ls-files``,
     ``blame``) is treated as a read-shape even when it mentions a governed
     identifier alongside a marker. Observed false positive: a scoped
     ``git commit ... -m "$(cat <<'EOF' ... EOF)"`` whose MESSAGE PROSE named
     a governed surface was denied purely because ``$(`` is an indirection
     marker -- but a commit message is not a path operand, and ``git
     commit`` writes the object store and the index, never a file in the
     working tree. The subcommand allow-list is deliberately narrow:
     ``checkout``, ``restore``, ``apply``, ``reset``, ``clean``, ``rm``,
     ``mv``, ``stash`` and anything unrecognised are NOT content-safe and
     stay subject to points 3-5.

     SCOPED-COMMIT WRAPPER RECOGNITION. Doctrine mandates the
     ``ceremony.scoped_git_commit`` wrapper family (``scoped-git-commit``,
     ``coordinator-safe-commit``, ``spinoff-deliverable-and-commit``) over a
     raw ``git add -A``/``git commit`` -- but until this point
     existed, the carve-out above recognised only the literal ``git``
     executable by name,
     so every one of those wrappers fell through to the general deny branch
     for the exact shapes point 7 already lets ``git`` itself through
     (commit-message prose containing ``>``, a ``$(...)`` command
     substitution, a heredoc). A guard that blocks the mandated path while
     permitting the raw one it replaces inverts BOTH rules at once: it
     punishes the wrapper doctrine tells agents to prefer, and it does so
     silently, since nothing about the wrapper's own behavior differs from
     ``git commit`` in a way that would justify different treatment. A
     segment whose COMMAND TOKEN's basename (the final ``/``-separated
     component, tolerating a leading env-assignment prefix the same way
     ``_git_subcommand`` does, and tolerating a
     ``"$VAR/bin/name"``/``"${VAR:-default}/bin/name"`` invocation form,
     and a trailing ``.cmd`` suffix stripped case-insensitively before the
     comparison -- Windows ships every wrapper as BOTH a bare POSIX form
     AND a ``.cmd`` form under the same ``bin/`` directory, and Windows
     paths/extensions are case-insensitive, so ``Scoped-Git-Commit.CMD``
     names the same binary as ``scoped-git-commit``; recognising the POSIX
     form while silently denying the ``.cmd`` form would be a multi-OS
     correctness defect, not a cosmetic gap) is one of those four names is
     treated as inherently commit-shaped -- equivalent to point 7's
     content-safe set -- because the wrappers take no git subcommand at
     all; there is no ``checkout``-class subcommand for them to carry, so
     they never become eligible for point 8's mutation treatment. Matching
     is BASENAME-EXACT (modulo the ``.cmd``/case handling above) against
     the command token only (never a substring, never an argument later in
     the segment), so a lookalike name (``my-scoped-git-commit-wrapper``)
     or the same name appearing as a mere argument rather than the invoked
     command does not match. Every other check in this carve-out -- the
     pathspec-vs-redirect
     scan, ``$(...)``/heredoc-as-argument vs. as-write-sink, ``tee``, an
     interpreter payload -- applies to a matched wrapper segment completely
     UNCHANGED: a real redirect that truncates a governed file
     (``scoped-git-commit -m msg > CLAUDE.md``) still denies, exactly as it
     would for ``git commit -m msg > CLAUDE.md``.

     Both of the carve-out's scans first strip HEREDOC BODIES
     (``_strip_heredoc_bodies``), keeping the introducing command line. A
     heredoc body is data on stdin and cannot redirect or execute; without
     this, a quote character inside a ``-m "$(cat <<'EOF' ... EOF)"``
     message closes the outer quoted span early and exposes the remaining
     prose -- an ``->`` arrow, a quoted example command -- as live shell.
     Keeping the introducing line intact is what preserves the original
     ``cat <<'EOF' > CLAUDE.md`` denial.

     The carve-out re-tightens twice more, so it grants no bypass:

       - Write markers are re-scanned with QUOTED SPANS STRIPPED. That keeps
         ``git commit -m "prose containing a > arrow"`` allowed while
         ``git commit -m msg > CLAUDE.md`` -- where git's stdout truncates a
         governed surface for real -- still denies, because that redirect
         lives outside any quote.
       - Code-execution markers (``python``/``perl``/``ruby``/``node``,
         ``eval``, ``xargs``, ``sh -c``) are scanned on the UNSTRIPPED text,
         so ``git commit -m "$(python3 -c '...')"`` still denies. Bare
         command substitution (``$(...)``/backticks) alone does NOT deny
         here: a substitution can only write a file by way of one of the
         markers already scanned for, and denying it outright is precisely
         the false positive this point exists to remove.

  8. GIT CONTENT-MUTATING SUBCOMMANDS ARE THEMSELVES A WRITE MARKER. The
     mirror of point 7, and a gap that predated it: ``git checkout HEAD~5
     -- CLAUDE.md`` overwrites a governed surface with an arbitrary
     historical revision while carrying NO redirect, NO ``tee`` and NO
     interpreter -- so it matched none of point 3's markers and was
     silently ALLOWED. ``checkout``, ``restore``, ``switch``, ``apply``,
     ``reset``, ``clean``, ``rm``, ``mv``, ``stash``, ``revert``,
     ``cherry-pick``, ``merge``, ``rebase`` and ``pull`` now deny on their
     own whenever the segment mentions a governed identifier. This check
     runs BEFORE point 7's carve-out, so the two sets can never both apply.

  9. ``coordinator_core.session.claude_md_grant`` CLI CARVE-OUT -- a
     deadlock between this hook and the C7a grant path it itself is paired
     with. ``block_unauthorized_claude_md_write`` (the engine-side write
     guard on Write/Edit/MultiEdit) denies an un-granted CLAUDE.md-class
     edit and names exactly one remediation:
     ``python3 -m coordinator_core.session.claude_md_grant grant pm
     "<verbatim PM note>"``. That remediation IS a ``python3`` invocation
     mentioning a governed identifier in the same segment (the PM's note
     almost always names the file it authorizes -- that is the natural
     shape of an authorization note, not an edge case), so point 3 denied
     it outright: the one command the other guard's own deny text tells the
     operator to run was itself unrunnable. The CLI's write target is its
     own grant record (``state/...`` ledger, never the governed file
     itself) for every subcommand (``grant``/``read``/``check``) by
     construction -- a governed filename appearing anywhere in its
     arguments is always DATA (the note prose), never a path operand, since
     the CLI takes no path argument at all. A segment invoking
     ``python3``/``python`` with ``-m coordinator_core.session.
     claude_md_grant`` is recognised as this known-safe CLI and treated as
     read-shape for the governed-identifier mention -- but, mirroring point
     7's re-tightening, a REAL write marker outside any quoted argument
     (``... claude_md_grant grant pm "..." > CLAUDE.md``) still denies; only
     the CLI's own expected ``python3``/``-m`` indirection marker is
     exempted, not an actual redirect/tee smuggled into the same segment.
     Matching is on the ``-m`` module argument, so a lookalike script name
     or the module string appearing only as prose elsewhere does not match.

     CROSS-REPO INVARIANT THIS CARVE-OUT DEPENDS ON (Review: code-reviewer,
     Finding 3, P2): the "write target is its own grant record, never the
     governed file" claim above is a property of
     ``coordinator_core.session.claude_md_grant`` -- a control-plane engine
     module this repo does not host, so there is no local source or test
     here asserting that invariant. A future change to that module (a new
     subcommand, a force-write flag, or any path argument) is required to
     co-review this carve-out; this comment is the backlink that makes that
     co-review discoverable from here.

  11. INTERPRETER-INVOCATION READ-SHAPE (fold dispatch fix,
      ``_is_interpreter_read_shape``, MEASURED false positive). Point 3/5's
      original posture treated the bare PRESENCE of an interpreter marker
      (``python3``/``perl``/``ruby``/``node``) in a mentioning segment as
      always enough to deny, on the theory that an interpreter can write
      with no textual trace of its own. That denied a genuinely read-only
      command observed live: a governed filename appearing inside a QUOTED
      Python string literal (e.g. ``python3 -c "print('reads CLAUDE.md')"``)
      with no write call anywhere in the payload. A segment is now
      READ-shaped -- exempted from the point-3 interpreter-marker deny, same
      as a content-safe ``git`` subcommand -- iff ALL hold: its own command
      token IS one of the four interpreters (not merely mentioned
      downstream/upstream of one); it carries no write marker
      (``_has_write_marker``, unchanged, still catches every point-3 write
      primitive on the raw text); no OS-exec escape hatch
      (``os.system(``/``subprocess.*(``/``shell=True``/``eval(``/``exec(``);
      no ``eval``/``xargs``; and the identifier mention does not survive
      ``_strip_quoted_spans`` (i.e. it is quoted content, never a bare path
      operand). A write marker, an OS-exec call, or a bare mention still
      denies exactly as before -- this narrows only the no-write,
      quoted-mention shape.

NEGATIVE-SPEC -- known, accepted over-denial, preserved from the prior
revision: a SEGMENT that mentions a governed surface AND also contains an
unrelated write marker in that SAME segment (e.g. ``git diff
coordinator/snippets/em-operating-doctrine.md > /tmp/out.txt``, where the
diff of the governed surface is redirected to an unrelated scratch file)
still denies -- this hook does not parse *which* argument a redirect
targets within a single segment, only whether one is present alongside a
mention. This is deliberate over-denial in the safe direction: a blocked
read-plus-redirect-elsewhere command can always be rewritten as two
separate Bash calls (a plain read, then a plain write to the unrelated
target) to route around it. What point 2/6 fix is the CROSS-segment/stage
false positive (an unrelated ``python3`` invocation two ``;`` away), not
this same-segment case.

NEGATIVE-SPEC -- a SECOND, deliberately un-fixed same-segment over-denial,
observed live in a reviewer dispatch: an interpreter payload that writes an
UNRELATED destination (e.g. a ``state/subagent-share/<session>/<agent>.md``
run-report sidecar) via ``p.write_text("...")``, where the STRING ARGUMENT
being written happens to quote a governed surface's filename as PROSE (a
finding *about* that file, not a path operand) -- e.g.
``p.write_text("Finding: em-operating-doctrine.md needs a clarifying
note.")``. This denies for the same structural reason as the NEGATIVE-SPEC
above: the governed identifier and the write marker (``.write_text(``) sit
in the same segment, and this hook does not parse call arguments to tell
"the path being constructed" from "the string content being written". A
targeted fix was evaluated and rejected: stripping quoted spans before the
identifier check (the one mechanism that could separate "identifier as
prose inside a content argument" from "identifier as a path operand")
would ALSO hide the true positive this hook exists to catch, because a
Python write target is *itself* normally a quoted string literal --
``open('coordinator/snippets/<doctrine-file>.md','w').write(...)``
(see ``test_deny_interpreter_write_mode_open_on_claude_md``) is
indistinguishable from the false positive above by quoting alone. Call-
argument-position parsing (which parenthesized argument the identifier
falls inside) was also rejected: nested parens, f-strings, and
multi-argument calls make it unreliable enough that a wrong parse would
silently reopen the interpreter-payload bypass this hook exists to close.
The fix that shipped instead is doctrine, not detection: the denial
message below (see ``_compose_deny_message``) names Edit as the correct persist
path for an already-provisioned sidecar destination -- Edit operates on
the file directly and never routes through this hook's Bash-command
classification at all, so a payload whose destination is NOT a governed
surface never needs to satisfy this hook's heuristics in the first place.
See ``coordinator/snippets/findings-self-persist-sentinel.md`` for the
doctrine-side half of this fix.

NEGATIVE-SPEC UPDATE (dispatch fix, see
``test_allow_heredoc_body_prose_mention_with_unrelated_write_target``
and ``test_allow_printf_scratch_redirect_with_quoted_prose_mention``): the
SAME-SEGMENT shape immediately above (a single ``python3 -c`` payload
where the identifier mention and ``.write_text(`` sit in one segment) is
still deliberately left denying, unchanged, for the reasons given above.
Two narrower shapes ARE now fixed, because each has a mechanism this hook
CAN reliably distinguish without argument-position parsing: (1) a bare
``>``/``>>`` redirect whose own target token does not name a governed
identifier, in a segment where the identifier's only appearance is inside
a quoted span (the printf/scratch-redirect shape); and (2) a HEREDOC BODY
line containing a Python triple-quoted assignment that mentions a
governed name in its own prose, that ``_ASSIGN_RE`` was misreading as a
live shell variable assignment for point 4's cross-segment scan, even
though the assignment and the unrelated ``.write_text(`` call are
DIFFERENT lines/segments never executed as shell at all. Neither fix
touches this SAME-SEGMENT ``-c`` shape, NEGATIVE-SPEC-1 (git-diff-plus-
unrelated-redirect with a BARE, unquoted mention), or any
``open(...,'w')`` true positive -- see ``_has_write_marker_for_point3``
and the point-4 heredoc-stripping comment in ``is_denied_bash_write`` for
the narrowing logic and why each stays scoped.

Contract: reads PreToolUse JSON from stdin (mirrors
``check-claude-md-size.py``): exit 0 = allow (silent), exit 2 = BLOCK
(stderr message shown to the user). Any failure to decode the stdin JSON, or
a missing/non-string ``tool_input.command``, fails OPEN (exit 0) -- there is
no command to classify at all in that case, which is a different situation
from "a command was extracted but its target could not be classified"
(covered by point 5 above, which fails CLOSED). Fires only on
``tool_name in _COMMAND_TOOL_NAMES`` (``"Bash"`` or ``"PowerShell"``).

Spec backlink: docs/plans/2026-07-30-boot-doctrine-cut-and-refill-gate.md § C7a
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from _claude_md_ledger import GOVERNED_AUTHORING_SURFACES  # noqa: E402
from _message_envelope import compose, render  # noqa: E402

#: Wiki section carrying the relocated deny-reason explanation (the SINK-
#: based classification rationale, the pathspec/Write-Edit/Edit-direct
#: remedies, and the grant-CLI carve-out) -- see this hook's relocation
#: fragment, state/relocations/guard-message-cap/
#: guard-doctrine-surface-bash-write.py.md, and
#: docs/plans/2026-08-02-guard-message-character-cap.md § C6.
_WIKI_ANCHOR = (
    "coordinator/docs/wiki/guard-message-concision.md"
    "#doctrine-surface-bash-write-guard-carve-outs-and-remedies"
)

#: The command-issuing tool names this guard's matcher covers. Mirrors the
#: `Bash|PowerShell` matcher in hooks.json; both are provisional local copies
#: pending the engine repo's `coordinator_core` SSOT constant (BX-17 Piece 2,
#: memo 2026-08-07 to the engine-side EM), which they will import once it lands.
_COMMAND_TOOL_NAMES = ("Bash", "PowerShell")


def _governed_identifiers() -> "list[str]":
    """Every full repo-relative path AND bare basename from
    ``GOVERNED_AUTHORING_SURFACES``, de-duplicated, longest-first (so a
    full-path match is checked before its own basename would also match --
    order doesn't change the verdict here since this is a pure membership
    test, but longest-first keeps the reported "matched" identifier the
    more specific one when this list is used for diagnostics)."""
    identifiers: "set[str]" = set()
    for surface in GOVERNED_AUTHORING_SURFACES:
        identifiers.add(surface)
        identifiers.add(surface.rsplit("/", 1)[-1])
    return sorted(identifiers, key=len, reverse=True)


_GOVERNED_IDENTIFIERS = _governed_identifiers()

#: Case-folded mirror of ``_GOVERNED_IDENTIFIERS`` -- see module docstring
#: point 3 (Review: security-audit-worker, "high" finding -- both macOS and
#: Windows are case-insensitive-filesystem-by-default, this repo's own
#: CLAUDE.md names macOS/Windows first-class, and ``claude.md``/
#: ``EM-Operating-Doctrine.MD`` name the SAME governed file as
#: ``CLAUDE.md``/``em-operating-doctrine.md`` on either platform). The
#: case-SENSITIVE list above is kept for diagnostics (the "matched"
#: identifier reported is the canonical-cased one); the membership TEST
#: itself runs case-folded. Deliberately not a full glob resolution
#: (``CLAUDE.*`` remains out of scope -- a harder, separate problem per the
#: security-audit-worker's own triage).
_GOVERNED_IDENTIFIERS_LOWER = tuple(identifier.lower() for identifier in _GOVERNED_IDENTIFIERS)

#: Path-segment-boundary-anchored mirror of ``_GOVERNED_IDENTIFIERS_LOWER`` --
#: see ``_mentions_governed_identifier``. A governed identifier (bare
#: basename or full repo-relative path alike) may legitimately sit adjacent
#: to a quote, `/`, `\`, whitespace, `=`, `(`, a backtick, `;`, `>`, or
#: string-start/end -- none of those are word characters, so a lookbehind/
#: lookahead excluding `[A-Za-z0-9]` on either side accepts all of them
#: while rejecting a longer basename that merely ends/starts with the same
#: characters (`dotclaude.md` contains `claude.md` as a raw substring, but
#: the character immediately before the match is `t`, a word character, so
#: the anchored pattern does not match it).
_GOVERNED_IDENTIFIER_PATTERNS = tuple(
    re.compile(r"(?<![A-Za-z0-9])" + re.escape(identifier) + r"(?![A-Za-z0-9])")
    for identifier in _GOVERNED_IDENTIFIERS_LOWER
)

#: Redirect targets that are never a write to a governed surface: fd
#: duplication (``2>&1``, ``>&2``) and ``/dev/null``. Stripped before
#: scanning for a bare ``>``/``>>`` so stderr/stdout plumbing that names no
#: real file never counts as a write marker.
_SAFE_REDIRECT_RE = re.compile(r"\d?>&\d|>>?\s*/dev/null")
_BARE_REDIRECT_RE = re.compile(r">>?")


def _has_redirect_marker(text: str) -> bool:
    stripped = _SAFE_REDIRECT_RE.sub("", text)
    return bool(_BARE_REDIRECT_RE.search(stripped))


#: Write markers -- see module docstring point 3. Deliberately broad
#: (favors over-denial within a single segment) rather than precisely
#: scoped to any one shell/interpreter dialect.
_TEE_RE = re.compile(r"\btee\b")
_SED_INPLACE_RE = re.compile(r"\bsed\b.{0,120}?(-i\b|--in-place\b)", re.DOTALL)
_PERL_INPLACE_RE = re.compile(r"\bperl\b.{0,120}?-i\b", re.DOTALL)
#: A copying/truncating command name counts only in COMMAND POSITION -- at the
#: start of the segment or right after a shell operator -- never as a word
#: inside a path operand. `\b(...)\b` alone matched `install` inside the
#: filename `2026-07-08-install-baton-rendezvous-off-dotclaude.md`, because
#: hyphens are non-word characters that make every hyphenated fragment its own
#: `\b`-delimited word; combined with the mention prefilter that denied a plain
#: `grep -c` as a write. A path operand never sits in command position, so this
#: keeps the over-deny side (any genuine `cp`/`mv`/`install` invocation) while
#: dropping the filename-fragment match.
_CP_MV_RE = re.compile(
    r"(?:^|[|&;(]|\|\||&&)\s*(?:\w+=\S*\s+)*(?:sudo\s+|command\s+|env\s+)*"
    r"\b(cp|mv|install|dd|truncate)\b"
)
_WRITE_MODE_OPEN_RE = re.compile(r"open\([^)]*['\"][wax]['\"]")
_WRITE_METHOD_RE = re.compile(r"\.write(_text|_bytes)?\(")

#: Additional file-write primitives -- see module docstring point 3
#: extension (Review: security-audit-worker, "high" finding -- enumeration
#: gap confirmed live against `ex -c '%d' -c 'wq' CLAUDE.md`,
#: `patch CLAUDE.md < x.patch`, `rsync -a src CLAUDE.md`,
#: `curl -o CLAUDE.md URL`, `wget -O CLAUDE.md URL`, and
#: `sed -n 'w CLAUDE.md' /dev/null` -- sed's `w` SCRIPT command writes a
#: file with no `-i`/`--in-place` flag at all, so `_SED_INPLACE_RE` never
#: fires on it). Built the same way `_CP_MV_RE` was: a bare command-name
#: word-boundary match, deliberately broad rather than scoped to one
#: invocation shape.
_EX_ED_RE = re.compile(r"\b(ex|ed)\b")
_PATCH_RSYNC_RE = re.compile(r"\b(patch|rsync)\b")
_CURL_OUTPUT_RE = re.compile(r"\bcurl\b.{0,200}?(-o\b|--output\b)", re.DOTALL)
_WGET_OUTPUT_RE = re.compile(r"\bwget\b.{0,200}?(-O\b|--output-document\b)", re.DOTALL)
#: `sed`'s own `w <file>` SCRIPT COMMAND (distinct from `-i`/`--in-place`):
#: a lowercase `w` followed by whitespace and a non-whitespace filename
#: token, anywhere inside a `sed` invocation.
_SED_WRITE_SCRIPT_RE = re.compile(r"\bsed\b.{0,200}?\bw\s+\S", re.DOTALL)


def _redirect_target_token(segment: str) -> "str | None":
    """The token immediately following the last real (non-fd-duplication,
    non-``/dev/null``) bare ``>``/``>>`` in ``segment`` -- the actual
    redirect destination. ``None`` when ``segment`` carries no such
    redirect, or the redirect is trailing with nothing after it. Used only
    by ``_has_write_marker_for_point3`` to tell a redirect that targets a
    governed surface from one that merely shares a segment with a QUOTED
    mention of one."""
    masked = _SAFE_REDIRECT_RE.sub(lambda m: " " * len(m.group(0)), segment)
    last = None
    for match in _BARE_REDIRECT_RE.finditer(masked):
        last = match
    if last is None:
        return None
    rest = segment[last.end() :].lstrip()
    if not rest:
        return None
    if rest[0] in ("'", '"'):
        quote = rest[0]
        end = rest.find(quote, 1)
        return rest[1:end] if end != -1 else rest[1:]
    end = 0
    while end < len(rest) and not rest[end].isspace():
        end += 1
    return rest[:end]


def _has_write_marker_for_point3(segment: str) -> bool:
    """Point 3's write-marker check, narrowed for the BARE-REDIRECT shape
    only -- observed live: ``printf '%s\\n' "..." "CLAUDE.md holds every op
    to a budget" ... > "scratch/spin-msg.txt"``, where the governed mention
    is prose INSIDE a quoted ``printf`` argument and the redirect's real
    target is an unrelated scratch file. The prior revision counted any
    bare-redirect marker anywhere in a mentioning segment as denying, with
    no check of what the redirect actually targets -- correct for
    NEGATIVE-SPEC-1's accepted case (``git diff <governed-path> >
    /tmp/out.txt``, where the mention is a BARE, unquoted path operand --
    still denies below via ``bare_mention``) but wrong for this one, where
    the mention never appears outside a quoted span at all.

    A redirect counts as evidence of a governed write iff EITHER the
    identifier mention survives ``_strip_quoted_spans`` (a bare operand,
    e.g. ``git diff CLAUDE.md > /tmp/out``) OR the redirect's own target
    token names a governed identifier (``> CLAUDE.md`` or ``>
    "CLAUDE.md"`` alike -- a real write, however the target happens to be
    quoted). When neither holds, the redirect itself is set aside and
    every OTHER write marker (``tee``, ``sed -i``, ``cp``/``mv``,
    ``open(...,'w')``, ``curl -o``, ...) is still checked at its existing
    broad, unnarrowed, fail-closed scope -- this function narrows only the
    plain-redirect case reproduced above, nothing else. Used only by the
    point-3 loop in ``is_denied_bash_write``; every other caller of
    ``_has_write_marker`` (the git/wrapper/grant carve-outs, point 4) is
    unchanged."""
    if not _has_redirect_marker(segment):
        return _has_write_marker(segment)
    target = _redirect_target_token(segment)
    target_mentions = bool(target) and _mentions_governed_identifier(target)
    bare_mention = _mentions_governed_identifier(_strip_quoted_spans(segment))
    if target_mentions or bare_mention:
        return True
    without_redirect = _BARE_REDIRECT_RE.sub(" ", _SAFE_REDIRECT_RE.sub(" ", segment))
    return _has_write_marker(without_redirect)


def _has_write_marker(text: str) -> bool:
    if _has_redirect_marker(text):
        return True
    for pattern in (
        _TEE_RE,
        _SED_INPLACE_RE,
        _PERL_INPLACE_RE,
        _CP_MV_RE,
        _WRITE_MODE_OPEN_RE,
        _WRITE_METHOD_RE,
        _EX_ED_RE,
        _PATCH_RSYNC_RE,
        _CURL_OUTPUT_RE,
        _WGET_OUTPUT_RE,
        _SED_WRITE_SCRIPT_RE,
    ):
        if pattern.search(text):
            return True
    return False


#: Interpreter / command-assembly indirection markers -- see module
#: docstring point 3/5. Presence of one of these, alongside a governed-
#: identifier mention in the SAME segment, is itself enough to deny --
#: an interpreter payload can write a file with no textual trace of
#: ">"/"tee"/"open(...,'w')" at all (``os.system(...)``,
#: ``subprocess.run(..., shell=True)``, or a payload this hook has no hope
#: of enumerating exhaustively), so the interpreter marker alone is treated
#: as "cannot prove this is a read".
_INTERPRETER_RE = re.compile(r"\b(python3?|perl|ruby|node)\b")
_SHELL_DASH_C_RE = re.compile(r"\b(sh|bash|zsh)\b.{0,40}?-c\b", re.DOTALL)
_EVAL_RE = re.compile(r"\beval\b")
_XARGS_RE = re.compile(r"\bxargs\b")
_CMD_SUBST_RE = re.compile(r"\$\(|`")

_INDIRECTION_PATTERNS = (
    _INTERPRETER_RE,
    _SHELL_DASH_C_RE,
    _EVAL_RE,
    _XARGS_RE,
    _CMD_SUBST_RE,
)


def _has_indirection_marker(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INDIRECTION_PATTERNS)


def _mentions_governed_identifier(text: str) -> bool:
    """Whole-command PREFILTER: does this text mention a governed surface at all?

    Deliberately UNBOUNDED (plain substring), and it must stay that way. This is
    the fast-path gate at the top of ``is_denied_bash_write``, so it decides what
    even reaches segmentation and the point-4 variable-assignment-indirection
    scan. Anchoring it narrows the funnel rather than the verdict: the write
    target may be a VARIABLE whose value merely CONTAINS the identifier with an
    adjacent character the shell strips before the write lands, e.g.
    ``X=xCLAUDE.md; echo pwned > "${X:1}"`` -- a real write to a governed
    surface that an anchored prefilter never sees. A false positive here costs
    nothing: the segment still has to clear a write-marker check downstream. A
    false negative here is total.

    Path-identity precision belongs at the decision point, not at the gate --
    see ``_names_governed_identifier``."""
    lowered = text.lower()
    return any(identifier in lowered for identifier in _GOVERNED_IDENTIFIERS_LOWER)


def _names_governed_identifier(text: str) -> bool:
    """Path-segment-BOUNDARY-anchored test: does this text name a governed
    surface as its own path component, rather than merely contain the
    characters inside a longer basename (``dotclaude.md``)? Precision half of
    the pair above; never a prefilter."""
    lowered = text.lower()
    return any(pattern.search(lowered) for pattern in _GOVERNED_IDENTIFIER_PATTERNS)


#: Markers that can actually EXECUTE arbitrary code inside a segment. A
#: strict subset of ``_INDIRECTION_PATTERNS`` -- deliberately excludes bare
#: command substitution (``$(...)``/backticks), which cannot write a file
#: except by way of one of the markers scanned for here or a redirect (which
#: ``_has_write_marker`` catches independently). Used only by the point-7
#: git carve-out; the general path in point 3 still treats substitution
#: itself as disqualifying.
_CODE_EXECUTION_PATTERNS = (
    _INTERPRETER_RE,
    _SHELL_DASH_C_RE,
    _EVAL_RE,
    _XARGS_RE,
)


def _has_code_execution_marker(text: str) -> bool:
    return any(pattern.search(text) for pattern in _CODE_EXECUTION_PATTERNS)


_HEREDOC_START_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def _strip_heredoc_bodies(text: str) -> str:
    """``text`` with the BODY of every heredoc removed, keeping the command
    line that introduces it.

    A heredoc body is inert data -- it is fed to a command's stdin, and no
    amount of ``>`` or quoting inside it can write a file. Only the
    introducing command line can. Keeping that line intact is what preserves
    the point-1/3 denial of ``cat <<'EOF' > CLAUDE.md`` (mention and
    redirect both sit on the command line, not in the body), while removing
    the body stops prose inside it from being read as shell syntax.

    UNDELIMITED (single-line) FALLBACK: a real shell heredoc always puts its
    body after a newline, but an agent-emitted command frequently arrives as
    ONE LINE with every newline collapsed to a space -- the introducing
    ``<<'TERM'`` marker and the terminator token then share a line with no
    newline to delimit the body between them, so the line-scan above never
    finds ``lines[idx].strip() == terminator`` and falls straight through to
    the end of ``lines`` with the body never stripped. That silently turns
    an ordinary heredoc body (commit-message prose, most often) into live
    text this hook scans for write/indirection markers -- a false denial by
    formatting, not intent. When the terminator cannot be found on a line of
    its own, this function falls back to locating it as a whitespace-
    bounded TOKEN later in the same line and strips the span between the
    marker and that token, exactly mirroring the multi-line body-removal
    above. If even that token cannot be found (a genuinely unterminated
    heredoc), nothing is stripped and the line is kept whole -- unchanged,
    maximal-suspicion posture from before this fallback existed.

    Used only by the point-7 git carve-out. Without it, a commit message
    delivered as ``-m "$(cat <<'EOF' ... EOF)"`` defeats
    ``_strip_quoted_spans``: a quote character inside the message closes the
    outer span early and exposes the remaining prose -- an em-dash arrow, or
    a quoted example command -- as though it were live shell."""
    lines = text.split("\n")
    out: "list[str]" = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        match = _HEREDOC_START_RE.search(line)
        idx += 1
        if not match:
            out.append(line)
            continue
        terminator = match.group(2)
        scan = idx
        while scan < len(lines) and lines[scan].strip() != terminator:
            scan += 1
        if scan < len(lines):
            out.append(line)
            out.append(lines[scan])  # keep the terminator line itself
            idx = scan + 1
            continue
        term_token_re = re.compile(r"(?<!\S)" + re.escape(terminator) + r"(?!\S)")
        term_match = term_token_re.search(line, match.end())
        if term_match is None:
            out.append(line)
            continue
        out.append(line[: match.end()])
        out.append(line[term_match.start() :])  # keep the terminator token onward
    return "\n".join(out)


#: An interpreter invocation that makes STDIN the program text rather than a
#: data stream: ``python3 -``, ``python -``, ``bash -s``, ``sh -s``, ``node -``,
#: ``perl -``, ``ruby -``, and a bare ``bash``/``sh`` with no script operand.
#: For these -- and ONLY these -- a heredoc body is executable source, not
#: inert stdin data.
_STDIN_PROGRAM_RE = re.compile(
    r"(?:^|[;&|]|\s)(?:python3?|perl|ruby|node)\s+-(?=\s|$)"
    r"|(?:^|[;&|]|\s)(?:bash|sh)\s+-s(?=\s|$)"
    r"|(?:^|[;&|]|\s)(?:bash|sh)\s*(?=<<)"
)


def _stdin_program_heredoc_bodies(text: str) -> "list[str]":
    """The BODY of every heredoc whose introducing line makes stdin the
    program (``_STDIN_PROGRAM_RE``).

    ``_strip_heredoc_bodies`` rests on "a heredoc body is inert data -- it is
    fed to a command's stdin, and no amount of ``>`` or quoting inside it can
    write a file." That premise is exactly false for ``python3 - <<'PY'`` and
    friends, where the body IS the executed program. Returning those bodies
    lets the point-4 companion below scan them as live code without
    disturbing the strip that legitimately suppresses prose-in-a-heredoc
    false positives everywhere else."""
    bodies: "list[str]" = []
    lines = text.split("\n")
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        match = _HEREDOC_START_RE.search(line)
        idx += 1
        if not match:
            continue
        terminator = match.group(2)
        scan = idx
        while scan < len(lines) and lines[scan].strip() != terminator:
            scan += 1
        body = "\n".join(lines[idx:scan]) if scan < len(lines) else ""
        if scan < len(lines):
            idx = scan + 1
        if body and _STDIN_PROGRAM_RE.search(line[: match.start()] + " "):
            bodies.append(body)
    return bodies


#: ``NAME = "<governed path>"`` in an interpreter payload. The value must be
#: the governed identifier ALONE (optionally with a directory prefix) -- prose
#: that merely embeds the name inside a larger string is the documented point-4
#: false positive and must keep passing.
#: Quoted form covers interpreter payloads (``p = "CLAUDE.md"``); the bare
#: form covers a shell assignment in a ``bash -s`` body (``p=CLAUDE.md``),
#: which carries no quotes at all.
#: Triple-quoted branch is checked FIRST so a Python triple-quoted literal
#: (``p = """CLAUDE.md"""``) is matched against the true `"""`/`'''`
#: terminator rather than the single-quote branch closing early on the
#: literal's own adjacent leading quote pair (Review: coordinator:code-
#: reviewer, wsc-c3final-20260818 slice4 finding 1 -- the empty-capture
#: evasion this branch exists to close).
_PAYLOAD_ASSIGN_RE = re.compile(
    r"(?<![\w.])([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"(?:('''|\"\"\")([\s\S]*?)\2"
    r"|(['\"])([^'\"]*)\4|([^\s;&|()]+))"
)


def _has_stdin_program_var_write(cmd: str) -> bool:
    """True iff a stdin-as-program heredoc body binds a governed doctrine
    surface to a name and then writes THROUGH that name.

    Closes the seam between point 3 and point 4. Point 3 denies only when the
    identifier and the write marker share one segment, so it catches
    ``open('CLAUDE.md','w')`` on a single body line. Point 4 catches the
    assign-then-dereference shape, but runs on heredoc-STRIPPED text so a
    body never reaches it. A payload that binds the path on one line and
    writes through the binding on another therefore satisfied neither.

    Requiring the bound value to be the governed path itself (not prose
    containing it) plus a write that names the same variable keeps the
    point-4 false positive -- a prose blob mentioning a governed surface
    beside a ``.write_text(`` to a DIFFERENT file -- passing."""
    for body in _stdin_program_heredoc_bodies(cmd):
        for match in _PAYLOAD_ASSIGN_RE.finditer(body):
            name = match.group(1)
            value = (
                match.group(3) or match.group(5) or match.group(6) or ""
            ).strip().replace("\\", "/")
            if " " in value:
                continue  # prose that embeds the name, not a path -- point-4 FP
            if not _mentions_governed_identifier(value.rsplit("/", 1)[-1]):
                continue
            # WRITE intent through the bound name only. A bare ``open(NAME)``
            # is a READ and must keep passing -- matching it on the name alone
            # denied ``print(open(p).read())``.
            deref = re.compile(
                r"open\s*\(\s*%s\s*,\s*['\"][wax]"  # open(p, "w")
                r"|%s\s*,\s*['\"][wax]"  # io.open(p, "w"), any write-mode call
                r"|%s\s*\)\s*\.\s*write"  # Path(p).write_text(...)
                r"|>\s*\$?\{?%s\}?\b" % ((re.escape(name),) * 4)  # redirect via $p
            )
            if deref.search(body):
                return True
    return False


def _copy_command_substitution(text: str, start: int) -> "tuple[str, int]":
    """The verbatim span of a command substitution beginning at ``start``
    (``text[start]`` is a backtick, or ``text[start:start+2] == "$("``),
    plus how many characters it consumes. Backtick spans end at the next
    unescaped backtick; ``$(...)`` spans end at the balancing close-paren,
    tracking nesting depth so an inner ``(...)``/``$(...)`` doesn't close
    the span early. Used only by ``_strip_quoted_spans`` (see Review:
    code-reviewer -- command substitution inside a quoted span must stay
    live text, not be erased as inert literal data)."""
    n = len(text)
    if text[start] == "`":
        end = start + 1
        while end < n and text[end] != "`":
            end += 1
        end = min(end + 1, n)
        return text[start:end], end - start
    depth = 0
    i = start
    while i < n:
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                i += 1
                break
        i += 1
    return text[start:i], i - start


def _strip_quoted_spans(text: str) -> str:
    """``text`` with the contents of single- and double-quoted spans removed
    (the quote characters themselves are kept, so token boundaries survive)
    -- EXCEPT for any command-substitution span (``$(...)`` or a backtick
    pair) that appears inside the quote, which is copied through verbatim.

    Lets the point-7 carve-out ask "is there a redirect OUTSIDE any quoted
    argument?" -- the difference between ``git commit -m "a > b"`` (prose,
    harmless) and ``git commit -m msg > CLAUDE.md`` (git's stdout truncating
    a governed surface for real).

    Review: code-reviewer (Finding 1/2, P0/P1) -- bash evaluates ``$(...)``/
    backtick substitution INSIDE a double-quoted argument regardless of the
    surrounding quotes; quoting only suppresses word-splitting of the
    *result*, never the execution. A prior revision of this function erased
    the ENTIRE quoted span uniformly, including a substitution's content, so
    a redirect smuggled inside one (``"$(echo pwned > CLAUDE.md)"``) was
    invisible to the write-marker re-scan on every carve-out built on this
    helper (point 7's git carve-out, its wrapper-family mirror, and point
    9's grant-CLI carve-out alike -- this bug predated point 9 and point 9's
    diff only propagated it, per Finding 2). Preserving substitution content
    verbatim closes all three at once, without reopening the point-7 false
    positive this carve-out exists to fix: a heredoc-wrapped substitution
    (``"$(cat <<'EOF' ... EOF)"``) has its BODY already removed by
    ``_strip_heredoc_bodies`` before this function ever runs, so the
    preserved substitution text contains no live redirect to find."""
    out: "list[str]" = []
    quote: "str | None" = None
    prev = ""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote:
            if ch == quote and prev != "\\":
                quote = None
                out.append(ch)
                prev = ch
                i += 1
                continue
            if ch == "`" or text[i : i + 2] == "$(":
                span, consumed = _copy_command_substitution(text, i)
                out.append(span)
                prev = span[-1] if span else prev
                i += consumed
                continue
            prev = ch
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            prev = ch
            i += 1
            continue
        out.append(ch)
        prev = ch
        i += 1
    return "".join(out)


#: ``git`` subcommands that never modify working-tree file content -- see
#: module docstring point 7. Anything NOT listed here (``checkout``,
#: ``restore``, ``apply``, ``reset``, ``clean``, ``rm``, ``mv``, ``stash``,
#: and every unrecognised subcommand) is deliberately absent: the carve-out
#: must be an allow-list, never a deny-list, or a new content-mutating
#: subcommand silently inherits the exemption.
_GIT_CONTENT_SAFE_SUBCOMMANDS = frozenset(
    {
        "commit",
        "add",
        "log",
        "show",
        "diff",
        "status",
        "cat-file",
        "tag",
        "notes",
        "rev-parse",
        "ls-files",
        "blame",
    }
)

#: ``git`` subcommands that DO overwrite working-tree file content. These
#: are a write marker in their own right -- see module docstring point 8.
#: ``git checkout HEAD~5 -- CLAUDE.md`` carries no redirect, no ``tee`` and
#: no interpreter, so before this set existed it matched none of the
#: markers in point 3 and was silently ALLOWED while truncating a governed
#: surface to an arbitrary historical revision.
_GIT_CONTENT_MUTATING_SUBCOMMANDS = frozenset(
    {
        "checkout",
        "restore",
        "apply",
        "reset",
        "clean",
        "rm",
        "mv",
        "stash",
        "switch",
        "revert",
        "cherry-pick",
        "merge",
        "rebase",
        "pull",
    }
)

#: Pre-subcommand ``git`` options that take a value (``git -C <path> commit``)
#: -- skipped in pairs when locating the subcommand.
_GIT_VALUE_OPTS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})


def _git_subcommand(segment: str) -> "str | None":
    """The ``git`` subcommand ``segment`` invokes, skipping any
    pre-subcommand global options (``git -C <path> commit`` -> ``commit``).
    ``None`` when the segment is not a ``git`` invocation, or carries no
    subcommand at all."""
    tokens = segment.split()
    idx = 0
    while idx < len(tokens) and tokens[idx] != "git":
        # Tolerate a leading env-assignment prefix (GIT_DIR=... git ...);
        # anything else means git is not this segment's command.
        if not _ASSIGN_RE.match(tokens[idx]):
            return None
        idx += 1
    if idx >= len(tokens):
        return None
    idx += 1  # step past "git"
    while idx < len(tokens):
        token = tokens[idx]
        if not token.startswith("-"):
            return token
        if token in _GIT_VALUE_OPTS:
            idx += 2  # option plus its separate value
            continue
        idx += 1  # --opt=value, or a valueless flag
    return None


#: Basenames of the ``ceremony.scoped_git_commit`` wrapper family -- see
#: module docstring point 7's "SCOPED-COMMIT WRAPPER RECOGNITION" prose.
#: Deliberately exact-match only, never a substring or prefix test: a
#: lookalike name (``my-scoped-git-commit-wrapper``) must NOT inherit the
#: exemption.
#:
#: ``safe-commit-offer`` was a member of this set (a fixed-shape CLI that
#: only ever committed AND pushed with no confirmation step, reusing
#: ``scoped-git-commit``'s own push path). Its engine-plane CLI was deleted
#: and replaced by the registered op ``session.safe_commit_offer``, dialed
#: through the generic ``coordinator-invoke`` door alongside every other
#: engine op. ``coordinator-invoke`` is NOT re-keyed in here to replace it:
#: this set's safety property is basename-only recognition of a wrapper
#: whose BEHAVIOR IS FIXED BY ITS NAME -- ``coordinator-invoke``'s behavior
#: is chosen by its op-name argument, so basename recognition alone would
#: exempt every op dialed through the door, not just the commit-shaped one.
#: See ``coordinator/docs/wiki/coordinator-tripwires/
#: guard-carve-out-keyed-on-executable-name.md``.
_COMMIT_WRAPPER_BASENAMES = frozenset(
    {
        "scoped-git-commit",
        "coordinator-safe-commit",
        "spinoff-deliverable-and-commit",
    }
)

#: Windows carries every wrapper as BOTH a bare form and a ``.cmd`` form
#: (``$COORDINATOR_SETTINGS_HOME/bin/scoped-git-commit.cmd`` alongside the
#: extension-less POSIX form), and Windows paths/extensions are
#: case-insensitive -- ``Scoped-Git-Commit.CMD`` is the same binary as
#: ``scoped-git-commit``. A carve-out that recognises the POSIX form and
#: silently denies the ``.cmd`` form is a multi-OS correctness defect (P0 in
#: this repo), not a cosmetic gap, so the suffix is stripped case-
#: insensitively before the exact-match comparison below.
_CMD_SUFFIX_RE = re.compile(r"\.cmd$", re.IGNORECASE)


def _segment_command_token(segment: str) -> "str | None":
    """The first non-env-assignment token in ``segment`` -- the command
    actually being invoked, tolerating a leading ``NAME=value`` prefix the
    same way ``_git_subcommand`` does. ``None`` for a segment that is
    entirely env-assignments (or empty)."""
    tokens = segment.split()
    for token in tokens:
        if _ASSIGN_RE.match(token):
            continue
        return token
    return None


def _command_token_basename(token: str) -> str:
    """The final ``/``-separated component of ``token``, with a single
    layer of surrounding quotes stripped first -- so
    ``"$COORDINATOR_SETTINGS_HOME/bin/scoped-git-commit"`` and
    ``"${VAR:-default}/bin/scoped-git-commit"`` both resolve to
    ``scoped-git-commit`` regardless of what the variable expansion itself
    looks like, since only the text after the LAST ``/`` is ever the
    binary name."""
    stripped = token.strip("'\"")
    return stripped.rsplit("/", 1)[-1]


def _is_commit_wrapper_command(segment: str) -> bool:
    """True iff ``segment``'s command token is one of
    ``_COMMIT_WRAPPER_BASENAMES``, invoked bare, by absolute/relative path,
    via a ``$VAR``/``${VAR:-default}`` prefix, or with a case-insensitive
    ``.cmd`` suffix (the Windows form every wrapper ships alongside its
    POSIX form) -- see module docstring point 7."""
    token = _segment_command_token(segment)
    if token is None:
        return False
    basename = _command_token_basename(token)
    basename = _CMD_SUFFIX_RE.sub("", basename)
    return basename.lower() in _COMMIT_WRAPPER_BASENAMES


def _is_commit_wrapper_read_shape(segment: str) -> bool:
    """The wrapper-family mirror of ``_is_git_read_shape``: the wrappers
    take no git subcommand, so an invocation is inherently commit-shaped
    (equivalent to point 7's content-safe set) -- but every other scan
    (heredoc-body stripping, quoted-span-stripped write-marker re-scan,
    unstripped code-execution re-scan) applies completely unchanged."""
    if not _is_commit_wrapper_command(segment):
        return False
    without_heredocs = _strip_heredoc_bodies(segment)
    if _has_write_marker(_strip_quoted_spans(without_heredocs)):
        return False
    return not _has_code_execution_marker(without_heredocs)


def _is_git_content_mutation(segment: str) -> bool:
    """Point 8: a ``git`` subcommand that overwrites working-tree content."""
    return _git_subcommand(segment) in _GIT_CONTENT_MUTATING_SUBCOMMANDS


def _is_git_read_shape(segment: str) -> bool:
    """Point 7: a content-safe ``git`` subcommand that smuggles no redirect
    outside its quoted arguments and no code-execution marker outside its
    heredoc bodies.

    Both scans run on the heredoc-stripped text, because a heredoc body is
    data and cannot execute or redirect anything. The write-marker scan
    additionally strips quoted spans, so message prose containing ``>``
    stays allowed while a real redirect on the command line does not."""
    if _git_subcommand(segment) not in _GIT_CONTENT_SAFE_SUBCOMMANDS:
        return False
    without_heredocs = _strip_heredoc_bodies(segment)
    if _has_write_marker(_strip_quoted_spans(without_heredocs)):
        return False
    return not _has_code_execution_marker(without_heredocs)


#: The known-safe grant-CLI module -- see module docstring point 9. Its
#: write target is its own grant record for every subcommand, never a
#: governed doctrine surface, so a segment invoking it via ``python3 -m``
#: is never denied on the strength of a governed identifier appearing
#: inside its (data-only) arguments.
_CLAUDE_MD_GRANT_MODULE = "coordinator_core.session.claude_md_grant"

#: Interpreter basenames recognised for the point-9 carve-out -- deliberately
#: the same set ``_INTERPRETER_RE`` matches, restricted to the ones that
#: support a ``-m <module>`` invocation form (``perl``/``ruby``/``node`` do
#: not carry this CLI, so they are not included here even though they are
#: indirection markers elsewhere in this module).
_PYTHON_BASENAMES = frozenset({"python", "python3"})


def _python_dash_m_module(segment: str) -> "str | None":
    """The module name following a ``-m`` flag in a ``python``/``python3``
    invocation, tolerating a leading env-assignment prefix -- ``None`` if
    ``segment`` is not such an invocation, or carries no ``-m``. Used only
    by the point-9 grant-CLI carve-out."""
    tokens = segment.split()
    idx = 0
    while idx < len(tokens) and _ASSIGN_RE.match(tokens[idx]):
        idx += 1
    if idx >= len(tokens):
        return None
    if _command_token_basename(tokens[idx]) not in _PYTHON_BASENAMES:
        return None
    idx += 1
    while idx < len(tokens):
        if tokens[idx] == "-m" and idx + 1 < len(tokens):
            return tokens[idx + 1].strip("'\"")
        idx += 1
    return None


def _is_claude_md_grant_invocation(segment: str) -> bool:
    """True iff ``segment`` invokes the
    ``coordinator_core.session.claude_md_grant`` CLI via ``python3 -m``
    (or ``python -m``). See module docstring point 9."""
    return _python_dash_m_module(segment) == _CLAUDE_MD_GRANT_MODULE


def _is_claude_md_grant_read_shape(segment: str) -> bool:
    """The point-9 mirror of ``_is_git_read_shape``/
    ``_is_commit_wrapper_read_shape``: a recognised grant-CLI invocation is
    treated as read-shape for the governed-identifier mention (its write
    target is never the governed file), but a REAL write marker outside any
    quoted argument -- a genuine redirect/tee smuggled into the same
    segment -- still denies. Only the CLI's own expected ``python3``/``-m``
    indirection is exempted, not an actual write."""
    if not _is_claude_md_grant_invocation(segment):
        return False
    without_heredocs = _strip_heredoc_bodies(segment)
    return not _has_write_marker(_strip_quoted_spans(without_heredocs))


#: A shell variable assignment opening a segment -- ``NAME=...`` or
#: ``NAME="..."``. See module docstring point 4.
_ASSIGN_RE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*=")


def _split_top_level_segments(cmd: str) -> "list[str]":
    """Split ``cmd`` at top-level ``;``, ``&&``, ``||``, ``|``, and
    newline -- "top-level" meaning outside single/double quotes and outside
    parenthesis grouping (``(...)``/``$(...)``), so a separator embedded in
    a quoted argument or a subshell does not fracture a single logical
    command. See module docstring point 2."""
    segments: "list[str]" = []
    current: "list[str]" = []
    quote: "str | None" = None
    paren_depth = 0
    i = 0
    n = len(cmd)
    while i < n:
        ch = cmd[i]
        if quote:
            current.append(ch)
            if ch == quote and cmd[i - 1] != "\\":
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            current.append(ch)
            i += 1
            continue
        if ch == "(":
            paren_depth += 1
            current.append(ch)
            i += 1
            continue
        if ch == ")":
            paren_depth = max(0, paren_depth - 1)
            current.append(ch)
            i += 1
            continue
        if paren_depth == 0:
            if cmd[i : i + 2] in ("&&", "||"):
                segments.append("".join(current))
                current = []
                i += 2
                continue
            if ch in (";", "|", "\n"):
                segments.append("".join(current))
                current = []
                i += 1
                continue
        current.append(ch)
        i += 1
    segments.append("".join(current))
    return segments


def _has_var_assignment_indirection(segments: "list[str]") -> bool:
    """True iff some segment is (or opens with) a shell variable
    assignment whose value mentions a governed identifier -- see module
    docstring point 4. The caller still requires a write marker somewhere
    in the whole command before denying on this basis."""
    for segment in segments:
        if _ASSIGN_RE.match(segment) and _mentions_governed_identifier(segment):
            return True
    return False


_ASSIGN_NAME_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=")
_VAR_DEREF_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")


def _governed_bound_variables(segments: "list[str]") -> "set[str]":
    """Variable names bound to a governed path, following aliases.

    ``p=CLAUDE.md`` binds ``p`` directly; ``q=$p`` then binds ``q`` too. The
    fixed-point loop is bounded (an alias chain longer than the segment count
    cannot exist) so a pathological command cannot spin here."""
    bound: "set[str]" = set()
    for _ in range(len(segments) + 1):
        changed = False
        for segment in segments:
            match = _ASSIGN_NAME_RE.match(segment)
            if not match:
                continue
            name = match.group(1)
            if name in bound:
                continue
            value = segment[match.end() :]
            if _mentions_governed_identifier(segment) or any(
                deref in bound for deref in _VAR_DEREF_RE.findall(value)
            ):
                bound.add(name)
                changed = True
        if not changed:
            break
    return bound


def _assignment_indirection_reaches_a_write(segments: "list[str]") -> bool:
    """Point 4's by-SINK narrowing -- MEASURED FALSE POSITIVE FIX.

    Point 4 denied on "some segment assigns a governed path to a variable"
    AND "a write marker exists ANYWHERE in the whole command". The second
    conjunct never asked what the write actually TARGETS, so a command that
    merely READS the governed file through the variable and writes somewhere
    unrelated was denied. Reproduced independently by two sessions in one day
    (2026-08-28), minimal pair, the only difference being the assignment:

        p=<governed> ; cat $p ; echo x > /tmp/probe.txt   -> denied (wrong)
        cat <governed> ;        echo x > /tmp/probe.txt   -> allowed

    This mirrors, for point 4, exactly the narrowing
    ``_has_write_marker_for_point3`` already applies to point 3: a REDIRECT
    counts as evidence of a governed write only when its own target names one
    -- here, when the target dereferences a variable bound to a governed path
    (``> $p``, ``> "${p}"``) or names a governed identifier outright.

    FAIL-CLOSED EVERYWHERE ELSE, deliberately. Only the plain-redirect shape
    is analysable by target token. A segment carrying any OTHER write marker
    (``tee``, ``cp``/``mv``, ``sed -i``, an interpreter payload, ``xargs``)
    keeps point 4's original broad behaviour, because this hook cannot cheaply
    tell ``tee $p`` from ``tee /tmp/x``. Narrowing those needs argument
    parsing per marker family; it is not attempted here, and a future
    narrowing must add them one measured family at a time.
    """
    bound = _governed_bound_variables(segments)
    for segment in segments:
        if not _has_write_marker(segment):
            continue
        if not _has_redirect_marker(segment):
            return True  # unanalysable marker family -- fail closed
        without_redirect = _BARE_REDIRECT_RE.sub(
            " ", _SAFE_REDIRECT_RE.sub(" ", segment)
        )
        if _has_write_marker(without_redirect):
            return True  # a second, unanalysable marker rides along
        target = _redirect_target_token(segment)
        if not target:
            return True  # cannot resolve the destination -- fail closed
        if _mentions_governed_identifier(target):
            return True
        if any(deref in bound for deref in _VAR_DEREF_RE.findall(target)):
            return True
    return False


def _has_xargs_pipe_indirection(segments: "list[str]") -> bool:
    """Point 10 (new) -- Review: security-audit-worker, "critical" finding,
    genuinely new root cause distinct from the command-substitution/quote
    bug above. Confirmed live:
    ``echo CLAUDE.md | xargs -I{} sh -c "echo pwned > {}"`` and
    ``echo CLAUDE.md | xargs tee`` both slipped past the per-segment model
    (point 3): ``xargs`` reads the governed identifier from stdin AT RUNTIME
    and substitutes it into a DIFFERENT segment's argument (``{}``, or the
    trailing positional a bare ``xargs tee``/``xargs cp`` appends) -- the
    segment carrying the actual write marker or interpreter never contains
    the literal identifier string, so ``_mentions_governed_identifier`` is
    False for that segment and it is skipped before any marker is even
    checked. Point 4 (variable-assignment indirection) does not help here;
    this is a pipe, not an assignment.

    Mirrors point 4's WHOLE-COMMAND scope (not segment-scoped) for the same
    reason point 4 is whole-command-scoped: this hook has no way to know
    which later segment ``xargs`` substitutes the piped value into, so any
    segment containing bare ``xargs`` in a command that mentions a governed
    identifier ANYWHERE is denied outright -- deliberate over-denial in the
    safe direction (a harmless ``cat CLAUDE.md | xargs -n1 echo`` denies
    too), consistent with this hook's fail-closed posture on indirection it
    cannot reliably parse (module docstring point 5)."""
    if not any(_mentions_governed_identifier(segment) for segment in segments):
        return False
    return any(_XARGS_RE.search(segment) for segment in segments)


#: Markers that prove a segment can actually EXECUTE arbitrary code via an
#: OS-level escape hatch reachable from an interpreter with no textual write
#: marker of its own (``os.system(``, ``subprocess.*(...)``, ``shell=True``,
#: ``eval(``/``exec(``) -- used only by ``_is_interpreter_read_shape`` below,
#: to keep that carve-out from misclassifying a payload that could still
#: write via one of these as a read.
_OS_EXEC_RE = re.compile(
    r"\bos\.system\(|\bsubprocess\.(run|call|Popen|check_call|check_output)\("
    r"|shell\s*=\s*True|\beval\(|\bexec\("
)


def _has_os_exec_marker(text: str) -> bool:
    return bool(_OS_EXEC_RE.search(text))


#: The one write shape whose sink is analysable inside an interpreter payload:
#: a write-mode ``open(<literal>, ...)``. Everything else -- every other marker
#: family, a non-literal path, a ``.write*`` not chained directly onto such an
#: open -- keeps the segment unanalysable and fails closed. See
#: ``_interpreter_write_sinks_are_ungoverned`` for why the analysable set is
#: this small and must stay so.
_OPEN_CALL_RE = re.compile(r"\bopen\s*\(")
_WRITE_MODE_RE = re.compile(r"['\"][^'\"]*[wax][^'\"]*['\"]")
_LITERAL_FIRST_ARG_RE = re.compile(r"\A\s*(['\"])(?P<path>[^'\"]*)\1\s*(?:,|\Z)")
_TRAILING_WRITE_CALL_RE = re.compile(r"\A\s*\.\s*write(?:_text|_bytes)?\s*\(")


def _open_call_spans(segment: str) -> "list[tuple[int, int, str]]":
    """Every ``open(`` call in ``segment`` as ``(start, end, args)``, where
    ``end`` is one past the call's matching close paren and ``args`` is the
    raw argument text. Depth-counted rather than regex-matched: an argument
    list can itself contain parens (``open(str(p), 'w')``), and a regex that
    stops at the first ``)`` would truncate the mode and read a write as a
    read. A call whose paren never closes is skipped, so a truncated payload
    contributes no analysable span and the caller falls back to closed."""
    spans: "list[tuple[int, int, str]]" = []
    for match in _OPEN_CALL_RE.finditer(segment):
        depth = 0
        i = match.end() - 1
        while i < len(segment):
            if segment[i] == "(":
                depth += 1
            elif segment[i] == ")":
                depth -= 1
                if depth == 0:
                    spans.append((match.start(), i + 1, segment[match.end():i]))
                    break
            i += 1
    return spans


def _interpreter_write_sinks_are_ungoverned(segment: str) -> bool:
    """True only when EVERY write in an interpreter payload is an analysable
    literal-path ``open()`` in a write mode and none of those paths names a
    governed surface.

    PORTED FROM THE ENGINE, deliberately, replacing a wider local attempt.
    This file is the doctrine-plane reference for
    ``coordinator_core.bash_guards.guard_doctrine_surface_bash_write``, which
    is the registered implementation; the two must not answer the same
    question differently.

    The earlier local version tried to resolve each write's sink through
    payload variable bindings and a chained-receiver walk -- effectively
    dataflow over unparsed interpreter text, which module docstring point 5
    exists to forbid. Review found five holes across two rounds, three of
    them regressions that OPENED governed writes the pre-narrowing code had
    denied: a trailing reassignment defeated last-write-wins binding
    (``p='<gov>'; open(p,'w').write('x'); p='/tmp/safe'``), ``os.write`` was
    read as a benign handle call, and Ruby's ``File.write('<gov>', ...)``
    class method was mistaken for a file handle. Analysing less is what makes
    this sound: no bindings, no receiver walk, no dataflow.

    FAIL-CLOSED EVERYWHERE ELSE. Only the adjacent
    ``open(<literal>, <write mode>)`` shape -- optionally chained into
    ``.write()``/``.write_text()``/``.write_bytes()`` -- is analysed. A
    write-mode ``open()`` whose path is not a string literal is unresolvable
    and declines, as does any write marker left standing once the analysable
    opens are blanked out: a redirect, ``tee``, ``sed -i``, ``.write_text``
    on a ``Path``, or ``.write(`` on a name bound earlier. Widening this to a
    bound file object needs dataflow this guard does not have and must not
    fake.

    READS ARE NOT SINKS. A read-mode ``open('<governed>')`` is left standing
    on purpose: reading a governed surface is exactly the shape this
    narrowing exists to stop denying."""
    blanked = list(segment)
    analysable = False
    for start, end, args in _open_call_spans(segment):
        if "," not in args or not _WRITE_MODE_RE.search(args[args.find(",") + 1:]):
            continue  # read-mode open -- not a sink, leave it standing
        literal = _LITERAL_FIRST_ARG_RE.match(args)
        if literal is None:
            return False  # write target is not a literal -- unresolvable
        if _mentions_governed_identifier(literal.group("path")):
            return False  # the write names a governed surface
        analysable = True
        stop = end
        chained = _TRAILING_WRITE_CALL_RE.match(segment[end:])
        if chained is not None:
            stop = end + chained.end()
        for i in range(start, stop):
            blanked[i] = " "
    if not analysable:
        return False
    return not _has_write_marker("".join(blanked))



def _is_interpreter_read_shape(segment: str) -> bool:
    """MEASURED FALSE POSITIVE FIX -- a read-only command was denied purely
    because a governed filename appeared inside a QUOTED Python string
    literal (e.g. ``python3 -c "print('reads CLAUDE.md')"``): the bare
    presence of an interpreter marker (``python3``) in the same segment as a
    governed-identifier mention was, by module docstring point 3/5's original
    design, ALWAYS enough to deny -- "an interpreter payload can write a
    file with no textual trace of a write marker at all, so the interpreter
    marker alone is treated as cannot-prove-a-read". That posture is kept
    for every OTHER indirection marker (``eval``, ``xargs``, a ``sh -c``
    subshell, bare command substitution) -- this carve-out narrows ONLY the
    bare-interpreter-invocation case, and only when every other signal this
    hook can cheaply check says "read":

      - the segment's own command token is one of the four interpreters
        (``python``/``python3``/``perl``/``ruby``/``node``) -- a mention
        reached via a DIFFERENT command piping into an interpreter, or a
        nested ``sh -c "python3 ..."``, does not qualify (stays subject to
        the existing, unnarrowed handling);
      - no write marker anywhere in the segment (``_has_write_marker`` --
        catches ``open(...,'w')``, ``.write(``/``.write_text(``, ``tee``,
        ``sed -i``, ``cp``/``mv``, ``curl -o``, every other point-3 write
        primitive, on the RAW unstripped text, so a write hidden inside a
        quoted -c payload is still caught exactly as before);
      - no OS-exec escape hatch (``_has_os_exec_marker`` -- ``os.system(``,
        ``subprocess.*(``, ``shell=True``, ``eval(``/``exec(`` -- a payload
        that could shell out to write with no textual write marker of its
        own);
      - no ``eval``/``xargs`` marker (the two remaining indirection markers
        an interpreter segment could still smuggle);
      - the governed-identifier mention does NOT survive
        ``_strip_quoted_spans`` -- i.e. it appears ONLY inside a quoted span
        (a Python string literal nested inside the shell's own quoting of
        the ``-c`` argument), never as a bare path operand. A bare mention
        (``python3 fix_doctrine.py CLAUDE.md``) is real evidence the file is
        an operand and stays denied;
      - the segment is NOT a ``-m <module>`` invocation. REGRESSION FOUND
        DURING THIS FIX (``test_deny_lookalike_grant_module_name_does_not_
        match``): without this exclusion, ANY ``python3 -m <arbitrary
        module>`` invocation whose only mention is quoted content -- not
        only the one recognised, known-safe grant CLI
        (``_is_claude_md_grant_read_shape``, already checked earlier in the
        caller's carve-out chain) -- would be silently treated as read-shape
        too, including a deliberate lookalike module name this hook must
        keep denying. A ``-m`` invocation is exactly the "opaque CLI, must
        be explicitly recognised by name" shape point 9 already exists for;
        this carve-out covers only the OTHER interpreter shape (``-c``/a
        script file), where no such recognised-CLI mechanism exists at all.

    Every existing true-positive regression test
    (``test_deny_interpreter_write_mode_open_on_claude_md``,
    ``test_deny_interpreter_payload_writing_governed_surface``,
    ``test_deny_genuine_interpreter_write_to_governed_surface_still_blocked``)
    carries an explicit write marker in the same segment, so
    ``_has_write_marker`` alone already keeps every one of them denying --
    this carve-out never reaches the quoted-span check for any of them."""
    token = _segment_command_token(segment)
    if token is None:
        return False
    if _command_token_basename(token) not in _PYTHON_BASENAMES and _command_token_basename(
        token
    ) not in ("perl", "ruby", "node"):
        return False
    if _python_dash_m_module(segment) is not None:
        return False
    if _has_write_marker(segment) and not _interpreter_write_sinks_are_ungoverned(segment):
        return False
    if _has_os_exec_marker(segment):
        return False
    if _EVAL_RE.search(segment) or _XARGS_RE.search(segment):
        return False
    return not _mentions_governed_identifier(_strip_quoted_spans(segment))


def is_denied_bash_write(cmd: str) -> bool:
    """The whole predicate, isolated from stdin/exit-code plumbing so it is
    directly unit-testable. Returns True (deny) iff:

      (a) some top-level segment mentions a governed identifier AND that
          same segment contains a write or indirection marker (point 3), or
      (b) some segment is a variable assignment whose value mentions a
          governed identifier, AND the whole command contains a write
          marker somewhere (point 4).

    ...EXCEPT that a segment satisfying the point-7 git carve-out
    (``_is_git_read_shape``) cannot deny under (a): a content-safe ``git``
    subcommand does not write working-tree files, so a governed identifier
    in its commit message or pathspec is not a write. The same applies to a
    segment recognised as one of the ``ceremony.scoped_git_commit`` wrapper
    basenames (``_is_commit_wrapper_read_shape`` -- see point 7's "SCOPED-
    COMMIT WRAPPER RECOGNITION"), and to a segment recognised as the
    ``coordinator_core.session.claude_md_grant`` CLI
    (``_is_claude_md_grant_read_shape`` -- see point 9): that CLI's write
    target is its own grant record, never a governed doctrine surface, so a
    governed filename inside its (data-only) note argument is not a write
    either -- unless a real write marker also sits outside its quoted
    arguments in that same segment, which still denies.

    A bare governed-identifier mention with no marker in reach, or a
    marker with no governed-identifier mention in reach, is never enough
    on its own -- see module docstring points 2 and 6."""
    if not _mentions_governed_identifier(cmd):
        return False

    segments = _split_top_level_segments(cmd)

    # Point 4's assignment-indirection scan is a shell-only concept ("a
    # variable is assigned a governed path, then dereferenced by a later
    # segment's write"). Scanning it over the RAW segments misfires on a
    # heredoc BODY: a Python source line like `add = """... CLAUDE.md
    # ..."""` inside `python3 - <<'PY' ... PY` is data on stdin, never
    # shell-parsed, but `_ASSIGN_RE` matches its `add =` prefix as though it
    # were a live `NAME=value` shell assignment -- observed live, denying a
    # heredoc whose body happened to contain both a governed-name mention in
    # one string literal and an unrelated `.write_text(` call writing a
    # DIFFERENT (non-governed) file in another. Heredoc-stripping this scan
    # (and only this scan) removes that false trigger while leaving point
    # 3's per-segment loop below -- which still runs over the RAW,
    # unstripped segments -- fully able to catch a REAL write inside a
    # heredoc body, e.g. `open('CLAUDE.md','w').write(...)` on its own
    # body line: that line still mentions the identifier AND carries the
    # write-mode-open marker in the SAME (unstripped) segment, so point 3
    # denies it exactly as before. See module docstring points 4/5 and the
    # dispatch brief's second reproduction.
    stripped_cmd = _strip_heredoc_bodies(cmd)
    stripped_segments = _split_top_level_segments(stripped_cmd)
    if _has_var_assignment_indirection(
        stripped_segments
    ) and _assignment_indirection_reaches_a_write(stripped_segments):
        return True

    # Point 4's companion for the one case the strip above cannot cover: a
    # heredoc feeding an interpreter that takes its PROGRAM from stdin. There
    # the body is executable source, so an assign-then-write-through-the-name
    # payload is a real indirected write that neither point 3 (identifier and
    # marker land on different body lines) nor the stripped point-4 scan sees.
    if _has_stdin_program_var_write(cmd):
        return True

    if _has_xargs_pipe_indirection(segments):
        return True

    for segment in segments:
        if not _mentions_governed_identifier(segment):
            continue
        if _is_git_content_mutation(segment):
            return True
        if (
            _is_git_read_shape(segment)
            or _is_commit_wrapper_read_shape(segment)
            or _is_claude_md_grant_read_shape(segment)
            or _is_interpreter_read_shape(segment)
        ):
            continue
        if _has_write_marker_for_point3(segment) or _has_indirection_marker(segment):
            return True

    return False


def _looks_commit_shaped(cmd: str) -> bool:
    """True iff some top-level segment of a DENIED command is a ``git
    commit``/``git add`` invocation or one of the scoped-commit wrapper
    basenames -- used only to decide whether ``_compose_deny_message`` owes
    the reader the commit-specific hint below. A denied commit-shaped command
    was denied for a real reason (an actual redirect/tee/interpreter marker
    outside its message), not because committing is itself disallowed, so
    the hint points at the pathspec form rather than repeating "use
    Write/Edit" advice that does not apply to a commit at all."""
    for segment in _split_top_level_segments(cmd):
        if _git_subcommand(segment) in ("commit", "add"):
            return True
        if _is_commit_wrapper_command(segment):
            return True
    return False


def _looks_quoted_content_shaped(cmd: str) -> bool:
    """True iff every top-level segment mentioning a governed identifier
    does so ONLY inside a quoted span -- the identifier never appears as a
    bare path operand anywhere in the command. Used only to decide whether
    ``_compose_deny_message`` owes the reader the "use Write/Edit on one of the four
    files" remedy: that remedy presumes the governed file itself is the
    write target, which is false by construction here -- the mention is
    prose inside a content argument (a finding, a commit-message excerpt)
    whose real destination is a different, non-governed path, so the only
    actionable remedy is editing that real destination directly. Mirrors
    ``_looks_commit_shaped``'s "diagnostic only, never re-derives the deny
    verdict" role."""
    mentioning_segments = [
        segment
        for segment in _split_top_level_segments(cmd)
        if _mentions_governed_identifier(segment)
    ]
    if not mentioning_segments:
        return False
    # A QUOTED mention can still be the redirect's own destination
    # (`echo x > "CLAUDE.md"`). That denies correctly on the point-3 path,
    # but it is NOT this shape: the remedy sentence below presumes the real
    # destination is some other, non-governed path, and here it is the
    # governed file itself. Emitting the quoted-content prose for it tells
    # the operator "the governed name is quoted content, not a write
    # target" about a command whose write target is exactly that governed
    # name -- a message that contradicts the block it is explaining. Fall
    # through to the default shape, which names the correct remedy.
    for segment in mentioning_segments:
        target = _redirect_target_token(segment)
        if target and _mentions_governed_identifier(target):
            return False
    return all(
        not _mentions_governed_identifier(_strip_quoted_spans(segment))
        for segment in mentioning_segments
    )


def _compose_deny_message(*, commit_shaped: bool = False, quoted_content_shaped: bool = False):
    """The pure composer, isolated from stdin/exit-code plumbing so a
    parameter sweep can call it directly per shape. Three shapes name three
    distinct, non-overlapping escape hatches (a commit-shaped denial names
    the pathspec form; a quoted-content-shaped denial names the direct Edit
    fix; the default shape offers both the Write/Edit and the Edit-direct
    remedies since this hook cannot always tell which applies). The SINK-
    based classification rationale and the full carve-out prose relocated
    to `_WIKI_ANCHOR` -- see this hook's relocation fragment
    (state/relocations/guard-message-cap/guard-doctrine-surface-bash-write.py.md)."""
    if commit_shaped:
        prose = (
            "BLOCKED: this looks commit-shaped, but a write marker sits "
            "outside the message. Use the pathspec form, not Write/Edit."
        )
    elif quoted_content_shaped:
        prose = (
            "BLOCKED: the governed name is quoted content, not a write "
            "target. Edit the real destination; see "
            "findings-self-persist-sentinel.md."
        )
    else:
        prose = (
            "BLOCKED: this Bash command writes a governed doctrine "
            "surface. If the real target is one of the four files, use "
            "Write or Edit."
        )
    return compose(prose, anchor=_WIKI_ANCHOR)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # nothing to classify -- fail open

    if data.get("tool_name") not in _COMMAND_TOOL_NAMES:
        return 0

    tool_input = data.get("tool_input")
    cmd = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(cmd, str) or not cmd:
        return 0  # no command text -- nothing to classify

    if not is_denied_bash_write(cmd):
        return 0

    message = _compose_deny_message(
        commit_shaped=_looks_commit_shaped(cmd),
        quoted_content_shaped=_looks_quoted_content_shaped(cmd),
    )
    # Latent-bug fix: sys.stderr.write text-mode-translates LF->CRLF on
    # Windows, breaking byte-fidelity with the bash oracle's stderr output
    # -- the same class of bug as _message_envelope.emit's CHANNEL_STOP fix
    # (review-integrator Finding 2), found here mid-task since this hook
    # bypasses `emit()` and writes `render()`'s output directly.
    sys.stderr.buffer.write((render(message) + "\n").encode("utf-8"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
