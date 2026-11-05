"""Source-link claim filter: drop claims without a source link from a stage file.

Usage: claim_filter.py <run> <stage>. Rewrites the stage file keeping only claims
with a non-empty source_link and records the removed claims in
<run>/<stage>.dropped.json. Idempotent: a second run drops nothing and keeps the
earlier dropped record. Exit 0 on success, 2 when the stage file is missing.
Stdlib only.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_folder  # noqa: E402


def dropped_file(run, stage):
    return Path(run) / f"{stage}.dropped.json"


def filter_claims(claims):
    """Split claims into (kept, dropped); a non-dict entry carries no link and is dropped."""
    kept, dropped = [], []
    for claim in claims:
        if isinstance(claim, dict) and run_folder.has_source_link(claim):
            kept.append(claim)
        else:
            dropped.append(claim)
    return kept, dropped


def filter_stage(run, stage):
    """Filter the stage file in place; returns the claims dropped by this run.

    Raises FileNotFoundError when the stage file does not exist.
    """
    data = run_folder.read_stage(run, stage)
    if data is None:
        raise FileNotFoundError(str(run_folder.stage_file(run, stage)))
    kept, dropped = filter_claims(data.get("claims") or [])
    if dropped:
        data["claims"] = kept
        run_folder.write_stage(run, stage, data)
    path = dropped_file(run, stage)
    if dropped or not path.is_file():
        prior = []
        if path.is_file():
            prior = run_folder._read_json(path).get("dropped", [])
        run_folder._write_json(path, {"stage": stage, "dropped": prior + dropped})
    return dropped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", help="run folder")
    parser.add_argument("stage", choices=run_folder.stage_ids())
    args = parser.parse_args(argv)
    try:
        dropped = filter_stage(args.run, args.stage)
    except FileNotFoundError as exc:
        print(f"stage file missing: {exc}", file=sys.stderr)
        return 2
    print(f"{args.stage}: dropped {len(dropped)} claim(s) without a source link")
    return 0


if __name__ == "__main__":
    sys.exit(main())
