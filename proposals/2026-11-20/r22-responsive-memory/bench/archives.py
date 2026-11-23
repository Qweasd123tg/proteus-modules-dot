#!/usr/bin/env python3
"""4 independent passive archive pages vs one independent warm /send, stock HTTP + external JSONL (Linux)."""
import argparse
import json
import os
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from gen_fixture import label
from journal_watch import JournalOpens
from rpc import uid
from prepared import HEAD,case,prime,setup,physical

def require(truth, why):
    if not truth: raise ValueError(why)

def save(path, data):
    tmp=path.with_suffix(path.suffix+'.part')
    tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    tmp.replace(path)

def digest(p):
    h=sha256()
    with p.open('rb') as s:
        while b:=s.read(1<<20): h.update(b)
    return h.hexdigest()

def corpus(dirs):
    files=[(i,str(p.relative_to(d)),digest(p)) for i,d in enumerate(dirs) for p in sorted(d.rglob('*')) if p.is_file() and (p.name=='journal.jsonl' or 'blobs' in p.relative_to(d).parts)]
    return sha256(json.dumps(files).encode()).hexdigest()

def cache(d):
    return sorted(str(p.relative_to(d)) for p in d.rglob('*') if p.is_file() and p.name not in ('journal.jsonl','session.json') and 'blobs' not in p.relative_to(d).parts)

def check(v, sid, start, total):
    require((v['total'],v['start'])==(total,start),'total/start mismatch')
    require(len(v['messages'])==50 and len(v['revision'])>0,'page size/revision')
    actual=[(m['message_id'],m['role'],m['text']) for m in v['messages']]
    expect=[(uid(1000+n),'assistant' if n%2 else 'user',label(sid,n)) for n in range(start,start+50)]
    require(actual==expect,f'page ID/role/text mismatch for {sid} at {start}')
    if sid >= 100:
        require('base' in v and v['base'] is None, 'immutable cold fixture has unexpected base')
        require(all(not m['streaming'] and not m['images'] and m['tool'] is None and m['subagent'] is None
                    for m in v['messages']), 'text-only fixture contains unexpected adornments')
    return v['revision']

def err(exc):
    e={'type':type(exc).__name__,'detail':str(exc)}
    if isinstance(exc,HTTPError):
        e.update(http_status=exc.code,body=exc.read(3000).decode(errors='replace'))
    return e

def ns():return time.monotonic_ns()
def ms(a,b): return round((b-a)/1e6,3)

