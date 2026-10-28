#!/usr/bin/env python3
"""Read source manifests and print a plan; never build, run, copy or install."""
import argparse
import json
from pathlib import Path, PurePosixPath
import tomllib


def parse_extension(cargo_text, extension_text, folder):
    manifest = tomllib.loads(cargo_text)
    package = manifest.get("package", {}).get("name")
    extension = json.loads(extension_text)
    command = extension.get("command")
    if not isinstance(package, str) or not package:
        raise ValueError(f"{folder}: package.name is required")
    if not isinstance(command, list) or not command or not isinstance(command[0], str):
        raise ValueError(f"{folder}: extension command is required")
    program = PurePosixPath(command[0])
    if len(program.parts) != 2 or program.parts[0] != "bin":
        raise ValueError(f"{folder}: only an explicit bin/NAME extension is supported")
    targets = manifest.get("bin", [])
    if not isinstance(targets, list) or not all(isinstance(target, dict) for target in targets):
        raise ValueError(f"{folder}: Cargo binary declarations must be a list")
    matches = [target for target in targets if target.get("name") == program.name]
    if len(matches) != 1:
        raise ValueError(f"{folder}: command must match exactly one explicit Cargo binary")
    return {"package": package, "binary": program.name, "folder": folder}


def validate_workspace(cargo_text):
    workspace = tomllib.loads(cargo_text).get("workspace")
    if not isinstance(workspace, dict):
        raise ValueError("Expected an explicit Cargo workspace")
    members = workspace.get("members")
    if (not isinstance(members, list) or len(members) != 2
            or not all(isinstance(member, str) for member in members)
            or set(members) != {"sdk", "packages/*"} or workspace.get("exclude")):
        raise ValueError("Expected exactly sdk and packages/* workspace members, without excludes")


def read_catalog(source):
    source = source.resolve(strict=True)
    validate_workspace((source / "Cargo.toml").read_text(encoding="utf-8"))
    catalog = []
    for manifest in sorted((source / "packages").glob("*/Cargo.toml")):
        folder = manifest.parent.resolve(strict=True)
        if not folder.is_relative_to(source):
            raise ValueError("Extension source resolves outside the selected source root")
        extension_manifest = folder / "extension.json"
        if not all(path.resolve(strict=True).is_relative_to(source)
                   for path in (manifest, extension_manifest)):
            raise ValueError("An extension manifest resolves outside the selected source root")
        catalog.append(parse_extension(
            manifest.read_text(encoding="utf-8"),
            extension_manifest.read_text(encoding="utf-8"),
            folder.relative_to(source).as_posix(),
        ))
    if not catalog:
        raise ValueError("No Rust extension packages found")
    names = [item["package"] for item in catalog]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate Cargo package names in extension catalog")
    return source, catalog


def create_plan(catalog, package=None, all_packages=False):
    if bool(package) == bool(all_packages):
        raise ValueError("Select exactly one package or the explicit full-package path")
    selected = catalog if all_packages else [
        item for item in catalog if item["package"] == package
    ]
    if not selected or (not all_packages and len(selected) != 1):
        raise ValueError(f"Expected one known extension package: {package!r}")
    build = ["cargo", "build", "--locked", "--release", "--jobs", "2",
             "--message-format=json-render-diagnostics"]
    test = ["cargo", "test", "--locked", "--jobs", "2"]
    if all_packages:
        build += ["--workspace"]
        test += ["--workspace"]
    else:
        selector = ["-p", selected[0]["package"], "--bin", selected[0]["binary"]]
        build += selector
        test += ["-p", selected[0]["package"]]
    test += ["--", "--test-threads=4"]
    return {
        "schema": 1,
        "mode": "all-packages" if all_packages else "one-package",
        "execution_performed": False,
        "build_argv": build,
        "test_argv": test,
        "expected_artifacts": selected,
        "packaging": {
            "performed": False,
            "status": "not-implemented",
            "reason": "Current upstream package.py has no package selector; this plan does not install binaries.",
        },
        "notes": [
            "Build uses release; tests retain the existing default test profile. These are distinct artifact sets.",
            "A Cargo invocation may reuse fresh dependencies; selected downstream binaries may still need linking.",
            "Resolve executable paths only from successful Cargo compiler-artifact records, never target/profile guesses.",
            "This source-only plan does not grant permission to execute native code or bypass a denied action.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="Existing Proteus-desktop-extensions source root; read only")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--package", help="Exact Cargo package name, for example extension-files")
    scope.add_argument("--all-packages", action="store_true",
                       help="Explicit full workspace build/test plan, including SDK tests")
    args = parser.parse_args()
    try:
        source, catalog = read_catalog(args.source)
        plan = create_plan(catalog, args.package, args.all_packages)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    plan["cwd"] = str(source)
    print(json.dumps(plan, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
