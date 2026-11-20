"""Gate comparable named arms; no leak of warm A mutations or path-bound indices between runs."""
import json,sys
from pathlib import Path
arms=[json.loads((Path(arg)/'summary.json').read_text()) for arg in sys.argv[1:]]
assert len(arms)>=2
for k in ('canonical_sha_before','canonical_sha_after','fixture_manifest_sha256','profile_sha256','sampler_sha256','worker_sha256','reference_sha256','desktop_client_sha256','case_path','history_global_deadline_s','stand_sha256','companion_file_hashes'):
    assert all(x[k]==arms[0][k] for x in arms), k
assert len(set(x['core_sha256'] for x in arms))==2
assert arms[0]['history_global_deadline_s']==30
assert all(x['rows']==125000 and x['archives']==100 and x['nonactive_count']==100 and x['unselected_cache_free'] and x['hot_canonical']['durable_success'] for x in arms)
rev0=[c['revision'] for c in arms[0]['cold'] if c['ok']]
for x in arms:
    if len([c for c in x['cold'] if c['ok']])==4:assert [c['revision'] for c in x['cold']]==rev0
    if x['index_state']=='indexed':
        p=x['preparation'];assert [r['revision'] for r in p['pages']]==rev0 and x['disk_heads_opened']==list(range(4))
        assert p['preparation_process_exited'] and all(p['catalog_present']) and all(r['has_head'] for r in p['inventory']['archives'])
print(json.dumps({'arms_checked':len(arms),'all_passed':all(x['passed'] for x in arms),'hashes_corpus_and_opportunistic_revisions_match':True,'revisions':rev0}))
