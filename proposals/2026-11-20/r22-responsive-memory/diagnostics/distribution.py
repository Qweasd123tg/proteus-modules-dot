#!/usr/bin/env python3
"""Attribute SDK terminal response timings from a finished R22 run.

Distributions are wall times; do not add percentiles or assume concurrently
executed phases are an application critical path. Only verified matched frames
with complete successful SDK phases enter the distributions.
"""
import argparse
import collections
import json
import math
from pathlib import Path
import statistics

STAMPS = """admitted_ns dispatch_start_ns storage_start_ns value_start_ns
value_end_ns dispatch_end_ns count_start_ns count_end_ns stdout_lock_ns
encode_end_ns flush_end_ns""".split()
PHASES = {
    "spawn_dispatch": ("admitted_ns", "dispatch_start_ns"),
    "route_decode_validate": ("dispatch_start_ns", "storage_start_ns"),
    "backend_execute": ("storage_start_ns", "value_start_ns"),
    "typed_to_value": ("value_start_ns", "value_end_ns"),
    "envelope": ("dispatch_end_ns", "count_start_ns"),
    "frame_count_preflight": ("count_start_ns", "count_end_ns"),
    "stdout_lock_wait": ("count_end_ns", "stdout_lock_ns"),
    "encode_and_write": ("stdout_lock_ns", "encode_end_ns"),
    "flush_total": ("encode_end_ns", "flush_end_ns"),
}
BUCKETS = [
    (64 * 1024, "<=64KiB"),
    (1024 * 1024, "64KiB..1MiB"),
    (8 * 1024 * 1024, "1..8MiB"),
    (math.inf, ">8MiB"),
]


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def ms(ns):
    return round(ns / 1_000_000, 4)


def metric(values, convert=lambda v: v):
    ordered = sorted(values)
    return {
        "min": convert(ordered[0]),
        "median": convert(statistics.median(ordered)),
        "p95_nearest_rank": convert(ordered[math.ceil(.95 * len(ordered)) - 1]),
        "max": convert(ordered[-1]),
    }


def stages(s):
    times = {phase: s[end] - s[begin] for phase, (begin, end) in PHASES.items()}
    w_encode = s["sink_write_ns_at_encode_end"]
    w_flush = s["sink_write_ns"] - w_encode
    f_sink = s["sink_flush_ns"]
    times.update(
        encode_excluding_sink_write=times["encode_and_write"] - w_encode,
        sink_write_during_encode=w_encode,
        sink_write_during_flush=w_flush,
        sink_flush=f_sink,
        flush_excluding_sink=times["flush_total"] - w_flush - f_sink,
        stdout_lock_hold=s["flush_end_ns"] - s["stdout_lock_ns"],
    )
    return times


def distributions(rows):
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[row["sdk"]["operation"]].append(row)
    return {op: aggregate(bucket) for op, bucket in sorted(grouped.items())}


def aggregate(rows):
    sizes = [r["sdk"]["frame_bytes"] for r in rows]
    keys = [*next(iter(rows))["stages"], "relay_request_response", "relay_end_to_admit"]
    return {
        "n": len(rows),
        "bytes_including_newline": metric(sizes) | {"sum": sum(sizes)},
        "sink_write_calls": metric([r["sdk"]["sink_write_calls"] for r in rows]),
        "stages_ms": {key: metric([r["stages"][key] for r in rows], ms) for key in keys},
    }


def index_unique(rows, key, label):
    indexed = {}
    for row in rows:
        k = row[key]
        if k in indexed:
            raise ValueError(f"duplicate {label}: {k}")
        indexed[k] = row
    return indexed


