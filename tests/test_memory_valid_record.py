# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""The `_valid_memory_record` load-time guard — the hot-path shield.

`_load_jsonl` already tolerates a *torn* line (a `json.JSONDecodeError`, covered by
test_memory_durability). But a record can be perfectly valid JSON and still be
schema-INCOMPLETE — a hand-edit, a partial migration, or an older/foreign writer —
e.g. `123`, `["a"]`, or `{"text": "x"}` with no `emb`/`ts`. `json.loads` accepts all
of those, so the ONLY thing standing between such a record and a crash is
`_valid_memory_record`: the recall hot path dereferences `item["emb"]` and
`item["ts"]` with bare subscripts (`_salience`), so an unguarded schema-incomplete
record would raise KeyError *before the user gets a reply*.

That guard had zero DIRECT coverage — the durability suite only exercised the
JSONDecodeError branch. These tests pin every rejection branch (incl. the non-dict
branch, previously uncovered) and the end-to-end guarantee: a schema-incomplete but
valid-JSON line is dropped at load while the good memories survive and recall works.
"""
import json

import pytest

from memoryagent.memory import MemoryStore

_GOOD = {"text": "ok", "emb": [0.1, 0.2, 0.3], "ts": 1.0}


@pytest.mark.parametrize(
    "rec, why",
    [
        (123, "non-dict: bare number"),
        (["a", "b"], "non-dict: list"),
        ("just a string", "non-dict: string"),
        (None, "non-dict: null"),
        ({"emb": [0.1], "ts": 1.0}, "missing text"),
        ({"text": 42, "emb": [0.1], "ts": 1.0}, "text not a string"),
        ({"text": "   ", "emb": [0.1], "ts": 1.0}, "text blank after strip"),
        ({"text": "x", "ts": 1.0}, "missing emb"),
        ({"text": "x", "emb": "nope", "ts": 1.0}, "emb not a list"),
        ({"text": "x", "emb": [], "ts": 1.0}, "emb empty"),
        ({"text": "x", "emb": ["a"], "ts": 1.0}, "emb has non-number"),
        ({"text": "x", "emb": [True], "ts": 1.0}, "emb has bool (not a real number)"),
        ({"text": "x", "emb": [0.1]}, "missing ts"),
        ({"text": "x", "emb": [0.1], "ts": "soon"}, "ts not a number"),
        ({"text": "x", "emb": [0.1], "ts": True}, "ts is bool (not a real number)"),
    ],
)
def test_rejects_schema_incomplete_record(rec, why):
    assert MemoryStore._valid_memory_record(rec) is False, why


def test_accepts_a_well_formed_record():
    # The positive case must still pass — the guard rejects the bad, keeps the good.
    assert MemoryStore._valid_memory_record(dict(_GOOD)) is True
    # importance stays optional (read via .get elsewhere), int emb/ts are numbers.
    assert MemoryStore._valid_memory_record(
        {"text": "y", "emb": [1, 2], "ts": 3}) is True


def test_load_drops_incomplete_lines_and_recall_survives(patched):
    """End-to-end: a non-dict line and a missing-emb record sit in facts.jsonl
    next to two good facts. Load must drop the bad two (not crash), and recall —
    which dereferences item['emb']/item['ts'] — must run without a KeyError."""
    root = str(patched / "incomplete")
    s = MemoryStore(root=root)
    s.add_fact("User is allergic to peanuts")
    s.add_fact("User lives in Lubbock, TX")

    # Append records that PARSE as JSON but are schema-incomplete (not torn).
    with open(s._p("facts.jsonl"), "a", encoding="utf-8") as f:
        f.write("123\n")                                         # valid JSON, non-dict
        f.write(json.dumps({"text": "no embedding here"}) + "\n")  # missing emb + ts

    reloaded = MemoryStore(root=root)
    texts = {fct["text"] for fct in reloaded.facts}
    # Only the two well-formed facts survive; the incomplete records are dropped.
    assert texts == {"User is allergic to peanuts", "User lives in Lubbock, TX"}
    # The hot path the guard protects does not raise on the reloaded store.
    assert reloaded.recall("peanuts") is not None
