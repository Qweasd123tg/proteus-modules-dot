"""Private text-only smoke canonical checks; source-only draft, never imported here.
Core shipping replay remains the typed DTO/projection validator.
"""
import copy
import hashlib
import json
import uuid

TASK = "Run the fixed benchmark probe calls, then finish."
BASE = uuid.UUID("11111111-1111-4111-8111-111111111100").int
MAX_FRAME = 8 * 1024 * 1024


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def same(left, right):
    return encoded(left) == encoded(right)


def sha(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def assistant(index):
    measured = index == 16
    return {"id": "22222222-2222-4222-8222-222222222221" if measured
            else str(uuid.UUID(int=BASE + 2 * index)),
            "role": "Assistant", "phase": "final_answer",
            "parts": [{"part_id": "22222222-2222-4222-8222-222222222222" if measured
                       else str(uuid.UUID(int=BASE + 2 * index + 1)),
                       "provenance": "model", "scope": "conversation",
                       "payload": {"Text": {"text": "benchmark complete" if measured
                                             else "seed accepted"}}}],
            "name": None, "tool_call_id": None, "metadata": None}


def user(message, text):
    need(set(message) == {"id", "role", "phase", "parts", "name", "tool_call_id", "metadata"},
         "user message fields")
    need(message["role"] == "User" and message["phase"] is None and message["name"] is None
         and message["tool_call_id"] is None and message["metadata"] is None
         and len(message["parts"]) == 1, "user message shape")
    part = message["parts"][0]
    need(set(part) == {"part_id", "provenance", "scope", "payload"}
         and part["provenance"] == "user" and part["scope"] == "conversation"
         and part["payload"] == {"Text": {"text": text}}, "user payload changed")
    for value in (message["id"], part["part_id"]):
        need(isinstance(value, str) and str(uuid.UUID(value)) == value, "user UUID")
    return message["id"], part["part_id"]


def config_identity(summary):
    need(type(summary["module_epoch"]) is int and summary["module_epoch"] >= 0,
         "config epoch type")
    need(isinstance(summary["profile"], str) and summary["profile"], "config profile")
    need(summary["model"]["provider"] == "release-probe"
         and summary["model"]["name"] == "fixture", "authenticated model selector")
    return {"module_epoch": summary["module_epoch"], "profile_name": summary["profile"]}


def snapshot_identity(opening, expected):
    snapshot = opening["config_snapshot"]
    need(set(snapshot) == {"schema_version", "ts", "profile_name", "active_provider",
                           "model", "reasoning", "modules", "agent_control_surface",
                           "tools", "permission_mode_default", "approval_available"},
         "recorded config snapshot fields")
    need(type(snapshot["schema_version"]) is int and snapshot["schema_version"] == 8
         and type(snapshot["ts"]) is int and snapshot["ts"] >= 0,
         "recorded config snapshot version/time")
    need(type(opening["module_epoch"]) is int
         and opening["module_epoch"] == expected["module_epoch"]
         and snapshot["profile_name"] == expected["profile_name"], "config epoch/profile drift")
    need(snapshot["active_provider"] == "fixture"
         and same(snapshot["model"], {"provider": "release-probe", "model": "fixture"})
         and same(snapshot["modules"], {"workflow": "coding.codex_loop", "policy": "allow_all",
                                        "hooks": [], "context": None})
         and snapshot["agent_control_surface"] == "none", "recorded config selector drift")
    need(same(snapshot["reasoning"], {"effort": None, "summary": False, "budget_tokens": None}),
         "unexpected reasoning")
    need(type(snapshot["approval_available"]) is bool and len(snapshot["tools"]) == 1
         and snapshot["tools"][0]["spec"]["name"] == "benchmark_probe"
         and snapshot["tools"][0]["model_visible"] is True, "recorded tool surface")
    return {key: value for key, value in snapshot.items() if key != "ts"}


def canonical_turns(records, session, transcript_turns, payload_each, measured, workspace, estimate):
    """Validate every record's attribution/order, then exact text-history witnesses.
    No raw record is discarded: caller retains original journal and all blobs.
    """
    count = 17 if measured else 16
    need(payload_each in (256, 65536) and len(transcript_turns) == count, "workload inventory")
    turn_ids = [row["turn_id"] for row in transcript_turns]
    need(len(set(turn_ids)) == count, "duplicate turn")
    groups = {turn: [] for turn in turn_ids}
    for record in records:
        need(record["session_id"] == session and record["turn_id"] in groups,
             "unattributed or foreign record")
        need(not record["kind"].startswith(("tool_call", "tool_result", "tool_effect")),
             "tool invocation forbidden")
        groups[record["turn_id"]].append(record)
    history, revision, requests, inventory = [], 0, [], []
    config_witnesses, executions, exchanges = [], set(), set()
    all_ids, all_parts = set(), set()
    last_seq = 0
    for index, wire in enumerate(transcript_turns):
        rows = groups[wire["turn_id"]]
        need(rows and rows[0]["session_seq"] > last_seq, "interleaved root turns")
        last_seq = rows[-1]["session_seq"]
        need(all(row["thread_id"] == wire["thread_id"] for row in rows), "thread attribution")
        execution = rows[0]["execution_id"]
        need(isinstance(execution, str) and str(uuid.UUID(execution)) == execution
             and execution not in executions
             and all(row["execution_id"] == (None if row["kind"] in
                     ("history_mutated", "turn_settled") else execution) for row in rows),
             "typed execution attribution")
        executions.add(execution)
        kinds = {}
        for row in rows:
            kinds.setdefault(row["kind"], []).append(row)
        for kind in ("turn_opened", "model_request_recorded", "model_message_recorded",
                     "model_response_recorded", "turn_settled"):
            need(len(kinds.get(kind, [])) == 1, "missing or extra " + kind)
        opened = kinds["turn_opened"][0]
        request_row = kinds["model_request_recorded"][0]
        message_row = kinds["model_message_recorded"][0]
        response_row = kinds["model_response_recorded"][0]
        settled = kinds["turn_settled"][0]
        need(opened == rows[0] and settled == rows[-1], "turn boundary order")
        need(opened["session_seq"] < request_row["session_seq"] < message_row["session_seq"]
             < response_row["session_seq"] < settled["session_seq"], "exchange order")
        text = TASK if index == 16 else "A" * payload_each
        opening = opened["payload"]
        config_witnesses.append(snapshot_identity(opening, wire["config_identity"]))
        need(opening["base_history_revision"] == revision and opening["intent"] is None,
             "turn base revision/intent")
        need(opening["task"]["text"] == text and opening["task"]["cwd"] == workspace,
             "canonical task identity")
        request_payload = request_row["payload"]
        request = request_payload["request"]
        exchange = request_payload["exchange_id"]
        need(isinstance(exchange, str) and str(uuid.UUID(exchange)) == exchange
             and exchange not in exchanges, "exchange identity reuse")
        exchanges.add(exchange)
        need(request_payload["origin"] == "direct"
             and same(request_payload["owner"], {"owner": "workflow"}),
             "non-workflow or auxiliary model exchange")
        need(message_row["payload"]["exchange_id"] == exchange
             and response_row["payload"]["exchange_id"] == exchange, "exchange mismatch")
        identity = {key: request["client_metadata"][key]
                    for key in ("session_id", "thread_id", "turn_id")}
        need(identity == {"session_id": session, "thread_id": wire["thread_id"],
                          "turn_id": wire["turn_id"]}, "model request attribution")
        need(same(request["messages"][:-1], history) and len(request["messages"]) == 2 * index + 1,
             "history trimmed, reordered, changed or compacted")
        current = request["messages"][-1]
        mid, part = user(current, text)
        expected = assistant(index)
        need(mid not in all_ids and part not in all_parts and expected["id"] not in all_ids
             and expected["parts"][0]["part_id"] not in all_parts
             and mid != expected["id"] and part != expected["parts"][0]["part_id"],
             "canonical ID reuse")
        all_ids.update((mid, expected["id"]))
        all_parts.update((part, expected["parts"][0]["part_id"]))
        need(request["limits"]["max_input_tokens"] == 2097152
             and request["limits"]["max_output_tokens"] == 4096, "model window changed")
        need(len(request["tools"]) == 1 and request["tools"][0]["name"] == "benchmark_probe",
             "tool surface changed")
        token_receipt = estimate(request)
        need(token_receipt["total"] <= 1048576, "complete token estimate exceeds headroom")
        need(len(encoded(request)) <= MAX_FRAME, "encoded model request exceeds frame budget")
        need(same(message_row["payload"]["message"], expected), "accepted message differs")
        need(same(response_row["payload"]["outcome"], {"status": "response", "response": {
            "messages": [expected], "tool_calls": [], "finish_reason": "Stop",
            "usage": None, "end_turn": True, "provider_metadata": None}}), "model terminal differs")
        need(wire["output"]["text"] == ("benchmark complete" if index == 16 else "seed accepted")
             and {key: wire["output"]["metadata"][key] for key in identity} == identity,
             "wire output attribution/text")
        need(same(settled["payload"], {"status": "success", "output": wire["output"], "error": None}),
             "canonical settlement differs from wire")
        projected = list(history)
        current_committed = assistant_committed = False
        mutations = kinds.get("history_mutated", [])
        need(2 <= len(mutations) <= 8, "history mutation count")
        for mutation_row in mutations:
            mutation = mutation_row["payload"]
            report = mutation["compaction"]
            need(mutation["previous_revision"] == revision
                 and mutation["new_revision"] == revision + 1
                 and mutation["tool_results"] == []
                 and (report is None or report.get("changed") is False),
                 "history revision or changed compaction")
            if mutation["mutation"] == "append":
                projected = projected + mutation["messages"]
            else:
                need(mutation["mutation"] == "checkpoint", "history replacement forbidden")
                projected = mutation["messages"]
            before_request = mutation_row["session_seq"] < request_row["session_seq"]
            allowed = history + [current]
            if not before_request:
                allowed = history + [current, expected]
            need(same(projected, allowed) or (not before_request and not assistant_committed
                                                 and same(projected, history + [current])),
                 "checkpoint changed/dropped/added history")
            if before_request:
                current_committed = True
            else:
                need(current_committed, "model request before durable current-user admission")
            if len(projected) == len(history) + 2:
                assistant_committed = True
                need(mutation_row["session_seq"] > message_row["session_seq"],
                     "assistant history before accepted model message")
            revision += 1
        need(same(projected, history + [current, expected]), "terminal history incomplete")
        history.extend((current, expected))
        requests.append(request)
        inventory.append({"turn_id": wire["turn_id"], "thread_id": wire["thread_id"],
                          "execution_id": execution, "exchange_id": exchange,
                          "user_id": mid, "user_part_id": part,
                          "config_identity": wire["config_identity"],
                          "request_sha256": sha(request), "request_bytes": len(encoded(request)),
                          "estimated_tokens": token_receipt, "settlement_sha256": sha(settled["payload"])})
    need(all(same(value, config_witnesses[0]) for value in config_witnesses),
         "recorded config changed within procedure")
    return {"history": history, "requests": requests, "turns": inventory, "revision": revision,
            "recorded_config_sha256": sha(config_witnesses[0])}


def semantic_requests(verified):
    """Only explicit typed slots are normalized; unknown volatile fields fail equality."""
    requests = copy.deepcopy(verified["requests"])
    mapping = {}
    thread_ordinals = {}
    def bind(kind, original, replacement):
        key = kind + ":" + original
        need(key not in mapping or mapping[key] == replacement, "nonbijective typed mapping")
        need(replacement not in mapping.values() or mapping.get(key) == replacement,
             "many-to-one typed mapping")
        mapping[key] = replacement
        return replacement
    for index, request in enumerate(requests):
        metadata = request["client_metadata"]
        for key in ("session_id", "thread_id", "turn_id"):
            original = metadata[key]
            if key == "thread_id":
                thread_ordinals.setdefault(original, len(thread_ordinals))
                replacement = "thread_id:" + str(thread_ordinals[original])
            else:
                replacement = key + (":" + str(index) if key == "turn_id" else ":0")
            metadata[key] = bind(key, original, replacement)
        for position, message in enumerate(request["messages"]):
            message["id"] = bind("message", message["id"], "message:" + str(position))
            for part_index, part in enumerate(message["parts"]):
                part["part_id"] = bind("part", part["part_id"],
                                       "part:" + str(position) + ":" + str(part_index))
    return {"requests": requests, "typed_mapping": mapping}


def replay_report(value, wire, session, journal_path):
    need(set(value) == {"schema_version", "source", "recorded", "replay",
                       "model_exchanges", "tool_calls", "comparison",
                       "source_journal_unchanged", "duration_ms"}, "replay report fields")
    need(type(value["schema_version"]) is int and type(value["duration_ms"]) is int
         and value["duration_ms"] >= 0, "replay numeric types")
    for key in ("model_exchanges", "tool_calls"):
        need(set(value[key]) == {"recorded", "replayed"}
             and all(type(count) is int and count >= 0 for count in value[key].values()),
             "replay count types")
    need(set(value["source"]) == {"journal_path", "session_id", "thread_id", "turn_id",
                                 "module_epoch", "profile_name", "workflow_id", "policy_id"}
         and type(value["source"]["module_epoch"]) is int, "replay source shape")
    need(set(value["comparison"]) == {"matched", "settlement_equal", "output_equal",
                                      "error_equal", "history_equal", "issues"},
         "replay comparison fields")
    need(value["schema_version"] == 1 and value["source_journal_unchanged"] is True,
         "replay schema/source integrity")
    source = value["source"]
    need(source["module_epoch"] == wire["config_identity"]["module_epoch"]
         and source["profile_name"] == wire["config_identity"]["profile_name"]
         and source["workflow_id"] == "coding.codex_loop" and source["policy_id"] == "allow_all",
         "replay recorded module/profile selectors")
    need(source["session_id"] == session and source["thread_id"] == wire["thread_id"]
         and source["turn_id"] == wire["turn_id"] and source["journal_path"] == journal_path,
         "replay source identity")
    expected = {"status": "success", "output": wire["output"], "error": None}
    need(same(value["recorded"], expected) and same(value["replay"], expected), "replay settlement")
    need(value["model_exchanges"] == {"recorded": 1, "replayed": 1}
         and value["tool_calls"] == {"recorded": 0, "replayed": 0}, "replay call counts")
    compare = value["comparison"]
    need(compare["matched"] is True and compare["settlement_equal"] is True
         and compare["output_equal"] is True and compare["error_equal"] is None
         and compare["history_equal"] is True and compare["issues"] == [], "replay comparison")
