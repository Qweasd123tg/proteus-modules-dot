#!/usr/bin/env python3
"""Exact-source parity for pure Python suffix compaction; never runs a worker."""

import copy
import hashlib
import itertools
import json
from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
PREPARE = Path("examples/modules/context-preparation-process/prepare.py")
RUNTIME = Path("examples/modules/component_runtime.py")
STOCK = "3afaeeb40818e3221d02c170f91c8e031fd5943a"
CANDIDATE = "5cdfc917fb2ae5a3c8aebc207b12e45ddc68294d"
HELPER = "32cc106bf49c82d652dacb2b4ff32f0d1b1c02f0"


def git_blob(path):
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def load(tier, prepare_sha):
    directory = ROOT / tier
    assert git_blob(directory / PREPARE) == prepare_sha
    assert git_blob(directory / RUNTIME) == HELPER
    path_before = list(sys.path)
    assert "component_runtime" not in sys.modules
    try:
        module = runpy.run_path(str(directory / PREPARE), run_name="_r199_compact_" + tier)
        assert Path(sys.modules["component_runtime"].__file__).resolve() == directory / RUNTIME
        return module["compact"]
    finally:
        sys.modules.pop("component_runtime", None)
        sys.path[:] = path_before


def row(tag, i):
    role, scopes = {
        "a": ("Assistant", ["conversation"]),
        "c": ("Assistant", ["request"]),
        "u": ("User", ["conversation"]),
        "r": ("User", ["request", "request"]),
        "m": ("User", ["request", "trace"]),
        "t": ("User", ["trace"]),
        "e": ("User", []),
    }[tag]
    return {
        "id": f"00000000-0000-4000-8000-{i:012x}",
        "role": role,
        "name": "context" if tag == "u" else None,
        "parts": [
            {"part_id": f"00000001-0000-4000-8000-{i * 4 + part:012x}",
             "scope": scope, "payload": {"Text": {"text": f"Synthetic row {i}/{part}"}}}
            for part, scope in enumerate(scopes)
        ],
        "metadata": None,
    }


def payload(rows):
    return {"messages": rows, "request": None, "token_estimate": None,
            "window_tokens": 100, "reason": "synthetic"}


def strategy(trigger, keep):
    return {"trigger_messages": trigger, "retain_user_turns": keep}


def wire(output):
    return json.dumps(output, ensure_ascii=False, separators=(",", ":"))


def valid_case(stock, candidate, tags, trigger, keep, expected, alias=False):
    rows = [row(tag, i) for i, tag in enumerate(tags)]
    if alias:
        rows[-1] = rows[1]
    original_rows = tuple(rows)
    original = copy.deepcopy(rows)
    params = payload(rows)
    config = strategy(trigger, keep)
    expected_indices, expected_reason, expected_users = expected
    old, new = stock(params, config), candidate(params, config)
    assert wire(old) == wire(new), (tags, trigger, keep, expected)
    assert rows == original and all(a is b for a, b in zip(rows, original_rows, strict=True))
    for value in (old, new):
        out = value["output"]
        assert out["changed"] is (expected_reason is None), (tags, trigger, keep, out)
        assert out["skipped_reason"] == expected_reason
        assert out["user_message_replacements"] == []
        assert all(out[key] is None for key in ("token_estimate", "original_token_estimate", "trigger_tokens"))
        if expected_reason is not None:
            assert out["messages"] is rows and out["summary"] is None and out["summary_source"] is None
            assert out["metadata"] == {"strategy": "python_suffix"}
        else:
            assert out["messages"] is not rows
            wanted = [original_rows[i] for i in expected_indices]
            assert len(out["messages"]) == len(wanted)
            assert all(a is b for a, b in zip(out["messages"], wanted, strict=True))
            assert out["metadata"] == {"strategy": "python_suffix", "retained_user_turns": expected_users}
            assert out["summary_source"] == "deterministic_suffix"
            assert out["summary"] == (f"Deterministic suffix compaction retained {expected_users} recent user "
                                      f"turns and dropped {len(rows) - len(wanted)} earlier messages.")


def oracle(tags, trigger, keep):
    if len(tags) <= trigger:
        return (), "below_trigger_messages", 0
    # Category oracle independent of the source predicate and its call order.
    turns = tuple(i for i, tag in enumerate(tags) if tag in {"u", "m", "t", "e"})
    if not turns:
        return (), "no_user_turn_boundary", 0
    users = min(len(turns), keep)
    dropped_before = turns[-users]
    retained = (tuple(i for i in range(dropped_before) if tags[i] in {"c", "r"})
                + tuple(range(dropped_before, len(tags))))
    if len(retained) == len(tags):
        return (), "suffix_would_not_reduce_history", 0
    return retained, None, users


