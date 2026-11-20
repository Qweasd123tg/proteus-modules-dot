#!/usr/bin/env python3
"""Join separately collected, fail-closed arms only if fixtures/binaries match."""
import argparse
import json
from pathlib import Path

from verify import require


def summary(paths):
    outputs, specs = [], set()
    seen = set()
    for path in paths:
        require(path.resolve() not in seen, 'duplicate arm path')
        seen.add(path.resolve())
        doc = json.loads((path/'report.json').read_text())
        require(doc['status']=='passed','incomplete run')
        for row in doc['runs']:
            proof = row['parking_proof']
            require(proof['status']=='passed' and row['rounds']==2,'missing two-round correctness gate')
            specs.add((row['peers'],row['payload_bytes'],row['delay_ms'],row['sample_interval_s'],
                       row['idle_window_ms'],row['idle_guard_ms'],*((k,v['sha256']) for k,v in sorted(doc['binaries'].items()))))
            outputs.append(dict(arm=path.name,repeat=row['repeat'],peers=row['peers'],
                      strategy='park' if row['idle_cap']==0 else 'retain',
                      interround_idle_pss_swap_mib=proof['idle']['interround_idle']['median_pss_swap_mib'],
                      final_idle_pss_swap_mib=proof['idle']['resident_idle']['median_pss_swap_mib'],
                      total_sampled_peak_pss_swap_mib=row['sampled_peak_pss_swap_mib'],
                      resumed_round=proof['rounds'][1]))
    require(len(specs)==1, 'cannot compare different peer counts, profiles or binaries')
    require({x['strategy'] for x in outputs}=={'retain','park'}, 'need both successful arms')
    return outputs


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('arm_paths',nargs='+',type=Path)
    print(json.dumps(summary(parser.parse_args().arm_paths),indent=2))
