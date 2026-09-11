#!/usr/bin/env python3
"""emit-wave-fire — turn a frozen gate report into fireable plan-blitz wave scripts.

WHY THIS EXISTS. `plan-blitz`'s § Fire the wave used to end at a `Workflow({...})`
example the EM COPIED, filling the `batons` array in by hand from the gate report it
had just read. Every failure mode that example carries is a copying failure:

  - `executionOpen` reached a live wave missing, because the example that taught the
    call omitted it. The wave then dispatched no XS, closed none at the landing, and
    reported them under `routedElsewhere` — the recycling defect, entirely silent.
  - A wave over 8 batons is drained by several fires at the same `waveIndex`. Splitting
    that by hand is arithmetic done in an EM's head, once per fire, and a baton dropped
    between two fires looks exactly like a wave that finished.
  - The args object existed only inside a tool call, so nothing on disk said what was
    fired. A run could not be re-fired, diffed, or archived with its own trail.

This module makes the fire a QUERY over the frozen report rather than an assembly step.
It derives every per-baton field from the engine's own answer, splits the wave into
fires at the documented cap, and emits one standalone `.mjs` per fire — bound through
Claude-klabauter's `workflow.bind_args`, never composed here. The EM's remaining act is one
`Workflow({scriptPath})` per emitted file, with NO args.

WHAT IT DOES NOT DO. It does not read `blocked_by`, derive a wave, decide candidacy, or
re-check a gate — `roadmap.plan_gate` did all of that before the report was frozen, and
a second derivation here would be a second answer to a settled question. It does not
fire: keeping that one call explicit is what makes a runaway chain impossible, the same
boundary `mise-prep-entry.py` holds on the other side of the landing.

THE REPORT COMES IN TWO SHAPES, and both are on disk in live trails. `coordinator-invoke`
prints a JSON-RPC envelope, so the obvious freeze — redirect stdout — writes
`{jsonrpc, id, result: {...}}`, while a caller who unwrapped by hand writes the payload
bare. Reading only the bare shape turns an envelope into `waves == []`, which reports as
"the wave is empty" rather than "this file is wrapped", and the cheap conclusion is the
wrong one. Both are accepted here, as they are in `recycle-check.py`.

Usage:

    python3 emit-wave-fire.py --repo-root <abs> --trail-dir <abs> [--wave-index 0]
                              [--plugin-root <abs>] [--dispositions-cli <abs>]
                              [--spine-check-cli <abs>]
                              [--engine-root <abs>] [--batons-per-fire 8]

Writes `<trail-dir>/fire-<waveIndex>-<n>.mjs` per fire and prints, for each, the exact
`Workflow` invocation to make. Exit 0 on emit, 2 on a refusal that names its reason.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

# § Fire the wave: "Batons come from waves[0], at most 8 per fire."
DEFAULT_BATONS_PER_FIRE = 8

EXIT_OK = 0
EXIT_REFUSED = 2


def _gate_payload(path: Path) -> dict:
    """The report's payload, whether frozen as the JSON-RPC envelope or as `result`."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "result" in data and "waves" not in data:
        inner = data.get("result")
        if isinstance(inner, dict):
            return inner
    return data if isinstance(data, dict) else {}


def _baton_arg(record: dict) -> dict:
    """One `batons[]` entry, every field derived — never defaulted, never typed.

    `executionOpen` has no default on purpose. A baton whose report carries no
    `execution_gate` is a report this script will not paper over: the wave's XS lane
    tests it with `=== true`, so a wrong-by-omission `false` dispatches nothing and
    says so nowhere.
    """
    gate = record.get("execution_gate")
    if not isinstance(gate, dict) or "open" not in gate:
        raise ValueError(
            f"baton {record.get('id')!r} carries no `execution_gate.open` in the frozen "
            "report. `executionOpen` is REQUIRED and has no default — omitting it makes "
            "every XS fail the wave's dispatch test silently. Re-freeze the report from "
            "a `roadmap.plan_gate` read that includes it."
        )
    plan = record.get("plan") or {}
    return {
        "id": record["id"],
        "path": record["path"],
        "title": record.get("title") or "",
        "sized": bool(record.get("sized")),
        "planPath": plan.get("path"),
        "executionOpen": bool(gate["open"]),
    }


