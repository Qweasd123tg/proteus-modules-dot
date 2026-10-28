#!/usr/bin/env python3
"""Run mocked stdlib tests; reject standard process/network audit events."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def deny_process_network(event, args):
    if event.startswith(("socket.", "subprocess.")) or event in {
        "subprocess.Popen", "os.system", "os.posix_spawn", "os.exec",
        "os.spawn", "os.fork", "os.forkpty", "pty.spawn", "os.startfile",
        "os.startfile/2",
    }:
        raise RuntimeError("Mocked validation forbids process/network action: " + event)


def main():
    sys.addaudithook(deny_process_network)
    suite = unittest.TestSuite([
        unittest.TestLoader().discover(
            str(ROOT / "after/scripts"), pattern="test_cargo_binary.py",
        ),
        unittest.TestLoader().discover(
            str(ROOT / "reference"), pattern="test_extensions_cwd.py",
        ),
    ])
    expected = json.loads((ROOT / "VALIDATION.json").read_text())["tests"]["total"]
    if expected != 26 or suite.countTestCases() != expected:
        raise RuntimeError("Incomplete mocked test discovery")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
