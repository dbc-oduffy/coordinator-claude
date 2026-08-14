"""Phase-4 personal-data audit — the DoE→OSS publish boundary's last-line scrub for
operator identity leaking into the public coordinator-claude mirror.

Python port of the `perl_match` / `perl_any` / `perl_has_disallowed` machinery and
the Phase-4 audit loop in `setup/publish.sh` (grep `perl_match` there for the shell
original). The PCRE-to-`re` translation is faithful for every construct the ported
patterns actually use — `\\b` word boundaries, `\\s`/`\\S` classes, `(?!...)`
negative lookahead, and `$` end anchors are all directly supported by Python `re`;
none of the ported patterns rely on PCRE-only features (possessive quantifiers,
atomic groups, `\\K`, `\\p{...}` Unicode properties, or variable-width lookbehind),
so no semantic gap is introduced by the port.

SECURITY-LOAD-BEARING: this module's job is to stop operator-identity leakage into
a public mirror. Its central invariant is FAIL-CLOSED — an allowlist regex that has
been silently weakened (e.g. by an unescaped `|` in a token producing an empty
alternation branch) must raise `AuditError` rather than let files publish clean.
`check_scrub_canary` is the mechanism: before trusting an `allow_regex` to suppress
any bare-identifier hit, it must FAIL to match a fixed literal canary string that no
real token can legitimately match. If the canary matches, the allow_regex has gone
pathologically broad and the audit refuses to render a verdict.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

# The literal canary string the audit's allow_regex must NEVER match. Mirrors
# publish.sh's `_scrub_canary='xxpercolatescrubcanarymustnotmatchxx'`.
SCRUB_CANARY = "xxpercolatescrubcanarymustnotmatchxx"

# Pedagogical placeholders the cross-platform home-path patterns must NOT flag
# (mirrors publish.sh's `_placeholder_alt`). Real-looking usernames still flag.
_PLACEHOLDER_ALT = (
    "yourname|YourName|your-name|your-username|YourUsername|username|USERNAME|"
    "user|USER|name|NAME|you|operator|placeholder|example|EXAMPLE|foo|bar|baz|"
    "alice|bob|dev|op|me|runner|someone|someuser|<[A-Za-z0-9_-]+>"
)

# Persona-name belt-and-braces patterns (publish.sh `_review_pat_persona_names`).
# The two-letter initialism persona is deliberately omitted — a 2-char token
# false-positives on hyphenated axis labels and similar initialisms; the
# persona-name transform + CI handle it instead. (It is not spelled here for
# the same reason the entries below are fragment-split.)
#
# Each name is ASSEMBLED FROM FRAGMENTS and must not be "simplified" back into a
# contiguous literal. This module publishes into the public mirror, so a whole
# persona name in these bytes is itself the leak the patterns exist to find —
# and it shipped that way until 2026-08-07, invisible to the mirror's identity
# gate because that gate's alphanumeric lookbehind read the `b` of the preceding
# `\b` escape as an intra-word character. The gate now catches that class; this
# split is what stops the byte from being written in the first place. A
# `substitute` store rule is deliberately NOT the fix: it would rewrite the
# vocabulary tables and fixtures that legitimately assert on these tokens.
def _persona(*fragments: str) -> str:
    return rf"\b{''.join(fragments)}\b"


PERSONA_NAME_PATTERNS: tuple[str, ...] = (
    _persona("Pat", "rik"),
    _persona("S", "id"),
    _persona("Came", "lia"),
    _persona("Pa", "lí"),
    _persona("F", "ru"),
    _persona("Zo", "lí"),
)


class AuditError(Exception):
    """Raised when the Phase-4 audit cannot render a trustworthy verdict.

    Mirrors publish.sh's `local_audit_errored=true` path: a scan failure or a
    pathologically-broad allow_regex both abort with "verdict UNKNOWN" rather
    than silently reporting clean.
    """


@dataclass
class PercolateIdentity:
    """The EXPECTED / REVIEW / ALLOW token arrays sourced from `.percolate-identity`.

    Field names correspond to PERSONAL_EXPECTED_PATTERNS / PERSONAL_REVIEW_PATTERNS
    / PERSONAL_ALLOW_TOKENS in the shell original.
    """

    expected: list[str] = field(default_factory=list)
    review: list[str] = field(default_factory=list)
    allow: list[str] = field(default_factory=list)


def parse_percolate_identity(path: str | Path) -> PercolateIdentity:
    """Parse a `.percolate-identity` file's three bash arrays without executing it.

    The shell original sources the file as bash code (after ownership/mode
    checks — see publish.sh:154-174); this port never executes it, only reads
    the three known array literals. Full-line `#` comments inside an array body
    are stripped before tokenizing; inline quoting is handled via `shlex.split`.
    """
    text = Path(path).read_text(encoding="utf-8")

    def _extract(array_name: str) -> list[str]:
        match = re.search(rf"{array_name}=\((.*?)\n\)", text, re.S)
        if not match:
            return []
        body_lines = [
            line for line in match.group(1).splitlines() if not line.strip().startswith("#")
        ]
        return shlex.split("\n".join(body_lines))

    return PercolateIdentity(
        expected=_extract("PERSONAL_EXPECTED_PATTERNS"),
        review=_extract("PERSONAL_REVIEW_PATTERNS"),
        allow=_extract("PERSONAL_ALLOW_TOKENS"),
    )


def _xplatform_patterns() -> list[str]:
    """Cross-platform home-path SHAPE catchers (publish.sh `_review_pat_xplatform`).

    Catches Windows-native, Git-Bash-POSIX, Linux, and macOS home-path shapes
    regardless of the auditing machine's own OS — a Mac-run audit still flags a
    Windows-flavored leak sync'd over from another operator's machine.
    """
    neg = rf'(?!(?:{_PLACEHOLDER_ALT})[\\/"\'\s]|(?:{_PLACEHOLDER_ALT})$)'
    return [
        rf"[Cc]:[\\/]+[Uu]sers[\\/]+{neg}[A-Za-z][A-Za-z0-9._-]+",
        rf"/c/[Uu]sers/{neg}[A-Za-z][A-Za-z0-9._-]+",
        rf"/home/{neg}[A-Za-z][A-Za-z0-9._-]+",
        rf"/Users/{neg}[A-Za-z][A-Za-z0-9._-]+",
    ]


def _win_home_patterns(home: str) -> list[str]:
    """MSYS/Git-Bash-style `$HOME` (e.g. `/c/Users/foo`) → Windows-path literal
    patterns, both raw (`C:\\Users\\foo`) and JSON-escaped (`C:\\\\Users\\\\foo`)
    forms — mirrors publish.sh:511-516's `_home_rest` backslash-doubling dance,
    expressed directly as the two literal text shapes it is built to match.
    """
    match = re.match(r"^/([a-zA-Z])/(.+)$", home)
    if not match:
        return []
    drive = match.group(1).upper()
    segments = [re.escape(segment) for segment in match.group(2).split("/")]
    raw = f"{drive}:" + r"\\" + r"\\".join(segments)
    json_escaped = f"{drive}:" + r"\\\\" + r"\\\\".join(segments)
    return [json_escaped, raw]


def _drive_letter_patterns(drive: str) -> list[str]:
    """Bare-drive-letter leakage patterns (publish.sh:532-533) — JSON-escaped
    then raw, matching a secondary install drive with no subpath context.
    """
    return [f"{drive}:" + r"\\\\", f"{drive}:" + r"\\"]


def build_review_patterns(
    identity: PercolateIdentity, home: str | None = None, script_dir: str | None = None
) -> list[str]:
    """Compose the full REVIEW_PATTERNS list: generic $HOME/drive-letter derivation
    + cross-platform shape catchers + persona names + operator-specific tokens.

    Mirrors publish.sh:501-592. `home`/`script_dir` default to empty (not `$HOME`/
    `$SCRIPT_DIR`) so this function is deterministic for tests — callers doing a
    real publish pass `os.environ["HOME"]` and the resolved script directory
    explicitly.
    """
    home = home or ""
    script_dir = script_dir or ""
    patterns: list[str] = []

    home_win_match = re.match(r"^/([a-zA-Z])/(.+)$", home)
    if home_win_match:
        patterns.extend(_win_home_patterns(home))
    elif home:
        patterns.append(home)

    sd_match = re.match(r"^/([a-zA-Z])/", script_dir)
    home_drive_match = re.match(r"^/([a-zA-Z])/", home)
    sd_drive = sd_match.group(1).upper() if sd_match else None
    home_drive = home_drive_match.group(1).upper() if home_drive_match else None
    if sd_drive and sd_drive != home_drive:
        patterns.extend(_drive_letter_patterns(sd_drive))

    patterns.extend(_xplatform_patterns())
    patterns.extend(PERSONA_NAME_PATTERNS)
    patterns.extend(identity.review)
    return patterns


def escape_token(token: str) -> str:
    """Escape every non-word character in `token` for literal regex matching.

    Mirrors publish.sh:1987's `perl -pe 's/(\\W)/\\\\$1/g'` — escapes anything
    outside `[A-Za-z0-9_]`, not just regex metacharacters, so the translation
    is character-class-faithful rather than relying on `re.escape`'s narrower
    "only escape what `re` treats specially" behavior.
    """
    return "".join(char if re.match(r"\w", char) else "\\" + char for char in token)


def build_allow_regex(tokens: list[str]) -> str:
    """Build the allow_re alternation from pre-escaped tokens (publish.sh:1984-1998).

    Each token is escaped via `escape_token` BEFORE joining with `|` — joining
    raw tokens first would let a token containing an unescaped `|` (or an empty
    token) widen the alternation to an empty branch that matches everything,
    which is exactly the failure mode `check_scrub_canary` exists to catch.
    """
    escaped = [escape_token(tok) for tok in tokens if tok]
    return "|".join(escaped)


def check_scrub_canary(allow_regex: str) -> None:
    """Fail-closed guard: raise `AuditError` if `allow_regex` matches the canary.

    Mirrors publish.sh:2009-2021. A sane allow_re, built from real identity
    tokens, must not match `SCRUB_CANARY` — a string containing no allowlisted
    token. If it does, the allow_re has an empty/catch-all alternation branch
    (bare `|`, empty entry, or an unescaped metacharacter) and would silently
    suppress every REVIEW hit, letting personal data pass the scrub. An empty
    allow_regex (no tokens configured) cannot match anything and is not a
    canary failure — it is the "bare-identifier check disabled" case.
    """
    if not allow_regex:
        return
    if re.search(allow_regex, SCRUB_CANARY):
        raise AuditError(
            "allow_re matched the scrub canary — allowlist is pathologically "
            "broad and rejects nothing. Refusing to trust the scrub — verdict "
            "UNKNOWN. Inspect the allowlist tokens/slugs before publishing."
        )


def bare_identifier(allow_tokens: list[str]) -> str | None:
    """Derive the bare identifier to scan for from the first PERSONAL_ALLOW_TOKENS
    entry's leading alphabetic run, lowercased (publish.sh:1957-1961).

    E.g. `['foo-delphi', 'Foo Bar']` → `'foo'`. Returns `None` when there are no
    allow tokens or the first token has no leading alphabetic run.
    """
    if not allow_tokens:
        return None
    match = re.match(r"^([a-zA-Z]+)", allow_tokens[0])
    return match.group(1).lower() if match else None


def scan_review_patterns(text: str, patterns: list[str]) -> list[str]:
    """Return the subset of `patterns` that match at least one line of `text`.

    Line-by-line, mirroring `perl -sne '$f=1 if /$pat/; END{exit !$f}'` — the
    shell original scans per-line via `perl -ne`, so a pattern spanning a line
    break would never match there either; this preserves that behavior rather
    than doing a whole-file `re.search` which could diverge on multi-line input.
    """
    hits = []
    lines = text.splitlines()
    for pat in patterns:
        try:
            compiled = re.compile(pat)
        except re.error as exc:
            raise AuditError(f"REVIEW pattern failed to compile: {pat!r}: {exc}") from exc
        if any(compiled.search(line) for line in lines):
            hits.append(pat)
    return hits


def scan_bare_identifier(text: str, bare_ident: str, allow_regex: str) -> bool:
    """Bare-identifier disallowed-occurrence check (publish.sh:1962-2039 collapsed).

    Returns True (REVIEW) iff `bare_ident` occurs in `text` on at least one line
    that is NOT covered by `allow_regex`. Runs `check_scrub_canary` first — a
    poisoned allow_regex must abort before it can suppress a real hit.
    """
    check_scrub_canary(allow_regex)
    ident_re = re.compile(r"\b" + re.escape(bare_ident) + r"\b")
    lines = text.splitlines()
    matching_lines = [line for line in lines if ident_re.search(line)]
    if not matching_lines:
        return False
    allow_re = re.compile(allow_regex) if allow_regex else None
    for line in matching_lines:
        if allow_re is None or not allow_re.search(line):
            return True
    return False


def audit_file(
    path: str | Path,
    review_patterns: list[str],
    bare_ident: str | None = None,
    allow_regex: str = "",
) -> list[str]:
    """Audit a single file, returning `"REVIEW [...] <path>"`-shaped finding lines.

    Mirrors the per-file body of the publish.sh Phase-4 loop (:1933-2041).
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    findings = [f"REVIEW  [{pat}]  {path}" for pat in scan_review_patterns(text, review_patterns)]
    if bare_ident and scan_bare_identifier(text, bare_ident, allow_regex):
        findings.append(f"REVIEW  [bare {bare_ident}]  {path}")
    return findings


