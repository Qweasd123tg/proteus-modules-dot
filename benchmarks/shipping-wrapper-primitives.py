"""Private wrapper primitives, not an executable measurement runner.
No top-level product execution. Full admission, seed driver and pair acceptance
must be independently integrated after evidence-budget feasibility is sealed.
Do not import or call these drafted functions before explicit authorization.
"""
import hashlib
import json
import math
import os
import stat
import uuid
from pathlib import Path

MIB = 1024 * 1024
SCHEMA = 21
KINDS = {"hook_invoked", "turn_opened", "history_mutated",
         "context_request_recorded", "context_response_recorded",
         "model_request_recorded", "model_message_recorded",
         "model_response_recorded", "tool_call_recorded",
         "tool_result_recorded", "tool_effect_recorded", "turn_settled"}
ENVELOPE = {"schema_version", "record_id", "session_seq", "timestamp_ms",
            "session_id", "execution_id", "thread_id", "turn_id", "kind", "payload"}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict(raw):
    def object_pairs(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "duplicate JSON key")
            value[key] = item
        return value
    def invalid_constant(value):
        raise RuntimeError("nonfinite JSON constant: " + value)
    def finite_float(value):
        number = float(value)
        require(math.isfinite(number), "nonfinite parsed float")
        return number
    return json.loads(raw, object_pairs_hook=object_pairs, parse_constant=invalid_constant,
                      parse_float=finite_float)


def uuid_text(value):
    require(isinstance(value, str) and str(uuid.UUID(value)) == value, "UUID shape")
    return value


def hex_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value)


