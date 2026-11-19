"""Control: the previous boundary is only one record of a large fixed snapshot."""
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from rpc import Fixture, Worker, msg
import argparse, csv, os, tempfile
p=argparse.ArgumentParser()
p.add_argument('baseline');p.add_argument('candidate');p.add_argument('out');p.add_argument('--cpu',type=int);p.add_argument('--pairs',type=int,default=6);a=p.parse_args()
with open(a.out,'w') as out:
    wcsv=csv.writer(out)
    wcsv.writerow(('trial','arm','old_bytes','total_bytes','first_ns','retry1_ns','retry2_ns'))
    for trial in range(a.pairs):
        with tempfile.TemporaryDirectory() as tmp:
            f=Fixture(Path(a.baseline).resolve(),'jsonl',Path(tmp)); peers={}
            try:
                f.write([msg(1,'only prior')]); old_bytes=(f.dir/'journal.jsonl').stat().st_size
                for arm,path in [('baseline',a.baseline),('candidate',a.candidate)]:
                    w=peers[arm]=Worker(Path(path).resolve(),'jsonl')
                    if a.cpu is not None:os.sched_setaffinity(w.process.pid,{a.cpu})
                    old=w.do('open_snapshot',session=f.session)['snapshot'];w.do('release_snapshot',snapshot=old)
                for i in range(2,2050): f.write([msg(i,f'{i}:'+'x'*704)],mutation='replace')
                tot=(f.dir/'journal.jsonl').stat().st_size
                heads={arm:w.do('open_snapshot',session=f.session)['snapshot'] for arm,w in peers.items()}
                samples={arm:[] for arm in peers}
                for i in range(3):
                    for arm in list(peers)[::1 if (i+trial)%2==0 else -1]:
                        t=perf_counter_ns();p=peers[arm].do('read_records',snapshot=heads[arm],after_seq=1,limit=1)['page']
                        samples[arm].append(perf_counter_ns()-t)
                        assert len(p['records'])==1 and p['records'][0]['session_seq']==2 and p['next_after_seq']==2
                for arm in peers:wcsv.writerow((trial,arm,old_bytes,tot,*samples[arm]))
                out.flush()
            finally:
                for w in peers.values():w.close()
                f.w.close()
