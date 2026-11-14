"""Validate saved live process runs; native.py creates them."""
import json,pathlib,collections
E=pathlib.Path(__file__).resolve().parent
summaries=json.loads((E/'native-summary.json').read_text());assert len(summaries)==18
counts=collections.Counter()
for s in summaries:
    d=E/('native-'+s['name']);wire=json.loads((d/'wire.json').read_text())
    broken=s['cancel'] and s['workflow']!='coding.codex_loop'
    assert s['first']['ok'] == (not s['cancel'])
    assert all(s[k]['ok']==(not broken) for k in ('warm0','warm1','cold'))
    assert s['clear']['ok'] and s['cleared']['ok']
    malformed=[r for r in wire if r['missing_results']]
    assert len(malformed)==(3 if broken else 0),(s['name'],len(malformed))
    assert all(r['missing_results']==['probe-1'] for r in malformed)
    journal=[json.loads(line) for line in (d/'journal.jsonl').read_text().splitlines()]
    settlements=[r['payload']['value']['status'] for r in journal if r['kind']=='turn_settled']
    expected=['canceled' if s['cancel'] else 'success']+(['error']*3 if broken else ['success']*3)+['success']
    assert settlements==expected,(s['name'],settlements)
    # Checkpoint before the first settlement durably records call; cancel has no result.
    end=next(i for i,r in enumerate(journal) if r['kind']=='turn_settled')
    checkpoint=[r['payload']['value'] for r in journal[:end] if r['kind']=='history_mutated' and r['payload']['value']['mutation']=='checkpoint'][-1]
    parts=[p['payload'] for m in checkpoint['messages'] for p in m['parts']]
    assert sum('ToolCall' in p for p in parts)==1
    assert sum('ToolResult' in p for p in parts)==(0 if s['cancel'] else 1)
    if s['cancel'] and not broken:
        followup=wire[1]['body'];blocks=[p for m in followup['messages'] for p in m['content']]
        result=next(p for p in blocks if p['type']=='tool_result')
        assert result['tool_use_id']=='probe-1' and 'aborted' in str(result['content'])
    counts[s['workflow']+(' canceled' if s['cancel'] else ' control')]+=1
    print(s['name'], 'confirmed malformed warm/cold' if broken else 'valid control')
print('Verified',len(summaries),'process cases; malformed HTTP requests:',sum(len([r for r in json.loads((E/('native-'+s['name'])/'wire.json').read_text()) if r['missing_results']]) for s in summaries))
print(dict(counts))
