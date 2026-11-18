"""Make two synthetic public user-message DTO arrays for upstream history_demo.py."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

FIXTURE = "examples/performance/native-stream/fixture_server.py"
FIXTURE_SHA = "79b6836a17a710c06fa05b4a26d66165bc72221cd630a5ca569f67a8d08e7a4b"
BODY = "Обычный вопрос про файл: x < y && y > z. \n**это буквальный текст**\n" * 512
URL = " https://example.org/x"


def generate(desktop, output):
    source = desktop / FIXTURE
    if hashlib.sha256(source.read_bytes()).hexdigest() != FIXTURE_SHA:
        raise ValueError("use the pinned Desktop (210cc9f) fixture")
    spec = importlib.util.spec_from_file_location("native_stream_fixture", source)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    output.mkdir(parents=True, exist_ok=False)
    result = {}
    for name, body in {"plain": BODY + " 0", "url": BODY + URL + " 0"}.items():
        rows = [fixture.message(body, 256, role="user")]
        path = output / (name + ".json")
        path.write_bytes((json.dumps(rows, ensure_ascii=False, indent=2) + "\n").encode())
        result[name] = {
            "source_bytes": len(body.encode()),
            "source_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "dto_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("desktop", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate(args.desktop, args.output)