def analyze(path):
    summary = json.loads((path / "summary.json").read_text())
    if not summary["passed"]:
        raise ValueError("Run did not pass invariant checks")
    hot = summary["hot"]
    start, first_text = hot["start_ns"], hot["sse"]["first_text_ns"]
    wire = jsonl(path / "wire.jsonl")
    state_rows = jsonl(path / "worker-state.jsonl")
    state = collections.defaultdict(list)
    for row in state_rows:
        if row["event"] == "state":
            state[row["pid"], row.get("id")].append(row)
    sdk_rows = jsonl(path / "worker-sdk.jsonl")
    pids = {s["pid"] for s in sdk_rows}
    if len(pids) != 1 or any(row["clock"] != "CLOCK_MONOTONIC" for row in sdk_rows):
        raise ValueError("Expected one SDK worker PID, in the relay's monotonic clock domain")
    requests = index_unique((r for r in wire if r["event"] == "request"), "id", "request")
    responses = index_unique((r for r in wire if r["event"] == "response"), "id", "response")
    sdk_by_id = index_unique(sdk_rows, "id", "SDK")
    acks = [r for r in wire if r["event"] == "commit_ack" and r["kind"] == "turn_opened"
            and r["verified"] and start < r["t"] and r.get("turn_id") == hot["sse"]["turn_open_id"]]
    if len(acks) != 1:
        raise ValueError(f"Expected exactly one verified durable open ACK, got {len(acks)}")
    ack = acks[0]
    excluded = collections.Counter()
    matched = {}
    for ident, s in sdk_by_id.items():
        req, resp = requests.get(ident), responses.get(ident)
        if req is None or resp is None:
            excluded["missing_wire_pair"] += 1
            continue
        if not s["terminal_ok"] or any(s.get(k) is None for k in STAMPS):
            excluded["error_or_incomplete_stages"] += 1
            continue
        if not (s["frame_bytes"] == resp["bytes"] + 1 and req["operation"] == s["operation"]
                and resp["request_end"] == req["t"] <= s["admitted_ns"]
                and s["stdout_lock_ns"] <= resp["t"]):
            excluded["operation_size_or_clock_mismatch"] += 1
            continue
        phase = stages(s)
        if list(sorted(s[k] for k in STAMPS)) != [s[k] for k in STAMPS] or min(phase.values()) < 0:
            raise ValueError(f"Inconsistent SDK boundaries: {ident}")
        phase.update(relay_request_response=resp["t"] - req["t"],
                     relay_end_to_admit=s["admitted_ns"] - req["t"])
        matched[ident] = {"sdk": s, "request": req, "response": resp, "stages": phase}

    foreground = []
    s0 = ack["session_id"]
    for req in sorted(requests.values(), key=lambda r:r["t"]):
        ident = req["id"]
        if req.get("session_id") != s0 or not start <= req["t"] <= first_text:
            continue
        row = matched.get(ident)
        if not row:
            foreground.append(dict(id=ident, operation=req["operation"], matched=False))
            continue
        s = row["sdk"]
        lo, hi = s["count_end_ns"], s["stdout_lock_ns"]
        blockers = []
        for other in matched.values():
            z = other["sdk"]
            overlap = min(hi, z["flush_end_ns"]) - max(lo, z["stdout_lock_ns"])
            if overlap > 0:
                blockers.append(dict(id=z["id"], operation=z["operation"], bytes=z["frame_bytes"],
                                     cold_session=other["request"].get("session_id") not in (None, s0),
                                     overlap_ms=ms(overlap)))
        s_locks = state.get((s["pid"], ident), [])
        foreground.append(dict(
            id=ident, operation=s["operation"], kind=req.get("kind"), matched=True,
            request_from_send_ms=ms(req["t"]-start),
            reply_from_send_ms=ms(row["response"]["t"]-start),
            requested_before_ack=req["t"]<=ack["t"],
            responded_by_ack=row["response"]["t"]<=ack["t"],
            frame_bytes=s["frame_bytes"], stages_ms={k:ms(v) for k,v in row["stages"].items()},
            state_locks=[dict(op=z["op"], state_wait_ms=ms(z["wait_ns"]), state_hold_ms=ms(z["hold_ns"]))
                         for z in s_locks],
            coincident_stdout_holders=sorted(blockers,key=lambda b:-b["overlap_ms"]),
        ))
    cold_lo = min(c["start_ns"] for c in summary["cold"])
    cold_hi = max(c["end_ns"] for c in summary["cold"])
    cold_ids = {r["request"]["session_id"] for r in matched.values()
                if cold_lo <= r["request"]["t"] <= cold_hi and r["sdk"]["operation"]=="open_display_snapshot"
                and r["request"].get("session_id") not in (None, s0)}
    cold = [r for r in matched.values() if r["request"].get("session_id") in cold_ids
            and cold_lo <= r["request"]["t"] <= cold_hi]
    pages = collections.defaultdict(list)
    for row in cold:
        if row["sdk"]["operation"] in ("read_display_records", "read_records"):
            size = row["sdk"]["frame_bytes"]
            b = next(label for n,label in BUCKETS if size<=n)
            pages[b].append(row)
    return dict(
        analysis="single observed instrumented run; wall-time stages and nested sink times",
        run=path.name, pid=next(iter(pids)), sdk_rows=len(sdk_rows), matched=len(matched),
        wire_pairs=len(requests.keys() & responses.keys()),
        missing_sdk_for_wire_pair=len((requests.keys() & responses.keys())-sdk_by_id.keys()),
        excluded=dict(excluded),
        verified_turn_open_ack=dict(id=ack["id"], from_send_ms=ms(ack["t"]-start)),
        first_text_from_send_ms=ms(first_text-start),
        foreground=foreground,
        all_matched_by_op=distributions(matched.values()),
        cold_session_count=len(cold_ids),
        cold_by_op=distributions(cold),
        cold_record_pages_by_frame_size={b:aggregate(pages[b]) for _,b in BUCKETS if pages[b]},
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("run", type=Path, help="Finished R22 evidence directory")
    print(json.dumps(analyze(cli.parse_args().run), indent=2))
