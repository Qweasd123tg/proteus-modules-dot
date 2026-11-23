import json, sys
from pathlib import Path
for dirname in sys.argv[1:]:
    d=Path(dirname)
    report=json.loads((d/'summary.json').read_text())
    trace=[json.loads(s) for s in (d/'trace.jsonl').read_text().splitlines()]
    cold=[row for row in trace if row['stage']=='cold']
    def stats(rows,key):
        return dict(max_count=max(len(r[key]) for r in rows),
                    max_size_mib=round(max(sum(r[key]) for r in rows)/1048576,2))
    def peak(rows):
        x=max(rows,key=lambda r:sum(r['core_stage_bytes']+r['worker_stage_bytes']))
        return dict(core_count=len(x['core_stage_bytes']),worker_count=len(x['worker_stage_bytes']),
                    combined_mib=round(sum(x['core_stage_bytes']+x['worker_stage_bytes'])/1048576,2),
                    pss_mib=round(x['pss_kib']/1024,2))
    assert report['passed'] and report['canonical_sha_before']==report['canonical_sha_after']
    assert len(cold)>0 and all(x['ok'] for x in report['cold'])
    assert bool(max(len(r['core_stage_bytes']) for r in cold))==(report['core_stage']=='on')
    assert max(len(r['worker_stage_bytes']) for r in cold)>0
    print(json.dumps(dict(run=d.name, passed=True, stage=report['core_stage'],
        temp_mount=report['candidate_mount'],core_sha256=report['core_sha256'],
        worker_sha256=report['worker_sha256'],stand_sha256=report['stand_sha256'],
        fixture=report['canonical_sha_before'],
        cold_core_stage=stats(cold,'core_stage_bytes'),cold_worker_stage=stats(cold,'worker_stage_bytes'),
        cold_combined_at_max=peak(cold),
        cold_peak_pss_mib=round(report['phases']['cold']['peak_pss_kib']/1024,2),
        first_text_ms=report['hot']['first_text_ms'],
        cold_ms=[r['ms'] for r in report['cold']],
        latest=[r['revision'] for r in report['warm']['latest']],
        pinned=[r['revision'] for r in report['warm']['pinned']])))
