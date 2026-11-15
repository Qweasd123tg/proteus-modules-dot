"""Text extraction only. Does not import or execute project code or a compiler."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
SCOPES = Path("src/ui/extensions/declarative/runtime/scopes.rs")
RUNTIME = Path("src/ui/extensions/declarative/runtime.rs")


def extract(source, signature, following):
    start = source.index(signature)
    end = source.index(following, start)
    method = source[start:end].rstrip("\n")
    assert method.endswith("    }")
    return method


def main():
    template = (ROOT / "regression/template.rs").read_text()
    original_runtime = (ROOT / "sources/desktop" / RUNTIME).read_text()
    send = extract(original_runtime, "    pub(super) fn send(", "\n    /// Starts the process again")
    records = {}
    for variant, folder in [("baseline", "sources/desktop"), ("candidate", "candidate")]:
        scopes = (ROOT / folder / SCOPES).read_text()
        announce = extract(scopes, "    pub(super) fn announce_scope(", "\n    fn scope_event(")
        reset = extract(scopes, "    pub(super) fn reset_scopes(", "\n    pub(super) fn content_context(")
        pieces = {"ANNOUNCE_SCOPE": announce, "RESET_SCOPES": reset, "SEND": send}
        rendered = template
        for name, method in pieces.items():
            marker = "// @" + name + "@"
            assert rendered.count(marker) == 1
            rendered = rendered.replace(marker, method)
        assert "// @" not in rendered
        target = ROOT / "regression/generated" / (variant + ".rs")
        target.write_text(rendered)
        records[variant] = {
            "sha256": hashlib.sha256(rendered.encode()).hexdigest(),
            "methods": {name: hashlib.sha256(method.encode()).hexdigest() for name, method in pieces.items()},
            "tests_proposed": rendered.count("#[test]"),
            "compiled_or_run": False,
        }
    (ROOT / "regression/extraction.json").write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
