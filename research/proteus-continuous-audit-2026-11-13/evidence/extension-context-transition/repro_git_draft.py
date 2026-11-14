#!/usr/bin/env python3
"""Actual unchanged Git+SDK; session switching and synthetic GET-only API."""
import argparse, hashlib, http.server, json, pathlib, subprocess, threading, urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
A, B = '/fixture/session-a', '/fixture/session-b'
DRAFT = 'Keep this unfinished commit description\n\nSynthetic draft body.'

class API(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        self.server.reads.append({'method': 'GET', 'path': url.path, 'query': urllib.parse.parse_qs(url.query)})
        if url.path == '/workspace/changes':
            data = {'repository': True, 'refs_revision': 'r1', 'branch': 'main', 'head': None,
                    'upstream': None, 'ahead': 0, 'behind': 0, 'entries': []}
        elif url.path == '/workspace/diff':
            data = {'kind': 'text', 'patch': 'synthetic diff', 'revision': 'file-r1'}
        elif url.path == '/workspace/branches':
            data = {'branches': [{'name': 'main'}]}
        else:
            self.server.unexpected.append(self.path)
            self.send_error(404)
            return
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.server.unexpected.append('POST ' + self.path)
        self.send_error(405)

    def log_message(self, *args):
        pass

def walk(v):
    if isinstance(v, dict):
        yield v
        for item in v.values(): yield from walk(item)
    elif isinstance(v, list):
        for item in v: yield from walk(item)

def context(name, session):
    return {'type': 'context', 'context': name, 'workspace': '/fixture/project', 'session_dir': session}

def render(view, name, session, surface='panel', argument=None):
    return {'type': 'render', 'context': name, 'session_dir': session, 'surface': surface,
            'view': view, 'argument': argument}

def event(name, session):
    return {'type': 'event', 'context': name, 'session_dir': session, 'event': 'session_opened', 'document': None}

def run(binary, scenario):
    with http.server.ThreadingHTTPServer(('127.0.0.1', 0), API) as api:
        api.reads = []; api.unexpected = []
        threading.Thread(target=api.serve_forever, daemon=True).start()
        messages = [
            {'type': 'hello', 'protocol': 4, 'features': [], 'server': {'origin': f'http://127.0.0.1:{api.server_port}', 'token': 'synthetic'}},
            context('window', A), render('panel', 'window', A),
            context('window:command', A), render('badge', 'window:command', A, 'badge'),
            {'type': 'action', 'view': 'panel', 'sequence': 1, 'action': 'message', 'value': DRAFT},
        ]
        if scenario == 'retained-document-control':
            messages += [context('window:space:a', A), render('doc', 'window:space:a', A, 'document', 'fixture.txt')]
        if scenario == 'same-session-control':
            messages += [context('window', A), event('window', A), render('panel', 'window', A)]
        elif scenario == 'child-command-control':
            for session in [B, A]:
                messages += [context('window:command', session), event('window:command', session),
                             render('badge', 'window:command', session, 'badge')]
            messages += [render('panel', 'window', A)]
        else:
            surfaces = [('window', 'panel', 'panel'), ('window:command', 'badge', 'badge')]
            if scenario == 'badge-first-roundtrip': surfaces.reverse()
            for session in [B, A]:
                for name, view, surface in surfaces:
                    messages += [context(name, session), event(name, session), render(view, name, session, surface)]
        proc = subprocess.run([str(binary)], input=''.join(json.dumps(m) + '\n' for m in messages), text=True,
                              capture_output=True, timeout=10)
        api.shutdown()
        assert proc.returncode == 0 and not proc.stderr, (proc.returncode, proc.stderr)
        assert not api.unexpected, api.unexpected
        output = [json.loads(line) for line in proc.stdout.splitlines()]
        trace = []
        for response in output:
            if response.get('type') == 'view' and response.get('view') == 'panel':
                inputs = [n for n in walk(response['root']) if n.get('type') == 'input' and n.get('id') == 'message']
                assert len(inputs) == 1, inputs
                trace.append({'session': response.get('session_dir'), 'sequence': response.get('sequence'), 'draft': inputs[0]['value']})
        assert any(t['draft'] == DRAFT for t in trace), trace
        assert trace[-1]['session'] == A and trace[-1]['sequence'] == 1, trace
        observed = trace[-1]['draft']
        record = {'scenario': scenario, 'input': messages, 'output': output, 'trace': trace,
                  'http': api.reads, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                  'returncode': proc.returncode, 'stderr': proc.stderr, 'native_gui_run': False}
        (HERE / (scenario + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        return observed, trace

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=pathlib.Path, default=HERE / 'target/debug/git')
    parser.add_argument('--require-fixed', action='store_true')
    args = parser.parse_args()
    results = {}
    for scenario in ['same-session-control', 'child-command-control', 'session-roundtrip',
                     'badge-first-roundtrip', 'retained-document-control']:
        observed, trace = run(args.binary.resolve(), scenario)
        results[scenario] = {'draft_preserved': observed == DRAFT, 'trace': trace}
    assert results['same-session-control']['draft_preserved']
    assert results['child-command-control']['draft_preserved']
    assert results['retained-document-control']['draft_preserved']
    if not args.require_fixed:
        assert not results['session-roundtrip']['draft_preserved']
        assert not results['badge-first-roundtrip']['draft_preserved']
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if args.require_fixed:
        assert results['session-roundtrip']['draft_preserved'], 'A→B→A must preserve an unfinished Git commit message without requiring a retained Git document'

if __name__ == '__main__': main()
