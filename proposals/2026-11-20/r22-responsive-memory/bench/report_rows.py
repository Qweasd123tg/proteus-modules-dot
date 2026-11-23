#!/usr/bin/env python3
"""Compact printable ranking data from complete R22 summaries, using one PSS sample per peak."""
from pathlib import Path
import argparse,json
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('runs',type=Path,nargs='+')
rows=[]
for run in p.parse_args().runs:
    summary=json.loads((run/'summary.json').read_text())
    start=summary['hot']['start_ns']; phase=summary['phases']['cold']
    uu=[p['pss'] for p in phase['peak_processes'] if p['role']=='worker']
    cc=[p['pss'] for p in phase['peak_processes'] if p['role']=='core']
    # Include timeout/other failure duration in the worst history request; retain success separately.
    ms=max(p['ms'] for p in summary['cold'])
    first_hash=[p.get('full_rows_sha256') for p in summary['warm']['pinned']]
    last_hash=[p.get('full_rows_sha256') for p in summary['cold']]
    rows.append(dict(name=run.name,passed=summary['passed'], client=summary['desktop_client_sha256'],
        core=summary['core_sha256'],worker=summary['worker_sha256'],wire=summary['wire_observer'],
        render_fixture=summary['canonical_sha_before'],first_hash=first_hash,last_hash=last_hash,
        idle_pss_mib=round(summary['phases']['idle']['median_pss_kib']/1024,2),
        cold_pss_mib=round(phase['peak_pss_kib']/1024,2), core_at_tree_peak_mib=round(sum(cc)/1024,2),
        worker_at_tree_peak_mib=round(sum(uu)/1024,2), page_max_ms=ms,
        first_text_ms=summary['hot']['first_text_ms'], sse_open_upper_ms=summary['hot']['durable_open_upper_bound_ms'],
        pending_on_first_text=summary['hot']['cold_outstanding_at']['first_text']))
print(json.dumps(rows,indent=2))
