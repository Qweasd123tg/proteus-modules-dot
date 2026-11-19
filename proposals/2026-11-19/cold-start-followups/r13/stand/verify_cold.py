"""Read-only cross-check of the synthetic R9 fresh client/uncached Core startup.

Input: completed case directories containing core.log and the untouched R11
per-worker proxy wire CSVs. Does not inspect payloads, invoke Core, or replay.
"""
import argparse
import csv
import json
import re
from pathlib import Path


def require(ok, why):
    if not ok:
        raise ValueError(why)


def audit(path):
    log = (path / 'core.log').read_text()
    require('test result: ok. 1 passed;' in log, 'test did not succeed')
    cases = re.findall(r'CASE display=(\d+) active=100 journal_bytes=(\d+) '
                       r'fresh_storage=true prepared_ms=([\d.]+) launch_ms=([\d.]+)', log)
    require(len(cases) == 1, 'expected one fresh client case')
    count, journal_bytes, prepare, launch = cases[0]
    count, journal_bytes = int(count), int(journal_bytes)
    require(count >= 100 and count % 100 == 0, 'unexpected fixture shape')
    records = count // 100 + int(count > 100)
    pages = (records + 63) // 64
    require(f'SCAN display_only=true from=0 received={records} pages={pages}' in log,
            'cold display route not observed')
    require(re.search(rf'TURN display={count} active=100 request_messages=\[101\] '
                      rf'total_ms=[\d.]+ projected={count+2} ', log), 'turn checks incomplete')

    streams = []
    for f in sorted(path.glob('wire-*.csv')):
        with f.open(newline='') as inp:
            streams.append(list(csv.DictReader(inp)))
    require(len(streams) == 2, 'expected exactly two distinct worker streams')
    seed, measured = sorted(streams, key=lambda rs: not any(r['op']=='create' for r in rs))
    seed_ops = [r['op'] for r in seed]
    require(seed_ops == ['initialize', 'create', 'acquire_writer'] +
            ['commit'] * records + ['release_writer'],
            'seed performed operations other than seeding; cache state unknown')
    require(all(r['kind'] == 'history_mutated' for r in seed if r['op'] == 'commit'),
            'non-history seed record')
    require(int(seed[-1]['worker_response_done_ns']) <= int(measured[0]['req_done_ns']),
            'seed and measured workers overlap')
    ops = [r['op'] for r in measured]
    require(ops[:4] == ['initialize', 'open', 'read_cache', 'open_display_snapshot']
            and measured[2]['cache_key_class'] == 'display-view-v1-head', 'missing cold head recovery')
    require(ops[4:4+pages] == ['read_display_records'] * pages and
            ops.count('read_display_records') == pages, 'unexpected projected record pagination')
    # Save_read_model emits final versioned/current head after leaves; key names
    # refer only to synthetic keys classified by the original R10 wire tap.
    first_publish = next((i for i,r in enumerate(measured)
                          if r['op']=='write_cache' and r['cache_key_class']=='display-view-v1-head'), None)
    require(first_publish is not None and first_publish > 3+pages, 'no first head publish')
    require(first_publish < ops.index('commit') and ops.count('commit') == 6,
            'head not published before first real turn or unexpected turn record count')
    return dict(sample=path.name, display=count, canonical_seed_records=records,
                display_rpc_pages=pages, journal_bytes=journal_bytes,
                separate_worker_streams=True, prepared_plus_launch_ms=round(float(prepare)+float(launch),3))


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('cases', nargs='+', type=Path)
    args=ap.parse_args()
    for case in args.cases:
        try:
            print(json.dumps(audit(case)))
        except (ValueError, KeyError, OSError, IndexError) as exc:
            ap.exit(1, f'{case}: {exc}\n')
