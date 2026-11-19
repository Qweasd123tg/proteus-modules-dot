"""Attribute stock cold-index construction from the real storage call stream. Does not include startup fixture assertions."""
import csv, re, sys,json
from pathlib import Path
for a in sorted(map(Path,sys.argv[1:])):
    rows=sorted([r for f in a.glob('wire-*.csv') for r in csv.DictReader(f.open())],key=lambda r:int(r['req_done_ns']))
    if not rows: continue
    start=next(i for i,r in enumerate(rows) if r['op']=='open_display_snapshot')
    end=next(i for i in range(start+1,len(rows)) if rows[i]['op']=='read_metadata')
    collect=lambda op:[r for r in rows[start:end] if r['op']==op]
    ms=lambda r:(int(r['worker_response_done_ns'])-int(r['req_done_ns']))/1e6
    span=lambda a,b:(int(b['worker_response_done_ns'])-int(a['req_done_ns']))/1e6
    wr=collect('write_cache'); rd=collect('read_cache'); pg=collect('read_display_records')
    assert 3<=len(wr) and pg
    meta=[r for r in json.loads((a/'markers.json').read_text()) if r[1].startswith('CASE ')][0][1]
    st=re.search(r'display=(\d+).*prepared_ms=([\d.]+) launch_ms=([\d.]+)',meta)
    result={'sample':a.name,'messages':int(st[1]),'prepare_ms':float(st[2]),'launch_ms':float(st[3]),
        'open_display_ms':round(ms(rows[start]),2),'display_pages':len(pg),'display_wire_bytes':sum(int(r['response_bytes']) for r in pg),'display_service_ms':round(sum(map(ms,pg)),2),'display_page_span_ms':round(span(pg[0],pg[-1]),2),
        'cache_writes':len(wr),'cache_write_rpc_ms':round(sum(map(ms,wr)),2),'cache_read_rpc_ms':round(sum(map(ms,rd)),2),'first_to_last_write_span_ms':round(span(wr[0],wr[-1]),2),'write_first_100_ms':round(sum(map(ms,wr[:100]))/min(len(wr),100),3),'write_last_100_ms':round(sum(map(ms,wr[-104:-4]))/min(len(wr)-4,100),3)}
    print(json.dumps(result))
