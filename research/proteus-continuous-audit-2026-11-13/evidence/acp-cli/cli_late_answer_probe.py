import json, os, pathlib, pty, select, signal, subprocess, tempfile, time, sys
binary = '/workspace/shared/proteus-runtime-audit-target/debug/proteus'
fixture = '/workspace/shared/proteus-review-20261112/core/target/sources/modules/target/debug/proteus-reference-module'
command_fixture = '/workspace/shared/core-acp-cli-chain/crates/proteus-core/tests/fixtures/process_commands.py'
with tempfile.TemporaryDirectory(prefix='proteus-cli-late-answer-') as tmp:
    root = pathlib.Path(tmp)
    config = root / 'config.toml'
    config.write_text('''[components.test-model]
command = %s
[components.test-model.exports.model.fake]
[module_config.model.fake]
implementation = "fake"
[components.command-probe]
command = "/usr/bin/python3"
args = [%s]
[components.command-probe.exports.tool."probe.commands"]
[components.command-probe.exports.policy."probe.policy"]
[modules]
policy = "probe.policy"
[tools]
enabled = ["probe_command"]
[app_server]
approval_timeout_ms = 200
[event_log]
path = %s
''' % (json.dumps(fixture), json.dumps(command_fixture), json.dumps(str(root / 'events.jsonl'))))
    master, slave = pty.openpty()
    p = subprocess.Popen([binary, '--config', str(config), '--cwd', tmp, '--interactive'],
                         stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
    os.close(slave)
    transcript = bytearray()
    def until(needle, timeout=10, allow_exit=False):
        start = len(transcript)
        deadline = time.monotonic() + timeout
        while needle.encode() not in transcript[start:]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('timeout waiting for ' + repr(needle) + ':\n' + transcript.decode(errors='replace'))
            ready, _, _ = select.select([master], [], [], remaining)
            if ready:
                try: chunk = os.read(master, 65536)
                except OSError:
                    if allow_exit: return transcript[start:].decode(errors='replace') + '\n[PTY closed]\n'
                    raise RuntimeError('PTY closed: ' + transcript.decode(errors='replace'))
                if not chunk: raise RuntimeError('PTY EOF')
                transcript.extend(chunk)
        return transcript[start:].decode(errors='replace')
    try:
        until('Context waiting')
        os.write(master, b'/probe\n')
        until('Approve this tool call?')
        time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 0.8)
        os.write(master, b'n\n')
        first = until('Context waiting')
        os.write(master, b'/history\n')
        second = until('Context waiting')
        os.write(master, b'/history\n')
        third = until('Context waiting', allow_exit=True)
        print('=== FIRST COMMAND AFTER DELAYED REJECTION ===\n' + first)
        print('=== NEXT /history ===\n' + second)
        print('=== THIRD /history ===\n' + third)
        if len(sys.argv) <= 1 or float(sys.argv[1]) > 0.3:
            assert 'unknown approval id' in second, second
            assert 'unexpected response id' in third, third
        else:
            assert 'messages:' in second and 'messages:' in third, (second, third)
        print('tool_ran=', (root / 'command-started').exists())
        assert not (root / 'command-started').exists(), 'fixture must never run after denial'
        if p.poll() is None:
            os.write(master, b'/exit\n')
        try: p.wait(timeout=4)
        except subprocess.TimeoutExpired: pass
    finally:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
        os.close(master)
