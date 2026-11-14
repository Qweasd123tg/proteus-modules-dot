#!/usr/bin/env python3
"""Offline benchmark execution/provenance regressions, no model calls or secrets."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path('/workspace/shared/benchmark-execution-audit')
HERE = ROOT/'examples/performance/coding-harness'
sys.path.insert(0, str(HERE))
import runner
import reconnect_runs


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    evidence = {'core_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'python': sys.version, 'model_calls': 0, 'published_data_changed': False}
    with TemporaryDirectory(prefix='benchmark-execution-repro-') as directory:
        root = Path(directory)
        binaries = root/'bin'
        binaries.mkdir()
        picked = binaries/'proteus-candidate'
        sibling = binaries/'proteus'
        picked.write_text('#!/bin/sh\nprintf "candidate-selected\\n"\n')
        sibling.write_text('#!/bin/sh\nprintf "sibling-executed\\n"\n')
        picked.chmod(0o755)
        sibling.chmod(0o755)
        case = root/'case'
        (case/'repo').mkdir(parents=True)
        (case/'prompt.txt').write_text('OFFLINE SYNTHETIC NO-MODEL PROBE')
        auth = root/'synthetic-auth.json'
        auth.write_text('{}')
        output = root/'run'
        command = [sys.executable, str(HERE/'runner.py'), '--prepare-only', '--agent', 'proteus',
                   '--model', 'fixture', '--reasoning', 'high', '--base-config', str(ROOT/'configs/codex.config.toml'),
                   '--case-dir', str(case), '--output', str(output), '--binary', str(picked), '--auth-file', str(auth)]
        prepared = subprocess.run(command, capture_output=True, text=True)
        assert prepared.returncode == 0, prepared.stderr
        result = json.loads((output/'result.json').read_text())
        actual_inner = result['command'][result['command'].index('--')+1:]
        assert result['binary'] == str(picked)
        assert result['binary_sha256'] == sha(picked)
        assert actual_inner[0] == '/runtime/bin/proteus'
        assert result['binary_sha256'] != sha(sibling)
        execution = runner.execute(result['command'], output, 3, {'PATH': '/usr/bin:/bin'})
        out = (output/'stdout.jsonl').read_text()
        err = (output/'stderr.log').read_text()
        evidence['binary_selection'] = {
            'prepared_returncode': prepared.returncode,
            'claimed_binary_basename': Path(result['binary']).name,
            'claimed_binary_sha256': result['binary_sha256'],
            'actual_inner_executable': actual_inner[0],
            'mounted_sibling_sha256': sha(sibling),
            'sandbox_execution': execution, 'sandbox_stdout': out, 'sandbox_stderr': err,
            'selected_binary_direct_control': subprocess.check_output([str(picked)], text=True),
            'sibling_binary_direct_control': subprocess.check_output([str(sibling)], text=True),
        }
        if execution['returncode'] == 0:
            assert out == 'sibling-executed\n'
        else:
            assert 'bwrap:' in err, 'Unexpected execution failure'

        # Reproduce verification directly against a synthetic portable layout.
        fake_core = root/'reconnect/Core'
        prefix = fake_core.parent/'Proteus-desktop/build/Proteus'
        node_modules = prefix/'share/pi-runtime/tool/pi-tools/node_modules'
        package = node_modules/'example-model'
        package.mkdir(parents=True)
        (package/'package.json').write_text('{"name":"example-model","version":"1.0.0"}')
        implementation = package/'model-runtime.js'
        implementation.write_text('module.exports = "before";\n')
        entry = prefix/'share/pi-runtime/tool/pi-tools/driver.mjs'
        entry.write_text("import value from './node_modules/example-model/model-runtime.js'; console.log(value);\n")
        bin_dir = prefix/'bin'
        bin_dir.mkdir(parents=True)
        (bin_dir/'proteus').write_text('synthetic executable hash marker')
        original_core = reconnect_runs.CORE
        reconnect_runs.CORE = fake_core
        try:
            first = reconnect_runs.runtime_snapshot()
            before = subprocess.check_output([shutil.which('node'), str(entry)], text=True)
            first_sha = sha(implementation)
            implementation.write_text('module.exports = "after";\n')
            second = reconnect_runs.runtime_snapshot()
            after = subprocess.check_output([shutil.which('node'), str(entry)], text=True)
            second_sha = sha(implementation)
            assert before != after and first_sha != second_sha
            assert first == second
            # Positive control: changes to the wrapper ARE detected.
            entry.write_text(entry.read_text() + '\n// tracked-wrapper-control\n')
            third = reconnect_runs.runtime_snapshot()
            assert third != second
            evidence['runtime_snapshot'] = {
                'before_output': before, 'after_output': after,
                'before_dependency_sha256': first_sha, 'after_dependency_sha256': second_sha,
                'dependency_changed_but_snapshot_equal': first == second,
                'snapshot_hash_keys': sorted(first['hashes']),
                'package_json_omitted': not any(key.endswith('package.json') for key in first['hashes']),
                'wrapper_change_detected_control': third != second,
            }
        finally:
            reconnect_runs.CORE = original_core
    print(json.dumps(evidence, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
