#!/usr/bin/env python3
"""Unchanged Git process: previous-commit shortcut -> graph folder collapse."""
import argparse, http.server, json, subprocess, threading
from repro_git_views import API, HERE, DEFAULT, SESSION, ctx, render, act, walk
FULL='abc1234000000000000000000000000000000000'
SHORT='abc1234'
class CommitAPI(API):
    def do_GET(self):
        if self.path.split('?')[0] == '/workspace/commit':
            body=json.dumps({'hash':FULL,'short':SHORT,'summary':'First fixture commit','body':'','parents':[],'author':'Fixture','email':'fixture@example.invalid','time':0,'files':[{'path':'src/a.rs','status':'modified','added':1,'deleted':0}],'patch':'','truncated':False}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        else: super().do_GET()

def inspector(root):
    nodes=list(walk(root)); graph=next(n for n in nodes if n.get('type')=='lanes'); tree=next(n for n in nodes if n.get('id')=='commit-detail-files')
    return {'selected_graph_ids':[r['id'] for r in graph['rows'] if r.get('selected')], 'folder_expanded':next(r for r in tree['rows'] if r['id']=='dir:src')['expanded'],'file_visible':any(r['id']=='src/a.rs' for r in tree['rows'])}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--require-fixed',action='store_true'); args=p.parse_args()
    with http.server.ThreadingHTTPServer(('127.0.0.1',0),CommitAPI) as server:
        threading.Thread(target=server.serve_forever,daemon=True).start()
        messages=[{'type':'hello','protocol':4,'server':{'origin':f'http://127.0.0.1:{server.server_port}','token':'synthetic'},'features':[]},ctx('window-a'),{'type':'session_snapshot','context':'window-a','session_dir':SESSION,'state':{},'entries':[]},render('panel-a','window-a'),act('panel-a',1,'open_commit',SHORT),{'type':'render','context':'window-a','view':'commit','surface':'document','session_dir':SESSION,'argument':'Коммит '+SHORT},act('panel-a',2,'graph'),{'type':'render','context':'window-a','view':'graph','surface':'document','session_dir':SESSION,'argument':'Граф коммитов'},act('graph',1,'detail_file',{'id':'dir:src','event':'collapse'}),act('graph',2,'graph_log',{'id':FULL,'event':'select'}),act('graph',3,'detail_file',{'id':'dir:src','event':'collapse'}),act('graph',4,'detail_file',{'id':'dir:src','event':'expand'})]
        try:
            proc=subprocess.run([str(DEFAULT)],input=''.join(json.dumps(m)+'\n' for m in messages),capture_output=True,text=True,timeout=10)
            assert proc.returncode==0,proc.stderr
            out=[json.loads(line) for line in proc.stdout.splitlines()]
            initial=next(m for m in out if m.get('view')=='panel-a' and m.get('type')=='view')['root']
            shortcut=next(n for n in walk(initial) if n.get('action')=='open_commit')
            assert shortcut['value']==SHORT
            assert any(m.get('type')=='open_document' and m.get('argument')=='Коммит '+SHORT for m in out), out
            trace=[{'sequence':m['sequence'],**inspector(m['root'])} for m in out if m.get('type')=='view' and m.get('view')=='graph']
            if not args.require_fixed:
                assert trace[0]=={'sequence':0,'selected_graph_ids':[],'folder_expanded':True,'file_visible':True},trace
                assert trace[1]=={'sequence':1,'selected_graph_ids':[],'folder_expanded':True,'file_visible':True},trace
            assert trace[3]=={'sequence':3,'selected_graph_ids':[FULL],'folder_expanded':False,'file_visible':False},trace
            assert trace[4]['folder_expanded'] and trace[4]['file_visible'],trace
            (HERE/'short-hash-repro.json').write_text(json.dumps({'input':messages,'output':out,'trace':trace,'stderr':proc.stderr},ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({'emitted_shortcut_value':shortcut['value'],'full_hash_from_API':FULL,'trace':trace,'short_hash_collapse_ignored_observed':'PASS','full_hash_collapse_works_control':'PASS','full_hash_expand_works_control':'PASS','native_ui_run':False},ensure_ascii=False,indent=2))
            if args.require_fixed:
                assert not trace[1]['folder_expanded'], 'Directory must collapse after opening head commit from panel shortcut'
                assert trace[0]['selected_graph_ids']==[FULL], 'Graph row must select the shortcut commit canonical identity'
        finally: server.shutdown()
if __name__=='__main__': main()
