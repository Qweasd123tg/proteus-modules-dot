"""Private source-only model/v12 probe. No clocks, metrics files, or /proc reads.
Latency has no control-channel work. Python runtime intentionally retains params.
"""
import argparse
import hashlib
import json
import socket
import sys
import threading
import uuid

parser = argparse.ArgumentParser()
parser.add_argument("--runtime-dir", required=True)
args = parser.parse_args()
sys.path.insert(0, args.runtime_dir)
from component_runtime import ProtocolError, run_component

TASK = "Run the fixed benchmark probe calls, then finish."
SEED = "seed accepted"
ANSWER = "benchmark complete"
SEED_PAIRS = 16
SEED_ID_BASE = uuid.UUID("11111111-1111-4111-8111-111111111100").int
MEASURE_IDS = ("22222222-2222-4222-8222-222222222221",
               "22222222-2222-4222-8222-222222222222")
MAX_INPUT_TOKENS = 2_097_152
MAX_OUTPUT_TOKENS = 4_096
CAPS = {name: False for name in (
    "supports_tools", "supports_parallel_tool_calls", "supports_freeform_tools",
    "supports_streaming", "supports_json_schema", "supports_system_role",
    "supports_developer_role", "supports_cache_hints", "supports_reasoning_config",
    "supports_image_input", "supports_file_input")}
CAPS.update(supports_tools=True, supports_streaming=True, supports_system_role=True,
            supports_developer_role=True, provider_hosted_tools=[],
            max_input_tokens=MAX_INPUT_TOKENS, max_output_tokens=MAX_OUTPUT_TOKENS)
DESCRIPTOR = {"adapter_id": "release-probe", "capabilities": CAPS, "hosted_tools": []}
settings = None
next_step = 0
active = False
seed_identity = None
seed_turns = set()
seed_ids = []
lock = threading.Lock()


def need(value, message):
    if not value:
        raise ProtocolError(message)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def uid(value):
    need(isinstance(value, str) and str(uuid.UUID(value)) == value, "noncanonical UUID")
    return value


def message(phase, index=0):
    if phase == "seed":
        need(0 <= index < SEED_PAIRS, "seed index")
        mid = str(uuid.UUID(int=SEED_ID_BASE + index * 2))
        pid = str(uuid.UUID(int=SEED_ID_BASE + index * 2 + 1))
    else:
        mid, pid = MEASURE_IDS
    return {"id": mid, "role": "Assistant", "phase": "final_answer",
            "parts": [{"part_id": pid, "provenance": "model", "scope": "conversation",
                       "payload": {"Text": {"text": SEED if phase == "seed" else ANSWER}}}],
            "name": None, "tool_call_id": None, "metadata": None}


def text_of(value, role):
    need(value["role"] == role and len(value["parts"]) == 1, "message shape")
    part = value["parts"][0]
    need(part["scope"] == "conversation" and set(part["payload"]) == {"Text"},
         "nontext request")
    need(part["provenance"] == ("user" if role == "User" else "model"),
         "part provenance")
    return part["payload"]["Text"]["text"]


def initialize(params):
    global settings
    need(params["protocol_version"] == "v3" and len(params["exports"]) == 1,
         "expected one model export and wire v3")
    export = params["exports"][0]
    need(tuple(export[k] for k in ("slot", "module_id", "contract_version", "composition"))
         == ("model", "release-probe", "v12", "select_one"), "model export mismatch")
    settings = export["module_config"]
    need(set(settings) == {"phase", "mode", "payload_bytes", "nonce", "hold_socket",
                          "seed_user_ids", "seed_part_ids"}, "fixture config fields")
    need(settings["phase"] in ("seed", "measure") and settings["mode"] in ("latency", "resource"),
         "fixture mode")
    need(settings["payload_bytes"] in (4096, 1048576), "payload cell")
    for key in ("seed_user_ids", "seed_part_ids"):
        values = settings[key]
        if settings["phase"] == "seed":
            need(values is None, "seed IDs must come from ordinary shipping admission")
        else:
            need(isinstance(values, list) and len(values) == SEED_PAIRS
                 and len(set(uid(value) for value in values)) == SEED_PAIRS,
                 "measured seed ID inventory")
    need(isinstance(settings["nonce"], str) and len(settings["nonce"]) == 32
         and all(c in "0123456789abcdef" for c in settings["nonce"]), "nonce")
    need((settings["hold_socket"] is None) == (settings["mode"] == "latency"
         or settings["phase"] == "seed"), "hold channel mode mismatch")
    return {"protocol_version": "v3", "component_id": params["component_id"],
            "exports": [{**{k: export[k] for k in
                            ("slot", "module_id", "contract_version", "composition")},
                         "module_features": [], "config_schema": None}]}


