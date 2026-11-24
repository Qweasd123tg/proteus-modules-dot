"""Install identical test-only SDK overlays in private stock and candidate roots."""
from pathlib import Path
import hashlib
import sys
P=Path(__file__).resolve().parent
def blob(b):return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()
def run(root,candidate):
    dst=Path(root).resolve()/"crates/proteus-module-sdk/src"
    src=dst/"session_storage.rs"
    original=src.read_bytes()
    want="6b0b56d4a4a92c0a480619dd7c3b2731845ff444" if candidate else "a9ad263f69e79121395c640b7a8fee23f1dc32d0"
    if blob(original)!=want:raise ValueError(f"expected undecorated pinned source {src}")
    tests=(P/"sdk_tests.rs").read_text()
    if candidate:
        tests=tests.replace("const IS_CANDIDATE: bool = false;","const IS_CANDIDATE: bool = true;")
        inner=(P/"sdk_candidate_tests.rs").read_text().removeprefix("use super::*;\n")
        tests+="\n"+inner
    (dst/"r277_sdk_tests.rs").write_text(tests)
    src.write_bytes(original+b'\n#[cfg(test)]\n#[path = "r277_sdk_tests.rs"]\nmod r277_sdk_tests;\n')
if __name__=="__main__":
    a,b=sys.argv[1:]
    run(a,False);run(b,True)
