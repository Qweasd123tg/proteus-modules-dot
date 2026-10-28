"""Pure JSON profile factory. No file, process, import-time or network operations.
The wrapper writes and hashes the result outside all measured intervals.
Pinned AppConfig loading.rs accepts a single .json profile.
"""
def profile(paths, phase, mode, payload_bytes, nonce, sample_root,
            seed_user_ids=None, seed_part_ids=None):
    if phase not in ("seed", "measure") or mode not in ("latency", "resource"):
        raise ValueError("mode")
    if payload_bytes not in (4096, 1048576):
        raise ValueError("payload")
    fixture = {"phase": phase, "mode": mode, "payload_bytes": payload_bytes,
               "nonce": nonce, "seed_user_ids": seed_user_ids, "seed_part_ids": seed_part_ids,
               "hold_socket": sample_root + "/hold.sock"
               if mode == "resource" and phase == "measure" else None}
    return {
        "active_provider": "fixture",
        "providers": {"fixture": {"provider": "release-probe", "model": "fixture", "stream": True}},
        "modules": {"workflow": "coding.codex_loop", "policy": "allow_all", "hooks": []},
        "tools": {"enabled": ["benchmark_probe"]},
        "agent_control": {"surface": "none"},
        "event_log": {"path": sample_root + "/events.jsonl", "persist_deltas": False},
        "components": {
            "reference": {"command": paths["reference"], "exports": {
                "workflow": {"coding.codex_loop": {}}, "policy": {"allow_all": {}}}},
            "model": {"command": paths["python"],
                      "env": {"PYTHONHASHSEED": "0", "LC_ALL": "C", "TZ": "UTC"},
                      "args": ["-I", "-B", "-S", paths["model_fixture"], "--runtime-dir", paths["runtime_dir"]],
                      "exports": {"model": {"release-probe": {}}}},
            "probe": {"command": paths["python"],
                      "env": {"PYTHONHASHSEED": "0", "LC_ALL": "C", "TZ": "UTC"},
                      "args": ["-I", "-B", "-S", paths["probe_fixture"]],
                      "exports": {"tool": {"benchmark_probe": {}}}}},
        "module_config": {"model": {"release-probe": fixture}},
    }
