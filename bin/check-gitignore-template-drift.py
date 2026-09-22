"""check-gitignore-template-drift — flag `~/.claude/.gitignore` rules missing from the template.

WHY THIS EXISTS. `/coordinator:install` Phase 4 derives its `~/.claude/.gitignore` propagation
diff from `templates/dotgitignore.tmpl`, and that derivation is correct — but it only runs when
someone runs a full install. Nothing else ever fires it, so a template rule added between installs
propagates to zero already-installed machines until the next full run. Measured on the box that
AUTHORS the template: nine rules behind on 2026-08-26, fourteen behind on 2026-08-28 — roughly 7
rules/48h on an active box. This gate is the recurring check that beats that drift rate instead of
waiting for the next install. See `state/2026-08-28-machine-b-install-dogfood-friction-log.md` F9
(DoE-claude).

REPORT-ONLY BY DEFAULT. This runs at a cadence, unattended, against the operator's tracked
meta-repo. Without `--apply` it only prints and sets its exit code — it never touches
`~/.claude/.gitignore`. `--apply` appends missing rules (verbatim from the template) and is the
only mutating path; it still never runs `git rm --cached` for you — an ignore rule added for an
already-tracked path is inert until untracked, and deciding to untrack a path is not this script's
call to make unattended. See `docs/wiki/claude-home-tracking-policy.md` (DoE-claude).

TWO ENTRIES ARE REPLACE, NOT APPEND — carried over from Phase 4's own text, because a template-
derived line diff gets both wrong by construction:

  - The auto-memory re-inclusion chain (`projects/**` + its three `!` lines). Git does not descend
    into an excluded directory, so appending the chain BELOW a surviving bare `projects/` line
    never reaches it — the bare line must be deleted, not left in place. `--apply` does this
    substitution; report-only mode instead names the hazard explicitly when it detects it.
  - `/machine-local` must be the bare (unslashed) form: `dir/` matches only a real directory, and
    the settings-home registry path under the claude home becomes a symlink once the migration completes. A live
    file carrying the slashed form has a rule that reads as present and matches nothing.
    `--apply` adds the correct bare form alongside a wrong slashed one (leaving the harmless dead
    line for a human to clean up) rather than deleting anything.

Zero-spawn: this runs on a machine carrying a dozen-plus concurrent EM sessions, at a cadence
meant to be cheap enough to run often. No subprocess, stdlib only.

TEMPLATE RESOLUTION. `templates/dotgitignore.tmpl` is a doctrine asset: it stays in DoE-claude and
is published, so it is never at a fixed offset from this file's own location once this CLI lands
here in claude-klabauter (docs/plans/2026-09-18-doe-holds-no-scripts.md § Path resolution). The default
template path resolves through the plugin root
(`coordinator_core.subagent_sandbox.provision_report.resolve_plugin_root`), never from
`Path(__file__)`. `--template` always overrides it explicitly, for a caller that already knows
where the template lives (e.g. a test fixture).

Exit codes: 0 = no drift, or SKIP (`~/.claude` is not a git repo — nothing to propagate into).
1 = drift found (rules the template ships that the live file lacks). 2 = usage/environment error
(template unreadable, or the plugin root could not be resolved and `--template` was not given).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C5.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_TEMPLATE_REL = Path("templates") / "dotgitignore.tmpl"

_AUTO_MEMORY_CHAIN = [
    "projects/**",
    "!projects/*/",
    "!projects/*/memory/",
    "!projects/*/memory/**",
]


def _default_template_path() -> "Path | None":
    """Resolve `templates/dotgitignore.tmpl` through the coordinator-claude plugin root.

    Never `Path(__file__)`-derived: this CLI's own directory (coordinator/bin, in claude-klabauter) no
    longer has any `templates/` sibling — that content stays in DoE-claude and reaches an
    install through the publish pipeline. See module docstring § TEMPLATE RESOLUTION.

    Returns None when the plugin root cannot be resolved; the caller reports that as a usage
    error (exit 2) rather than silently treating "no template found" as "no drift".
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    from coordinator_core.subagent_sandbox.provision_report import resolve_plugin_root

    root = resolve_plugin_root()
    if root is None:
        return None
    return Path(root) / _TEMPLATE_REL


def _default_live_gitignore() -> Path:
    home = Path(os.environ.get("CLAUDE_HOME") or Path.home())
    return home / ".claude" / ".gitignore"