def _refusal_text(stdout: str, stderr: str) -> str:
    """The most specific account of a failed `coordinator-invoke`, never a banner.

    A JSON-RPC refusal rides in stdout's `error` object; stderr carries the
    engine's own `[warm-settings]` chatter, which is present on healthy calls
    too. So stdout's structured error wins, then stdout raw, and stderr is
    appended rather than substituted — a caller debugging a refusal needs the
    reason, and losing the banner entirely would hide a resolution failure that
    only ever reaches stderr.
    """
    detail = ""
    try:
        reply = json.loads(stdout)
        err = reply.get("error")
        if err:
            detail = err.get("message") or json.dumps(err)
    except (json.JSONDecodeError, AttributeError):
        pass
    if not detail:
        detail = stdout.strip()
    banner = stderr.strip()
    if banner and detail:
        return f"{detail[:800]} [stderr: {banner[:300]}]"
    return (detail or banner or "no output on either stream")[:800]


def _bind(
    engine_root: Path | None,
    script_path: Path,
    args: dict,
    live_engine_tree: bool = False,
) -> str:
    """Compose the standalone script through claude-klabauter's `workflow.bind_args`.

    Delegated, never reimplemented: the binding rule (where the literal goes, which
    sources are refused) is engine-owned, and a second composer here is how the two
    drift. The engine is reached through its own `coordinator-invoke`, resolved the way
    every other coordinator CLI is — the launcher at the settings home first, the
    engine's `coordinator/bin/` forwarder as the fallback rung for a box with no install.
    """
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(
        Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"
    )
    launcher = Path(settings_home) / "bin" / "coordinator-invoke"
    if launcher.is_file():
        cmd = [str(launcher)]
    elif engine_root is not None:
        forwarder = engine_root / "coordinator" / "bin" / "coordinator-invoke.py"
        if not forwarder.is_file():
            raise ValueError(
                f"no coordinator-invoke launcher at {launcher} and no forwarder at "
                f"{forwarder}. Pass --engine-root pointing at the engine checkout, or "
                "install the launcher."
            )
        cmd = [sys.executable, str(forwarder)]
    else:
        raise ValueError(
            f"no coordinator-invoke launcher at {launcher}, and no --engine-root or "
            "$COORDINATOR_ENGINE_ROOT to fall back to. Install the launcher, or pass "
            "--engine-root pointing at the engine checkout."
        )

    extra: list[str] = (
        ["--allow-unstamped-dispatch"] if live_engine_tree else []
    )

    env = dict(os.environ)
    # Set ONLY when we were actually given one. An empty value here resolves to `.`,
    # which does not merely fail to help — it OVERRIDES the engine's own resolution
    # ladder (the machine-local pointer and registry rungs) with a wrong answer, and
    # the resulting refusal names the cwd rather than the missing configuration.
    if engine_root is not None:
        env.setdefault("COORDINATOR_ENGINE_ROOT", str(engine_root))
    payload = json.dumps({"script_path": str(script_path), "args": args})
    proc = subprocess.run(
        cmd + ["workflow.bind_args", payload] + extra,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    # An engine that ANSWERED with a JSON-RPC error still exits non-zero, and its stderr
    # carries the engine's own `[warm-settings]` chatter. Preferring stderr there reports
    # the chatter as the failure and DISCARDS the diagnosis — measured: a mirror missing
    # the op surfaced as "warmth is disabled by configuration". Parse stdout first.
    reply: dict | None = None
    try:
        parsed = json.loads(proc.stdout)
        if isinstance(parsed, dict):
            reply = parsed
    except json.JSONDecodeError:
        reply = None
    if reply is None:
        if proc.returncode != 0:
            # No structured error to read. Name BOTH streams, stdout first, so the
            # banner can neither displace the refusal nor hide a resolution failure
            # that only ever reaches stderr.
            raise ValueError(
                f"workflow.bind_args failed (exit {proc.returncode}): "
                f"{_refusal_text(proc.stdout, proc.stderr)}"
            )
        raise ValueError(
            "workflow.bind_args returned non-JSON. First 400 bytes: "
            f"{proc.stdout[:400]!r}"
        )
    if "error" in reply:
        message = str((reply["error"] or {}).get("message") or reply["error"])
        if "Method not found" in message and "bind_args" in message:
            # The engine ANSWERED and does not carry the op. That is a publish lag, not a
            # broken resolution: `workflow.bind_args` is authored in claude-klabauter and
            # reaches a box through the claude-klabauter mirror, so a mirror published
            # before the op landed refuses every emit with a message that reads like a
            # missing or misresolved engine — the more expensive of the two conclusions.
            raise ValueError(
                f"workflow.bind_args refused: {message}. The resolved engine "
                f"({engine_root or 'settings-home launcher'}) ANSWERED and does not carry "
                "the op — a published mirror older than the op, not a resolution failure. "
                "Point --engine-root at a checkout that has it (claude-klabauter authors it), "
                "adding --live-engine-tree because that checkout carries no build stamp, or "
                "re-percolate the mirror."
            )
        raise ValueError(f"workflow.bind_args refused: {message}")
    script = (reply.get("result") or {}).get("script")
    if not isinstance(script, str) or not script:
        # A reply carrying neither `error` nor a usable `script` must REFUSE, not raise.
        # `main()` catches ValueError and names the reason; a KeyError escapes as a
        # traceback, which reads as this module being broken rather than the engine
        # having answered something unexpected.
        raise ValueError(
            "workflow.bind_args returned a reply carrying neither `error` nor a "
            f"`result.script` string. Got keys: {sorted(reply)!r}"
        )
    return script


def _settings_home_bin(name: str) -> str | None:
    """A settings-home launcher path, or None. Rung 2 of the resolution ladder."""
    settings_home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(
        Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"
    )
    candidate = Path(settings_home) / "bin" / name
    if candidate.is_file():
        return str(candidate)
    return shutil.which(name)


def _engine_env_prefix(engine_root: Path) -> str:
    """`COORDINATOR_ENGINE_ROOT=<engine> `, or empty. Part of the injected literal.

    `append-integrator-dispositions` resolves CLAUDE_KLABAUTER_ROOT before it does anything, and on a
    box with no machine-local registry that resolution fails outright — the CLI exits 3
    with a bootstrap message naming this variable as one of its remedies. The integrator
    then reports the op refused and correctly declines to hand-author around it, so the
    wave runs every review and records not one disposition. Silent by construction: the
    refusal loses only the RECORD. Measured 2026-09-10 on example-cockpit-repo, wave 4 — three
    sidecars, no `## Integrator Dispositions` block on any of them.

    The dispatching side already resolved an engine root to bind the fire with; the agent
    running the CLI cannot. Same rung-3 reasoning as the interpreter and DOE_ROOT.
    """
    if os.environ.get("COORDINATOR_ENGINE_ROOT"):
        return ""
    if os.name != "posix":
        return ""
    return f"COORDINATOR_ENGINE_ROOT={shlex.quote(str(engine_root))} "


#: The two layouts a published/mirrored plugin ships the registry manifest in. The private
#: DoE tree keeps it under `coordinator/`; the OSS publish row ships it flat at plugin root.
#: `coordinator_registry._mp_candidate_manifest_path` probes exactly this pair, so exporting
#: a root that satisfies neither is exporting a value its consumer cannot use.
_MANIFEST_RELPATHS = (
    Path("schemas") / "coordinator-registry.manifest.json",
    Path("coordinator") / "schemas" / "coordinator-registry.manifest.json",
)


def _registry_manifest_prefix(engine_root: Path, plugin_root: Path) -> str:
    """`DOE_ROOT=<a root the manifest actually resolves under> `, or empty.

    Both CLIs load the registry manifest, and an install-less box does not have it in the
    engine tree — the schemas ship with the DOCTRINE repo, not the engine mirror. The
    CLI's own diagnostic names `DOE_ROOT` as the remedy, but it is a remedy nobody reads:
    the failure happens inside a dispatched reviewer, where its stderr becomes "the
    sidecar step did not work".

    VALIDATE THE VALUE YOU EXPORT. An earlier cut checked for the manifest under
    `<plugin_root>/schemas/` and then exported `plugin_root.parent`, which agree only when
    the plugin root's basename is literally `coordinator` — the private layout. Under the
    published layout, where the manifest sits flat at plugin root, that exported a root
    the consumer cannot resolve from, AND `DOE_ROOT` is taken as-is ahead of every other
    rung and is the state-write root. A wrong value there is worse than none: it is the
    plausible-but-wrong invocation this module exists to stop emitting.

    POSIX-shaped, and deliberately not emitted elsewhere: `VAR=x cmd` is not a command on
    a PowerShell host. A Windows box in this state gets no prefix and the CLI's own
    diagnostic, which names the variable — a loud failure rather than a wrong literal.
    """
    if any((engine_root / rel).is_file() for rel in _MANIFEST_RELPATHS):
        return ""
    if os.name != "posix":
        return ""
    for candidate in (plugin_root.parent, plugin_root):
        if any((candidate / rel).is_file() for rel in _MANIFEST_RELPATHS):
            return f"DOE_ROOT={shlex.quote(str(candidate))} "
    return ""


def _engine_bin(
    engine_root: Path | None, name: str, plugin_root: Path | None = None
) -> str | None:
    """The engine checkout's own copy of a CLI, as a runnable invocation, or None.

    Rung N's rung 3. On a box with no settings home — every ephemeral container — the
    launcher rungs above resolve nothing, and the two CLIs this module injects are
    exactly the two whose absence fails SILENTLY downstream. The engine source is on
    disk regardless, but these files carry no shebang and no executable bit, so the path
    alone is not an invocation: the interpreter has to be part of the literal. Building
    it here is the whole of rung 3's "the dispatching side has a filesystem" — leaving it
    to the caller means a human hand-types an interpreter prefix per run, and a
    hand-typed resolution is the thing this module exists to remove.
    """
    if engine_root is None:
        return None
    candidate = engine_root / "coordinator" / "bin" / f"{name}.py"
    if not candidate.is_file():
        return None
    prefix = _engine_env_prefix(engine_root)
    if plugin_root is not None:
        prefix += _registry_manifest_prefix(engine_root, plugin_root)
    return (
        f"{prefix}{shlex.quote(sys.executable)} {shlex.quote(str(candidate))}"
    )


def _default_spine_check_cli(plugin_root: Path | None) -> str | None:
    """`plan-spine-check`, resolved off the PLUGIN root — rung 3's plugin-local case.

    It ships in the coordinator plugin's own `bin/`, never in the repo being planned, so
    the brief's `<repoRoot>/coordinator/bin/plan-spine-check.py` resolves to nothing
    everywhere except the plugin's own source tree. The planner then runs a check the
    brief calls "runnable, not advice", gets "No such file or directory", and returns a
    plan whose spine was never checked — silently, because a missing file reads as a
    tooling hiccup rather than a skipped gate.
    """
    if plugin_root is None:
        return None
    candidate = plugin_root / "bin" / "plan-spine-check.py"
    if not candidate.is_file():
        return None
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(candidate))}"