def invoke(context, method, params):
    global next_step, active, seed_identity
    if method == "describe":
        need(set(params) == {"model"}, "describe fields")
        return DESCRIPTOR
    need(method == "stream" and set(params) == {"request", "stream"}
         and params["stream"] is True, "stream input")
    phase, mode = settings["phase"], settings["mode"]
    with lock:
        need(not active, "overlapping model exchanges")
        need(next_step < (SEED_PAIRS if phase == "seed" else 1), "unexpected model exchange")
        index = next_step
        active = True  # A failed invocation poisons this fixture; no retry is accepted.
    request = params["request"]
    identity = {k: uid(request["client_metadata"][k])
                for k in ("session_id", "thread_id", "turn_id")}
    need(not (request.get("metadata") or {}).get("suppress_stream_deltas", False),
         "presentation suppression")
    need(request["limits"]["max_input_tokens"] == MAX_INPUT_TOKENS
         and request["limits"]["max_output_tokens"] == MAX_OUTPUT_TOKENS,
         "fixed model window changed")
    messages = request["messages"]
    pairs = index if phase == "seed" else SEED_PAIRS
    need(len(messages) == 2 * pairs + 1, "history count or unexpected compaction")
    payload_bytes = settings["payload_bytes"] // SEED_PAIRS
    need(payload_bytes < 256 * 1024, "shipping input admission cap")
    observed_users = []
    for position in range(pairs + (phase == "seed")):
        value = messages[2 * position]
        payload = text_of(value, "User")
        need(len(payload) == payload_bytes and payload.count("A") == payload_bytes,
             "historical A payload changed")
        ident = (uid(value["id"]), uid(value["parts"][0]["part_id"]))
        observed_users.append(ident)
        if position < pairs:
            expected = seed_ids[position] if phase == "seed" else (
                settings["seed_user_ids"][position], settings["seed_part_ids"][position])
            need(ident == expected, "seed user/part identity changed")
            need(messages[2 * position + 1] == message("seed", position),
                 "seed assistant history changed")
    if phase == "seed":
        current_identity = (identity["session_id"], identity["thread_id"])
        need(seed_identity is None or seed_identity == current_identity, "seed session/thread drift")
        need(identity["turn_id"] not in seed_turns, "seed turn reused")
        seed_identity = current_identity
        seed_turns.add(identity["turn_id"])
        seed_ids.append(observed_users[-1])
    else:
        need(text_of(messages[-1], "User") == TASK, "measured task changed")
    need(len(request["tools"]) == 1 and request["tools"][0]["name"] == "benchmark_probe",
         "tool surface changed")
    mids = [uid(m["id"]) for m in messages]
    pids = [uid(p["part_id"]) for m in messages for p in m["parts"]]
    need(len(set(mids)) == len(mids) and len(set(pids)) == len(pids), "duplicate IDs")
    output = message(phase, index)
    need(output["id"] not in mids and output["parts"][0]["part_id"] not in pids,
         "output identity collision")
    context.ensure_active()
    context.host_call("host.model.emit", {
        "sequence": 0, "event": {"MessageCompleted": {"message": output}}
    })
    if phase == "measure" and mode == "resource":
        # All resource-only work is after callback return. The controller also
        # waits for accepted Core presentation before starting its plateau.
        packet = {"kind": "hold_ready", "nonce": settings["nonce"],
                  "invocation_id": context.invocation_id, **identity,
                  "message_id": output["id"], "part_id": output["parts"][0]["part_id"],
                  "request_sha256": hashlib.sha256(encode(request)).hexdigest()}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.settimeout(5.0)
            channel.connect(settings["hold_socket"])
            channel.sendall(encode(packet) + b"\n")
            data = bytearray()
            while b"\n" not in data:
                chunk = channel.recv(4097 - len(data))
                need(chunk and len(data) + len(chunk) <= 4096, "release frame")
                data.extend(chunk)
            need(bytes(data) == encode({"kind": "release", "nonce": settings["nonce"]}) + b"\n",
                 "release identity")
        context.ensure_active()
    with lock:
        next_step += 1
        active = False
    return {"event_count": 1, "terminal": {"kind": "response", "response": {
        "messages": [output], "tool_calls": [], "finish_reason": "Stop",
        "usage": None, "end_turn": True, "provider_metadata": None}}}


run_component(initialize, invoke)
