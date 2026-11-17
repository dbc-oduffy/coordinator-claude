"""Triage contract and measured budget ledger shared by every learn-lessons pipeline stage.

Pure stdlib, no process spawning. The driver, the triage workflow and the bench import or mirror
these names; BudgetLedger is the hard stop on total (input + output) measured tokens.
"""
import json
from pathlib import Path

_COORDINATOR = Path(__file__).resolve().parents[2]
_PROFILE = _COORDINATOR / "queue-profiles" / "lessons.yaml"
_BUDGET_CONTRACT = _COORDINATOR / "contract" / "ceremony-budget.json"

# How big one single-turn triage call may be, in payload bytes (~25K tokens).
SYNTH_BATCH_BYTES = 100000
# How many triage calls a whole lesson queue may cost.
MAX_SYNTH_CALLS = 3
# How much of the whole-backlog bar one lessons slice may spend.
LESSONS_SLICE_TOKENS = 600000

CHECKPOINT_PERCENTS = (25, 50, 75)


def load_verdicts(profile: Path = _PROFILE) -> list:
    """Verdict names from the lessons queue profile's top-level `verdicts:` list, in file order."""
    out, in_block = [], False
    for raw in profile.read_text(encoding="utf-8").splitlines():
        if not in_block:
            in_block = raw.rstrip() == "verdicts:"
            continue
        stripped = raw.strip()
        if stripped.startswith("- "):
            out.append(stripped[2:].split("#", 1)[0].strip().strip("'\""))
        elif stripped and not stripped.startswith("#"):
            break
    if not out:
        raise ValueError(f"no verdicts list found in {profile}")
    return out


def _load_bar(path: Path = _BUDGET_CONTRACT) -> int:
    return int(json.loads(path.read_text(encoding="utf-8"))["whole_backlog_token_bar"])


VERDICTS = tuple(load_verdicts())
WHOLE_BACKLOG_TOKEN_BAR = _load_bar()
DEFAULT_BUDGET = LESSONS_SLICE_TOKENS
assert DEFAULT_BUDGET <= WHOLE_BACKLOG_TOKEN_BAR

_ITEM_FIELDS = ("id", "verdict", "target", "evidence", "tests")

TRIAGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdicts"],
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(_ITEM_FIELDS),
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                    "target": {"type": "string"},
                    "evidence": {"type": "string"},
                    "tests": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}


def validate_triage(payload: object) -> list:
    """Problems found validating a triage result against TRIAGE_SCHEMA; empty means valid."""
    if not isinstance(payload, dict) or set(payload) != {"verdicts"}:
        return ["result must be an object with exactly a `verdicts` key"]
    rows = payload["verdicts"]
    if not isinstance(rows, list):
        return ["`verdicts` must be an array"]
    problems, seen = [], set()
    for i, row in enumerate(rows):
        where = f"verdicts[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{where}: not an object")
            continue
        missing = [f for f in _ITEM_FIELDS if f not in row]
        extra = sorted(set(row) - set(_ITEM_FIELDS))
        if missing:
            problems.append(f"{where}: missing {missing}")
        if extra:
            problems.append(f"{where}: unexpected {extra}")
        rid = row.get("id")
        if not isinstance(rid, str) or not rid:
            problems.append(f"{where}: id must be a non-empty string")
        elif rid in seen:
            problems.append(f"{where}: duplicate id {rid!r}")
        else:
            seen.add(rid)
        if "verdict" in row and row["verdict"] not in VERDICTS:
            problems.append(f"{where}: verdict {row['verdict']!r} not in the lessons verdicts list")
        for key in ("target", "evidence"):
            if key in row and not isinstance(row[key], str):
                problems.append(f"{where}: {key} must be a string")
        tests = row.get("tests", [])
        if not isinstance(tests, list) or not all(isinstance(t, str) for t in tests):
            problems.append(f"{where}: tests must be an array of strings")
    return problems


def estimate_tokens(payload: object) -> int:
    """Tokens at 4 bytes each, rounded up; an int is a byte count, text and JSON payloads are measured as UTF-8."""
    if isinstance(payload, int) and not isinstance(payload, bool):
        size = payload
    elif isinstance(payload, (bytes, bytearray)):
        size = len(payload)
    elif isinstance(payload, str):
        size = len(payload.encode("utf-8"))
    else:
        size = len(json.dumps(payload, sort_keys=True).encode("utf-8"))
    if size < 0:
        raise ValueError("size must be non-negative")
    return -(-size // 4)


def _measured_total(usage: object) -> "int | None":
    """Input + output tokens of a call result's usage, or None when either side is absent."""
    if not isinstance(usage, dict):
        return None
    parts = []
    for snake, camel in (("input_tokens", "inputTokens"), ("output_tokens", "outputTokens")):
        val = usage.get(snake, usage.get(camel))
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            return None
        if val < 0:
            raise ValueError("usage tokens must be non-negative")
        parts.append(int(val))
    return sum(parts)


class BudgetLedger:
    """Hard token stop: admit() refuses a call whose projected cost would push measured spend past budget_tokens."""

    def __init__(self, budget_tokens: int = DEFAULT_BUDGET) -> None:
        if budget_tokens < 0:
            raise ValueError("budget_tokens must be non-negative")
        self.budget_tokens = int(budget_tokens)
        self.spent = 0
        self.calls = 0
        self.unmeasured = 0
        self.checkpoints = []

    @property
    def remaining(self) -> int:
        return max(self.budget_tokens - self.spent, 0)

    def admit(self, projected: int) -> bool:
        """True only when measured spend plus the projected cost stays within the budget."""
        if projected < 0:
            raise ValueError("projected must be non-negative")
        return self.spent + projected <= self.budget_tokens

    def record(self, usage: object, projected: "int | None" = None) -> int:
        """Charge a call's measured input + output tokens; returns the amount charged.

        A result without both sides is unmeasured: it is charged twice `projected` and flagged,
        never zero; with no projection to fall back on it raises.
        """
        total = _measured_total(usage)
        if total is None:
            if projected is None:
                raise ValueError("usage lacks input and output tokens and no projected fallback was given")
            total = 2 * int(projected)
            self.unmeasured += 1
        self.spent += total
        self.calls += 1
        if self.budget_tokens:
            pct = 100 * self.spent / self.budget_tokens
            for mark in CHECKPOINT_PERCENTS:
                if pct >= mark and mark not in self.checkpoints:
                    self.checkpoints.append(mark)
        return total

    def to_dict(self) -> dict:
        """The budget-ledger.json shape."""
        return {
            "budget_tokens": self.budget_tokens,
            "spent": self.spent,
            "remaining": self.remaining,
            "calls": self.calls,
            "unmeasured_calls": self.unmeasured,
            "checkpoints": list(self.checkpoints),
        }