def _refuse_live_tree_on_a_stamped_engine(engine_root, live_engine_tree: bool) -> str | None:
    """Enforce `--live-engine-tree`'s own stated precondition, or refuse.

    The flag forwards the engine's `--allow-unstamped-dispatch`, whose own help reads
    "For deliberate manual testing of engine changes ONLY". Unconditioned, it applies to
    whichever rung resolved — including a settings-home launcher on a fully installed box
    with a stamped published engine, which is precisely the case it must never touch.

    It also disarms MORE than the stamp gate: the same engine flag decides whether a
    warm-unavailable dispatch may fall through to a cold spawn, so passing it re-enables
    a silent-slow degrade. Both are reasons to require that the caller really is pointed
    at an unstamped tree before it is honoured.
    """
    if not live_engine_tree:
        return None
    if engine_root is None:
        return (
            "--live-engine-tree needs --engine-root: it exists to reach an UNSTAMPED "
            "authoring tree, and without one it would hand the engine's manual-testing "
            "carve-out to whatever rung happens to resolve, installed box included."
        )
    if (engine_root / "coordinator_core" / "_engine_stamp").is_file():
        return (
            f"--live-engine-tree refused: {engine_root} carries a build stamp, so it is a "
            "PUBLISHED engine and needs no carve-out. The flag disarms the stamp gate AND "
            "the cold-fallback refusal; neither is appropriate against a published mirror. "
            "Drop the flag."
        )
    return None


