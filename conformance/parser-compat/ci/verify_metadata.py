#!/usr/bin/env python3
"""Check resolved exact parser versions/features before the authored binary runs."""
import json
from pathlib import Path
import sys
import tomllib

PACKAGE = Path(__file__).resolve().parent.parent


def verify(metadata, pins, lock):
    nodes = {node["id"]: node for node in metadata["resolve"]["nodes"]}
    observed = {}
    for name, expected in pins["parsers"].items():
        packages = [package for package in metadata["packages"] if package["name"] == name]
        locked = [package for package in lock["package"] if package["name"] == name]
        if len(packages) != 1 or len(locked) != 1:
            raise ValueError("parser package identity ambiguous or missing")
        package, locked = packages[0], locked[0]
        if (package["version"] != expected["version"] or locked["version"] != expected["version"]
                or locked["checksum"] != expected["archive_sha256"]
                or package["source"] != expected["registry_source"]):
            raise ValueError("resolved parser pin/checksum drift")
        features = sorted(nodes[package["id"]]["features"])
        if name == "serde-saphyr" and features != ["comments", "deserialize"]:
            raise ValueError("unexpected saphyr feature; include/property/other extensions must stay off")
        observed[name] = {"version": package["version"], "features": features,
                          "registry_checksum": locked["checksum"]}
    return {"dependency_identity_and_features": "passed", "parsers": observed,
            "not_claimed": "dependency security audit or maintenance guarantee"}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_metadata.py CARGO_METADATA_JSON")
    metadata = json.loads(Path(sys.argv[1]).read_text())
    pins = json.loads((PACKAGE / "SOURCE_PINS.json").read_text())
    lock = tomllib.loads((PACKAGE / "Cargo.lock").read_text())
    print(json.dumps(verify(metadata, pins, lock), indent=2))


if __name__ == "__main__":
    main()
