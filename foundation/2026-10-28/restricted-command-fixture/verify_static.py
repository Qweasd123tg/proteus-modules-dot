#!/usr/bin/env python3
"""Offline source-only checks; never compile or run Rust/product code."""
from pathlib import Path
import difflib
import hashlib
import json
import re
import sys
import tomllib

CORE_SHA = "125a9eb4088991513e9f61d899469be2076e266c"
MODULES_SHA = "5fa8978684a37e8083c64f4d6cf0289e72450c6a"
BASE_BLOB = "1b7cb442583e0b9ccb3df7152508857bc6dbb9d6"
FRAGMENT_BLOB = "428603e5ff9728c2518fd3832975b5a43fad5fa7"
SOURCE_PATH = "crates/proteus-core/tests/config_profiles.rs"
MATRIX = [
    ("reference-workflow", "proteus-coding-workflow-module", "workflow", "coding.codex_loop", False),
    ("reference-context", "proteus-context-pack-module", "context", "codex_context", True),
    ("reference-policy", "proteus-policy-pack-module", "policy", "codex_policy", False),
    ("reference-compact", "proteus-codex-context-preparation-module", "hook", "codex_compact", False),
    ("reference-search-tool", "proteus-rg-search-module", "tool", "rg_search", True),
    ("reference-search-provider", "proteus-rg-search-module", "context_provider", "rg_search", True),
]
START = "async fn restricted_profile_resolves_six_single_export_read_only_process_specs() {"
END = "fn tracked_configs() -> Vec<PathBuf> {"
ASSERT_START = "    assert_eq!(\n        config\n            .components"
OLD_FIXTURE = '''    // Resolve the shipped command against a private child PATH. No mutation of
    // the test process environment or dependency on an installed reference binary.
    std::fs::copy(
        std::env::current_exe().unwrap(),
        bin.join("proteus-reference-module"),
    )
    .unwrap();
'''
NEW_FIXTURE = '''    // Resolve each shipped command against a private child PATH without changing
    // the test process environment or requiring installed module binaries.
    // These ELF fixtures are only validated, never executed. Copy once and use
    // same-directory hard links so independent names do not multiply disk usage.
    let fixture = bin.join(restricted[0].1);
    std::fs::copy(std::env::current_exe().unwrap(), &fixture).unwrap();
    let commands = restricted
        .iter()
        .map(|(_, command, _, _, _)| *command)
        .collect::<std::collections::BTreeSet<_>>();
    for command in commands {
        let path = bin.join(command);
        if path != fixture {
            std::fs::hard_link(&fixture, path).unwrap();
        }
    }
'''


def require(condition, message):
    if not condition:
        raise ValueError(message)


def blob_sha1(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def split_function(text):
    require(text.count(START) == 1 and text.count(END) == 1, "unexpected test boundaries")
    prefix, rest = text.split(START, 1)
    body, suffix = rest.split(END, 1)
    return prefix, body, suffix


def matrix_text(body):
    prefix, rest = body.split("    let restricted = [\n", 1)
    matrix, suffix = rest.split("    ];\n", 1)
    return prefix, matrix, suffix


def parse_matrix(text, with_commands):
    literal = r'"([^"\\]+)"'
    fields = 4 if with_commands else 3
    pattern = r"\(\s*" + r"\s*,\s*".join([literal] * fields)
    pattern += r"\s*,\s*(true|false)\s*,?\s*\)\s*,"
    compiled = re.compile(pattern)
    matches = list(compiled.finditer(text))
    require(not compiled.sub("", text).strip(), "matrix contains non-literal or unrecognized content")
    return [tuple(match.groups()[:-1]) + (match.groups()[-1] == "true",) for match in matches]


def validate_source_contract(before, after, fragment):
    bp, bb, bs = split_function(before)
    ap, ab, ass = split_function(after)
    require(bp == ap and bs == ass, "bytes outside corrected test changed")
    bpre, bmatrix, bpost = matrix_text(bb)
    apre, amatrix, apost = matrix_text(ab)
    require(parse_matrix(bmatrix, False) == [
        (component, slot, module, access) for component, _, slot, module, access in MATRIX
    ], "unexpected preimage matrix")
    rows = parse_matrix(amatrix, True)
    require(rows == MATRIX, "six explicit command/slot/export/cwd mappings changed")
    require(len({row[1] for row in rows}) == 5, "expected five distinct fixture names")
    require(bpre.count(OLD_FIXTURE) == 1, "unexpected preimage fixture")
    require(apre == bpre.replace(OLD_FIXTURE, ""), "test prelude changed beyond obsolete fixture")
    expected_assertions = bpost.replace(
        "    for (id, slot, module, workspace_access) in restricted {",
        "    for (id, command, slot, module, workspace_access) in restricted {",
    ).replace(
        'assert_eq!(component.command(), "proteus-reference-module");',
        "assert_eq!(component.command(), command);",
    ).replace(
        'assert_eq!(spec.command, "proteus-reference-module");',
        "assert_eq!(spec.command, command);",
    )
    require(bpost.startswith(ASSERT_START), "unexpected assertion boundary")
    require(apost == NEW_FIXTURE + expected_assertions,
            "fixture operations or original sandbox/env/cwd/export/args assertions changed")
    require(ab.count("std::fs::copy(") == 1 and ab.count("std::fs::hard_link(") == 1,
            "fixture must copy once and hard-link distinct names")
    components = tomllib.loads(fragment)["components"]
    restricted = {name for name, value in components.items()
                  if value.get("sandbox", {}).get("mode") == "restricted"}
    require(restricted == {row[0] for row in MATRIX}, "restricted component inventory changed")
    for component, command, slot, module, access in MATRIX:
        value = components[component]
        require(value["command"] == command, component + ": fragment command mismatch")
        require(value["exports"] == {slot: {module: {}}}, component + ": not exact single export")
        require(value.get("cwd") == (None if access else "/usr"), component + ": cwd mismatch")
        require(value.get("env_allowlist", []) == [] and value.get("env", {}) == {},
                component + ": environment mismatch")
        require(value["sandbox"] == {
            "mode": "restricted", "read_executable": True,
            "read_only": ["/usr", "/lib", "/lib64", "/bin"] + (["."] if access else []),
            "read_write": [], "network": False,
        }, component + ": sandbox grants mismatch")


def validate_patch(before, after, patch):
    expected = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="a/" + SOURCE_PATH, tofile="b/" + SOURCE_PATH,
    ))
    require(patch == expected, "patch is not exact canonical preimage-to-postimage diff")