def failure(fn, params, config):
    try:
        fn(params, config)
    except Exception as error:
        return type(error).__name__, str(error)
    raise AssertionError("expected a validation error")


def structural_growth(stock, candidate):
    total = 50_000
    messages = [row("u" if i % 2 else "a", i) for i in range(total)]
    params, opts = payload(messages), strategy(12, 2)
    outcomes, calls = [], []
    for compact in (stock, candidate):
        scope = compact.__globals__
        predicate = scope["is_user_message"]
        seen = 0

        def counted(message):
            nonlocal seen
            seen += 1
            return predicate(message)

        scope["is_user_message"] = counted
        try:
            out = compact(params, opts)
        finally:
            scope["is_user_message"] = predicate
        outcomes.append(out)
        calls.append(seen)
        output_rows = out["output"]["messages"]
        assert len(output_rows) == 3
        assert all(a is b for a, b in zip(output_rows, messages[-3:], strict=True))
    assert calls == [50_003, 3]
    assert wire(outcomes[0]) == wire(outcomes[1])
    return {"messages": total, "stock_matching_user_indices": total // 2, "candidate_index_list": 0,
            "stock_user_predicates": calls[0], "candidate_user_predicates": calls[1], "retained_rows": 3,
            "output_sha256": hashlib.sha256(wire(outcomes[0]).encode()).hexdigest()}


def main():
    stock, candidate = load("stock", STOCK), load("candidate", CANDIDATE)
    explicit = [
        ("auc", 3, 2, ((), "below_trigger_messages", 0), False),
        ("acra", 1, 2, ((), "no_user_turn_boundary", 0), False),
        ("cuae", 1, 2, ((), "suffix_would_not_reduce_history", 0), False),
        ("cauramat aea".replace(" ", ""), 1, 2, ((0, 3, 7, 8, 9, 10), None, 2), False),
        ("aucatca", 1, 10, ((1, 2, 3, 4, 5, 6), None, 2), False),
        ("au", 1, 1, ((1,), None, 1), False),
        ("auau", 1, 2, ((1, 2, 3), None, 2), True),
    ]
    for tags, trigger, keep, expected, alias in explicit:
        valid_case(stock, candidate, tags, trigger, keep, expected, alias)

    coverage = 0
    for length in range(6):
        for tags in itertools.product("acurme", repeat=length):
            for trigger, keep in itertools.product((1, 3), (1, 2, 4, 7)):
                valid_case(stock, candidate, tags, trigger, keep, oracle(tags, trigger, keep))
                coverage += 1

    good = payload([row("u", i) for i in range(8)])
    invalid = [
        (good, strategy(1, -1), "retain_user_turns must be a positive integer"),
        (good, strategy(1, 0), "retain_user_turns must be a positive integer"),
        (good, strategy(1, False), "retain_user_turns must be a positive integer"),
        (good, strategy(1, 2.0), "retain_user_turns must be a positive integer"),
        (good, strategy(1, "2"), "retain_user_turns must be a positive integer"),
        (good, strategy(True, 2), "trigger_messages must be a positive integer"),
        (good, None, "compactor strategy must be an object"),
        (good, {"unknown": True}, "unknown compactor strategy fields"),
        ({**good, "request": []}, strategy(1, 2), "request must be an object or null"),
        ({**good, "messages": [{}]}, strategy(12, 2), "canonical message parts must be an array"),
        ({**good, "messages": None}, strategy(1, 2), "messages must contain canonical objects"),
        ({**good, "messages": [None]}, strategy(1, 2), "messages must contain canonical objects"),
        (dict(good, messages=[{"parts": [None]}, *good["messages"]]), strategy(1, 2), "canonical part scope"),
        (dict(good, messages=[{"parts": [{"scope": "unknown"}]}, *good["messages"]]), strategy(1, 2), "canonical part scope"),
        (dict(good, messages=[*good["messages"], {"parts": [{}]}]), strategy(1, 2), "canonical part scope"),
        ({"messages": []}, strategy(1, 2), "ContextPreparationInput fields mismatch"),
    ]
    for params, opts, expected in invalid:
        old, new = failure(stock, params, opts), failure(candidate, params, opts)
        assert old == new and old[0] == "ProtocolError" and expected in old[1], (expected, old, new)

    result = {"status": "passed", "scope": "exact optional Python compact() only; no workers/provider/Cargo",
              "stock_blob": STOCK, "candidate_blob": CANDIDATE, "shared_helper_blob": HELPER,
              "python_version": sys.version.split()[0], "explicit_cases": len(explicit),
              "exhaustive_cases": coverage, "invalid_cases": len(invalid),
              "structural_workload": structural_growth(stock, candidate)}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