def run(a,out,root,report):
    sys.path[:0]=[str(a.source/'examples/performance/history-scale'),str(a.source/'examples/performance/common')]
    from fixtures import profile
    from journal import records,text,message_digest
    from proc_sampler import Tree
    golden=a.golden; cfg=root/'config';cwd=golden/'work'
    meta=json.loads((golden/'archives.json').read_text())
    rows=meta['rows']; archives=meta['archives']
    require(len(meta['dirs'])==archives and len(set(meta['dirs']))==archives and archives>=4 and rows>=100,'manifest shape')
    shutil.copytree(golden/'config',cfg)
    active=cfg/meta['active']; dirs=[cfg/k for k in meta['dirs']]
    require(all(d.resolve().is_relative_to(cfg) for d in dirs+[active]),'unsafe fixture')
    require([json.loads((d/'session.json').read_text())['session_id'] for d in [active]+dirs]==[uid(9)]+[uid(100+i) for i in range(archives)],'seeded session identity')
    require(not any(cache(d) for d in dirs),'seed was not app-cache cold')
    initial=corpus(dirs); hot_before=(active/'journal.jsonl').read_bytes()
    hot_model=[p['messages'] for r,p in records(active) if r['kind']=='history_mutated']
    require(len(hot_model)==1 and len(hot_model[0])==100,'invalid hot fixture')
    seed_msgs=hot_model[0]
    report.update(companion_file_hashes={f.name:digest(f) for f in sorted(Path(__file__).parent.glob('*.py'))},archives=archives,rows=rows,canonical_sha_before=initial,stand_sha256=digest(Path(__file__)),profile_sha256=digest(a.source/"examples/performance/history-scale/fixtures.py"),sampler_sha256=digest(a.source/"examples/performance/common/proc_sampler.py"),core_sha256=digest(a.core),worker_sha256=digest(a.worker),reference_sha256=digest(a.reference),fixture_manifest_sha256=digest(golden/'archives.json'))
    if a.expected_corpus:require(a.expected_corpus==initial,'corpus identity differs')
    save(out/'identity.json',report)
    if a.state=='prepare':
        report['preparation']=prime(a,out,root,meta,dirs,active)
        return
    pre=None
    if a.state=='indexed':
        pre=prime(a,out,root,meta,dirs,active)
        report['preparation']=pre
        require(physical(dirs[:4])==pre['physical_identity'],'primed source identity changed before restart')
    config=setup(a,cfg,out/'wire.jsonl' if a.wire else None)
    report['client']='pinned real Desktop Api' if a.desktop_bridge else 'python loopback HTTP'
    report['wire_observer']=a.wire
    if a.desktop_bridge:
        report['history_global_deadline_s']=30
        report['desktop_client_sha256']=digest(a.desktop_bridge.resolve().parent/'client')
    else:report['history_client_socket_timeout_s']=a.observe
    report.update(case_path=str(root),index_state=a.state,hot_trigger='first selected session descriptor IN_OPEN',sampler_interval_s=.010)
    text_probe='r19 foreground proof'
    phases={}; stage='starting';samples=[]; stop=threading.Event()
    opened=JournalOpens(dirs)
    heads=JournalOpens(dirs[:4],HEAD) if a.state=='indexed' else None
    tree_errors=[]
    proc=None; monitor=None; desktop=None
    try:
        with (out/'server.log').open('w') as slog,(out/'trace.jsonl').open('w',buffering=1) as trace:
            proc=subprocess.Popen([a.core,'--config',config,'--cwd',cwd,'--resume-session',active,'server','http','--host','127.0.0.1','--port','0','--ready-stdout'],cwd=cwd,stdout=subprocess.PIPE,stderr=slog,start_new_session=True)
            tree=Tree(proc.pid,root_group='backend')
            def scan():
                try:
                    while not stop.is_set():
                        st=stage;s=tree.sample()
                        if st!=stage:continue
                        procs=[dict(pid=i['pid'],start_ticks=i['start_ticks'],role=('core' if i['pid']==proc.pid else 'worker' if i['exe']==str(a.worker) else 'reference' if i['exe']==str(a.reference) else 'other'),pss=i['Pss']) for i in s['processes']]
                        v={k:s[k] for k in ('monotonic_ns','pss_kib','rss_kib','private_kib','swap_pss_kib','process_count','memory_incomplete_pids','scan_duration_seconds')}
                        v.update(stage=st,processes=procs)
                        try:trace.write(json.dumps(v,separators=(',',':'))+'\n')
                        except ValueError:
                            if trace.closed:return
                            raise
                        samples.append(v);stop.wait(.010)
                except Exception as e:tree_errors.append(err(e))
            monitor=threading.Thread(target=scan,daemon=True);monitor.start()
            with selectors.DefaultSelector() as sel:
                sel.register(proc.stdout,selectors.EVENT_READ);require(sel.select(60),'http ready timeout')
                ready=json.loads(proc.stdout.readline());require(ready['type']=='http_ready','http ready frame')
                origin=ready['origin'];require(origin.startswith('http://127.0.0.1:'),'not loopback')
            def http(route,body=None):
                req=Request(origin+route,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
                with urlopen(req,timeout=a.observe) as r:return json.load(r)
            def q(d,**kw):return '?'+urlencode(dict(session_dir=str(d),**kw))
            def page(d,**kw):return http('/history/page'+q(d,**kw))
            if a.desktop_bridge:
                sys.path.insert(0,str(a.desktop_bridge.resolve().parent))
                from desktop_api import DesktopApi
                desktop=DesktopApi(origin);page=desktop.page
            require(http('/bootstrap')['session_dir']==str(active),'not active A')
            check(page(active),9,50,100)
            stage='idle';time.sleep(.45)
            sse={};ready_sse=threading.Event();done_sse=threading.Event()
            def watch_sse():
                try:
                    with urlopen(origin+'/events'+q(active),timeout=a.observe) as r:
                        for line in r:
                            if not line.startswith(b'data: '): continue
                            t=ns();ev=json.loads(line[6:]).get('event',{});typ=ev.get('type')
                            if typ=='session_snapshot':
                                require(ev['snapshot']['session_id']==uid(9),'SSE wrong session');ready_sse.set()
                            if typ=='runtime' and ev['envelope']['session_id']==uid(9):
                                item=ev['envelope']['event']
                                if isinstance(item,dict) and item.get('TurnStarted',{}).get('session_id')==uid(9):
                                    sse.update(durable_open_upper_bound_ns=t,turn_open_id=item['TurnStarted']['turn_id'])
                                if isinstance(item,dict) and item.get('TaskReceived',{}).get('task',{}).get('text')==text_probe:
                                    sse.setdefault('durable_user_upper_bound_ns',t)
                                if isinstance(item,dict) and item.get('AssistantTextDelta',{}).get('text'):sse.setdefault('first_text_ns',t)
                            if typ=='turn_output':sse.update(terminal_ns=t,result=ev['output']);return
                            if typ=='error':sse.update(terminal_ns=t,error=ev);return
                except Exception as e:sse.update(error=err(e))
                finally:done_sse.set()
            watcher=threading.Thread(target=watch_sse,daemon=True);watcher.start()
            require(ready_sse.wait(20),'SSE active snapshot not ready')
            def request(i,mode,fence,revision=None):
                fence.wait();start=ns()
                try:
                    d=dirs[i];kwargs={} if mode!='pinned' else dict(before=50,revision=revision)
                    v=page(d,**kwargs);end=ns()
                    rev=check(v,100+i,0 if mode=='pinned' else rows-50,rows)
                    if pre:require(rev==pre['pages'][i]['revision'],'measured and stock-prepared immutable revisions differ')
                    if revision:require(rev==revision,'revision mismatch')
                    rows_digest=sha256(json.dumps(v['messages'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
                    return dict(index=i,start_ns=start,end_ns=end,ms=ms(start,end),ok=True,validated_rows=50,
                                revision=rev,http_status=200,page_base=v['base'],full_rows_sha256=rows_digest)
                except Exception as e:
                    end=ns();return dict(index=i,start_ns=start,end_ns=end,ms=ms(start,end),ok=False,error=err(e))
            hot={}; cold=[];warm={}
            stage='cold';report['cold_start_unix_ns']=time.time_ns();report['cold_start_loadavg']=os.getloadavg()
            witness=JournalOpens(dirs[:4],'session.json')
            try:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    gate=threading.Barrier(4);jobs=[pool.submit(request,i,'cold',gate) for i in range(4)]
                    try:
                        with selectors.DefaultSelector() as sel:
                            sel.register(witness.fd,selectors.EVENT_READ);require(sel.select(min(a.observe,40)),'no cold descriptor OPEN')
                        seen=witness.observed();hot['seen_cold_descriptors']=seen
                        start=ns();hot['start_ns']=start;hot['pending_cold_clients_at_send']=sum(not j.done() for j in jobs)
                        ans=http('/send',dict(id='r19-foreground',text=text_probe,session_dir=str(active)))
                        end=ns();hot.update(end_ns=end,ms=ms(start,end),reply=ans,received_success=bool(ans.get('ok') and ans.get('output',{}).get('text')))
                    except Exception as e:hot.update(end_ns=ns(),error=err(e),received_success=False)
                    finally:
                        save(out/'hot-reply.json',hot)
                    cold=[j.result() for j in jobs];report['cold_end_unix_ns']=time.time_ns();report['cold_end_loadavg']=os.getloadavg();save(out/'cold.json',cold)
            finally:witness.close()
            # Capture SSE before warm phases. A failed HTTP never earns a first-text or durable-success claim by default.
            done_sse.wait(2);hot['sse']=dict(sse)
            for key in ('durable_open_upper_bound','durable_user_upper_bound','first_text','terminal'):
                if f'{key}_ns' in sse and 'start_ns' in hot:hot[key+'_ms']=ms(hot['start_ns'],sse[key+'_ns'])
            hot['cold_outstanding_at']={key:sum(c['start_ns']<=t<c['end_ns'] for c in cold) for key,t in [('send_start',hot.get('start_ns')),('durable_open_upper_bound',sse.get('durable_open_upper_bound_ns')),('durable_user_upper_bound',sse.get('durable_user_upper_bound_ns')),('first_text',sse.get('first_text_ns')),('send_response',hot.get('end_ns'))] if t is not None}
            hot['overlap']=any(c['start_ns']<=hot.get('start_ns',-1)<c['end_ns'] for c in cold) and bool(hot.get('seen_cold_descriptors'))
            report.update(hot=hot,cold=cold)
            stage='retained';time.sleep(1)
            report['cold_journals_observed']=opened.observed();opened.close()
            if heads:report['disk_heads_opened']=heads.observed();heads.close()
            # Keep cold failures failed; only attempt warm tests on previously successful cold heads.
            ok=[(c['index'],c['revision']) for c in cold if c['ok']]
            for mode in ('pinned','latest'):
                stage='warm_'+mode
                with ThreadPoolExecutor(max_workers=4) as pool:
                    gate=threading.Barrier(len(ok) or 1)
                    jobs=[pool.submit(request,i,mode,gate,revision=r) for i,r in ok]
                    warm[mode]=[j.result() for j in jobs]
                save(out/('warm-'+mode+'.json'),warm[mode])
            report['warm']=warm;stage='proof';inactive=[]
            for i,d in enumerate(dirs):
                try:http('/addons'+q(d))
                except HTTPError as e:
                    if e.code==400 and 'not active' in e.read().decode():inactive.append(i)
            report.update(nonactive_count=len(inactive),unselected_cache_free=all(not cache(d) for d in dirs[4:]))
            try:
                a_page=page(active)
                hot['page_total']=a_page['total'];hot['tail']=[{k:m[k] for k in ('message_id','role','text')} for m in a_page['messages'][-2:]]
            except Exception as e:hot['page_error']=err(e)
            try:http('/shutdown',{})
            except Exception as e:report['shutdown_error']=err(e)
    finally:
        if desktop:
            desktop.close();report['desktop_api_requests']=desktop.observed
        opened.close();stop.set()
        if heads:heads.close()
        if monitor:monitor.join(10)
        if proc:
            try:os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
            proc.stdout.close()
        for st in sorted({s['stage'] for s in samples}):
            ss=[s for s in samples if s['stage']==st]
            peak=max(ss,key=lambda s:s['pss_kib'])
            phases[st]=dict(samples=len(ss),peak_pss_kib=peak['pss_kib'],median_pss_kib=sorted(s['pss_kib'] for s in ss)[len(ss)//2],peak_processes=peak['processes'],incomplete_samples=sum(bool(s['memory_incomplete_pids']) for s in ss))
        report.update(phases=phases,sampler_errors=tree_errors,complete_cold_pss=any(s['stage']=='cold' and {p['role'] for p in s['processes']}>={'worker','core','reference'} for s in samples) and not tree_errors and not any(s['memory_incomplete_pids'] for s in samples if s['stage']=='cold'))
        # Postprocess even if fewer than four journals opened, hot timed out or a proof failed.
        report['canonical_sha_after']=corpus(dirs)
        try:
            entries=list(records(active)); reqs=[(r,p['request']['messages']) for r,p in entries if r['kind']=='model_request_recorded']
            opened_turns=[r['turn_id'] for r,p in entries if r['kind']=='turn_opened' and p.get('task',{}).get('text')==text_probe]
            settled=[(r['turn_id'],p.get('status')) for r,p in entries if r['kind']=='turn_settled']
            changes=[m for r,p in entries if r['kind']=='history_mutated' and p['mutation']=='append' for m in p['messages'] if text(m)==text_probe]
            prompt_match=(len(reqs)==1 and message_digest([m for m in reqs[0][1] if text(m).startswith('synthetic-')])==message_digest(seed_msgs) and len([m for m in reqs[0][1] if text(m)==text_probe])==1)
            ids_ok=bool(reqs and len(changes)==1 and [m['id'] for m in reqs[0][1] if text(m)==text_probe]==[changes[0]['id']])
            hot=report.get('hot',{})
            tail=hot.get('tail',[])
            page_ok=bool(len(tail)==2 and len(changes)==1 and hot.get('page_total')==102 and tail[0]['message_id']==changes[0]['id'] and tail[0]['role']=='user' and tail[0]['text']==text_probe and tail[1]['role']=='assistant' and tail[1]['text']==((hot.get('reply') or {}).get('output') or {}).get('text'))
            proof=dict(prefix_unchanged=(active/'journal.jsonl').read_bytes().startswith(hot_before),model_count=len(reqs),settled=settled,user_append_count=len(changes),exact_prompt=prompt_match,ids_match=ids_ok,projected_user_and_reply=page_ok)
            replymeta=((hot.get('reply') or {}).get('output') or {}).get('metadata') or {}
            proof['reply_turn_matches']=bool(len(settled)==1 and replymeta.get('turn_id')==settled[0][0] and replymeta.get('session_id')==uid(9))
            proof['opened_task_same_sse_turn']=bool(len(opened_turns)==1 and opened_turns[0]==hot.get('sse',{}).get('turn_open_id'))
            proof['durable_success']=bool(proof['opened_task_same_sse_turn'] and proof['reply_turn_matches'] and proof['prefix_unchanged'] and prompt_match and ids_ok and page_ok and len(settled)==1 and reqs[0][0]['turn_id']==settled[0][0] and settled[0][1]=='success' and all(r['session_id']==uid(9) for r,p in entries))
            report['hot_canonical']=proof
        except Exception as e: report['hot_canonical']={'error':err(e),'durable_success':False}
        save(out/'summary.json',report)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('source','core','worker','reference','golden','out'):ap.add_argument('--'+k,type=Path,required=True)
    for k in ('core-commit','core-sha256','worker-sha256'):ap.add_argument('--'+k,required=True)
    ap.add_argument('--expected-corpus',required=True)
    ap.add_argument('--state',choices=('prepare','absent','indexed'),required=True)
    ap.add_argument('--case-path',type=Path,required=True)
    ap.add_argument('--prime-core',type=Path,required=True)
    ap.add_argument('--prime-sha',required=True)
    ap.add_argument('--desktop-bridge',type=Path)
    ap.add_argument('--wire',action='store_true')
    ap.add_argument('--observe',type=float,default=240,help='client timeout only; backend policy unchanged')
    a=ap.parse_args()
    for n in ('source','golden','core','worker','reference','prime_core'):setattr(a,n,getattr(a,n).resolve(strict=True))
    require(len(a.core_commit)==40 and subprocess.check_output([a.core,'--version'],text=True).strip().endswith('('+a.core_commit[:12]+')'),'core embedded SHA mismatch')
    require(a.prime_sha==digest(a.prime_core),'preparer binary hash mismatch')
    require(a.core_sha256==digest(a.core) and a.worker_sha256==digest(a.worker),'binary hash mismatch')
    a.out.mkdir(parents=True,exist_ok=False);report={'passed':False,'core_commit':a.core_commit,'python_socket_timeout_s':a.observe}
    try:
        with case(a.case_path.resolve()) as tmp:run(a,a.out,tmp,report)
    except Exception as exc:report['harness_error']=err(exc)
    if a.state=='prepare':
        report['passed']=bool(report.get('preparation') and not report.get('harness_error'))
        save(a.out/'summary.json',report)
        print(json.dumps(dict(passed=report['passed'],harness_error=report.get('harness_error'),out=str(a.out))),flush=True)
        return 0 if report['passed'] else 2
    hot=report.get('hot',{}); cold=report.get('cold',[]); warm=report.get('warm',{})
    exact_history=all((c['revision'], c['full_rows_sha256']) ==
                      (cold[c['index']]['revision'], cold[c['index']]['full_rows_sha256'])
                      for c in warm.get('latest',[]) if c['ok'])
    report['passed']=bool(exact_history and not report.get('harness_error') and report.get('hot_canonical',{}).get('durable_success') and hot.get('received_success') and hot.get('overlap') and hot.get('pending_cold_clients_at_send') and hot.get('sse',{}).get('first_text_ns') and hot.get('sse',{}).get('result')==(hot.get('reply') or {}).get('output') and len(cold)==4 and all(c['ok'] for c in cold) and set(warm)=={'latest','pinned'} and all(len(w)==4 and all(c['ok'] for c in w) for w in warm.values()) and report.get('canonical_sha_before')==report.get('canonical_sha_after') and (report.get('cold_journals_observed')==[0,1,2,3] if a.state!='indexed' else report.get('disk_heads_opened')==[0,1,2,3] and set(report.get('cold_journals_observed',[]))<=set(range(4))) and report.get('nonactive_count')==report.get('archives') and report.get('unselected_cache_free') and report.get('complete_cold_pss'))
    save(a.out/'summary.json',report)
    print(json.dumps(dict(passed=report['passed'],harness_error=report.get('harness_error'),out=str(a.out)),ensure_ascii=False),flush=True)
    return 0 if report['passed'] else 2

if __name__=='__main__':sys.exit(main())
