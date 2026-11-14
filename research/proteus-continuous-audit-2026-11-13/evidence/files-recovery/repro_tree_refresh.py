#!/usr/bin/env python3
"""Unmodified Files+SDK, real production polls, synthetic loopback workspace API."""
import argparse, http.server, json, pathlib, threading, time, urllib.parse
from wire_fixture import Fixture, API, Client, context, render, action, walk, SESSION
HERE=pathlib.Path(__file__).resolve().parent

class TreeFixture(Fixture):
    def __init__(self, files):
        super().__init__(); self.files=files; self.fail_once=None; self.failed=[]
    def reply(self,method,url,body):
        u=urllib.parse.urlparse(url); q=urllib.parse.parse_qs(u.query); path=q.get('path',[''])[0]
        if u.path=='/workspace/list' and self.fail_once==path:
            self.fail_once=None
            self.requests.append({'method':method,'path':u.path,'query':q,'body':body,'status':503})
            self.failed.append(path)
            return 503,{'error':'synthetic temporary listing failure'}
        return super().reply(method,url,body)

def rows(message):
    return [{'id':row['id'],'expanded':row.get('expanded'),'label':row['label']} for node in walk(message.get('root')) if node.get('type')=='tree' for row in node['rows']]
def ids(message):return [r['id'] for r in rows(message)]
def list_count(f,path):return sum(r['path']=='/workspace/list' and r['query'].get('path',[''])[0]==path for r in f.requests)
def next_poll(c):return c.until(lambda m:m.get('type')=='view' and m.get('view')=='panel')[-1]
def send(c,msg,seq=None):c.one(msg,'panel',seq);return c.output[-1]

class Run:
    def __init__(self,binary,files):
        self.fixture=TreeFixture(files); self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),API); self.server.fixture=self.fixture
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.client=Client(binary,f'http://127.0.0.1:{self.server.server_port}','files')
        self.client.send(context('window')); self.initial=send(self.client,render('panel','window'))
    def save(self,name,result):
        trace=self.client.close(); (HERE/(name+'.json')).write_text(json.dumps({'result':result,'trace':trace,'api':self.fixture.requests},ensure_ascii=False,indent=2)+'\n'); return result
    def close(self):
        if self.client.p.poll() is None:self.client.p.terminate();self.client.p.wait(timeout=3)
        self.server.shutdown();self.server.server_close()

def folded_expand(binary,all_folders):
    r=Run(binary,{'src/lib/existing.rs':'original','top.txt':'top'});c=r.client;f=r.fixture
    try:
        assert 'src/lib' in ids(r.initial),rows(r.initial)
        if all_folders: msg=action('panel',1,'expand-all','src/lib')
        else: msg=action('panel',1,'files',{'id':'src/lib','event':'expand'})
        opened=send(c,msg,1);assert 'src/lib/existing.rs' in ids(opened),rows(opened)
        f.files['src/new.rs']='added outside the extension';started=time.monotonic()
        polls=[next_poll(c) for _ in range(2)];elapsed=time.monotonic()-started
        result={'operation':'expand-all' if all_folders else 'expand','initial_rows':rows(r.initial),'opened_rows':rows(opened),'poll_rows':[rows(p) for p in polls],'elapsed_seconds':round(elapsed,3),'src_list_requests_after_two_polls':list_count(f,'src'),'src_lib_list_requests_after_two_polls':list_count(f,'src/lib'),'new_file_visible':all('src/new.rs' in ids(p) for p in polls),'native_gui':False}
        # Full invalidation is a positive recovery control, not part of the repro.
        recovered=send(c,{'type':'event','context':'window','event':'run_settled','session_dir':SESSION},1)
        result['run_settled_rows']=rows(recovered)
        if 'src/new.rs' not in ids(recovered):
            recovered=send(c,action('panel',2,'files',{'id':'src','event':'expand'}),2)
        result['full_invalidation_then_open_rows']=rows(recovered)
        assert 'src/new.rs' in ids(recovered),result
        assert elapsed>=9.5,result
        return r.save('folded-'+result['operation'],result)
    finally:r.close()

def transient_listing(binary,fail_root):
    r=Run(binary,{'src/visible.rs':'original','top.txt':'top'});c=r.client;f=r.fixture
    try:
        opened=send(c,action('panel',1,'files',{'id':'src','event':'expand'}),1); assert 'src/visible.rs' in ids(opened)
        f.fail_once='' if fail_root else 'src';started=time.monotonic()
        polls=[next_poll(c) for _ in range(3)];elapsed=time.monotonic()-started
        result={'failing_path':'' if fail_root else 'src','opened_rows':rows(opened),'poll_rows':[rows(p) for p in polls],'poll_error_strings':[[n.get('text') for n in walk(p.get('root')) if n.get('tone')=='danger'] for p in polls],'elapsed_seconds':round(elapsed,3),'failed_requests':f.failed,'src_list_requests_after_polls':list_count(f,'src'),'root_list_requests_after_polls':list_count(f,''),'recovered_automatically':'src/visible.rs' in ids(polls[-1]),'native_gui':False}
        recovered=send(c,action('panel',2,'files',{'id':'src','event':'expand'}),2)
        result['manual_expand_rows']=rows(recovered)
        assert 'src/visible.rs' in ids(recovered),result
        assert elapsed>=14.5,result
        return r.save('transient-root-control' if fail_root else 'transient-child-repro',result)
    finally:r.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=pathlib.Path,default=HERE/'target/debug/files');p.add_argument('--case',choices=['folded','transient','all'],default='all');p.add_argument('--require-fixed',action='store_true');a=p.parse_args();results=[]
    if a.case in ['folded','all']:
        bug=folded_expand(a.binary,True);control=folded_expand(a.binary,False);results += [bug,control]
        assert control['new_file_visible']; assert control['src_list_requests_after_two_polls']==3
        if a.require_fixed: assert bug['new_file_visible'],bug
        else: assert not bug['new_file_visible']; assert bug['src_list_requests_after_two_polls']==1
    if a.case in ['transient','all']:
        bug=transient_listing(a.binary,False);control=transient_listing(a.binary,True);results += [bug,control]
        assert control['recovered_automatically'],control
        if a.require_fixed: assert bug['recovered_automatically'],bug
        else: assert not bug['recovered_automatically']; assert bug['failed_requests']==['src']; assert bug['src_list_requests_after_polls']==2
    print(json.dumps(results,ensure_ascii=False,indent=2))
