#!/usr/bin/env python3
"""Real unchanged Git + SDK NDJSON process, synthetic loopback HTTP only."""
import argparse, contextlib, http.server, json, pathlib, subprocess, threading, urllib.parse
HERE = pathlib.Path(__file__).resolve().parent
DEFAULT = HERE / 'extension-target/debug/git'
SESSION = '/fixture/session'
READS = []
class API(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        READS.append(path)
        if path == '/workspace/log':
            data = {'head':'abc1234','has_more':False,'entries':[{'hash':'abc1234000000000000000000000000000000000','short':'abc1234','parents':[],'summary':'First fixture commit','author':'Fixture','email':'fixture@example.invalid','time':0,'refs':[{'name':'main','kind':'branch'}]}]}
        elif path == '/workspace/branches': data = {'branches':[{'name':'main'}]}
        elif path == '/workspace/commit': data = {'hash':'abc1234000000000000000000000000000000000','short':'abc1234','summary':'First fixture commit','body':'','parents':[],'files':[]}
        elif path == '/workspace/changes':
            data = {'repository':True,'refs_revision':'refs-1','branch':'main','head':{'short':'abc1234','summary':'First fixture commit'},'upstream':None,'ahead':0,'behind':0,'truncated':False,'entries':[]}
        else:
            self.send_error(404); return
        body = json.dumps(data).encode()
        self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass

def ctx(name): return {'type':'context','context':name,'workspace':'/fixture/project','session_dir':SESSION}
def render(view, context): return {'type':'render','context':context,'view':view,'surface':'panel','session_dir':SESSION}
def act(view, sequence, action, value=None): return {'type':'action','view':view,'sequence':sequence,'action':action,'value':value}
def shared_second_panel():
    # Desktop registers the same runtime in the destination when a document moves.
    return [{'type':'render','context':'window-a','view':'moved-commit','surface':'document','session_dir':SESSION,'argument':'Коммит abc1234'}, ctx('window-b'), {'type':'rehost','view':'moved-commit','context':'window-b'}, render('panel-b','window-b')]
def event(context): return {'type':'event','context':context,'event':'navigation_changed','session_dir':SESSION,'document':None}
def walk(root):
    yield root
    for child in root.get('children', []): yield from walk(child)
    for tab in root.get('tabs', []):
        for child in tab.get('children', []): yield from walk(child)
def history(root):
    tabs = next(n for n in walk(root) if n.get('type') == 'tabs')
    children = tabs['tabs'][1]['children']
    nodes = [n for c in children for n in walk(c)]
    return {'loaded':any(n.get('type') == 'list' for n in nodes), 'loading':[n.get('text') for n in nodes if n.get('type') == 'loading']}

def run(binary, origin, tail, name):
    messages = [
        {'type':'hello','protocol':4,'server':{'origin':origin,'token':'synthetic'},'features':[]},
        ctx('window-a'),
        {'type':'session_snapshot','context':'window-a','session_dir':SESSION,'state':{},'entries':[]},
        render('panel-a','window-a'), act('panel-a',1,'tab',1), *tail,
    ]
    proc = subprocess.run([str(binary)],input=''.join(json.dumps(m)+'\n' for m in messages),text=True,capture_output=True,timeout=10)
    assert proc.returncode == 0, proc.stderr
    output = [json.loads(line) for line in proc.stdout.splitlines()]
    trace = [{'view':m['view'],'sequence':m.get('sequence'),**history(m['root'])} for m in output if m.get('type') == 'view' and m.get('view','').startswith('panel-')]
    assert not any(m.get('type') not in ['view'] for m in output), output
    record = {'input':messages,'output':output,'trace':trace,'stderr':proc.stderr,'http_reads':list(READS)}
    (HERE / f'{name}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    READS.clear()
    return trace

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--binary',type=pathlib.Path,default=DEFAULT); parser.add_argument('--require-fixed',action='store_true'); args=parser.parse_args()
    with http.server.ThreadingHTTPServer(('127.0.0.1',0),API) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        origin=f'http://127.0.0.1:{server.server_port}'
        try:
            single=run(args.binary,origin,[render('panel-a','window-a'),event('window-a'),act('panel-a',2,'refresh')],'single-panel-control')
            assert all(t['loaded'] for t in single if t['sequence'] >= 1), single
            multi=run(args.binary,origin,[*shared_second_panel(),event('window-a'),act('panel-a',2,'refresh'),act('panel-a',3,'tab',0),act('panel-a',4,'tab',1)],'second-panel-repro')
            a=[t for t in multi if t['view']=='panel-a']
            assert a[1]['loaded'], a
            if not args.require_fixed:
                assert not a[2]['loaded'] and a[2]['loading']==['Загрузка истории…'], a
                assert not next(t for t in a if t['sequence']==2)['loaded'], a
            assert a[-1]['sequence']==4 and a[-1]['loaded'], a
            switch=run(args.binary,origin,[*shared_second_panel(),act('panel-b',1,'tab',1),act('panel-b',2,'tab',0)],'sibling-tab-repro')
            a2=[t for t in switch if t['view']=='panel-a']
            assert a2[-2]['loaded'], a2
            if not args.require_fixed: assert not a2[-1]['loaded'], a2
            result={'single_panel_control':'PASS','second_panel_history_reset_observed':'PASS','refresh_does_not_recover_observed':'PASS','local_tab_roundtrip_recovers_control':'PASS','sibling_changes_tab_breaks_history_observed':'PASS','source_trace':a,'sibling_switch_trace':a2,'native_ui_run':False}
            print(json.dumps(result,ensure_ascii=False,indent=2))
            if args.require_fixed:
                assert a[2]['loaded'], 'History in existing panel must survive opening second panel'
                assert next(t for t in a if t['sequence']==2)['loaded'], 'Refresh must retain History in addressed panel'
                assert a2[-1]['loaded'], 'Changing sibling tab must not hide History in existing panel'
        finally: server.shutdown()
if __name__=='__main__': main()
