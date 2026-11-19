"""ReadRecords across real SDK pipes, same bytes pinned by both worker processes.
Scopes: cold open and first Compare, first suffix page(s), discontinuous retries.
"""
import argparse, csv, os, tempfile, time
from pathlib import Path
from rpc import Fixture, Worker, msg

p=argparse.ArgumentParser()
p.add_argument('baseline'); p.add_argument('candidate'); p.add_argument('out')
p.add_argument('--counts',default='0,128,512,2048');p.add_argument('--pairs',type=int,default=9)
p.add_argument('--flip',action='store_true');p.add_argument('--cpu',type=int);args=p.parse_args()
def clock(w): return time.clock_gettime_ns((~w.process.pid << 3) | 2)
def measure(w, op, **kwargs):
    c=clock(w);t=time.perf_counter_ns(); val=w.do(op,**kwargs)
    return val, time.perf_counter_ns()-t, clock(w)-c

with open(args.out,'w') as file:
    csvout=csv.writer(file);csvout.writerow('cut,inline_bytes,pair,order,arm,phase,wall_ns,worker_cpu_ns'.split(','))
    for ix,num in enumerate(map(int,args.counts.split(','))):
        with tempfile.TemporaryDirectory() as tmp:
            f=Fixture(args.baseline,'jsonl',Path(tmp))
            peers={}
            try:
                for i in range(num): f.write([msg(i,f'{i}:'+'x'*704)],mutation='replace')
                old={}
                for arm,binary in [('baseline',args.baseline),('candidate',args.candidate)]:
                    peers[arm]=w=Worker(Path(binary).resolve(),'jsonl')
                    if args.cpu is not None: os.sched_setaffinity(w.process.pid,{args.cpu})
                    old[arm]=w.do('open_snapshot',session=f.session)['snapshot']
                    w.do('release_snapshot',snapshot=old[arm])
                suffix=[msg(num+i,'tail-'+str(i)) for i in range(3)]
                for m in suffix:f.write([m])
                nbytes=(f.dir/'journal.jsonl').stat().st_size
                heads={}
                for arm in list(peers)[::1 if (ix+int(args.flip))%2==0 else -1]:
                    w=peers[arm]
                    val,t,c=measure(w,'open_snapshot',session=f.session)
                    heads[arm]=val['snapshot'];csvout.writerow([num,nbytes,0,'once',arm,'open',t,c])
                    val,t,c=measure(w,'compare_snapshots',snapshot=heads[arm],prefix=old[arm])
                    assert val['matches'];csvout.writerow([num,nbytes,0,'once',arm,'compare',t,c])
                for r in range(args.pairs+1):
                    arms=list(peers)[::1 if (r+ix+int(args.flip))%2==0 else -1]
                    order='AB' if arms[0]=='baseline' else 'BA'
                    for arm in arms:
                        w=peers[arm]
                        for start,limit,expected,next_seq,phase in [(num,1,suffix[:1],num+1,'page1'),(num+1,32,suffix[1:],None,'page2')]:
                            val,t,c=measure(w,'read_records',snapshot=heads[arm],after_seq=start,limit=limit)
                            page=val['page']
                            assert page['snapshot']==heads[arm] and page['next_after_seq']==next_seq
                            assert [rec['session_seq'] for rec in page['records']]==list(range(start+1,start+1+len(expected)))
                            assert [rec['entry']['payload']['messages'] for rec in page['records']]==[[m] for m in expected]
                            csvout.writerow([num,nbytes,r,order,arm,phase,t,c])
                file.flush()
                print('checked cut',num,'bytes',nbytes,flush=True)
            finally:
                for w in peers.values(): w.close()
                f.w.close()
