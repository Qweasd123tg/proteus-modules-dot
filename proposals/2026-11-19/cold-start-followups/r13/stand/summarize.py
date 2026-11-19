import re, csv, json, sys
from pathlib import Path
out=[]
for p in sorted(Path(sys.argv[1]).iterdir()):
 if not p.is_dir(): continue
 log=(p/'core.log').read_text()
 assert 'test result: ok. 1 passed;' in log,p
 m=re.search(r'CASE display=(\d+) active=100 journal_bytes=(\d+) fresh_storage=true prepared_ms=([\d.]+) launch_ms=([\d.]+)',log); assert m,p
 with_files=[]
 for f in p.glob('wire-*.csv'):
  with f.open() as ff: with_files.extend(csv.DictReader(ff))
 pre=sorted(with_files,key=lambda x:int(x['req_done_ns']))
 start=next(i for i,x in enumerate(pre) if x['op']=='open_display_snapshot')
 settle=next((i for i,x in enumerate(pre[start:],start) if x['op']=='commit'),len(pre))
 front=pre[start:settle]
 pub=[x for x in front if x['op']=='write_cache']
 if 'R13_BOUND' in log: assert not pub and 'tail=50 cache_publish=omitted' in log
 prefix=[x for x in pub if x['cache_key_class']=='display-view-v1-prefix']
 assert len(prefix)==(0 if 'R13_BOUND' in log else 1),p
 pr=[x for x in pre[settle:] if x['cache_key_class']=='display-view-v1-prefix' and x['op'] in ('write_cache','read_cache')]
 settle_ms=re.search(r'SETTLE_END wall_ms=([\d.]+)',log)
 turn_ms=re.search(r'TURN display=\d+.*total_ms=([\d.]+)',log)
 out.append(dict(sample=p.name,rows=int(m[1]),ready_bound='R13_BOUND' in log,
  journal_bytes=int(m[2]),prepare_ms=float(m[3]),launch_ms=float(m[4]),open_ms=round(float(m[3])+float(m[4]),3),
  cache_writes=len(pub),prefix_publish_bytes=int(prefix[0]['request_bytes']) if prefix else 0,
  turn_prefix_read_plus_write_bytes=sum(int(x['request_bytes']) if x['op']=='write_cache' else int(x['response_bytes']) for x in pr),
  post_turn_settlement_ms=float(settle_ms[1]) if settle_ms else None,turn_ms=float(turn_ms[1]) if turn_ms else None))
for o in out:print(json.dumps(o))
