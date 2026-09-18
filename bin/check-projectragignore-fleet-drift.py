#!/usr/bin/env python3
"""check-projectragignore-fleet-drift — flag fleet repos whose `.project-rag-ignore` is behind the template.

WHY THIS EXISTS. `scaffold_structure` (via `repo-setup` Phase 3e) copies
`templates/dotprojectragignore.tmpl` into a fresh repo and, by design, **never clobbers an
existing file**. That non-clobber rule is correct — a repo's exclusion surface accumulates local
knowledge about its own trees, and an installer must not delete it. The consequence is that a
template edit reaches every repo scaffolded *after* it and none scaffolded *before*, forever,
with nothing reporting the gap.

Measured, not hypothetical. The 2026-08-20 rollout put the same file into 14 repos in one day
(`854afc534`). The nested-archive fix landed in the template on 2026-08-29 (`84164fd18`) and
reached exactly one repo — this one. On 2026-08-30 a fleet audit found example-game-workbench-repo
still carrying the 08-20 text, so its `docs/archive/**` is unpruned. See
`state/audits/data/rag-fleet-exclusion-blast-radius.md`.

WHY IT MATTERS MORE THAN ORDINARY DRIFT. project-rag's exclusion globs are read at the corpus
walk root, so until that anchoring defect is fixed the whole surface is inert fleet-wide and the
staleness is masked. Once anchoring is fixed, a stale glob set becomes *worse than the status
quo in one specific way*: the surface starts working and looks fixed while still missing rules.
A rebuild is only as good as the file it reads. That is why this gate exists as a precondition
on corpus rebuilds rather than as tidy-up.

SUBSET SEMANTICS, NOT EQUALITY. A peer repo carrying rules the template lacks is doing exactly
what the surface is for — pruning trees only it knows about — and is NOT drift. Only template
rules ABSENT from a repo are drift. (This repo is the exception: it must stay byte-identical to
the template, which is a stricter invariant enforced separately by
`test_starter_projectragignore_completeness.py` under PROJECT-RAG-IGNORE-SCAFFOLD-PARITY.)

REPORT-ONLY BY DEFAULT, AND NO FLEET-WIDE MUTATION EVER. `--apply` requires an explicit
`--repo <slug>` and touches that one repo. There is deliberately no apply-to-all: writing into
a dozen peer trees unattended is not a thing this script should be able to do by accident, and
each repo's own EM is better placed to judge whether a template rule fits their tree. Report,
then let them apply — or memo them.

Zero-spawn: stdlib only, no subprocess. This box routinely runs 20+ concurrent sessions.

TEMPLATE RESOLUTION — DOCTRINE-ASSET CLASS. `templates/dotprojectragignore.tmpl` stays in
DoE-claude and is published through the plugin root — it is not `Path(__file__)`-relative any
more, because this script now lives in the engine, not beside the template
(`docs/plans/2026-09-18-doe-holds-no-scripts.md` § Path resolution). Resolution order:
`--template` override, then `CLAUDE_PLUGIN_ROOT`/the ambient plugin-root probe
(`coordinator_core.warm.caller_context.resolve_caller_context`, falling back to
`coordinator_core.subagent_sandbox.provision_report.resolve_plugin_root`), joined with
`templates/dotprojectragignore.tmpl`.

Exit codes: 0 = no repo is behind. 1 = at least one repo is behind the template.
2 = usage/environment error (template or registry unreadable).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C2.
"""
from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path

_TEMPLATE_REL = Path("templates") / "dotprojectragignore.tmpl"
_IGNORE_NAME = ".project-rag-ignore"
_REPO_KEY_PREFIX = "repos."


def _plugin_root() -> "Path | None":
    """The plugin content root the published `templates/dotprojectragignore.tmpl` lives under.

    Engine imports happen here, inside a function, never at module scope — keeps the module
    body pure so `serve_classifier` still classifies this file warm-servable.
    """
    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.require_engine_on_path(__file__)
        from coordinator_core.warm.caller_context import resolve_caller_context

        ctx = resolve_caller_context()
        if ctx.plugin_root:
            return Path(ctx.plugin_root)
    except Exception:
        pass
    try:
        from coordinator_core.subagent_sandbox.provision_report import resolve_plugin_root

        root = resolve_plugin_root()
        return Path(root) if root else None
    except Exception:
        return None


def _own_template_path() -> "Path | None":
    root = _plugin_root()
    return (root / _TEMPLATE_REL) if root is not None else None


def _settings_home() -> Path:
    explicit = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if explicit:
        return Path(explicit)
    return Path.home() / ".coordinator-claude-settings"


