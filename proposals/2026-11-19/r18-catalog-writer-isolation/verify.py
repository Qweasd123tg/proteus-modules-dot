#!/usr/bin/env python3
"""Verify persisted small synthetic reports, without starting a worker."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent/'evidence'/'paired-final'
for flavor in ('stock','candidate'):
    for trial in range(3):
        mode='overlap' if trial else 'idle'
        d=json.loads((root/f'{flavor}-{mode}-{trial}.json').read_text())
        assert (d['worker'],d['mode'],d['trial'])==(flavor,mode,trial)
        assert d['archives']==100 and d['rows_per_archive']==2000
        assert d['request_count']==1 and d['request_length']==102 and d['canonical_archives_unchanged'] is True
        m=d['marks'];assert m['send_start']<m['ack'] and m['send_start']<m['first_text']<=m['turn_output']
        assert d['first_text_ms']==round((m['first_text']-m['send_start'])/1e6,3)
        if mode=='overlap':
            assert 0<d['index_files_observed_at_trigger']<d['archives']
            assert m['list_start']<m['observed_progress']<=m['send_start']<m['list_done']
            assert d['list_ms']==round((m['list_done']-m['list_start'])/1e6,3)
            print(f"{flavor} {trial}: accepted={d['accepted_ms']:.3f}, text={d['first_text_ms']:.3f}, outcome={d['turn_output_ms']:.3f}, list={d['list_ms']:.3f} ms; first text before list done: {m['first_text']<m['list_done']}")
print('6 reports verified')
