"""Compare complete JSONL views on CommonMark inputs and three public Proteus documents.

No model/service or GUI; this is A/B parity of the extension's own behaviour,
NOT CommonMark compliance. The spec's HTML is deliberately not used as oracle.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

SPEC_HASH = "d431b29d97b6f73e69d547109cf5081578fac931e72afe95639ebe766c1b2a20"
CORE = "8ea2cdaf4195ae24e941354f68d4e97335d139d7"
DOCS = ["docs/development/memory.md", "docs/development/testing.md", "docs/architecture/architecture.md"]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sources(spec, repo):
    data = spec.read_bytes()
    if digest(data) != SPEC_HASH:
        raise ValueError("Wrong CommonMark 0.31.2 spec.json")
    for row in json.loads(data):
        yield f"commonmark-{row['example']}", row["markdown"]
    for name in DOCS:
        yield name, subprocess.check_output(["git", "-C", repo, "show", CORE + ":" + name]).decode()


def as_line(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"


def requests(corpus, out):
    out.write(as_line({"type": "hello", "protocol": 4, "workspace": "/fixture",
                       "features": ["surfaces.content.v1", "widgets.rich_text.v1", "widgets.rich_text.inlines.v1", "widgets.content.v1", "widgets.code_embedded.v1"]}))
    spans = []
    for i, (name, src) in enumerate(corpus):
        view = f"content:fixture-{i}"
        # Fresh source, hot duplicate, shorter source, re-append; change only
        # contributor configuration on the last revision. Split at Unicode scalars.
        cuts = sorted(set([len(src) // j for j in (8, 4, 2)] + [len(src)]))
        cuts += [len(src), len(src) // 2, len(src), len(src)]
        for rev, cut in enumerate(cuts):
            out.write(as_line({"type": "render", "surface": "content", "context": "scope",
                "session_dir": "/fixture-session", "view": view,
                "content": {"language": "text/markdown", "source": src[:cut], "source_revision": rev,
                            "context": {"languages": [] if rev == len(cuts)-1 else ["latex","mermaid"]}}}))
        out.write(as_line({"type":"close","view":view}))
        spans.append((name, view, len(cuts)))
    return spans


def main(before, after, spec, core):
    binary_hashes = [digest(p.read_bytes()) for p in (before, after)]
    if binary_hashes[0] == binary_hashes[1]:
        raise ValueError("Expected distinct baseline and candidate binaries")
    corpus = list(sources(spec, core))
    assert len(corpus) == 652 + len(DOCS)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        req = root / "requests.jsonl"
        with req.open("wb") as stream:
            spans = requests(corpus, stream)
        results = []
        for i, bin_path in enumerate((before, after)):
            dest = root / f"out-{i}.jsonl"
            with req.open("rb") as inp, dest.open("wb") as out:
                subprocess.run([bin_path.resolve()], stdin=inp, stdout=out, timeout=90, check=True)
            results.append(dest)
        section_hash = {"commonmark": hashlib.sha256(), "project_docs": hashlib.sha256()}
        counts = {name: 0 for name in section_hash}
        with results[0].open("rb") as a, results[1].open("rb") as b:
            for name, view, n in spans:
                group = "commonmark" if name.startswith("commonmark-") else "project_docs"
                for rev in range(n):
                    l, r = a.readline(), b.readline()
                    if not l or l != r:
                        raise RuntimeError(f"Output mismatch: {name}, revision {rev}")
                    msg = json.loads(l)
                    assert msg["type"] == "view" and msg["view"] == view and msg["source_revision"] == rev
                    assert msg["root"]["type"] == "stack"
                    section_hash[group].update(l)
                    counts[group] += 1
            assert not a.read(1) and not b.read(1)
        print(json.dumps({"spec_sha256": SPEC_HASH, "core": CORE, "documents": DOCS,
            "synthetic_input_sets": 652, "public_project_docs": len(DOCS), "native_executable_sha256": binary_hashes,
            "full_request_sha256": digest(req.read_bytes()), "matching_wire_responses": counts,
            "full_wire_digest_by_group": {g: h.hexdigest() for g, h in section_hash.items()}}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("before","after","spec","core"):
        p.add_argument(arg, type=Path)
    a = p.parse_args()
    main(a.before,a.after,a.spec,a.core)