def _registry_paths() -> list[Path]:
    """Tracked baseline first, machine-local overlay second — later wins, matching
    `machine-local get`'s own precedence. The overlay is where real paths live; the tracked
    file mostly carries empty declarations."""
    base = _settings_home() / "machine-local"
    return [base / "registry.toml", base / "registry.local.toml"]


def _load_repo_roots() -> dict[str, Path]:
    """Flat `"repos.<slug>" = "<path>"` keys, overlay winning. Empty values are declarations
    with no per-machine value and are skipped, not reported as missing repos.

    A nested `[repos]` table raises rather than silently yielding nothing: a registry written
    that way would drop every repo and be indistinguishable from a registry with no repos at
    all, which is the same read-as-empty-and-report-success trap this whole workstream was about.
    """
    merged: dict[str, str] = {}
    for path in _registry_paths():
        if not path.is_file():
            continue
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        if isinstance(data.get("repos"), dict):
            raise ValueError(
                f"{path} declares a nested [repos] table; this reader expects flat "
                f'"{_REPO_KEY_PREFIX}<slug>" keys and would silently see no repos'
            )
        for key, value in data.items():
            if not isinstance(key, str) or not key.startswith(_REPO_KEY_PREFIX):
                continue
            if isinstance(value, str) and value.strip():
                merged[key[len(_REPO_KEY_PREFIX):]] = value.strip()
    return {slug: Path(raw) for slug, raw in sorted(merged.items())}


