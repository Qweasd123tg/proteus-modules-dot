import csv,hashlib,json,sys,time,os,argparse
from pathlib import Path
from rpc import Worker
p=argparse.ArgumentParser(); p.add_argument('info',type=Path);p.add_argument('stock',type=Path);p.add_argument('candidate',type=Path);p.add_argument('--pairs',type=int,default=4);p.add_argument('--cpu',type=int,default=6)
a=p.parse_args(); info=json.loads(a.info.read_text()); ses=info['session']; journal=Path(info['file'])
def digest(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def unchanged(): assert hashlib.sha256(journal.read_bytes()).hexdigest()==info['sha256']
unchanged(); oracle=None; page_oracle=None
rec=csv.writer(sys.stdout);rec.writerow(('pair','arm','open_us','worker_cpu_ms','rss_open_kib','records','active','bytes','state_sha256','pages_sha256'))
for i in range(a.pairs):
    for k,exe in ([('stock',a.stock),('candidate',a.candidate)][::1 if i%2==0 else -1]):
        w=Worker(exe.resolve(),'jsonl');os.sched_setaffinity(w.process.pid,{a.cpu})
        try:
            def process_ticks():
                f=Path(f'/proc/{w.process.pid}/stat').read_text().split(') ')[1].split()
                return int(f[11])+int(f[12])
            b=process_ticks()
            start=time.monotonic_ns(); res=w.do('open_display_snapshot',session=ses)['projection']; duration=(time.monotonic_ns()-start)//1000
            cpu_ms=(process_ticks()-b)*1000/os.sysconf('SC_CLK_TCK')
            rss=[x.split()[1] for x in Path(f'/proc/{w.process.pid}/status').read_text().splitlines() if x.startswith('VmHWM:')][0]
            state=res['state'];snap=res['snapshot'];active=state['conversation']['messages']
            assert len(active)==100 and snap['revision']=={'session_seq':1251,'history_revision':1251}
            assert snap['content_sha256']==info['sha256']
            d=digest(state);oracle=oracle or d;assert d==oracle
            # Compare the two complete, ordered typed display streams after timing.
            # On later runs candidate/stock check the exact source and resume state.
            pd=''
            if i==0:
                h=hashlib.sha256();n=0;s=0
                while True:
                    res=w.do('read_display_records',snapshot=snap,after_seq=s,limit=64)['page']
                    for r in res['records']:
                        assert r['session_seq']==n+1
                        n+=1;h.update(digest(r).encode())
                    if res['next_after_seq'] is None:break
                    s=res['next_after_seq']
                assert n==1251;pd=h.hexdigest();page_oracle=page_oracle or pd;assert pd==page_oracle
            rec.writerow([i,k,duration,cpu_ms,rss,snap['revision']['session_seq'],len(active),info['bytes'],d,pd]);sys.stdout.flush()
        finally:w.close()
unchanged()
