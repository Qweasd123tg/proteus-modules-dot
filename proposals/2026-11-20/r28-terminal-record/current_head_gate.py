"""R28 Core guard. Reuse R27's real private synthetic seed/stdio fixture. No user data."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
PROBE_PATH = Path(os.environ.get("R27_PROBE", HERE.parents[1] / "r27/probe/probe.py"))
spec = importlib.util.spec_from_file_location("cold_fixture", PROBE_PATH)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


async def run():
    with tempfile.TemporaryDirectory(dir=HERE, prefix="current-head-") as tmp:
        base = Path(tmp).resolve()
        cli = p.config(base)
        seed = await p.seed(cli, 12, 32)
        old = seed["checkpoint"]
        journal = Path(old["session"]["session_dir"]) / "journal.jsonl"
        assert journal.resolve().is_relative_to(base)
        before = journal.read_bytes()
        # Positive control: the standard checkpoint is obtainable at this exact head.
        _, healthy_root = await p.attach(cli, old)
        assert healthy_root != seed["root_thread_id"]
        proc = await p.start(cli, [
            "--resume-session", old["session"]["session_dir"],
            "--resume-child-checkpoint", json.dumps(old, separators=(",", ":")),
        ])
        try:
            # This is still the *first* inbound request after successful strict launch.
            # The initial snapshot proves launch/assembly completed with original bytes.
            while True:
                _, _, frame = await p.frame(proc)
                if p.tag(frame) == "session_snapshot":
                    assert frame["event"]["snapshot"]["session_id"] == old["session"]["session_id"]
                    break
            assert journal.read_bytes() == before
            # Replace one decimal digit of a timestamp (not seq/revision or payload) in
            # our disposable journal; retain size, inode and mtime. ctime may advance.
            st = journal.stat()
            match = re.search(rb'"timestamp_ms"\s*:\s*(\d+)', before)
            assert match
            pos = match.end(1) - 1
            replacement = b"1" if before[pos:pos + 1] != b"1" else b"2"
            with journal.open("r+b") as src:
                src.seek(pos)
                src.write(replacement)
                src.flush()
                os.fsync(src.fileno())
            os.utime(journal, ns=(st.st_atime_ns, st.st_mtime_ns))
            observed = journal.stat()
            assert (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) == (
                observed.st_dev, observed.st_ino, observed.st_size, observed.st_mtime_ns)
            altered = before[:pos] + replacement + before[pos + 1:]
            assert journal.read_bytes() == altered
            req_id = str(uuid.uuid4())
            await p.send(proc, {"type": "child_session_checkpoint", "id": req_id})
            while True:
                _, _, result = await p.frame(proc)
                if result["type"] == "response" and result.get("id") == req_id:
                    break
            if result["ok"]:
                new = result["output"]["checkpoint"]
                assert set(old) == set(new)
                changed = [k for k in old if old[k] != new[k]]
                assert changed == ["content_sha256"], changed
                disposition = "same_revision_new_content_digest"
            else:
                disposition = "checkpoint_rejected"
            await p.clean(proc)
            assert journal.read_bytes() == altered
        finally:
            p.emergency(proc)
        # The altered bytes are still a well-formed settled history. An old checkpoint
        # must fail *before* normal bridge startup if it is presented to a new peer.
        stale = await asyncio.create_subprocess_exec(
            *cli, "--resume-session", old["session"]["session_dir"],
            "--resume-child-checkpoint", json.dumps(old, separators=(",", ":")),
            "server", "stdio", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(stale.communicate(), timeout=20)
            assert stale.returncode != 0 and not stdout
            assert b"parked child journal changed" in stderr, stderr.decode(errors="replace")[:160]
        finally:
            p.emergency(stale)
        # Restore only our temp seed to demonstrate nondestructive positive control.
        journal.write_bytes(before)
        _, root = await p.attach(cli, old)
        assert root not in (healthy_root, seed["root_thread_id"])
        print(json.dumps(dict(
            gate="post_launch_same_revision_revalidation", precheck="exact",
            first_request=disposition, stale_relaunch="rejected_without_stdout",
            restored="exact", journal_same_inode_size_mtime=True,
            core_sha256=p.fhash(p.CLI), worker_sha256=p.fhash(p.WORKER),
        ), sort_keys=True))


if __name__ == "__main__":
    asyncio.run(run())
