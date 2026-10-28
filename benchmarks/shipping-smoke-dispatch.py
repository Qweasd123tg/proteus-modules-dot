"""Private four-cell resource-only dispatcher. No top-level execution.
Admission/build integration and external authorization are mandatory, not inferred.
"""
import copy
import hashlib
import json
import time
from pathlib import Path

TABLE = (("smoke-01", "baseline", "small", 4096),
         ("smoke-02", "candidate", "small", 4096),
         ("smoke-03", "baseline", "large", 1048576),
         ("smoke-04", "candidate", "large", 1048576))


def raw_jsonl(primitives, path):
    raw = primitives.owned_bytes(Path(path).parent, Path(path).name, 128*1024**2)
    primitives.require(raw.endswith(b"\n"), "incomplete stdout")
    rows = []
    for line in raw.splitlines():
        primitives.require(line and len(line) + 1 <= 8*1024**2, "encoded frame cap")
        rows.append(primitives.strict(line.decode("utf-8", "strict")))
        primitives.require(len(rows) <= 16384, "stdout row count")
    return rows


def command_output(primitives, rows, ident):
    found = [row["output"] for row in rows
             if row.get("type") == "response" and row.get("id") == ident and row.get("ok") is True]
    primitives.require(len(found) == 1, "missing/duplicate terminal response")
    return found[0]


def discover_session(primitives, supervisor, config_root, expected, cap):
    journals = [path for path, _ in supervisor.files(config_root)
                if path.name == "journal.jsonl"]
    primitives.require(len(journals) == 1, "fresh procedure has ambiguous session")
    session = journals[0].parent
    raw = primitives.owned_bytes(session, "journal.jsonl", cap)
    first = primitives.strict(raw.splitlines()[0])
    primitives.require(first["session_id"] == expected, "session path attribution")
    return str(session)


def wire_witness(primitives, capture, destination, receipt):
    root = Path(destination)
    raw = primitives.owned_bytes(root, "stdout.raw", 128*1024**2)
    rows = raw_jsonl(primitives, root / "stdout.raw")
    frames = [{"encoded_bytes": len(line) + 1,
               "sha256": hashlib.sha256(line + b"\n").hexdigest()}
              for line in raw.split(b"\n")[:-1]]
    primitives.require(frames == receipt["raw_capture"]["stdout_frames"],
                       "raw/output frame inventory differs")
    inputs = receipt["input_frames"]
    primitives.require(inputs and all(frame["complete"] is True
        and frame["encoded_bytes"] == frame["written_bytes"]
        and 0 < frame["encoded_bytes"] <= capture.LINE_LIMIT for frame in inputs),
        "incomplete actual input frames")
    snapshots = [frames[index] for index, row in enumerate(rows)
                 if row.get("type") == "event" and row["event"].get("type") == "session_snapshot"]
    primitives.require(snapshots, "missing actual encoded snapshot witness")
    return {"stdout_bytes": len(raw), "stdout_sha256": hashlib.sha256(raw).hexdigest(),
            "maximum_input_frame_bytes": max(frame["encoded_bytes"] for frame in inputs),
            "maximum_output_frame_bytes": max(frame["encoded_bytes"] for frame in frames),
            "snapshot_frames": snapshots, "input_frames": inputs}


