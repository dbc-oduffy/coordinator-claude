r"""check-install-doc-payload.py — assert install-doc commands resolve in the
published tree.

Why this exists: the klabauter row-1 P0 (state/audits/2026-08-05-klabauter-
scrub-and-gate-both-silent.md's originating incident) shipped `INSTALL.md`
telling every user's first command was `python3 scripts/setup.py`, while
`scripts/` was in none of the publish rows — every existing gate validated
its own table (the publish-targets allowlist, the identity scan, the leak
scan); none of them ever opened the doc a user actually reads and confirmed
the doc's own commands resolve against the tree that gets published. This
module is that missing check.

MECHANISM (the load-bearing design choice)
    This gate does NOT carry a hardcoded list of "the installer lives at
    scripts/setup.py" — a copy of that claim is exactly the shape of check
    that missed the original P0 (the doc said one thing, the publish rows
    said another, nothing compared them). Instead it PARSES the install
    docs themselves for the commands they tell a reader to run, extracts
    the script-shaped path each command invokes, and asserts that path
    exists in the tree under test. A doc edit that references a new file
    fails this gate until that file ships — no gate edit required.

    Extraction only looks inside Markdown code spans — fenced ``` blocks
    (every line) and inline single-backtick spans (`` `like this` ``) — on
    the theory that a doc author always code-formats a command meant to be
    typed, and scanning prose too would manufacture false positives from
    incidental path-shaped words. Within a span, tokens immediately after a
    `-c`/`-m` interpreter flag are skipped (inline code / module names, not
    file paths); flag tokens (`-i-am-agent` etc.) and anything containing
    `<`/`>` (placeholders) are skipped; anything ending in one of the
    tracked script extensions (`.py .cmd .ps1 .sh .bat`, case-insensitive)
    and not absolute (no leading `/` and no drive-letter root such as
    `C:` followed by a separator) is a candidate relative path, checked
    against the tree with backslashes normalized to a forward slash so a
    Windows-spelled command (`python scripts` + separator + `setup.py`) is held to the
    identical existence standard as its POSIX twin — deliberately: this
    gate does not pair POSIX/Windows commands up or treat either as
    optional, it just checks every path-shaped token it finds, so a broken
    Windows-only reference fails exactly as loud as a broken POSIX one.

    RESOLUTION of an extracted token depends on whether it carries a
    directory component:
      - PATH-QUALIFIED (`scripts/setup.py`, `bin\\probe.py`) — resolved at
        exactly that path under the tree root, and nowhere else. A doc that
        promises a reader a specific path is held to that path; no
        directory search is attempted, so the original P0 shape (INSTALL.md
        saying `scripts/setup.py` while `scripts/` ships nowhere) still
        fails exactly as before.
      - BARE BASENAME (`validate-references.py`) — a doc naming a script by
        filename alone is not promising a location, so requiring it at the
        tree root would be a false positive against any payload that homes
        its executables in a subdirectory. Such a token resolves against the
        SCRIPT-HOME SET: the tree root, plus the parent directory of every
        path-qualified script reference that the same doc set already makes
        AND that already resolves to a real file.

    That derivation is the load-bearing part, so spell out what it is not:
    the home set is not a hardcoded convention list (`.github/scripts`,
    `bin`, `tools`, ...) — a lucky guess of that shape is the same
    hardcoded-claim smell this module's MECHANISM section rejects, and it
    would silently stop matching the moment a payload picked a different
    layout. It is not the whole tree either: resolving a bare name against
    any directory anywhere would let a genuinely retired filename resolve
    against an unrelated vendored copy and quietly stop catching stale
    install pointers, which is the entire value of this gate. The set is
    exactly the directories the scanned docs THEMSELVES demonstrate are
    executable homes for this payload, evidenced by a working reference —
    typically one or two directories. A broken path-qualified reference
    contributes nothing (it cannot vouch for a directory it does not
    resolve in), so a doc set cannot bootstrap a bogus home directory out
    of its own stale pointers.

    Default doc set is every top-level (non-recursive) `*.md` file in the
    tree under test — the first-five-minutes surface (README, INSTALL,
    AGENTS, CONTRIBUTING, ...) — not a curated filename list, so a newly
    added top-level doc is covered automatically. `--docs` overrides with
    an explicit glob (relative to `--tree`); `--recursive` extends the
    default glob to `**/*.md`.

    FOREIGN-REPO MARKER (`foreign-repo:<repo-name>/<relative-script-path>`)
    A command that legitimately resolves inside a NAMED SIBLING repo, not
    the tree under test, cannot be expressed as a plain relative path — this
    gate resolves every unmarked candidate against `--tree` and nothing
    else, by design. A doc author who needs to say "this path is real, but
    it lives in the other repo you just cloned" marks the token
    `foreign-repo:<repo-name>/<relative-script-path>` (e.g.
    `foreign-repo:claude-klabauter/scripts/setup.py`) inside a code span.
    This is checked for WELL-FORMEDNESS only — a repo-name segment, then a
    relative path ending in one of the tracked script extensions, no `..`
    traversal, no absolute/drive-rooted/drive-relative path, no leading `\`
    or UNC path (`\\host\share\...`), no `<`/`>` placeholder chars — and is
    never resolved against `--tree`; the marker's whole point is
    that the referenced file is NOT expected to exist in the tree under
    test. A malformed marker (empty repo-name segment, a path that escapes
    with `..`, an absolute path, a non-script extension) is still a
    Finding — the marker is not a blanket skip, it is a narrow, checked
    escape hatch. An unmarked path that does not resolve in `--tree` fails
    exactly as before; this section does not change that.

    This is deliberately a DIFFERENT mechanism from the pre-existing
    `<clone-dir>/scripts/setup.py`-style angle-bracket placeholder (see
    `extract_script_paths`'s `<`/`>` skip) that some install docs already
    use for "substitute your own clone path here" — that form is a
    prose-readability placeholder with no repo identity and is invisible to
    this gate by construction (it never becomes a candidate token at all).
    The foreign-repo marker is additive: it does not require migrating any
    existing `<...>`-placeholder command, and both forms are expected to
    keep appearing side by side in the same doc.

    A SECOND, independent check runs over the same doc set: every Markdown
    inline link/image target (`[text](target)` / `![alt](target)`) is
    resolved relative to the LINKING doc's own directory (standard Markdown
    relative-link semantics, not `--tree` — a link in `docs/reference/x.md`
    to `../y.md` means the tree's `docs/y.md`, not `docs/reference/y.md`)
    and asserted to exist (file OR directory — a link to a directory is not
    a missing-file finding). This is why this gate exists as a SEPARATE
    check from the command-span extraction above rather than a widened
    regex on the same pass: a Markdown LINK is not a code span — the
    original gap this closes (`INSTALL.md` linking `docs/reference/install-
    chain-walk.md`, a file `claude-klabauter-toplevel-reference`'s allowlist
    never shipped) went uncaught by the command-extraction pass precisely
    because a plain prose link carries no backticks for it to see.

    Link targets deliberately EXCLUDED from this check, so as not to
    manufacture false positives from patterns this gate cannot verify or
    was never asked to:
      - scheme-having URLs (`https://…`, `mailto:…`, etc.) — external,
        outside the published tree's own file existence by construction.
      - pure same-page anchors (`#section`) — no path component at all.
      - a link target starting with `/` — ambiguous between GitHub's
        repo-root-relative convention and a real filesystem-absolute path;
        deciding which is which is not attempted (see NAMED BLIND SPOT).
      - a `#fragment` suffix on an otherwise-checked target is stripped
        before the existence check (`file.md#section` checks `file.md`
        exists; the anchor's own validity within that file is not verified
        — same "named, not guaranteed" discipline as the rest of this
        module).
      - a target that resolves OUTSIDE `tree_root` (e.g. `../../elsewhere`
        escaping the published subtree entirely) is skipped, not flagged —
        this gate only asserts about the published tree's own contents; it
        has no way to know whether something outside that tree exists, and
        guessing would be exactly the "overclaim past what was verified"
        this module's own docstring says never to do.

NAMED BLIND SPOT (do not overclaim past this)
    A command-shaped reference embedded in prose without any backtick
    formatting is invisible to the COMMAND check — e.g. a sentence that
    just says "run scripts/setup.py" with no code span. In every install
    doc audited for this gate (INSTALL.md, README.md, AGENTS.md,
    CONTRIBUTING.md) every actual runnable command is code-formatted, so
    this has not been observed to matter in practice, but it is a real,
    named gap, not a guarantee.

    For the LINK check specifically: reference-style links (`[text][ref]`
    with a separate `[ref]: target` definition line) are not parsed — only
    the inline `[text](target)` / `![alt](target)` form. Every install doc
    audited for this gate uses inline links exclusively, so this is
    unobserved in practice, same discipline as the command-span gap above:
    named, not silently assumed absent.

WIRING (not performed by this module — see report / docstring below)
    Standalone, importable, independently testable. Intended call site:
    `coordinator/bin/publish.py`'s `dispatch_percolate_pre_ci` guard chain,
    alongside the existing `run_identity_check` call — invoke
    `check_tree(target.dest_dir_root_for_docs, ...)` (the directory that
    actually contains the published INSTALL.md/README.md — for a row whose
    published subtree is not the destination repo root, this is NOT
    `target.dest_dir`, the same directory-resolution trap this module's
    sibling audit (state/audits/2026-08-05-klabauter-scrub-and-gate-both-
    silent.md § Q3) diagnosed for `run_identity_check`) and append to
    `guard_results`/raise via the same `EngineUnavailableError`-shaped path
    `run_identity_check`'s non-zero branch uses, on any non-empty findings
    list. This module does not perform that wiring itself — a parallel
    executor owns `publish.py` for this dispatch.

Spec backlink: state/audits/2026-08-05-klabauter-scrub-and-gate-both-silent.md
Spec backlink: pln-claude-klabauter-oss-release-e-50bd5d
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Sequence

_SCRIPT_EXT_RE = re.compile(r"^[A-Za-z0-9_./\\-]+\.(py|cmd|ps1|sh|bat)$", re.IGNORECASE)
_FLAG_CONSUMING_NEXT = {"-c", "-m"}
_TOKEN_RE = re.compile(r"'[^']*'|\"[^\"]*\"|\S+")
_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")
# Drive-relative Windows form (`C:setup.py`, no separator after the colon):
# resolves against that drive's current directory rather than being purely
# relative, so it must be caught alongside the drive-rooted form above.
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")

# Foreign-repo marker: `foreign-repo:<repo-name>/<relative-script-path>`.
# See module docstring's FOREIGN-REPO MARKER section for the rationale and
# the distinction from the pre-existing `<clone-dir>/...` placeholder form.
_FOREIGN_REPO_PREFIX = "foreign-repo:"
_FOREIGN_REPO_RE = re.compile(r"^foreign-repo:([^/]+)/(.+)$")
_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

# Markdown inline link/image target: `[text](target)` / `![alt](target)`.
# Matches both (the `!` prefix for an image is outside the `[...]` group, so
# this pattern alone covers both forms without a separate image-specific
# regex). `([^)]+)` intentionally does not try to parse a nested paren in
# the target -- none of this repo's own install docs use one; a target
# containing an unescaped `)` is out of scope, same "named, not guessed"
# discipline as the rest of this module.
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")

DEFAULT_DOC_GLOB = "*.md"
RECURSIVE_DOC_GLOB = "**/*.md"


@dataclass(frozen=True)
class Finding:
    """One install-doc reference (a command's script path, or a Markdown
    link target) absent from the tree under test. `kind` distinguishes the
    two check passes in rendered output only -- both are structurally the
    same finding shape (a doc, a line, a referenced path that does not
    resolve)."""

    doc: Path
    lineno: int
    context: str
    missing_path: str
    kind: str = "command"
    searched_dirs: tuple = ()

    def render(self, tree_root: Path) -> str:
        try:
            doc_rel = self.doc.relative_to(tree_root)
        except ValueError:
            doc_rel = self.doc
        if self.kind == "command":
            noun = "command references"
        elif self.kind == "link":
            noun = "link points at"
        else:
            noun = "foreign-repo reference"
        if self.kind == "foreign-repo":
            where = (
                "which is not a well-formed foreign-repo marker "
                "(expected `foreign-repo:<repo-name>/<relative-script-path>`, "
                "no `..` traversal, no absolute path, tracked script extension)"
            )
            return (
                f"{doc_rel}:{self.lineno}: {noun} {self.missing_path!r}, {where}. "
                f"Offending line: {self.context.strip()!r}"
            )
        where = f"which does not exist in the published tree ({tree_root})"
        if self.searched_dirs:
            where = (
                f"which is a bare script name that resolves in none of the "
                f"script-home directories this doc set demonstrates "
                f"({', '.join(self.searched_dirs)}), under {tree_root}"
            )
        return (
            f"{doc_rel}:{self.lineno}: {noun} {self.missing_path!r}, "
            f"{where}. "
            f"Offending line: {self.context.strip()!r}"
        )


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for match in _TOKEN_RE.finditer(text):
        tok = match.group(0)
        if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "'\"":
            tok = tok[1:-1]
        tokens.append(tok)
    return tokens


def extract_script_paths(snippet: str) -> List[str]:
    """Return candidate relative script-file paths referenced in *snippet*.

    Negative-spec: does NOT return absolute paths (leading `/` or a Windows
    drive letter), flag tokens, `-c`/`-m` argument payloads, or placeholder
    tokens containing `<`/`>`.
    """
    tokens = _tokenize(snippet)
    paths: List[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in _FLAG_CONSUMING_NEXT:
            skip_next = True
            continue
        if not tok or tok.startswith("-"):
            continue
        if "<" in tok or ">" in tok:
            continue
        if tok.startswith("/") or _WINDOWS_ABS_RE.match(tok):
            continue
        if _SCRIPT_EXT_RE.match(tok):
            paths.append(tok)
    return paths


def extract_foreign_repo_refs(snippet: str) -> List[str]:
    """Return every `foreign-repo:...`-prefixed token in *snippet*, well-formed
    or not — `parse_foreign_repo_ref` validates each one. Tokenized the same
    way as `extract_script_paths` so a marker sitting alongside other
    command tokens (flags, the interpreter name, ...) on the same code-span
    line is still found.
    """
    return [tok for tok in _tokenize(snippet) if tok.startswith(_FOREIGN_REPO_PREFIX)]


def parse_foreign_repo_ref(tok: str) -> Optional[tuple]:
    r"""Validate a `foreign-repo:...`-prefixed *tok* for well-formedness.

    Returns `(repo_name, relative_path)` (with `relative_path`'s backslashes
    normalized to `/`) when *tok* is well-formed. Returns `("", tok)` when
    *tok* carries the marker prefix but fails validation — malformed, not
    absent, so callers can still raise a Finding for it (this marker is a
    narrow, checked escape hatch, not a blanket skip — see module docstring).
    Returns `None` only if *tok* does not start with the marker prefix at
    all (not expected given `extract_foreign_repo_refs`'s own filter, but
    kept for callers that pass arbitrary tokens).

    Negative-spec: rejects an empty/malformed repo-name segment, a leading
    `/` or `\` (including a UNC path, e.g. a leading `\\host\share\...`), a
    Windows drive-rooted or drive-relative path (a drive letter immediately
    followed by `:`), any `..` path segment, a `<`/`>` placeholder character,
    and any extension outside the tracked script set.
    """
    if not tok.startswith(_FOREIGN_REPO_PREFIX):
        return None
    m = _FOREIGN_REPO_RE.match(tok)
    if not m:
        return ("", tok)
    repo_name, rel_path = m.group(1), m.group(2)
    if not _REPO_NAME_RE.match(repo_name):
        return ("", tok)
    if "<" in rel_path or ">" in rel_path:
        return ("", tok)
    if rel_path.startswith(("/", "\\")) or _WINDOWS_ABS_RE.match(rel_path) or _WINDOWS_DRIVE_RE.match(rel_path):
        return ("", tok)
    normalized = rel_path.replace("\\", "/")
    if any(seg == ".." for seg in normalized.split("/")):
        return ("", tok)
    if not _SCRIPT_EXT_RE.match(normalized):
        return ("", tok)
    return (repo_name, normalized)


def _iter_code_spans(text: str) -> Iterator[tuple]:
    """Yield ``(lineno, snippet, context_line)`` for every Markdown code span.

    Fenced ``` blocks contribute one entry per contained line (snippet ==
    context_line). Inline single-backtick spans contribute one entry per
    span found on a (non-fenced) line, snippet == span content, context_line
    == the full source line (for error-message readability).
    """
    lines = text.splitlines()
    in_fence = False
    for i, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            yield (i, raw_line, raw_line)
            continue
        for m in re.finditer(r"`([^`\n]+)`", raw_line):
            yield (i, m.group(1), raw_line)


def extract_relative_link_targets(text: str) -> List[tuple]:
    """Return `(lineno, target, context_line)` for every Markdown inline
    link/image target in *text* that is a candidate for existence-checking
    -- i.e. not a scheme-having URL, not a pure same-page anchor, and not a
    leading-`/` target (see module docstring's link-check exclusion list).

    Unlike `extract_script_paths`, this scans every line of the doc, not
    just code spans -- a Markdown link is prose-visible by design (that is
    the whole point of the check this closes), so restricting it to code
    spans would reproduce the exact gap being fixed.
    """
    results: List[tuple] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _MD_LINK_RE.finditer(line):
            target = m.group(1).strip()
            # `[text](target "a title")` -- an optional quoted title after
            # the target, separated by whitespace; strip it before checking.
            title_split = re.match(r'^(\S+)(?:\s+"[^"]*")?$', target)
            if title_split:
                target = title_split.group(1)
            if not target or target.startswith("#"):
                continue
            if _SCHEME_RE.match(target):
                continue
            if target.startswith("/"):
                continue
            results.append((lineno, target, line))
    return results


def find_doc_files(
    tree_root: Path,
    doc_glob: str = DEFAULT_DOC_GLOB,
) -> List[Path]:
    return sorted(p for p in tree_root.glob(doc_glob) if p.is_file())


def derive_script_home_dirs(
    tree_root: Path,
    doc_texts: Sequence[str],
) -> List[Path]:
    """Return the directories a BARE script basename may resolve against.

    The tree root, plus the parent of every path-qualified script reference
    in *doc_texts* that resolves to a real file under *tree_root* — i.e.
    the directories this payload's own docs demonstrate it homes
    executables in. See the module docstring's RESOLUTION section for why
    the set is derived rather than a convention list, and why it must stay
    this narrow.

    Negative-spec: a path-qualified reference that does NOT resolve
    contributes no directory (a stale pointer cannot vouch for a location),
    and no directory is added merely because it exists in the tree.
    """
    tree_root = Path(tree_root)
    extra: List[Path] = []
    seen = {tree_root}
    for text in doc_texts:
        for _lineno, snippet, _context in _iter_code_spans(text):
            for raw_path in extract_script_paths(snippet):
                normalized = raw_path.replace("\\", "/")
                if "/" not in normalized:
                    continue
                candidate = tree_root / normalized
                if not candidate.is_file():
                    continue
                parent = candidate.parent
                if parent not in seen:
                    seen.add(parent)
                    extra.append(parent)
    return [tree_root] + sorted(extra, key=lambda p: p.as_posix())


def check_tree(
    tree_root: Path,
    doc_paths: Optional[Sequence[Path]] = None,
    doc_glob: str = DEFAULT_DOC_GLOB,
) -> List[Finding]:
    """Parse install docs under *tree_root* and return every unresolved
    command-referenced path, as :class:`Finding` objects.

    *doc_paths* overrides discovery entirely (used by tests / an explicit
    `--docs` invocation); otherwise every file matched by *doc_glob*
    (default: top-level ``*.md``, non-recursive) is scanned.
    """
    tree_root = Path(tree_root)
    if doc_paths is None:
        doc_paths = find_doc_files(tree_root, doc_glob=doc_glob)

    findings: List[Finding] = []
    loaded: List[tuple] = []
    for doc in doc_paths:
        doc = Path(doc)
        try:
            text = doc.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(
                Finding(doc=doc, lineno=0, context=str(exc), missing_path="<unreadable doc>")
            )
            continue
        loaded.append((doc, text))

    # Derived from the whole doc set before any checking, so a home
    # directory evidenced by one doc serves a bare name cited in another.
    script_homes = derive_script_home_dirs(tree_root, [text for _doc, text in loaded])
    home_labels = tuple(
        (d.relative_to(tree_root).as_posix() if d != tree_root else ".") for d in script_homes
    )

    for doc, text in loaded:
        for lineno, snippet, context in _iter_code_spans(text):
            for raw_tok in extract_foreign_repo_refs(snippet):
                parsed = parse_foreign_repo_ref(raw_tok)
                if parsed is None:
                    continue
                repo_name, _rel_path = parsed
                if not repo_name:
                    findings.append(
                        Finding(
                            doc=doc, lineno=lineno, context=context,
                            missing_path=raw_tok, kind="foreign-repo",
                        )
                    )
                # else: well-formed marker -- accepted, never resolved
                # against tree_root (see module docstring).

            for raw_path in extract_script_paths(snippet):
                normalized = raw_path.replace("\\", "/")
                if "/" in normalized:
                    if (tree_root / normalized).is_file():
                        continue
                    searched: tuple = ()
                else:
                    if any((home / normalized).is_file() for home in script_homes):
                        continue
                    searched = home_labels if len(script_homes) > 1 else ()
                findings.append(
                    Finding(
                        doc=doc, lineno=lineno, context=context,
                        missing_path=raw_path, kind="command",
                        searched_dirs=searched,
                    )
                )

        resolved_tree_root = tree_root.resolve()
        for lineno, target, context in extract_relative_link_targets(text):
            fragment_stripped = target.split("#", 1)[0]
            if not fragment_stripped:
                # The whole target was `something#fragment` with an empty
                # path half (e.g. a stray `()#foo`) -- nothing to resolve.
                continue
            normalized = fragment_stripped.replace("\\", "/")
            candidate = (doc.parent / normalized).resolve()
            try:
                candidate.relative_to(resolved_tree_root)
            except ValueError:
                # Resolves outside the published tree entirely -- out of
                # scope for this gate (§ module docstring's exclusion
                # list), not a finding.
                continue
            if not candidate.exists():
                findings.append(
                    Finding(
                        doc=doc, lineno=lineno, context=context,
                        missing_path=target, kind="link",
                    )
                )
    return findings


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Assert every script-file path referenced by an install doc's "
            "commands exists in the published tree under test. Exit 0: "
            "clean. Exit 1: one or more referenced paths are missing."
        ),
    )
    parser.add_argument(
        "--tree",
        required=True,
        help="Absolute path to the published tree to check (NOT the source tree).",
    )
    parser.add_argument(
        "--docs",
        default=None,
        help=(
            "Glob (relative to --tree) selecting install docs to scan. "
            f"Default: {DEFAULT_DOC_GLOB!r} (top-level only, non-recursive)."
        ),
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help=f"Shorthand for --docs {RECURSIVE_DOC_GLOB!r}.",
    )
    args = parser.parse_args(argv)

    tree_root = Path(args.tree)
    if not tree_root.is_dir():
        print(f"ERROR: --tree path does not exist or is not a directory: {tree_root}", file=sys.stderr)
        return 1

    doc_glob = args.docs
    if doc_glob is None:
        doc_glob = RECURSIVE_DOC_GLOB if args.recursive else DEFAULT_DOC_GLOB

    findings = check_tree(tree_root, doc_glob=doc_glob)

    if not findings:
        print(f"[check-install-doc-payload] clean — every install-doc command resolves in {tree_root}")
        return 0

    print(
        f"[check-install-doc-payload] FAIL — {len(findings)} install-doc command(s) "
        f"reference a path absent from the published tree:",
        file=sys.stderr,
    )
    for finding in findings:
        print(f"  {finding.render(tree_root)}", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    return _main(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
