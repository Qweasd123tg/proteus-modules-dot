#!/usr/bin/env python3
"""Attribute worker State wait to simultaneous measured State holders.
Only valid in the same Linux clock domain as the R22 trace and its byte relay.
"""
import argparse
import json
from pathlib import Path

def read(path):
    with path.open() as f:
        return [json.loads(line) for line in f]

def ms(ns):
    return round(ns / 1_000_000, 4)

def relative(row, anchor, keys):
    return {k.removesuffix("_ns") + "_ms": ms(row[k] - anchor) for k in keys if k in row}

def main(path):
    start = json.loads((path / "hot-reply.json").read_text())["start_ns"]
    wire = read(path / "wire.jsonl")
    locks = [row for row in read(path / "worker-state.jsonl") if row["event"] == "state"]
    pairs = {}
    for row in wire:
        if row["event"] in ("request", "response"):
            pairs.setdefault(row["id"], {})[row["event"]] = row
    acks = [w for w in wire if w["event"] == "commit_ack" and w["verified"] and w["kind"] == "turn_opened" and w["t"] > start]
    if not acks:
        raise ValueError("no matched post-send durable TurnOpened ACK")
    ack = min(acks, key=lambda w: w["t"])
    first_text = json.loads((path / "summary.json").read_text())["hot"]["sse"]["first_text_ns"]
    anchors = [p for p in pairs.values() if "request" in p and "response" in p and p["request"].get("session_id") == ack["session_id"]
               and start <= p["request"]["start"] <= first_text]
    details = []
    for p in sorted(anchors,key=lambda p:p["request"]["start"]):
        req,resp=p["request"],p["response"]
        record = dict(id=req["id"],op=req["operation"],kind=req.get("kind"),
                      relay_request_ms=ms(req["t"]-start), relay_reply_ms=ms(resp["t"]-start),
                      before_ack=req["t"]<=ack["t"], locks=[])
        for row in sorted((s for s in locks if s.get("id")==req["id"]),key=lambda s:s["acquired_ns"]):
            lo,hi=row["wait_start_ns"],row["acquired_ns"]
            held=[]
            for other in locks:
                if other is row or other["pid"]!=row["pid"]:
                    continue
                a,b=max(lo,other["acquired_ns"]), min(hi,other["release_ns"])
                if a < b:
                    held.append((a,b,{k:other.get(k) for k in ("id","op","session_id","kind","seq")}))
            held.sort(key=lambda i:i[0])
            for left,right in zip(held,held[1:]):
                if right[0] < left[1]:
                    raise ValueError("traced State holds overlap; clock or lock scope mismatch")
            record["locks"].append(dict(
                **relative(row,start,("wait_start_ns","acquired_ns","release_ns","released_ns")),
                wait_ms=ms(hi-lo),hold_ms=ms(row["release_ns"]-hi),
                unexplained_wait_ms=ms(hi-lo-sum(b-a for a,b,_ in held)),
                holders=[dict(**data,overlap_ms=ms(b-a),from_send_ms=ms(a-start)) for a,b,data in held],
                stages=row.get("stages"),
            ))
        details.append(record)
    display_locks = [dict(id=s.get("id"), session_id=s.get("session_id"),
                           **relative(s,start,("wait_start_ns","acquired_ns","release_ns")),
                           hold_ms=ms(s["release_ns"]-s["acquired_ns"]), stages=s.get("stages"))
                     for s in locks if s["op"]=="open_display_snapshot"]
    sdk = path / "worker-sdk.jsonl"
    if sdk.exists():
        sdk_by_id={s["id"]:s for s in read(sdk) if s["clock"]=="CLOCK_MONOTONIC"}
        intervals=(
            ("admission_to_dispatch", "admitted_ns", "dispatch_start_ns"),
            ("value", "value_start_ns", "value_end_ns"),
            ("counting", "count_start_ns", "count_end_ns"),
            ("stdout_wait", "count_end_ns", "stdout_lock_ns"),
            ("encode", "stdout_lock_ns", "encode_end_ns"),
            ("flush", "encode_end_ns", "flush_end_ns"),
        )
        for record in details:
            row=sdk_by_id.get(record["id"])
            if row is None:
                continue
            record["sdk"]={label+"_ms":ms(row[b]-row[a]) for label,a,b in intervals
                           if row.get(a) is not None and row.get(b) is not None}
            record["sdk"].update(frame_bytes=row["frame_bytes"], sink_write_ms=ms(row["sink_write_ns"]),
                                 sink_flush_ms=ms(row["sink_flush_ns"]))
    return dict(trace=str(path), ack_ms=ms(ack["t"]-start), first_text_ms=ms(first_text-start),
                state_records=len(locks), foreground=details, display_locks=display_locks)

if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("path",type=Path)
    args=p.parse_args()
    print(json.dumps(main(args.path),indent=2))
