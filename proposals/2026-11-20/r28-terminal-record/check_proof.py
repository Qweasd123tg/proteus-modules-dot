"""R28 regression gates for a local R24-compatible peer and JSONL worker. No model calls."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("PROTEUS_R27_PROBE", str(HERE.parents[1] / "r27/probe")))
import probe  # R27's unchanged fixture and subprocess helpers


def selection(checkpoint):
    return [
        "--resume-session", checkpoint["session"]["session_dir"],
        "--resume-child-checkpoint", json.dumps(checkpoint, separators=(",", ":")),
    ]


async def rejected(cli, checkpoint, expected_error):
    proc = await asyncio.create_subprocess_exec(
        *cli, *selection(checkpoint), "server", "stdio",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, start_new_session=True,
    )
    try:
        check = b'{"type":"child_session_checkpoint","id":"test"}\n'
        out, err = await asyncio.wait_for(proc.communicate(check), 10)
        assert proc.returncode != 0 and not out and expected_error.encode() in err, (
            proc.returncode, len(out), err.decode(errors="replace")[:240],
        )
    finally:
        probe.emergency(proc)
        await proc.wait()


async def bootstrap_snapshot(peer, checkpoint):
    # An explicit barrier for the writer-loss test, not a protocol ordering requirement.
    while True:
        _, _, frame = await probe.frame(peer)
        if probe.tag(frame) == "session_snapshot":
            assert frame["event"]["snapshot"]["session_id"] == checkpoint["session"]["session_id"]
            return


def owns_fixture_worker(pid, peer_pid):
    try:
        path = Path("/proc") / str(pid)
        parent = next(line.split()[1] for line in (path / "status").read_text().splitlines()
                      if line.startswith("PPid:"))
        return int(parent) == peer_pid and (path / "exe").resolve(strict=True) == probe.WORKER
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return False


async def checkpoint_response(peer):
    ident = str(uuid.uuid4())
    await probe.send(peer, dict(type="child_session_checkpoint", id=ident))
    while True:
        _, _, frame = await probe.frame(peer)
        if frame.get("type") == "response" and frame.get("id") == ident:
            return frame


async def lost_lease(cli, checkpoint, journal, original):
    peer = await probe.start(cli, selection(checkpoint))
    try:
        await bootstrap_snapshot(peer, checkpoint)
        await rejected(cli, checkpoint, "writer")
        matches = [int(p.name) for p in Path("/proc").glob("[0-9]*")
                   if owns_fixture_worker(int(p.name), peer.pid)]
        assert len(matches) == 1, "expected one disposable worker started by this fixture peer"
        pid, = matches
        fd = os.pidfd_open(pid)
        try:
            assert owns_fixture_worker(pid, peer.pid)
            signal.pidfd_send_signal(fd, signal.SIGTERM)
        finally:
            os.close(fd)
        for _ in range(200):
            if not (Path("/proc") / str(pid)).exists():
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("test storage did not exit")
        for _ in range(2):
            frame = await checkpoint_response(peer)
            assert frame["ok"] is False and frame["output"] is None
        assert journal.read_bytes() == original
        await probe.clean(peer)
    finally:
        probe.emergency(peer)
        await peer.wait()


async def main():
    checks = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        cli = probe.config(base)
        first = await probe.seed(cli, 12, 32)
        checkpoint = first["checkpoint"]
        journal = Path(checkpoint["session"]["session_dir"]) / "journal.jsonl"
        assert journal.resolve(strict=True).is_relative_to(base.resolve())
        original = journal.read_bytes()
        for field, error in [
            ("authority_sha256", "parked child profile changed"),
            ("content_sha256", "parked child journal changed"),
            ("effective_sha256", "parked child effective settings changed"),
        ]:
            wrong = {**checkpoint, field: hashlib.sha256(field.encode()).hexdigest()}
            await rejected(cli, wrong, error)
            assert journal.read_bytes() == original
            checks.append(f"wrong_{field}_no_frames_no_append")
        await lost_lease(cli, checkpoint, journal, original)
        checks += ["simultaneous_cold_writer_excluded",
                   "lost_pinned_writer_rejects_both_first_and_second_checkpoint"]

        peer = await probe.start(cli, selection(checkpoint))
        try:
            # First command on this connection is a legitimate metadata write, not a checkpoint.
            await probe.request(peer, "set_model_configuration",
                                model={"provider": "fake", "model": "fake-tool-model"},
                                reasoning={}, stream=True)
            sealed = (await probe.request(peer, "child_session_checkpoint"))["checkpoint"]
            assert sealed["session"] == checkpoint["session"]
            assert sealed["revision"] == checkpoint["revision"]
            assert sealed["content_sha256"] != checkpoint["content_sha256"]
            assert journal.read_bytes() == original
            checks.append("same_journal_new_selection_document_before_first_checkpoint")

            await probe.request(peer, "set_permission_mode", mode="plan")
            changed = (await probe.request(peer, "child_session_checkpoint"))["checkpoint"]
            assert changed["session"] == sealed["session"]
            assert changed["effective_sha256"] != sealed["effective_sha256"]
            checks.append("permission_change_updates_effective_fingerprint")

            await probe.request(peer, "send", text="archive 3 10", images=[], options={})
            advanced = (await probe.request(peer, "child_session_checkpoint"))["checkpoint"]
            assert advanced["revision"]["session_seq"] > changed["revision"]["session_seq"]
            assert advanced["content_sha256"] != changed["content_sha256"]
            now = journal.read_bytes()
            assert now.startswith(original)
            added = [json.loads(line) for line in now[len(original):].splitlines()]
            kinds = [entry["kind"] for entry in added]
            assert kinds.count("turn_settled") == 1 and kinds[-1] == "turn_settled"
            checks.append("subsequent_append_proves_new_settled_prefix")
            await probe.clean(peer)
        finally:
            probe.emergency(peer)
            await peer.wait()
        await rejected(cli, checkpoint, "parked child journal changed")
        assert journal.read_bytes() == now
        checks.append("outdated_receipt_cannot_reopen_advanced_journal")
    print(json.dumps(dict(cli_sha256=probe.fhash(probe.CLI), worker_sha256=probe.fhash(probe.WORKER),
                          checks=checks), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
