import json, pathlib, queue, subprocess, tempfile, threading, time
binary = '/workspace/shared/proteus-runtime-audit-target/debug/proteus'
fixture = '/workspace/shared/proteus-review-20261112/core/target/sources/modules/target/debug/proteus-reference-module'
rows = []
for flags in (['--plan'], ['--auto'], []):
    with tempfile.TemporaryDirectory(prefix='proteus-cli-mode-') as tmp:
        root = pathlib.Path(tmp)
        config = root / 'config.toml'
        config.write_text('''[components.test-model]
command = %s
[components.test-model.exports.model.fake]
[module_config.model.fake]
implementation = "fake"
[permissions]
mode = "normal"
[event_log]
path = %s
''' % (json.dumps(fixture), json.dumps(str(root / 'events.jsonl'))))
        original = config.read_bytes()
        command = [binary, '--config', str(config), '--cwd', tmp, '--new-session', *flags, 'server', 'stdio']
        p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        messages = queue.Queue()
        def read():
            for line in p.stdout:
                messages.put(json.loads(line))
            messages.put(None)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        def request(kind, ident):
            p.stdin.write(json.dumps({'type': kind, 'id': ident}) + '\n'); p.stdin.flush()
            while True:
                item = messages.get(timeout=10)
                if item is None:
                    raise RuntimeError('server stdout closed: ' + p.stderr.read())
                if item.get('type') == 'response' and item.get('id') == ident:
                    assert item['ok'], item
                    return item.get('output')
        try:
            before = request('config_summary', 'before')
            time.sleep(1.0)
            after = request('config_summary', 'after')
            request('shutdown', 'stop')
            p.stdin.close(); p.wait(timeout=5)
            assert p.returncode == 0, p.stderr.read()
            assert config.read_bytes() == original
            row = {'flags': flags, 'before': before['permission_mode'], 'after': after['permission_mode'],
                   'epoch_before': before['module_epoch'], 'epoch_after': after['module_epoch'], 'profile_unchanged': True}
            rows.append(row); print(json.dumps(row))
        finally:
            if p.poll() is None:
                p.kill(); p.wait()
print('observed mode override loss:', sum(r['before'] != r['after'] for r in rows))
