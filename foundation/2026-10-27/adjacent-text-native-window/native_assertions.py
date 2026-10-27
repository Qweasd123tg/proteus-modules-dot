"""Fail-closed receipt checks. These are harness oracles, not a copied reducer."""
import hashlib
import re

class GateFailure(RuntimeError):
    pass

def require(condition, message):
    if not condition:
        raise GateFailure(message)

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def marker(words, text, confidence=65):
    hits = [word for word in words
            if word["text"].casefold() == text.casefold()
            and word["confidence"] >= confidence]
    require(len(hits) == 1, f"Expected exactly one visible {text!r}, found {len(hits)}")
    return hits[0]

def window_ok(meta, pid):
    require(meta["pid"] == pid, "Mapped window PID does not match launched native process")
    require(meta["viewable"], "Native X11 window is not viewable")
    require("dev.proteus.native" in meta["wm_class"], "Unexpected native window class")
    require("Proteus" in meta["title"], "Unexpected native window title")
    require(900 <= meta["width"] <= 1280 and 650 <= meta["height"] <= 900,
            "Unexpected client geometry")
    require(meta["id"] > 0, "No native window ID")

def capture_ok(receipt, stage_ns, meta):
    require(receipt["captured_ns"] >= stage_ns, "Stale pre-stage screenshot")
    require(receipt["window_id"] == meta["id"], "Screenshot belongs to another window")
    require(receipt["size"] == [meta["width"], meta["height"]], "Capture geometry changed")
    require(re.fullmatch("[0-9a-f]{64}", receipt["png_sha256"]) is not None,
            "Missing screenshot digest")

def ordered(words, names):
    points = [marker(words, name) for name in names]
    require(all(a["top"] + a["height"] <= b["top"] + 3
                for a, b in zip(points, points[1:])), "Visible row order differs")
    return points

def continuation_ok(words, prior, appended, barrier):
    before, tail, tool = [marker(words, text) for text in (prior, appended, barrier)]
    require(abs(before["top"] - tail["top"]) <= 2,
            "Same-message continuation is not on the original final line")
    require(tail["left"] >= before["left"] + before["width"],
            "Continuation does not follow the original final marker")
    require(tail["top"] + tail["height"] <= tool["top"] + 3,
            "Same-message continuation moved after the non-text barrier")

def anchor_ok(before, after, tolerance=2):
    require(abs(before["top"] - after["top"]) <= tolerance, "Visible anchor moved")
    require(abs(before["left"] - after["left"]) <= tolerance, "Visible anchor shifted horizontally")

def clipboard_ok(receipt, expected, protocol):
    require(receipt["nonce"] != expected, "Clipboard sentinel equals expected output")
    require(receipt["before"] == receipt["nonce"], "Sentinel was not installed in CLIPBOARD")
    require(receipt["after"] == expected, "Native CLIPBOARD text does not match delta oracle")
    require(receipt["owner_before"] != 0 and receipt["owner_after"] != 0,
            "Missing CLIPBOARD owner")
    require(receipt["owner_before"] != receipt["owner_after"], "CLIPBOARD ownership did not change")
    require(receipt["click_ns"] > receipt["before_ns"], "Copy was not clicked after sentinel")
    require(receipt["after_ns"] > receipt["click_ns"], "Clipboard was read before native Copy")
    require(receipt["icon_before_sha256"] != receipt["icon_after_sha256"],
            "Copy control has no observed visual feedback")
    require(receipt["target_visible"], "Copy target row was not visible")
    require(receipt["selection"] == "CLIPBOARD", "Wrong X11 selection")
    for item in protocol:
        if item["at_ns"] <= receipt["after_ns"] and item.get("heals_delta_oracle", False):
            raise GateFailure("Completion or replacement snapshot could heal the delta oracle")

def cancel_ok(request, session, run_id):
    require(request["path"] == "/cancel", "Stop did not call /cancel")
    require(request["session"] == session, "Cancel targeted another session")
    require(request["body"]["target_id"] == run_id, "Cancel targeted another run")

def reported_errors(log):
    patterns = (r"panicked at", r"GPU device lost", r"Failed to create surface",
                r"No GPU adapter", r"surface configuration failed",
                r"wgpu[\s\S]{0,160}(?:validation error|device lost|error)",
                r"GPU error during frame", r"instance texture write out of bounds",
                r"X11:.*failed")
    for pattern in patterns:
        require(re.search(pattern, log, re.I) is None,
                f"Reported native/renderer error: {pattern}")

def complete(result, spec):
    require(set(result["scenarios"]) == set(spec["required_scenarios"]),
            "Missing or unexpected required scenarios")
    require(all(row.get("status") == "passed" for row in result["scenarios"].values()),
            "A required scenario did not pass")
    for key in ("native_binary_before", "native_binary_after", "qualified_native_sha256"):
        require(re.fullmatch("[0-9a-f]{64}", (result.get(key) or "")) is not None,
                "Missing or invalid binary identity: " + key)
    require(result["native_binary_before"] == result["native_binary_after"]
            == result["qualified_native_sha256"], "Native binary differs from same-job qualifier")
    wanted = {receipt for rows in spec["required_receipts"].values() for receipt in rows}
    require(wanted.issubset(set(result.get("receipt_ids", []))),
            "Missing a required semantic screenshot receipt")
    require(result.get("rust_log_backend_initialized") is False
            and result.get("renderer_diagnostics_complete") is False,
            "Unsupported comprehensive renderer observability claim")
    require(result["portable_inventory_unchanged"], "Portable inventory changed")
    require(not result["evidence_overflow"], "Evidence cap exceeded")
    require(not result["fixture_errors"], "Protocol fixture reported an error")
    require(result["native_window_proven"], "Actual mapped-window proof missing")
    require(result["feasibility_gate_passed"], "Initial native feasibility gate did not pass")