def validate_inventory(inventory):
    require(inventory["repository"] == "Proteus-harness/Proteus-modules", "inventory repo mismatch")
    require(inventory["commit"] == MODULES_SHA, "inventory commit mismatch")
    packages = inventory["packages"]
    expected_ids = {command.removeprefix("proteus-").removesuffix("-module")
                    for _, command, _, _, _ in MATRIX}
    require(set(packages) == expected_ids, "inventory must contain exactly five packages")
    for _, command, slot, module, _ in MATRIX:
        identity = command.removeprefix("proteus-").removesuffix("-module")
        records = packages[identity]
        for filename in ("Cargo.toml", "exports.json"):
            record = records[filename]
            require(record["path"] == f"components/{identity}-module/{filename}", "inventory path mismatch")
            require(blob_sha1(record["content"].encode()) == record["git_blob_sha1"],
                    record["path"] + ": pinned blob mismatch")
        manifest = tomllib.loads(records["Cargo.toml"]["content"])
        require(manifest["package"]["name"] == command, identity + ": package name mismatch")
        require(manifest["package"]["metadata"]["proteus"]["id"] == identity, "package identity mismatch")
        require(manifest["bin"][0]["name"] == command, identity + ": executable name mismatch")
        exports = json.loads(records["exports.json"]["content"])
        require(module in exports[slot], identity + ": missing selected export")


def verify(root):
    manifest = json.loads((root / "manifest.json").read_text())
    require(manifest["core_commit"] == CORE_SHA and manifest["modules_commit"] == MODULES_SHA,
            "commit pins changed")
    require(manifest["qualification"] == {
        "static_checks": "PASS", "rust_test": "NOT_RUN", "compilation": "NOT_RUN",
        "product_execution": "NOT_RUN", "github_actions": "NOT_RUN",
    }, "qualification must not claim Rust/runtime validation")
    expected_files = {"preimage.rs", "postimage.rs", "restricted-components.toml",
                      "module-inventory.json", "fix.patch", "verify_static.py",
                      "test_verify_static.py", "README.md"}
    require(set(manifest["files"]) == expected_files, "unexpected manifest inventory")
    for name, hashes in manifest["files"].items():
        data = (root / name).read_bytes()
        require(hashlib.sha256(data).hexdigest() == hashes["sha256"], name + ": sha256 mismatch")
        require(blob_sha1(data) == hashes["git_blob_sha1"], name + ": blob hash mismatch")
    require(blob_sha1((root / "preimage.rs").read_bytes()) == BASE_BLOB, "preimage is not pinned source")
    require(blob_sha1((root / "restricted-components.toml").read_bytes()) == FRAGMENT_BLOB,
            "fragment is not pinned source")
    before = (root / "preimage.rs").read_text()
    after = (root / "postimage.rs").read_text()
    validate_source_contract(before, after, (root / "restricted-components.toml").read_text())
    validate_patch(before, after, (root / "fix.patch").read_text())
    validate_inventory(json.loads((root / "module-inventory.json").read_text()))
    print("STATIC_CHECKS: PASS (six bindings, five fixture names, exact patch and preserved assertions)")
    print("RUST_TEST: NOT_RUN; COMPILATION: NOT_RUN; PRODUCT_EXECUTION: NOT_RUN; GITHUB_ACTIONS: NOT_RUN")
    print("Static source checks are not Rust compilation, test execution, or production qualification.")


if __name__ == "__main__":
    try:
        verify(Path(__file__).resolve().parent)
    except (ValueError, KeyError, OSError, TypeError) as error:
        print(f"STATIC_CHECKS: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