def _archived_fire_identity(path: Path) -> tuple[int | None, frozenset[str]] | None:
    """`(waveIndex, baton ids)` of an already-emitted fire, or None if unreadable.

    The collision guard keys on THIS, not on the bound bytes. Bytes carry emit-time
    ambient facts — `sys.executable`, and whether `COORDINATOR_ENGINE_ROOT` happened to
    be exported, which decides whether `_engine_env_prefix` contributes — so the same
    fire re-emitted from a different shell produces different bytes and a byte guard
    calls it a different fire. What makes two emits the SAME fire is the wave and the
    batons, and nothing else.
    """
    try:
        text = path.read_text(encoding="utf-8")
        marker = text.index("const args = ")
        obj, _ = json.JSONDecoder().raw_decode(text, marker + len("const args = "))
    except (OSError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    batons = obj.get("batons")
    if not isinstance(batons, list):
        return None
    ids = frozenset(
        b.get("id") for b in batons if isinstance(b, dict) and b.get("id")
    )
    index = obj.get("waveIndex")
    return (index if isinstance(index, int) else None, ids)


def _default_arming_check_cli(plugin_root: Path | None) -> str | None:
    """`instrument-can-report-red`, resolved off the PLUGIN root. Same rung, worse citation.

    The brief cited it as a BARE RELATIVE path, so it resolved against the planner's cwd —
    the repo being planned — and every wave outside the plugin's own tree got "No such file
    or directory". The arming line then read `N/A`, which is indistinguishable from a plan
    that declared no falsifier at all.
    """
    if plugin_root is None:
        return None
    candidate = plugin_root / "bin" / "instrument-can-report-red.py"
    if not candidate.is_file():
        return None
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(candidate))}"