def _rule_lines(text: str) -> list[str]:
    """Non-blank, non-comment lines, in file order, exactly as written."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(stripped)
    return out


def _rule_anchor(rule: str) -> str:
    """The literal path prefix of a glob — everything before the first wildcard segment."""
    parts = []
    for segment in rule.split("/"):
        if any(ch in segment for ch in "*?["):
            break
        parts.append(segment)
    return "/".join(parts)


def _applicable(repo_root: Path, rule: str) -> bool:
    """Whether a rule can match anything in this repo at all.

    A rule pruning a tree the repo does not have is inert, so its absence is not drift.
    Reporting it as missing is how a fleet gate ends up telling example-stats-repo to adopt
    `coordinator/cockpit-contract/...` — a rule that cannot match a path in that tree,
    for a directory it does not have. That noise is worse than useless: it inflates every
    repo's BEHIND count with rules nobody should apply, which is how a report stops being
    read.

    Deliberately re-evaluated per run rather than cached. A repo that later grows one of
    these trees becomes genuinely behind at that point, and the next run says so.
    """
    anchor = _rule_anchor(rule)
    if not anchor:
        return True
    return (repo_root / anchor).exists()


def _detect_eol(text: str) -> str:
    """Preserve the target file's own line-ending convention. Multi-OS support is P0 here and a
    CRLF-authored file must stay CRLF after --apply."""
    return "\r\n" if "\r\n" in text else "\n"


def _classify(repo_root: Path, template_rules: list[str]) -> tuple[str, list[str], int]:
    """Returns (state, missing_rules, local_extra_count).

    States: OK | BEHIND | ABSENT | NOREPO | UNREADABLE. ABSENT, NOREPO, and UNREADABLE are
    reported but are not drift — a repo may legitimately carry no exclusion surface (a publish
    mirror, say), and an unreadable file is unknown state, not stale state; conflating either
    with OK would misreport a repo as current when this gate simply couldn't tell.
    """
    if not repo_root.is_dir():
        return ("NOREPO", [], 0)
    ignore_path = repo_root / _IGNORE_NAME
    if not ignore_path.is_file():
        return ("ABSENT", [], 0)
    try:
        text = ignore_path.read_text(encoding="utf-8", newline="")
    except (UnicodeDecodeError, OSError):
        return ("UNREADABLE", [], 0)
    live = _rule_lines(text)
    live_set = set(live)
    missing = [
        rule
        for rule in template_rules
        if rule not in live_set and _applicable(repo_root, rule)
    ]
    template_set = set(template_rules)
    extra = sum(1 for rule in live if rule not in template_set)
    return ("BEHIND" if missing else "OK", missing, extra)


def _apply(ignore_path: Path, missing: list[str]) -> None:
    """Append missing template rules verbatim. Append is safe for this surface in a way it is
    not for a .gitignore: `.project-rag-ignore` has no negation syntax, so order carries no
    meaning and a later line can never re-include what an earlier one pruned.

    Writes via temp-file + os.replace in the same directory: this is the one path that mutates
    a peer repo's tracked file unattended, and a crash mid-write must not truncate it."""
    text = ignore_path.read_text(encoding="utf-8", newline="")
    eol = _detect_eol(text)
    if text and not text.endswith(eol):
        text += eol
    if text and not text.endswith(eol * 2):
        text += eol
    text += eol.join(missing) + eol

    tmp_path = ignore_path.with_name(f".{ignore_path.name}.tmp{os.getpid()}")
    tmp_path.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp_path, ignore_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-projectragignore-fleet-drift",
        description=(
            "Flag fleet repos whose .project-rag-ignore lacks rules the coordinator template "
            "ships. Report-only unless --apply is paired with an explicit --repo."
        ),
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help="template path (default: resolved through the plugin root)",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="restrict to one repos.<slug> from the machine-local registry",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="append missing rules to the target repo; REQUIRES --repo (never fleet-wide)",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress per-repo OK lines")
    args = parser.parse_args(argv)

    if args.apply and not args.repo:
        print(
            "check-projectragignore-fleet-drift: --apply requires --repo <slug>. There is no "
            "fleet-wide apply: writing into peer trees unattended is not this script's call.",
            file=sys.stderr,
        )
        return 2

    template_path = args.template or _own_template_path()
    if template_path is None:
        print(
            "check-projectragignore-fleet-drift: cannot resolve templates/dotprojectragignore.tmpl "
            "— the plugin root did not resolve and --template was not given",
            file=sys.stderr,
        )
        return 2
    try:
        template_rules = _rule_lines(template_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(
            f"check-projectragignore-fleet-drift: cannot read template {template_path}: {exc}",
            file=sys.stderr,
        )
        return 2
    if not template_rules:
        print(
            f"check-projectragignore-fleet-drift: template {template_path} has no rules — "
            "refusing to report every repo as current against an empty template",
            file=sys.stderr,
        )
        return 2

    try:
        repo_roots = _load_repo_roots()
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"check-projectragignore-fleet-drift: cannot read registry: {exc}", file=sys.stderr)
        return 2

    if args.repo:
        if args.repo not in repo_roots:
            known = ", ".join(sorted(repo_roots)) or "(none)"
            print(
                f"check-projectragignore-fleet-drift: unknown repo slug {args.repo!r}. "
                f"Known: {known}",
                file=sys.stderr,
            )
            return 2
        repo_roots = {args.repo: repo_roots[args.repo]}

    behind: list[tuple[str, Path, list[str]]] = []
    absent: list[str] = []
    unreadable: list[str] = []
    for slug, root in repo_roots.items():
        state, missing, extra = _classify(root, template_rules)
        if state == "BEHIND":
            behind.append((slug, root / _IGNORE_NAME, missing))
            suffix = f", {extra} local rule(s)" if extra else ""
            print(f"  BEHIND  {slug}: {len(missing)} template rule(s) missing{suffix}")
        elif state == "ABSENT":
            absent.append(slug)
        elif state == "UNREADABLE":
            unreadable.append(slug)
            print(f"  UNREADABLE  {slug}: could not read {_IGNORE_NAME} — state unknown")
        elif state == "OK" and not args.quiet:
            suffix = f" (+{extra} local)" if extra else ""
            print(f"  OK      {slug}{suffix}")

    if absent and not args.quiet:
        print(
            f"  note: {len(absent)} repo(s) carry no {_IGNORE_NAME} at all "
            f"({', '.join(absent)}) — not counted as drift; whether a repo wants an exclusion "
            "surface is its owner's call."
        )
    if unreadable and not args.quiet:
        print(
            f"  note: {len(unreadable)} repo(s) had an unreadable {_IGNORE_NAME} "
            f"({', '.join(unreadable)}) — not counted as drift; their state is unknown, not OK."
        )

    if not behind:
        if not args.quiet:
            print("check-projectragignore-fleet-drift: PASS — no repo is behind the template")
        return 0

    print(
        f"\ncheck-projectragignore-fleet-drift: {len(behind)} repo(s) behind "
        f"{template_path.name}:"
    )
    for slug, ignore_path, missing in behind:
        print(f"\n  {slug} — {ignore_path}")
        for rule in missing:
            print(f"    {rule}")

    if args.apply:
        slug, ignore_path, missing = behind[0]
        _apply(ignore_path, missing)
        print(f"\n  applied: appended {len(missing)} rule(s) to {ignore_path}")
        print(
            "  note: the corpus is not re-walked by this script. An added rule changes nothing "
            "until that repo's corpus is rebuilt, and an INCREMENTAL rebuild will not retire "
            "already-embedded chunks — it needs a purged rebuild to take effect."
        )
    else:
        print(
            "\n  Report-only. Fix per repo with --repo <slug> --apply, or memo the repo's EM. "
            "Rules are appended verbatim; this surface has no negation syntax, so append order "
            "carries no meaning."
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