def audit_files(
    paths: list[str | Path],
    identity: PercolateIdentity,
    native_slugs: list[str] | None = None,
    home: str | None = None,
    script_dir: str | None = None,
) -> list[str]:
    """Run the full Phase-4 audit over `paths`, returning all finding lines.

    Mirrors publish.sh's Phase-4 loop (:1925-2057) end to end: derives
    REVIEW_PATTERNS, builds the bare-identifier allow_regex from
    `identity.allow` + `native_slugs`, runs the scrub-canary guard ONCE per
    call (matching the shell's per-target `_canary_checked` gate — the
    allow_regex is target-constant, not per-file), then scans every file.
    Raises `AuditError` — the caller's "verdict UNKNOWN" path — on any scan
    failure or a poisoned allow_regex, rather than returning a partial/clean
    result.
    """
    review_patterns = build_review_patterns(identity, home=home, script_dir=script_dir)
    bare_ident = bare_identifier(identity.allow)
    allow_regex = ""
    if bare_ident:
        allow_regex = build_allow_regex(list(identity.allow) + list(native_slugs or []))
        check_scrub_canary(allow_regex)

    findings: list[str] = []
    for path in paths:
        findings.extend(
            audit_file(path, review_patterns, bare_ident=bare_ident, allow_regex=allow_regex)
        )
    return findings