def _rule_lines(text: str) -> list[str]:
    """Non-blank, non-comment lines, in file order, exactly as the template writes them."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(stripped)
    return out


def _is_repo(gitignore_path: Path) -> bool:
    return (gitignore_path.parent / ".git").exists()


def _detect_eol(text: str) -> str:
    """Preserve the live file's own line-ending convention rather than silently normalizing it —
    a CRLF-authored .gitignore (plausible on Windows, a stated P0 target) must stay CRLF after
    `--apply` touches it."""
    return "\r\n" if "\r\n" in text else "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-gitignore-template-drift",
        description=(
            "Flag ~/.claude/.gitignore rules that templates/dotgitignore.tmpl ships but the "
            "live file lacks."
        ),
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help="template path (default: resolved through the coordinator-claude plugin root)",
    )
    parser.add_argument(
        "--live",
        type=Path,
        default=None,
        help="live .gitignore path (default: $CLAUDE_HOME or ~ , joined .claude/.gitignore)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="append missing rules to the live file (opt-in mutation; never runs git rm --cached)",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress the no-drift line")
    args = parser.parse_args(argv)

    template_path = args.template or _default_template_path()
    if template_path is None:
        print(
            "check-gitignore-template-drift: cannot resolve the coordinator-claude plugin root "
            "to find templates/dotgitignore.tmpl — pass --template explicitly",
            file=sys.stderr,
        )
        return 2
    try:
        template_text = template_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"check-gitignore-template-drift: cannot read template {template_path}: {exc}",
              file=sys.stderr)
        return 2

    live_path = args.live or _default_live_gitignore()

    if live_path.is_dir():
        print(
            f"check-gitignore-template-drift: --live {live_path} is a directory, not a "
            "gitignore file",
            file=sys.stderr,
        )
        return 2

    if not _is_repo(live_path):
        print(
            f"check-gitignore-template-drift: SKIP — {live_path.parent} is not a git repo, "
            "nothing to propagate the template into"
        )
        return 0

    template_rules = _rule_lines(template_text)
    # newline="" preserves the file's original line-ending convention (no universal-newline
    # translation) so _apply can detect and round-trip CRLF rather than silently flattening it.
    # `Path.read_text(newline=...)` is a 3.13+ signature; this repo's floor is 3.11
    # (pyproject.toml `requires-python`), so the newline-preserving read goes through `open()`.
    if live_path.is_file():
        with open(live_path, "r", encoding="utf-8", newline="") as fh:
            live_text = fh.read()
    else:
        live_text = ""
    live_lines = set(_rule_lines(live_text))

    missing = [rule for rule in template_rules if rule not in live_lines]

    # The bare `projects/` hazard is a finding in its own right whenever the line is present —
    # independent of whether the auto-memory chain still has any entry in `missing`. A
    # partially-migrated file (chain already fully present, bare line surviving) is inert exactly
    # the same way a from-scratch one is: git never descends into an excluded directory, so the
    # re-inclusion chain below a surviving bare line is dead regardless of the textual rule diff.
    # This must be checked BEFORE the "no missing rules" early return, or a partially-migrated
    # file — the common case, since every existing install starts there — reports a false PASS.
    bare_projects_hazard = "projects/" in live_lines

    if not missing and not bare_projects_hazard:
        if not args.quiet:
            print(f"check-gitignore-template-drift: PASS — {live_path} has every template rule")
        return 0

    if missing:
        print(f"check-gitignore-template-drift: {len(missing)} template rule(s) missing from {live_path}:")
        for rule in missing:
            print(f"  {rule}")
    else:
        print(f"check-gitignore-template-drift: hazard found in {live_path}:")

    # Name the two REPLACE-shaped hazards explicitly — a plain line diff gets both wrong.
    if bare_projects_hazard:
        print(
            "  HAZARD: live file has a bare `projects/` line — appending the auto-memory chain "
            "below it is inert (git never descends into an excluded directory). The bare line "
            "must be REPLACED by the four-line chain, not left in place."
        )
    if "/machine-local" in missing and "/machine-local/" in live_lines:
        print(
            "  HAZARD: live file has `/machine-local/` (trailing slash) — that form stops "
            "matching once the settings-home registry path becomes a symlink post-migration. Add the "
            "bare `/machine-local` form; the slashed line is now a harmless dead rule to clean up."
        )

    if args.apply:
        _apply(live_path, live_text, live_lines, missing)
        print(f"  applied: appended {len(missing)} rule(s) to {live_path}")
        print(
            "  note: an added rule does not retroactively untrack an already-tracked path — "
            "run `git ls-files` against any newly-covered path and `git rm --cached` it by hand."
        )

    return 1


def _apply(live_path: Path, live_text: str, live_lines: set[str], missing: list[str]) -> None:
    """Append `missing` verbatim, except the auto-memory chain, which REPLACES a bare
    `projects/` line rather than appending below it (append there is inert — see module docstring).

    The replace branch is keyed on the bare `projects/` line's PRESENCE, never on whether any
    chain entry happens to still be `missing` — a partially-migrated file (chain already fully
    present, bare line surviving) needs the same deletion a from-scratch file does. Only the
    chain entries genuinely absent from `live_lines` are written; an entry already present
    elsewhere in the file is never duplicated.
    """
    eol = _detect_eol(live_text)
    text = live_text
    to_append = list(missing)

    if "projects/" in live_lines:
        lines = text.splitlines()
        lines = [ln for ln in lines if ln.strip() != "projects/"]
        text = eol.join(lines)
        if text and not text.endswith(eol):
            text += eol
        # Only write chain entries genuinely absent from the live file — never the whole
        # constant unconditionally, or an entry already present elsewhere gets duplicated.
        chain_to_add = [entry for entry in _AUTO_MEMORY_CHAIN if entry not in live_lines]
        for entry in chain_to_add:
            if entry in to_append:
                to_append.remove(entry)
        if chain_to_add:
            text += eol.join(chain_to_add) + eol

    if to_append:
        if text and not text.endswith(eol):
            text += eol
        text += eol.join(to_append) + eol

    live_path.parent.mkdir(parents=True, exist_ok=True)
    # `Path.write_text(newline=...)` is likewise a 3.13+ signature — see the read-side note above.
    with open(live_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
