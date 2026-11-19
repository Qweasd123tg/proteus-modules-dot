from pathlib import Path
import re,statistics,json
p=Path(__file__).resolve().parent
data={}
for f in sorted(p.glob('e2e*.log')):
 t=f.read_text(); assert 'test result: ok.' in t
 for n in sorted(set(map(int,re.findall(r'MANIFEST n=(\d+)',t)))):
  def read(pattern):return re.search(pattern,t,re.M).groups()
  header,tp,cp,xp=map(int,read(rf'MANIFEST n={n} .*?\[\((\d+), (\d+), (\d+), (\d+)\)'))
  total_body=int(read(rf'^SWEEP n={n} ns=\d+ bytes=(\d+)')[0])
  sweep=int(read(rf'^C_SWEEP n={n} ns=(\d+)')[0])
  p50rows=[int(x[1]) for x in re.findall(rf'^CLIENT n={n} rep=[1-9]\d* pos=(tail|middle|oldest) ns=(\d+)',t,re.M)]
  data.setdefault(n,[]).append(dict(series=f.name,header_json_bytes=header,transcript_pages=tp,conversation_pages=cp,context_pages=xp,repeated_header_value_bytes=header*tp,http_body_bytes=total_body,desktop_api_sweep_ns=sweep,desktop_api_page_median_ns=statistics.median(p50rows),sample_count=len(p50rows)))
print(json.dumps(data,indent=2))