def prefix_unchanged(primitives, path, before, cap):
    raw = primitives.owned_bytes(Path(path).parent, Path(path).name, cap)
    primitives.require(len(raw) >= before["bytes"]
                       and hashlib.sha256(raw[:before["bytes"]]).hexdigest() == before["sha256"],
                       "closed evidence prefix was replaced or truncated")
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def one_procedure(mod, shared, item, root, authorization_sha):
    """Called by a hard-supervised worker. Result is never a latency observation."""
    p, c, sem, seed, profile, sup = (mod[key] for key in
                                   ("primitives", "capture", "semantics", "seed", "profile", "supervisor"))
    ident, arm, cell, payload = item
    started, deadline = time.monotonic(), time.monotonic() + 235
    root = Path(root)
    config_root = root / "config"
    config_root.mkdir(mode=0o700)
    (root / "replay").mkdir(mode=0o700)
    binary = shared["binaries"][arm]
    nonce = hashlib.sha256((shared["attempt_id"] + ":" + ident).encode()).hexdigest()[:32]
    seed_config = config_root / "seed.json"
    measure_config = config_root / "measure.json"
    journal_cap = sup.CAPS[cell]["journal"]*sup.MIB
    event_cap = sup.CAPS[cell]["events"]*sup.MIB
    seed_profile = profile.profile(shared["paths"], "seed", "resource", payload, nonce,
                                   str(root / "seed"))
    sup.write_json(seed_config, seed_profile)
    seed_config_sha = c.sha(seed_config)
    spec = {"binary": binary["path"], "binary_sha256": binary["sha256"],
            "config": str(seed_config), "workspace": shared["workspace"],
            "evidence_root": str(root),
            "payload_bytes": payload, "env": shared["runtime_env"],
            "run_id": shared["attempt_id"] + ":" + ident + ":seed", "seconds": 70}
    seeded = seed.serve(c, sem, spec, root / "seed")
    p.require(seeded["status"] == "PENDING_CANONICAL_VERIFICATION", "seed transport failed")
    seed_wire = wire_witness(p, c, root / "seed", seeded)
    session_id = seeded["session_id"]
    session = discover_session(p, sup, config_root, session_id, journal_cap)
    relative_session = str(Path(session).relative_to(root))
    cache_paths = [relative_session + "/.read-" + name + ".sqlite" + suffix
                   for name in ("view", "summary") for suffix in ("", "-wal", "-shm")]
    discovery = p.strict(p.owned_bytes(root, "session-discovery.json", 16384))
    p.require(discovery["schema"] == "shipping-smoke-session-discovery-v1"
              and discovery["session_id"] == session_id
              and discovery["session_relative"] == relative_session
              and discovery["cache_paths"] == cache_paths, "session discovery changed")
    records, inventory, seed_journal_wire = p.journal_records(session, session_id, journal_cap)
    seed_inventory = copy.deepcopy(inventory)
    verified_seed = sem.canonical_turns(records, session_id, seeded["turns"],
                                     payload//16, False, shared["workspace"], p.token_estimate_text_request)
    measure_profile = profile.profile(shared["paths"], "measure", "resource", payload, nonce,
        str(root / "sample"),
        [row["user_id"] for row in verified_seed["turns"]],
        [row["user_part_id"] for row in verified_seed["turns"]])
    # Same profile/summary in readiness and measurement; event output is outside
    # sample so readiness cannot precreate capture's exclusive destination.
    measure_profile["event_log"]["path"] = str(root / "events-measure" / "events.jsonl")
    sup.write_json(measure_config, measure_profile)
    measure_config_sha = c.sha(measure_config)
    inspection = dict(spec, config=str(measure_config), session_id=session_id, session_dir=session,
                      run_id=shared["attempt_id"] + ":" + ident + ":readiness", seconds=20)
    ready = seed.serve(c, sem, inspection, root / "readiness", inspect_only=True)
    p.require(ready["status"] == "PENDING_CANONICAL_VERIFICATION", "readiness failed")
    readiness_wire = wire_witness(p, c, root / "readiness", ready)
    event_path = root / "events-measure" / "events.jsonl"
    event_raw = p.owned_bytes(event_path.parent, event_path.name, event_cap)
    readiness_events = {"bytes": len(event_raw), "sha256": p.digest(event_raw)}
    p.verify_source_unchanged(session, inventory)
    p.require(ready["snapshot"]["transcript"] == seeded["snapshot"]["transcript"]
              and ready["snapshot"]["history"] == seeded["snapshot"]["history"],
              "resume display history changed")
    predicted = copy.deepcopy(verified_seed["requests"][-1])
    current = copy.deepcopy(verified_seed["history"][-2])
    current["id"], current["parts"][0]["part_id"] = (
        "33333333-3333-4333-8333-333333333331", "33333333-3333-4333-8333-333333333332")
    current["parts"][0]["payload"] = {"Text": {"text": sem.TASK}}
    predicted["messages"] = verified_seed["history"] + [current]
    bounds = {"status": "SMOKE_ADMISSION_CAP_WITH_POSTFLIGHT_REQUIRED",
              "observed_seed_request_max_bytes": max(x["request_bytes"] for x in verified_seed["turns"]),
              "actual_initial_snapshot_bytes": len(sem.encoded(ready["snapshot"])),
              "predicted_message_only_successor_request_bytes": len(sem.encoded(predicted)),
              "frame_acceptance_cap": c.LINE_LIMIT,
              "not_a_proof_of_all_future_encoded_frames": True}
    p.require(max(bounds["actual_initial_snapshot_bytes"],
                  bounds["predicted_message_only_successor_request_bytes"]) <= c.LINE_LIMIT,
              "preflight witnesses already exceed frame cap")
    sup.write_json(root / "wire-admission.json", bounds)
    input_files = shared["input_files"] + [{"path": str(measure_config), "sha256": c.sha(measure_config)}]
    run_id = shared["attempt_id"] + ":" + ident + ":measure"
    plan = {"schema": "authenticated-shipping-sample-v1", "mode": "resource",
            "payload_bytes": payload, "qualification_status": "EXACT_FINAL_COMPOSITION_PASS",
            "root_authorization_receipt_sha256": authorization_sha,
            "max_encoded_witness_bytes": c.LINE_LIMIT,
            "wire_bounds_receipt_sha256": c.sha(root / "wire-admission.json"),
            "env": shared["runtime_env"], "session_id": session_id, "run_id": run_id,
            "binary": binary["path"], "binary_sha256": binary["sha256"],
            "config": str(measure_config), "workspace": shared["workspace"], "session_dir": session,
            "nonce": nonce, "input_files": input_files,
            "config_summary_sha256": sem.sha(ready["config_summary"]),
            "seed_transcript": ready["snapshot"]["transcript"],
            "seed_history_cursor": ready["snapshot"]["history"],
            "run_options": {"intent": None, "permission_mode": "normal"}}
    observed = c.capture(plan, root / "sample")
    p.require(observed["status"] == "PENDING_CANONICAL_VERIFICATION"
              and observed["latency_ns"] is None, "resource capture did not complete")
    sample_wire = wire_witness(p, c, root / "sample", observed)
    rows = raw_jsonl(p, root / "sample/stdout.raw")
    wire = {"turn_id": observed["turn_id"], "thread_id": observed["thread_id"],
            "output": command_output(p, rows, run_id), "run_id": run_id,
            "config_identity": sem.config_identity(ready["config_summary"])}
    records, inventory, final_journal_wire = p.journal_records(session, session_id, journal_cap)
    prefix_unchanged(p, Path(session)/"journal.jsonl", seed_inventory["journal.jsonl"], journal_cap)
    p.verify_source_unchanged(session, {key: value for key, value in seed_inventory.items()
                                       if key != "journal.jsonl"})
    final_events = prefix_unchanged(p, event_path, readiness_events, event_cap)
    verified = sem.canonical_turns(records, session_id, seeded["turns"]+[wire],
                                  payload//16, True, shared["workspace"], p.token_estimate_text_request)
    p.require(verified["turns"][-1]["request_sha256"] == observed["hold_ready"]["request_sha256"],
              "held actual request differs from durable canonical request")
    replay_receipts = []
    for label, config, turn in (("seed-final", seed_config, seeded["turns"][-1]),
                                ("measured", measure_config, wire)):
        p.require(time.monotonic() < deadline-30, "replay time budget")
        out = root / "replay" / label
        sup.command(p.shipping_replay_argv(binary["path"], config, session, turn["turn_id"]),
                    shared["workspace"], shared["runtime_env"], out, 29, 2*sup.MIB-65536)
        report = p.strict((out / "stdout.raw").read_bytes())
        sem.replay_report(report, turn, session_id, str(Path(session)/"journal.jsonl"))
        replay_receipts.append({"label": label, "config_sha256": c.sha(config),
            "stdout_sha256": c.sha(out/"stdout.raw"), "stderr_sha256": c.sha(out/"stderr.raw"),
            "source_evidence": "SOURCE_VERIFIED_REPLAY_SUBSTITUTION",
            "runtime_process_non_start": "NOT_INDEPENDENTLY_OBSERVED"})
        p.verify_source_unchanged(session, inventory)
    p.require(c.sha(seed_config) == seed_config_sha and c.sha(measure_config) == measure_config_sha,
              "seed/measure profile changed")
    p.require(prefix_unchanged(p, event_path, final_events, event_cap) == final_events,
              "replay changed retained event stream")
    normalized = sem.semantic_requests(verified)
    # Persist mappings and hashes, not a second copy of MiB histories/requests.
    sup.write_json(root / "semantic-mapping.json", normalized["typed_mapping"])
    result = {"status": "PROCEDURE_FEASIBILITY_COMPLETE", "id": ident, "arm": arm, "cell": cell,
              "session_id": session_id, "turns": verified["turns"],
              "cache_paths": cache_paths, "recorded_config_sha256": verified["recorded_config_sha256"],
              "wire_witnesses": {"seed": seed_wire, "readiness": readiness_wire,
                                 "sample": sample_wire, "seed_journal": seed_journal_wire,
                                 "final_journal": final_journal_wire},
              "measure_event_stream": {"scope": "readiness and measured processes, append-only",
                                       "readiness_prefix": readiness_events, "final": final_events},
              "replay_receipts": replay_receipts,
              "module_rpc_bounds": {
                  "status": "MODULE_RPC_LENGTH_SOURCE_ENFORCED_NOT_CAPTURED",
                  "outgoing_json_body_max_bytes": 8*sup.MIB,
                  "outgoing_newline_wire_max_bytes": 8*sup.MIB + 1,
                  "incoming_line_including_lf_max_bytes": 8*sup.MIB,
                  "observed_raw_module_rpc_length": None},
              "canonical_inventory": inventory, "resource_capture_status": observed["status"],
              "semantic_requests_sha256": sem.sha(normalized["requests"]),
              "typed_mapping_sha256": sem.sha(normalized["typed_mapping"]),
              "resource_receipt": "sample/attempt.json", "performance_claim": None,
              "actual_max_output_frame": observed["raw_capture"]["max_line_bytes"],
              "elapsed_seconds": time.monotonic()-started}
    p.require(time.monotonic() < deadline, "procedure deadline")
    return result


def summarize_procedure_result(value):
    """Pure bounded control-plane projection; full result stays in raw evidence."""
    keys = ("status", "id", "arm", "cell", "session_id", "semantic_requests_sha256",
            "typed_mapping_sha256", "recorded_config_sha256", "cache_paths",
            "resource_capture_status", "resource_receipt", "performance_claim")
    result = {key: value[key] for key in keys}
    if len(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()) > 8192:
        raise RuntimeError("procedure summary cap")
    return result


def four(mod, shared, work, evidence, authorization_sha):
    p, sup, c = (mod[key] for key in ("primitives", "supervisor", "capture"))
    root, archive = Path(work), Path(evidence)
    archive.mkdir(mode=0o700, parents=False, exist_ok=False)
    outcomes, retained, failure = [], 0, None
    for item in TABLE:
        ident, arm, cell, payload = item
        controls = shared["control_budget"]
        if shared["control_sync"](controls, time.monotonic()) <= 155:
            failure = "control budget cannot preserve retention and terminal reserves"
            break
        procedure = root / ident
        procedure.mkdir(mode=0o700)
        result_path = procedure / "worker-result.json"
        controls = shared["control_budget"]
        shared["control_sync"](controls, time.monotonic())
        observer = controls.get("outer_observer")
        procedure_started = None
        try:
            if observer is not None:
                observer({"event": "begin", "phase": "procedure-"+ident,
                          "cap_seconds": 240.0, "at": time.monotonic()})
            # Any outer admission/ACK wait is charged control time.
            procedure_started = time.monotonic()
            guard = sup.supervise(c, one_procedure, (mod, shared, item, procedure, authorization_sha),
                                  procedure, sup.CAPS[cell], 240, result_path,
                                  result_summary=summarize_procedure_result)
        except BaseException as error:
            guard = {"status": "FAILED_CENSORED", "value": None,
                     "reason": "procedure supervision: " + type(error).__name__ + ": " + str(error)[:2048]}
        finally:
            if procedure_started is not None:
                procedure_finished = time.monotonic()
                excluded = min(240.0, max(0.0, procedure_finished-procedure_started))
                controls["excluded_noncontrol_seconds"] += excluded
                shared["control_sync"](controls, time.monotonic())
                if observer is not None:
                    try:
                        observer({"event": "end", "phase": "procedure-"+ident,
                                  "call_started": procedure_started,
                                  "call_finished": procedure_finished,
                                  "excluded_seconds": excluded,
                                  "cumulative_excluded_seconds": controls["excluded_noncontrol_seconds"]})
                    except BaseException as error:
                        # A broken outer control channel must not bypass raw
                        # failure retention or promote a completed inner stage.
                        guard["status"] = "FAILED_CENSORED"
                        guard["outer_control_observer_error"] = (
                            type(error).__name__ + ": " + str(error)[:2048])
            shared["control_sync"](controls, time.monotonic())
        # No parent filesystem read: a torn/failed result write is already a failed
        # supervised stage, and its raw prefix must still reach retention.
        value = ({"status": "WORKER_RETURNED", "value": guard["value"]}
                 if guard["status"] == "SUPERVISED_STAGE_COMPLETE"
                 and isinstance(guard.get("value"), dict) else None)
        valid = (guard["status"] == "SUPERVISED_STAGE_COMPLETE" and value is not None
                 and value["status"] == "WORKER_RETURNED"
                 and value["value"]["status"] == "PROCEDURE_FEASIBILITY_COMPLETE"
                 and (value["value"]["id"], value["value"]["arm"], value["value"]["cell"]) ==
                     (ident, arm, cell) and value["value"]["performance_claim"] is None)
        control_started = time.monotonic()
        available = shared["control_sync"](controls, control_started) - 150
        if available <= 5 or time.monotonic() >= shared["attempt_deadline"]:
            manifest = {"status": "FAILED_CENSORED", "retained_bytes_including_manifest": 0,
                        "reason": "retention control budget exhausted",
                        "original_evidence_preserved_at": str(procedure),
                        "complete_primary_evidence": False}
        else:
            try:
                cache_paths = (value["value"]["cache_paths"] if valid else ())
                manifest = sup.retain(procedure, archive / ident, sup.CAPS[cell],
                    464*sup.MIB-retained, ledger=shared["evidence_ledger"], capture=c,
                    deadline=min(shared["attempt_deadline"], control_started + min(45, available)),
                    bucket=ident, cache_paths=cache_paths,
                    expected_files=({"worker-result.json": {
                        "bytes": guard["result_receipt"]["bytes"],
                        "sha256": guard["result_receipt"]["sha256"]}}
                        if isinstance(guard.get("result_receipt"), dict) else {}))
            except BaseException as error:
                manifest = {"status": "FAILED_CENSORED", "retained_bytes_including_manifest": 0,
                            "reason": type(error).__name__ + ": " + str(error)[:2048],
                            "original_evidence_preserved_at": str(procedure),
                            "retention_accounting": "UNKNOWN; finalizer must fail closed",
                            "complete_primary_evidence": False}
            finally:
                shared["control_sync"](controls, time.monotonic())
        retained += manifest["retained_bytes_including_manifest"]
        valid = (valid and manifest["status"] == "COMPLETE_PRIMARY_EVIDENCE"
                 and shared["control_sync"](controls, time.monotonic()) > 0)
        outcomes.append({"id": ident, "arm": arm, "cell": cell, "supervision": guard,
                         "result": value, "retention": manifest, "valid": valid})
        if not valid:
            failure = "first failed/censored procedure"
            break
    if failure is None:
        for cell in ("small", "large"):
            pair = [(row["result"]["value"]["semantic_requests_sha256"],
                     row["result"]["value"]["recorded_config_sha256"])
                    for row in outcomes if row["cell"] == cell]
            if len(pair) != 2 or pair[0] != pair[1]:
                failure = "cross-arm typed semantic requests or recorded configuration differ"
    return {"status": "FEASIBILITY_SMOKE_COMPLETE" if failure is None else "FAILED_CENSORED",
            "reason": failure, "attempt_table": TABLE, "outcomes": outcomes,
            "unattempted": [item[0] for item in TABLE[len(outcomes):]],
            "retained_procedure_bytes": retained, "latency_or_effect_statistics": None}
