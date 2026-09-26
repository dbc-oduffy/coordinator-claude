# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
#   Op: workflow.scaffold — COMPUTE_ONLY, returns text, does NOT write to disk.
#       what looks like a JSON-RPC business/param error (e.g. missing name/description,
#     fails loud instead (the op is COMPUTE_ONLY and this veneer has no local copy
#     subprocess (ARG_MAX-safe --params-file transport), same as the bash oracle.

from __future__ import annotations

import os
import re
import sys

GENERATES = []

_PROG = "coordinator-workflow-scaffold.py"

StructuralPinError = None  # type: ignore  # bound by _bootstrap_imports()
cc_invoke_bare = None  # type: ignore  # bound by _bootstrap_imports()
is_timeout_error = None  # type: ignore  # bound by _bootstrap_imports()
none_scoped_repo_refusal = None  # type: ignore  # bound by _bootstrap_imports()

def _bootstrap_imports() -> None:
    global StructuralPinError, cc_invoke_bare, is_timeout_error, none_scoped_repo_refusal

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke as _cc_invoke_mod

    StructuralPinError = _cc_invoke_mod.StructuralPinError
    is_timeout_error = _cc_invoke_mod.is_timeout_error
    none_scoped_repo_refusal = _cc_invoke_mod.none_scoped_repo_refusal
    if cc_invoke_bare is None:
        cc_invoke_bare = _cc_invoke_mod.cc_invoke_bare


class _TransportError(Exception):
    pass


class _OpError(Exception):
    pass


def _cc_invoke(op: str, params: dict, repo_root: str) -> dict:
    try:
        return cc_invoke_bare(op, params, repo_root)
    except StructuralPinError as exc:
        raise _OpError(str(exc)) from exc
    except RuntimeError as exc:
        msg = str(exc)
        # `_TIMEOUT_MESSAGE_PREFIX`, so it cannot drift out from under this classifier
        # `CLAUDE_KLABAUTER_ROOT` to engine-root wording, and matching only the old spelling
        if (
            "engine will not import/start" in msg
            or is_timeout_error(exc)
            or "CLAUDE_KLABAUTER_ROOT" in msg
            or "engine root" in msg
            or "engine-root" in msg
            or "empty stdout" in msg
            or "not valid JSON" in msg
        ):
            raise _TransportError(msg) from exc
        raise _OpError(msg) from exc


def _usage() -> str:
    return (
        f"  Usage: {_PROG} --name <kebab> "
        "[--description \"<line>\" | --description-file <path>] "
        "[--title \"<line>\" | --title-file <path>] "
        "[--phase \"Title::Detail\"]... [--pattern <p>] [--out PATH]"
    )


def main(argv: list[str]) -> int:
    _bootstrap_imports()
    name = ""
    title: str | None = None
    title_file: str | None = None
    description: str | None = None
    description_file: str | None = None
    pattern = "pipeline-default"
    out_path = ""
    phases_raw: list[str] = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--name":
            name = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif arg == "--title":
            title = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif arg == "--title-file":
            title_file = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif arg == "--description":
            description = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif arg == "--description-file":
            description_file = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif arg == "--phase":
            phases_raw.append(argv[i + 1] if i + 1 < len(argv) else "")
            i += 2
        elif arg == "--pattern":
            pattern = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif arg == "--repo":
            print(none_scoped_repo_refusal(_PROG, "workflow.scaffold"), file=sys.stderr)
            return 1
        elif arg == "--out":
            out_path = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        else:
            print(f"{_PROG}: unknown arg: {arg}", file=sys.stderr)
            print(_usage(), file=sys.stderr)
            return 1

    from coordinator_core.argv_fidelity import ArgvFidelityError, resolve_optional_prose

    try:
        title = resolve_optional_prose(
            title, title_file, flag_name="--title"
        )
    except ArgvFidelityError as exc:
        print(f"{_PROG}: {exc}", file=sys.stderr)
        return 1

    try:
        description = resolve_optional_prose(
            description, description_file, flag_name="--description"
        )
    except ArgvFidelityError as exc:
        print(f"{_PROG}: {exc}", file=sys.stderr)
        return 1

    title = title or ""
    description = description or ""

    if not name and not title:
        print(f"{_PROG}: --name or --title is required", file=sys.stderr)
        return 1

    if not description and not title:
        print(f"{_PROG}: --description or --title is required", file=sys.stderr)
        return 1

    if not name:
        slug = title.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
        name = slug or "unnamed-workflow"

    if not description:
        description = title

    phases = []
    for raw in phases_raw:
        if "::" not in raw:
            print(f'{_PROG}: malformed --phase (expected "Title::Detail"): {raw}', file=sys.stderr)
            print(f"{_PROG}: params JSON build failed — see the error printed above", file=sys.stderr)
            return 1
        ptitle, pdetail = raw.split("::", 1)
        phases.append({"title": ptitle, "detail": pdetail})

    params = {
        "name": name,
        "description": description,
        "phases": phases,
        "pattern": pattern,
    }

    try:
        result = _cc_invoke("workflow.scaffold", params, "")
    except _TransportError as exc:
        print(str(exc), file=sys.stderr)
        print(
            f"{_PROG}: transport/engine failure dispatching workflow.scaffold — "
            "see stderr above (timeout, engine-root resolution, or engine "
            "import failure).",
            file=sys.stderr,
        )
        return 3
    except _OpError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    script_text = result.get("script") if isinstance(result, dict) else None
    if script_text is None:
        print(f'{_PROG}: cc_invoke result missing "script" key', file=sys.stderr)
        print(f"{_PROG}: failed to extract .script from workflow.scaffold result", file=sys.stderr)
        return 2

    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(script_text + "\n")
        except OSError as exc:
            print(f"{_PROG}: failed to write to --out path: {out_path} ({exc})", file=sys.stderr)
            return 1
        print(out_path)
    else:
        sys.stdout.write(script_text + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