def _default_sidecar_cli(
    engine_root: Path | None, plugin_root: Path | None = None
) -> str | None:
    """`provision-sidecar`, resolved caller-side for the same reason as the op below.

    A reviewer cannot resolve `<machinery_root>` or `<your session id>` from inside its
    brief — both are facts about this box. An agent handed those placeholders invents
    them, and the invention is silent: the path it picks still carries the
    `subagent-share` segment `append-integrator-dispositions` checks for, so the findings
    are written, accepted, and simply kept somewhere the repo does not track.
    """
    return _settings_home_bin("provision-sidecar") or _engine_bin(
        engine_root, "provision-sidecar", plugin_root
    )


def _default_dispositions_cli(
    engine_root: Path | None, plugin_root: Path | None = None
) -> str | None:
    """`append-integrator-dispositions`, resolved the way rung 3 says the CALLER must.

    The op ships no launcher on a stock install, so a bareword exits 127 and the
    integrator reports the tool ABSENT — a misdiagnosis that gets escalated rather than
    fixed, while the op runs fine from its own bin/. Resolve it here, where there is a
    filesystem, and inject the literal. Returning None is honest: the workflow's brief
    then says the caller omitted it, rather than letting the integrator guess.
    """
    return _settings_home_bin("append-integrator-dispositions") or _engine_bin(
        engine_root, "append-integrator-dispositions", plugin_root
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="emit-wave-fire",
        description="Emit fireable plan-blitz wave scripts from a frozen gate report.",
    )
    ap.add_argument("--repo-root", required=True, help="ABSOLUTE path to the repo being planned")
    ap.add_argument("--trail-dir", required=True, help="ABSOLUTE trail dir; also where scripts land")
    ap.add_argument("--gate-report", help="frozen report (default: <trail-dir>/gate-report.json)")
    ap.add_argument(
        "--wave-index",
        type=int,
        default=0,
        help="which wave OF THE FROZEN REPORT to fire. `roadmap.plan_gate` numbers `waves` "
        "from the READ, so every wave of a run arrives as 0 and this is almost always 0.",
    )
    ap.add_argument(
        "--wave-number",
        type=int,
        help=(
            "this run's own wave count, used for `waveIndex` in the bound args, the fire "
            "filename and the trail slot. Defaults to --wave-index. They are different "
            "questions: --wave-index indexes the frozen report, which renumbers from 0 on "
            "every read, while the trail and the landing want the run's absolute wave. "
            "Without this the run's second wave emits over its first's archived fire, and "
            "the workaround is hand-editing the frozen report — the retype this module "
            "exists to remove."
        ),
    )
    ap.add_argument("--plugin-root", help="resolved CLAUDE_PLUGIN_ROOT (default: this file's plugin root)")
    ap.add_argument("--engine-root", help="claude-klabauter root (default: $COORDINATOR_ENGINE_ROOT)")
    ap.add_argument("--dispositions-cli", help="absolute append-integrator-dispositions invocation")
    ap.add_argument("--provision-sidecar-cli", help="absolute provision-sidecar invocation")
    ap.add_argument(
        "--spine-check-cli",
        help="absolute plan-spine-check invocation (default: derived from --plugin-root). "
        "Plugin-owned tooling, so it is resolved against the PLUGIN root and never the repo "
        "being planned — the two coincide only on DoE-claude.",
    )
    ap.add_argument(
        "--live-engine-tree",
        action="store_true",
        help=(
            "the --engine-root given is claude-klabauter's live authoring tree, which carries "
            "no build stamp. The engine's own live-tree path (the PM's manual "
            "test-and-execute carve-out) is taken for the bind call and NOTHING else — every "
            "other op this run makes still goes through the engine the caller resolved. Its "
            "case is an ephemeral box whose published mirror predates `workflow.bind_args`."
        ),
    )
    ap.add_argument("--batons-per-fire", type=int, default=DEFAULT_BATONS_PER_FIRE)
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="BATON-ID",
        help=(
            "drop this baton from the emit. Repeatable. For a wave already PART-fired — "
            "another fire at this waveIndex is live over those batons, and emitting them "
            "again would run two waves against one plan. It narrows what is FIRED, never "
            "what the gate computed: the baton stays in the frozen report as a resolved "
            "blocker. An id that matches nothing in the wave is refused, not ignored."
        ),
    )
    ap.add_argument(
        "--plugin-agents-available",
        choices=("true", "false"),
        default="false",
        help="whether coordinator:* agent types resolve on this host (default false, the safe direction)",
    )
    ap.add_argument("--json", action="store_true", help="emit the fire manifest as JSON")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    trail_dir = Path(args.trail_dir).resolve()
    # skills/plan-blitz/<this file> -> the plugin root is two parents up.
    plugin_root = Path(args.plugin_root).resolve() if args.plugin_root else Path(__file__).resolve().parents[2]
    _engine = args.engine_root or os.environ.get("COORDINATOR_ENGINE_ROOT") or ""
    engine_root = Path(_engine).resolve() if _engine.strip() else None

    wave_number = args.wave_number if args.wave_number is not None else args.wave_index

    live_tree_refusal = _refuse_live_tree_on_a_stamped_engine(
        engine_root, args.live_engine_tree
    )

    report_path = Path(args.gate_report) if args.gate_report else trail_dir / "gate-report.json"
    if not report_path.is_absolute():
        report_path = repo_root / report_path

    def refuse(msg: str) -> int:
        print(f"emit-wave-fire: REFUSED — {msg}", file=sys.stderr)
        return EXIT_REFUSED

    if live_tree_refusal:
        return refuse(live_tree_refusal)

    if not report_path.is_file():
        return refuse(f"no frozen gate report at {report_path}")
    if not trail_dir.is_dir():
        return refuse(
            f"trail dir {trail_dir} does not exist. Scaffold it before emitting — the "
            "workflow has no filesystem primitive, so an unscaffolded directory means "
            "every sidecar write lands nowhere and the readiness gate reads an empty trail."
        )

    script_source = plugin_root / "workflows" / "plan-blitz.mjs"
    if not script_source.is_file():
        return refuse(
            f"no plan-blitz.mjs at {script_source} — the plugin root did not resolve. "
            "Pass --plugin-root with the absolute path."
        )

    payload = _gate_payload(report_path)
    waves = payload.get("waves") or []
    if args.wave_index >= len(waves):
        return refuse(
            f"the report has {len(waves)} wave(s); wave {args.wave_index} is not one of them"
        )
    wave_ids = list(waves[args.wave_index])
    if not wave_ids:
        return refuse(f"wave {args.wave_index} is empty — nothing to fire")

    if args.exclude:
        unmatched = [i for i in args.exclude if i not in wave_ids]
        if unmatched:
            return refuse(
                f"--exclude names {unmatched}, which wave {args.wave_index} does not "
                "contain. An exclusion that matches nothing is a typo, and silently "
                "honouring it emits a fire the caller did not mean to emit."
            )
        wave_ids = [i for i in wave_ids if i not in set(args.exclude)]
        if not wave_ids:
            return refuse(
                f"every baton in wave {args.wave_index} was excluded — nothing to fire"
            )

    by_id = {b["id"]: b for b in (payload.get("batons") or [])}
    missing = [i for i in wave_ids if i not in by_id]
    if missing:
        return refuse(
            f"wave {args.wave_index} names {len(missing)} baton(s) the report's own "
            f"`batons[]` does not carry: {missing}. The report is internally inconsistent; "
            "re-freeze it rather than emitting a fire that plans a subset."
        )

    try:
        entries = [_baton_arg(by_id[i]) for i in wave_ids]
    except ValueError as exc:
        return refuse(str(exc))

    # Multi-OS is P0, and the env-prefix rungs above are POSIX-shaped by necessity —
    # `VAR=x cmd` is not a command on a PowerShell host. A Windows box with no install
    # therefore gets an invocation the CLI will reject for a reason nobody sees, since
    # that stderr surfaces inside a dispatched reviewer. Saying so here is the whole
    # mitigation available: this module cannot write a PowerShell literal into a POSIX
    # brief, but it can refuse to be quiet about the gap.
    if os.name != "posix" and not os.environ.get("COORDINATOR_SETTINGS_HOME"):
        print(
            "  WARNING: non-POSIX host with no settings home. The injected CLI literals "
            "carry no environment prefix (`VAR=x cmd` is not a command here), so "
            "`append-integrator-dispositions` may fail CLAUDE_KLABAUTER_ROOT resolution inside a "
            "dispatched agent, where its diagnostic is not read. Resolve the CLIs "
            "explicitly with --dispositions-cli / --provision-sidecar-cli.",
            file=sys.stderr,
        )

    dispositions = args.dispositions_cli or _default_dispositions_cli(
        engine_root, plugin_root
    )
    sidecar_cli = args.provision_sidecar_cli or _default_sidecar_cli(
        engine_root, plugin_root
    )
    spine_check_cli = args.spine_check_cli or _default_spine_check_cli(plugin_root)
    arming_check_cli = _default_arming_check_cli(plugin_root)

    per = max(1, args.batons_per_fire)
    fires = [entries[i : i + per] for i in range(0, len(entries), per)]

    manifest = []
    for n, batch in enumerate(fires, start=1):
        wave_args = {
            "repoRoot": str(repo_root),
            "waveIndex": wave_number,
            "trailDir": str(trail_dir),
            "gateReportPath": str(report_path),
            "pluginAgentsAvailable": args.plugin_agents_available == "true",
            "batons": batch,
        }
        if dispositions:
            wave_args["dispositionsCli"] = dispositions
        if sidecar_cli:
            wave_args["provisionSidecarCli"] = sidecar_cli
        if spine_check_cli:
            wave_args["spineCheckCli"] = spine_check_cli
        if arming_check_cli:
            wave_args["armingCheckCli"] = arming_check_cli
        try:
            text = _bind(
                engine_root, script_source, wave_args, args.live_engine_tree
            )
        except ValueError as exc:
            return refuse(str(exc))

        out = trail_dir / f"fire-{wave_number}-{n}.mjs"
        # An emitted script is on disk SO THAT the fire can be re-read, re-fired and
        # diffed, and so it archives with the trail. Silently overwriting one destroys
        # exactly that. The collision is not hypothetical: `roadmap.plan_gate` numbers
        # `waves` from the READ, so every wave of a run comes back as `waves[0]`, and a
        # driver that emits the run's second wave into the same trail clobbers the
        # first's scripts while the trail SLOTS — keyed by baton set — stay correctly
        # separate. Nothing else notices, because the fire that mattered already ran.
        archived = _archived_fire_identity(out) if out.is_file() else None
        if archived is not None:
            archived_index, archived_ids = archived
            fresh_ids = frozenset(b["id"] for b in batch)
            # Two emits are the SAME fire when they cover the same wave and the same
            # batons. A NARROWING re-emit is also legitimate and is the documented
            # `--exclude` flow: a wave already part-fired, re-emitted over the batons
            # still to go. Only a fire covering batons the archived one did not is a
            # genuine collision — that is the one that would destroy a record of work.
            same_wave = archived_index in (None, wave_number)
            if not (same_wave and fresh_ids <= archived_ids):
                return refuse(
                    f"{out.name} already exists in this trail and binds a DIFFERENT fire "
                    f"— it covers {sorted(archived_ids)}, this one covers "
                    f"{sorted(fresh_ids)}. Emitting over it would destroy the archived "
                    "fire, which is the reason these are written to disk at all. "
                    "`roadmap.plan_gate` numbers waves from the read, so a run's second "
                    "wave also arrives as wave 0: pass --wave-number matching this run's "
                    "own wave count, or --trail-dir a fresh directory for this wave."
                )
        out.write_text(text, encoding="utf-8")
        manifest.append(
            {"fire": n, "scriptPath": str(out), "batons": [b["id"] for b in batch]}
        )

    if args.json:
        print(json.dumps({"waveIndex": wave_number, "fires": manifest}, indent=2))
        return EXIT_OK

    print(
        f"emit-wave-fire: wave {wave_number} — {len(entries)} baton(s) across "
        f"{len(fires)} fire(s), at most {per} per fire."
    )
    if not dispositions:
        print(
            "  WARNING: no append-integrator-dispositions resolved. The integrator brief "
            "will say the caller omitted it; dispositions for this wave go unrecorded.",
            file=sys.stderr,
        )
    if not sidecar_cli:
        print(
            "  WARNING: no provision-sidecar resolved. Every reviewer will place its own "
            "findings sidecar by guessing the machinery root and its session id, and the "
            "guess does not error — the findings land where the repo does not keep them.",
            file=sys.stderr,
        )
    for row in manifest:
        print(f"\n  fire {row['fire']}: {', '.join(row['batons'])}")
        print(f'    Workflow({{ scriptPath: "{row["scriptPath"]}" }})   # no args — they are bound')
    print(
        "\nFire every one of them at this waveIndex before landing. `blitz_land` takes ONE "
        "fire's result, so sum the three lanes across all fires before reading the "
        "stop condition."
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