def owned_bytes(root, relative, cap, *, missing_ok=False):
    """Read an owned regular file; optional absence applies only below an admitted root."""
    parts = relative.split("/")
    require(parts and all(part not in ("", ".", "..") for part in parts), "relative path")
    require(type(cap) is int and 0 <= cap <= 128 * MIB, "file cap")
    require(type(missing_ok) is bool, "missing policy")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if missing_ok:
            info = os.fstat(directory)
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid(),
                    "unowned or non-directory evidence root")
        for part in parts[:-1]:
            try:
                following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=directory)
            except FileNotFoundError:
                if missing_ok:
                    return None
                raise
            os.close(directory)
            directory = following
            if missing_ok:
                info = os.fstat(directory)
                require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid(),
                        "unowned or non-directory evidence parent")
        try:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid(),
                    "unowned or nonregular evidence")
            require(before.st_size <= cap, "file size budget")
            chunks, total = [], 0
            while True:
                chunk = os.read(fd, min(65536, cap + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                require(total <= cap, "file grew beyond budget")
            after = os.fstat(fd)
            require((before.st_dev, before.st_ino, before.st_size,
                     before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_dev, after.st_ino, after.st_size,
                     after.st_mtime_ns, after.st_ctime_ns), "evidence changed during read")
            raw = b"".join(chunks)
            require(len(raw) == before.st_size, "evidence size changed")
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def journal_records(session_dir, expected_session, session_cap):
    """Hydrate bounded source evidence, not a parallel replacement for Core replay.
    Caller owns the closed private session and retains the original files.
    Return every envelope in order, plus immutable source inventory.
    """
    uuid_text(expected_session)
    require(type(session_cap) is int and 0 < session_cap <= 128 * MIB, "session cap")
    raw = owned_bytes(session_dir, "journal.jsonl", session_cap)
    require(raw and raw.endswith(b"\n"), "empty or torn completed journal")
    inventory = {"journal.jsonl": {"bytes": len(raw), "sha256": digest(raw)}}
    wire = {"journal_max_line_bytes": 0, "blob_max_bytes": 0, "record_count": 0}
    records, ids, blobs = [], set(), {}
    physical_bytes = len(raw)
    for number, line in enumerate(raw.splitlines(), 1):
        require(number <= 4096 and line and len(line) + 1 <= 8 * MIB, "journal line/count budget")
        wire["journal_max_line_bytes"] = max(wire["journal_max_line_bytes"], len(line) + 1)
        wire["record_count"] = number
        value = strict(line.decode("utf-8", "strict"))
        require(isinstance(value, dict) and set(value) == ENVELOPE, "journal envelope fields")
        require(type(value["schema_version"]) is int and value["schema_version"] == SCHEMA,
                "journal schema")
        require(type(value["session_seq"]) is int and value["session_seq"] == number,
                "journal sequence")
        require(type(value["timestamp_ms"]) is int, "journal timestamp")
        require(value["session_id"] == expected_session, "foreign journal session")
        record_id = uuid_text(value["record_id"])
        require(record_id not in ids, "duplicate record ID")
        ids.add(record_id)
        for key in ("execution_id", "thread_id", "turn_id"):
            if value[key] is not None:
                uuid_text(value[key])
        require(value["kind"] in KINDS, "unknown journal kind")
        payload = value["payload"]
        require(isinstance(payload, dict), "stored payload type")
        if payload.get("storage") == "inline":
            require(set(payload) == {"storage", "value"}, "inline fields")
            hydrated = payload["value"]
        else:
            require(set(payload) == {"storage", "sha256", "bytes", "relative_path"}
                    and payload["storage"] == "blob", "blob fields")
            expected = payload["sha256"]
            require(hex_digest(expected), "blob digest shape")
            name = "blobs/" + expected + ".json"
            require(payload["relative_path"] == name and type(payload["bytes"]) is int
                    and 0 <= payload["bytes"] <= 8 * MIB, "blob reference/size")
            if name not in blobs:
                content = owned_bytes(session_dir, name, min(8 * MIB, session_cap))
                require(len(content) == payload["bytes"] and digest(content) == expected,
                        "blob size/hash mismatch")
                wire["blob_max_bytes"] = max(wire["blob_max_bytes"], len(content))
                physical_bytes += len(content)
                require(physical_bytes <= session_cap, "session evidence budget")
                blobs[name] = strict(content.decode("utf-8", "strict"))
                inventory[name] = {"bytes": len(content), "sha256": expected}
            require(inventory[name]["bytes"] == payload["bytes"], "inconsistent blob reference")
            hydrated = blobs[name]
        require(isinstance(hydrated, dict), "typed payload must be object")
        records.append({**value, "payload": hydrated})
    return records, inventory, wire


def verify_source_unchanged(session_dir, inventory):
    """Run after supported replay as well as before; covers referenced blobs too."""
    for relative, receipt in inventory.items():
        raw = owned_bytes(session_dir, relative, receipt["bytes"])
        require(len(raw) == receipt["bytes"] and digest(raw) == receipt["sha256"],
                "canonical source changed during validation/replay")


def token_estimate_text_request(request):
    """Pinned full-request categories for this text-only, tool-free-call workload.
    Not the message-only shortcut. Reject unsupported shapes, never undercount.
    Tool/metadata JSON must use only finite integers and printable ASCII strings, so compact
    JSON byte lengths agree with the pinned serde_json path irrespective of key order.
    """
    def json_ascii(value):
        if isinstance(value, str):
            require(all(32 <= ord(char) <= 126 for char in value),
                    "unreviewed non-printable-ASCII schema/metadata serializer")
        elif isinstance(value, list):
            for item in value:
                json_ascii(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                require(isinstance(key, str), "nonstring JSON key")
                json_ascii(key)
                json_ascii(item)
        else:
            require(value is None or type(value) in (bool, int), "unreviewed numeric JSON shape")
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"),
                          allow_nan=False).encode("ascii")
    instructions = request["instructions"]
    instruction_bytes = sum(len(item["text"].encode("utf-8")) + 8 for item in instructions)
    message_bytes = 0
    for message in request["messages"]:
        require(message["role"] in ("User", "Assistant"), "unexpected message role")
        message_bytes += len(message["role"].lower()) + 4
        message_bytes += len((message["name"] or "").encode("utf-8"))
        message_bytes += len((message["tool_call_id"] or "").encode("utf-8"))
        message_bytes += len(json_ascii(message["metadata"]))
        require(len(message["parts"]) == 1, "unexpected part count")
        payload = message["parts"][0]["payload"]
        require(set(payload) == {"Text"} and set(payload["Text"]) == {"text"},
                "non-text category needs new source review")
        message_bytes += len(payload["Text"]["text"].encode("utf-8"))
    tool_bytes = sum(len(json_ascii(tool)) for tool in request["tools"])
    categories = {"instructions": instruction_bytes, "messages": message_bytes,
                  "tool_schemas": tool_bytes}
    tokens = {key: max(1, count // 4) for key, count in categories.items() if count}
    return {"category_bytes": categories, "category_tokens": tokens, "total": sum(tokens.values())}


def release_environment(home, cargo_home, rustup_home, path):
    """New explicit environment; never call the correctness helper clean_env."""
    return {"PATH": path, "HOME": str(home), "CARGO_HOME": str(cargo_home),
            "RUSTUP_HOME": str(rustup_home), "RUSTUP_TOOLCHAIN": "1.95.0",
            "CARGO_BUILD_JOBS": "2", "CARGO_INCREMENTAL": "0",
            "CARGO_TERM_COLOR": "never", "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONOPTIMIZE": "0",
            "PYTHONHASHSEED": "0", "LC_ALL": "C", "TZ": "UTC"}


def shipping_build_argv(source, target):
    """Installer-equivalent build selection; JSON reporting is not a codegen flag."""
    return ["cargo", "build", "--locked", "--release", "--manifest-path",
            str(Path(source) / "Cargo.toml"), "--target-dir", str(target),
            "-p", "proteus-core", "--message-format=json-render-diagnostics"]


def shipping_replay_argv(binary, config, session, turn):
    uuid_text(turn)
    return [str(binary), "--config", str(config), "replay", "workflow",
            str(session), "--turn-id", turn, "--json"]


