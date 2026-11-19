"""Parse exact bounded settlement diagnostics and libtest status; never silently discard failures."""
from pathlib import Path
import json,re
out=Path(__file__).resolve().parent
data=[]
for name in ('A1','B1','B2','A2'):
  log=(out/f'{name}.log').read_text()
  code=int((out/f'{name}.exit').read_text())
  ok=code==0 and 'test result: ok. 1 passed; 0 failed' in log
  row={'run':name,'worker':'stock' if name.startswith('A') else 'candidate','passed':ok,'exit_code':code}
  data.append(row)
  if not ok: continue
  pre,measured=log.split('SETTLE_BEGIN\n')
  scoped,post=measured.split('SETTLE_END wall_ms=')
  m=re.match(r'([\d.]+) ok=true\n',post)
  assert m
  settle=float(m[1])
  n=re.search(r'TURN display=(\d+) active=(\d+) request_messages=\[(.*?)\] total_ms=([\d.]+) projected=(\d+) journal_bytes_after=(\d+)',post)
  assert n and n[3]=='101' and n[1]=='50000' and n[2]=='100' and n[5]=='50002'
  scans=[dict(after_seq=int(a),returned_records=int(b),page_calls=int(c)) for a,b,c in re.findall(r'SCAN from=(\d+) rows=(\d+) pages=(\d+)',scoped)]
  assert len(scans)==6
  total=float(n[4])
  row.update(full_send_ms=total,history_settlement_ms=settle,other_turn_including_fake_model_ms=round(total-settle,3),settlement_percent=round(100*settle/total,3),active_messages=int(n[2]),model_requests=1,model_request_messages=[101],display_after=int(n[5]),journal_bytes_before=int(re.search(r'CASE display=50000 active=100 journal_bytes=(\d+)',pre)[1]),journal_bytes_after=int(n[6]),settlement_readrecord_calls=sum(x['page_calls'] for x in scans),settlement_records_returned=sum(x['returned_records'] for x in scans),settlement_scans=scans)
pairs=[]
for a,b in [(0,1),(3,2)]:
  if not (data[a]['passed'] and data[b]['passed']): continue
  va=data[a]['history_settlement_ms']
  vb=data[b]['history_settlement_ms']
  pairs.append(dict(stock=data[a]['run'],candidate=data[b]['run'],candidate_minus_stock_ms=round(vb-va,3),candidate_change_pct=round((vb/va-1)*100,3)))
summary=dict(case_count=len(data),passed=sum(r['passed'] for r in data),failed=sum(not r['passed'] for r in data),order='A1 B1 B2 A2',runs=data,paired_changes=pairs)
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(pairs))
