"""Check the synthetic DTOs through Desktop's official local replay server. No GUI."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import tempfile
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener


def main(desktop, fixtures):
    upstream = desktop / "examples/performance/native-stream"
    sys.path.insert(0, str(upstream.resolve()))
    from history_demo import HistoryFixture
    expected = json.loads(Path(__file__).with_name("fixture-hashes.json").read_text())
    opener = build_opener(ProxyHandler({}))
    for case, digests in expected.items():
        encoded = (fixtures / (case + ".json")).read_bytes()
        assert hashlib.sha256(encoded).hexdigest() == digests["dto_sha256"]
        rows = json.loads(encoded)
        with tempfile.TemporaryDirectory() as root:
            fixture = HistoryFixture(Path(root) / "workspace", Path(root) / "session",
                                     secrets.token_hex(24), transcript=rows).start()
            try:
                query = urlencode({"session_dir": fixture.session})
                request = Request(fixture.origin + "/events?" + query,
                                  headers={"Authorization": "Bearer " + fixture.token})
                with opener.open(request, timeout=5) as response:
                    assert response.status == 200
                    assert response.readline().strip() == b"event: output"
                    line = response.readline()
                    assert line.startswith(b"data: ")
                    assert response.readline().strip() == b""
                    snapshot = json.loads(line[6:])["event"]["snapshot"]
                    assert snapshot["transcript"] == rows and snapshot["history"] is None
                    assert rows[0]["role"] == "user" and not rows[0]["streaming"]
                    digest = hashlib.sha256(rows[0]["text"].encode()).hexdigest()
                    assert digest == digests["source_sha256"]
                    fixture.stopping.set()
                assert not fixture.errors
                print(f"{case}: expected single user row delivered, {digests['source_bytes']} UTF-8 bytes")
            finally:
                fixture.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("desktop", type=Path)
    parser.add_argument("fixtures", type=Path)
    args = parser.parse_args()
    main(args.desktop, args.fixtures)
