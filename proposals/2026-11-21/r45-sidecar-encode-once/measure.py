#!/usr/bin/env python3
"""Synthetic paired measurements; no installed worker, real data or system configuration."""
import argparse,hashlib,json,os,signal,sqlite3,tempfile,time
from contextlib import ExitStack
from pathlib import Path
from rpc import Client,setup,append
p=argparse.ArgumentParser()
for x in ('stock','candidate'):p.add_argument(x,type=Path)
p.add_argument('--plain',action='store_true',help='repeat sidecar and row parity with production binaries that have no counters')
p.add_argument('--pairs',type=int,default=7);p.add_argument('--blobs',type=int,action='append');p.add_argument('--backend',action='append',choices=('jsonl','sqlite'))
p.add_argument('--tmp',type=Path,default=Path('/tmp'));a=p.parse_args()
assert 0<a.pairs<=15
bins={x:getattr(a,x).resolve() for x in ('stock','candidate')}
cardname='.storage-catalog-v1.json'
def serialize(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def oracle(b):
    e=json.loads(b);assert list(e)==['checksum','data']
    payload=serialize(e['data']); digest=hashlib.sha256(payload).hexdigest()
    assert digest==e['checksum'] and b==b'{"checksum":"'+digest.encode()+b'","data":'+payload+b'}'
    return e['data']
def blobfixture(paths,n):
    for d in paths:
        if n:
            b=d/'blobs';b.mkdir(exist_ok=True)
            for j in range(n):(b/f'inventory-{j:04}.probe').touch(exist_ok=False)
def timed(f):
    t=time.perf_counter_ns(); v=f()
    return v,time.perf_counter_ns()-t
def row(backend,case,blobs,trial,variant,ns,logs,raw):
    if a.plain:
        assert not logs;print(f'{backend} {case} blobs={blobs} {variant}: verified {len(raw)} generated sidecars',flush=True);return
    assert len(logs)==len(raw)>0,(case,logs)
    assert all(v[0]==(2 if variant=='stock' else 1) for v in logs),logs
    assert sorted(v[1] for v in logs)==sorted(map(len,raw))
    print(json.dumps(dict(backend=backend,case=case,blobs_per_session=blobs,trial=trial,variant=variant,saves=len(logs),
        index_serializations=sum(v[0] for v in logs),bytes=sum(map(len,raw)),encode_ns=sum(v[2] for v in logs),rpc_ns=ns,**({'encode_cpu_ns':sum(v[3] for v in logs)} if len(logs[0])==4 else {})),separators=(',',':')),flush=True)
def order(t):return ('stock','candidate') if t%2==0 else ('candidate','stock')
def freshroot(td):
    cfg=td/'config';ws=td/'workspace';cfg.mkdir();ws.mkdir()
    return cfg,ws
def list_params(cfg,ws):return dict(config_root=str(cfg),workspace_path=str(ws),audit=False)
def cold(backend,blobs,td):
    cfg,ws=freshroot(td); n=10; lp=list_params(cfg,ws)
    with Client(bins['stock'],backend) as seed:paths=[setup(seed,cfg,ws,i) for i in range(n)]
    blobfixture(paths,blobs)
    cards=[x/cardname for x in paths]
    # Retain only read connections across each matched pair. SQLite may otherwise
    # create/delete an empty WAL with a fresh mtime on repeated opens.
    with ExitStack() as stack:
        if backend=='sqlite':
            for d in paths:
                con=sqlite3.connect((d/'journal.sqlite').as_uri()+'?mode=ro',uri=True)
                stack.callback(con.close);con.execute('select count(*) from journal').fetchall()
        for t in range(a.pairs):
            first=None
            for name in order(t):
                for s in cards:s.unlink(missing_ok=True)
                with Client(bins[name],backend) as c:
                    res,ns=timed(lambda:c.call('list',**lp))
                raw=[s.read_bytes() for s in cards]
                assert all(oracle(b)['summary']['message_count']==8 for b in raw)
                rows=res['sessions'];assert len(rows)==10 and all(x['preview']=='q'*160+'...' for x in rows)
                if first is None:first=(res,raw)
                else:assert (res,raw)==first,('cold same-root parity',backend,name)
                row(backend,'cold_list',blobs,t,name,ns,c.reports,raw)
        # Non-UTF8 inventory entry: old generation remains intact, no partial file;
        # authority and nonfatal cache write failure are identical on this host.
        bad=os.fsencode(paths[0]/'blobs')+b'/invalid-\xff'
        (paths[0]/'blobs').mkdir(exist_ok=True);open(bad,'xb').close()
        before=cards[0].read_bytes(); prior=None
        try:
            for name in ('stock','candidate'):
                with Client(bins[name],backend) as c:result=c.call('list',**lp)
                assert c.reports==[] and before==cards[0].read_bytes()
                assert list(paths[0].glob('.storage-catalog-*.tmp'))==[]
                assert len(result['sessions'])==n and (prior is None or result==prior); prior=result
        finally:os.unlink(bad)
def normal(backend,blobs,td,t,name):
    cfg,ws=freshroot(td);lp=list_params(cfg,ws)
    with Client(bins['stock'],backend) as seed:d=setup(seed,cfg,ws,0)
    blobfixture([d],blobs)
    card=d/cardname;card.unlink(missing_ok=True)
    other='stock' if name=='candidate' else 'candidate'
    with Client(bins[name],backend) as w:
        s=w.call('open',path=str(d))['descriptor']['session']; wr=w.call('acquire_writer',session=s)
        rev=append(w,wr['lease'],wr['revision'],0,8,'q'*512); assert not card.exists()
        ans,ns=timed(lambda:w.call('open_snapshot',session=s))
        snap=ans['snapshot']; assert snap['revision']==rev
        raw=card.read_bytes(); ix=oracle(raw);assert ix['revision']==rev and ix['summary']['message_count']==9
        card.unlink()
        # Independent opposite worker rebuilds the *same generation* from the
        # journal while the primary writer and its WAL are still held steady.
        with Client(bins[other],backend) as r:
            res=r.call('list',**lp)
        assert res['sessions']==[ix['summary']] and card.read_bytes()==raw,('writer save vs independent replay',backend,name)
        assert len(r.reports)==(0 if a.plain else 1)
        w.call('release_snapshot',snapshot=snap)
        w.call('release_writer',lease=wr['lease'])
    assert len(w.reports)==(0 if a.plain else 2 if backend=='sqlite' else 1),w.reports
    row(backend,'writer_open_snapshot',blobs,t,name,ns,w.reports[:1],[raw])
    # For SQLite an additional successful save at release rebinds source stamps;
    # the opposite worker must reuse the final generation without republishing.
    final=card.read_bytes();before=card.stat();assert oracle(final)['revision']==rev
    with Client(bins[other],backend) as verify:res=verify.call('list',**lp)
    assert verify.reports==[] and res['sessions'][0]['message_count']==9 and card.read_bytes()==final
    assert (before.st_ino,before.st_ctime_ns)==(card.stat().st_ino,card.stat().st_ctime_ns)
for backend in a.backend or ('jsonl','sqlite'):
    for blobs in a.blobs or (0,492):
        assert 0<=blobs<=492
        with tempfile.TemporaryDirectory(dir=a.tmp) as d:cold(backend,blobs,Path(d))
        for t in range(a.pairs):
            for name in order(t):
                with tempfile.TemporaryDirectory(dir=a.tmp) as d:normal(backend,blobs,Path(d),t,name)
