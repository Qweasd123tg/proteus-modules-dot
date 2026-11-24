#!/usr/bin/env python3
"""Apply the identical test-only phase probe to already-staged pinned Core sources."""
import argparse
from pathlib import Path


def replace(path, source, target):
    old = path.read_text()
    if old.count(source) != 1:
        raise RuntimeError(f"exact probe anchor not present once: {path}: {source!r}")
    path.write_text(old.replace(source, target))


def install(root, meter):
    sdk = root / "crates/proteus-module-sdk/src"
    replace(sdk / "lib.rs", "mod runtime;", "mod native_meter;\nmod runtime;")
    (sdk / "native_meter.rs").write_bytes(meter.read_bytes())
    export = sdk / "session_storage.rs"
    replace(export, "        request.validate()?;\n", """        request.validate()?;
        if matches!(&request, SessionStorageRequest::ReadBlob { .. } | SessionStorageRequest::ReadBlobByHash { .. }) {
            crate::native_meter::begin();
        }
""")
    stock = "        Ok(serde_json::to_value(self.storage.execute(request)?)?)"
    if stock in export.read_text():
        replace(export, stock, """        let response = self.storage.execute(request)?;
        crate::native_meter::backend(&response);
        Ok(serde_json::to_value(response)?)""")
    else:
        replace(export, "        let response = self.storage.execute(request)?;\n",
                "        let response = self.storage.execute(request)?;\n        crate::native_meter::backend(&response);\n")
    runtime = sdk / "runtime.rs"
    replace(runtime, "        let result = self.component.dispatch(call, &method, &bridge);\n",
            "        let result = self.component.dispatch(call, &method, &bridge);\n"
            "        crate::native_meter::value(\"converted\", result.as_ref().ok());\n")
    replace(runtime, "        if let Err(error) = self.finish_invocation(&invocation_id) {\n",
            "        crate::native_meter::value(\"flushed\", response.get(\"result\"));\n"
            "        if let Err(error) = self.finish_invocation(&invocation_id) {\n")
    replace(runtime,
            '            eprintln!("proteus-module-sdk: failed to settle invocation: {error:#}");\n'
            '            std::process::exit(1);\n        }\n',
            '            eprintln!("proteus-module-sdk: failed to settle invocation: {error:#}");\n'
            '            std::process::exit(1);\n        }\n'
            '        drop(response);\n'
            '        crate::native_meter::line("dropped", 0, 0, 0);\n')
    transport = sdk / "transport.rs"
    replace(transport, "        serde_json::to_writer(&mut counter, value)?;\n",
            '        serde_json::to_writer(&mut counter, value)?;\n'
            '        crate::native_meter::value("counted", value.get("result"));\n')


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("core_roots", nargs="+", type=Path)
    settings = args.parse_args()
    for core in settings.core_roots:
        install(core, Path(__file__).with_name("native_meter.rs"))
