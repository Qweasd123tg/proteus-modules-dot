"""Inspect four pinned public data files. No application, module, command, plugin or network is used.
Usage: python3 static-check.py PATH_TO_CORE PATH_TO_MODULES  (Python 3.11+).
The list overlay calculations illustrate the guide's documented array replacement rule;
they are NOT a call into the Core loader or evidence of a live system.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tomllib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('core', type=Path)
parser.add_argument('modules', type=Path)
opt = parser.parse_args()

def read(path, expected):
    raw = path.read_bytes()
    digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if digest != expected:
        raise ValueError(f'{path.name}: expected pinned source blob {expected}, got {digest}')
    return raw.decode()

sample = tomllib.loads(read(opt.core/'examples/configs/proteus.example.toml',
                             '9b9376873841eb9e7a7505009b0c2c4e6fc0a2d6'))
catalog = json.loads(read(opt.modules/'proteus-catalog.json','c00f4170f0ef39902db0a4623b748570d0f07420'))
entries = {row['id']:row for row in catalog['entries']}
public = ['remember_fact', 'recall_memory']  # declared in Core's configuration guide, lines 1185–1193
component_exports = {}
for package, module_id, blob in [
        ('memory-pack', 'jsonl_memory', 'c1db0b9691ef0630e5e6cde6903320f856f55e8b'),
        ('sqlite-memory', 'sqlite_memory', '788a34e688074e5df04f70c5bac56989b805b446')]:
    item = entries[package]
    assert item['path'] == f'components/{package}-module'
    exports = json.loads(read(opt.modules/item['path']/'exports.json', blob))
    assert exports == {'tool':[module_id], 'context_provider':[module_id]}
    assert all(n not in rep for rep in exports.values() for n in public)
    component_exports[package] = exports
sample_exports = sample['components']['memory-pack']['exports']
assert sample_exports == {'tool':{'jsonl_memory':{}}}
ordinary = sample['tools']['enabled']
assert set(ordinary).intersection(public) == {'remember_fact'}
lost_if_replaced = [n for n in ordinary if n not in public]
safe_full_list = list(dict.fromkeys(ordinary+public))
other_names_when_tools_off = [n for n in safe_full_list if n not in public]
assert lost_if_replaced == ['apply_patch','request_user_input','search']
assert other_names_when_tools_off == lost_if_replaced
assert safe_full_list == ordinary+['recall_memory']
added_here = [n for n in safe_full_list if n not in ordinary]
rollback_picture = [n for n in safe_full_list if n not in added_here]
assert rollback_picture == ordinary and 'remember_fact' in rollback_picture
print(json.dumps({
    'public_files_blob_checked':4,
    'component_export_lists':component_exports,
    'sample_project_selected_exports':sample_exports,
    'sample_project_enabled_tools':ordinary,
    'guide_public_names_enabled_in_sample':[n for n in public if n in ordinary],
    'modules_catalog_entry_count':len(entries),
    'modules_catalog_observed_entry_keys':sorted(set().union(*(set(e) for e in entries.values()))),
    'memory_pack_source_requirements':entries['memory-pack']['source']['requirements'],
    'illustration_not_Core_loader':{
        'feature_list_wins_existing_names_lost':lost_if_replaced,
        'original_list_wins_new_public_names_missing':[n for n in public if n not in ordinary],
        'explicit_existing_plus_feature_names':safe_full_list,
        'explicitly_hide_both_public_names_not_reversible_uninstall':other_names_when_tools_off,
        'rollback_only_what_this_example_added':rollback_picture}},
    indent=2, sort_keys=True))
