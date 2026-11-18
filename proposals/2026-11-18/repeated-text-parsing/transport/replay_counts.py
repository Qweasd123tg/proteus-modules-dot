"""Replay the native host's exact admitted revisions on instrumented children (never for timing)."""
import argparse
import collections
import hashlib
import json
import re
import subprocess
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def line(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("protocol", "fixtures", "proofs", "before_elf", "after_elf"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    table = json.loads(args.proofs.read_text())["cases"]
    protocol = args.protocol.read_text().split("pub const FEATURES:", 1)[1].split("];", 1)[0]
    features = re.findall(r'^    "([^"]+)",$', protocol, re.M)
    assert "surfaces.content.v1" in features
    hello = line({
        "type": "hello", "protocol": 4, "features": features,
        "workspace": "/fixture", "server": {"origin": "", "token": ""},
    })
    languages = ["json-render", "svg", "md", "markdown", "mermaid"]
    context = {
        "languages": languages,
        "contributors": dict(zip(languages, ["json-render", "json-render", "markdown-render", "markdown-render", "mermaid-render"])),
        "theme": {"appearance": "dark"},
    }
    binaries = [args.before_elf, args.after_elf]
    result = {"counter_elf_sha256": [digest(p.read_bytes()) for p in binaries], "cases": {}}
    for key, case in table.items():
        fixture, n, _, mode = key.split("/")
        source = (args.fixtures / (fixture + ".md")).read_bytes()
        assert digest(source) == case["source_sha256"]
        packet = bytearray(hello)
        for observation in case["proofs"]:
            rev = observation["rev"]
            data = source[:len(source) * (rev + 1) // int(n)] if mode == "grow" else source
            text = data.decode("utf8", errors="ignore")
            assert len(text.encode()) == observation["source_bytes"]
            packet.extend(line({
                "type": "render", "surface": "content", "context": "scope", "argument": "0",
                "view": "content:reply", "session_dir": "/fixture-session",
                "content": {"language": "text/markdown", "source": text, "context": context, "source_revision": rev},
            }))

        sides = []
        wire_digests = []
        for binary in binaries:
            run = subprocess.run([binary], input=packet, capture_output=True, check=True, timeout=90)
            frames = run.stdout.splitlines()
            assert len(frames) == len(case["sent_revisions"])
            wire_digests.append(digest(run.stdout))
            for frame, observed in zip(frames, case["proofs"]):
                message = json.loads(frame)
                assert message["type"] == "view" and message["source_revision"] == observed["rev"]
                html = message["root"]["children"][0]["html"]
                assert digest(html.encode()) == observed["html_sha256"]
            samples = []
            total = collections.defaultdict(lambda: [0, 0])
            for log in run.stderr.decode().splitlines():
                tag, value, size = log.split()
                if tag == "MDFRAME":
                    index = len(samples)
                    assert int(value) == case["sent_revisions"][index]
                    assert int(size) == case["proofs"][index]["source_bytes"]
                    samples.append([])
                else:
                    assert tag == "MDPASS" and value in ("route", "html", "inline", "guard")
                    samples[-1].append([value, int(size)])
                    total[value][0] += 1
                    total[value][1] += int(size)
            assert len(samples) == len(frames)
            sides.append({"sum_calls_input_bytes": dict(total), "per_frame": samples})
        assert wire_digests[0] == wire_digests[1]
        result["cases"][key] = {"output_jsonl_sha256": wire_digests[0], "before_after": sides}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
