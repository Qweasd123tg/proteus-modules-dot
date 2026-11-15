"""Generate source-exact Rust callback controls; never compile or run Rust."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "regression/template.rs").read_text()


def extract(source, name):
    start = source.index("fn " + name + "(")
    start = source.rfind("\n", 0, start) + 1
    end = source.index("{", start) + 1
    depth = 1
    # Selected functions have balanced braces in their literals and comments.
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    raw = source[start:end].strip()
    adapted = raw.replace("pub(super) ", "pub ").replace(
        "super::extensions::OpenDocument", "OpenDocument"
    )
    return raw, adapted


def main():
    records = []
    for variant in ("baseline", "candidate"):
        projects = ROOT / ("sources" if variant == "baseline" else "candidate") / "src/ui/projects.rs"
        src = projects.read_text()
        functions = ["open_project"]
        if variant == "candidate":
            functions.append("request_project_catalog")
        functions.append("finish_project_navigation")
        methods = []
        helpers = []
        for name, source, target in [
            *[(name, src, methods) for name in functions],
            ("set_sessions", (ROOT / "sources/src/ui/chats.rs").read_text(), methods),
            *[(name, src, helpers) for name in ("latest_main_session", "project_open")],
        ]:
            raw, adapted = extract(source, name)
            target.append(adapted)
            records.append({"variant": variant, "function": name,
                            "source_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                            "adapted_sha256": hashlib.sha256(adapted.encode()).hexdigest()})
        generated = TEMPLATE.replace("// @METHODS@", "\n".join(methods)).replace("// @HELPERS@", "\n".join(helpers))
        output = ROOT / "regression/generated" / (variant + ".rs")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(generated)
    (ROOT / "regression/extraction.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
