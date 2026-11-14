"""Synthetic packaging regression: real main/assemble/validators/publish.

Uses upstream PortableSelectionTests' fake compiler, source resolution, assets,
notices, and package producer. Does not run real binaries or a GUI.
"""
from pathlib import Path
import sys
import json
import shutil

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
from test_release_cargo_binary import PortableSelectionTests


def probe(protocol, features, label):
    case = PortableSelectionTests('test_default_builds_only_desktop_and_preserves_whole_reused_components')
    case.setUp()
    try:
        shutil.copytree(case.base, case.portable.PORTABLE)
        sentinel = case.portable.PORTABLE / 'working-sentinel'
        sentinel.write_text('previous structurally-valid protocol-4 bundle')
        case.portable.read_record(case.portable.PORTABLE)
        original = case.fake_run

        def future_bundle(command, cwd):
            original(command, cwd)
            if cwd.name == 'extensions':
                path = Path(command[command.index('--bundle') + 1]) / 'new/extension.json'
                spec = json.loads(path.read_text())
                spec.update(protocol=protocol, required_features=features)
                path.write_text(json.dumps(spec))

        case.run.side_effect = future_bundle
        case.write_json(case.root / 'extensions/packages/new/extension.json',
                        {'protocol': protocol, 'required_features': features})
        # The same source is rejected before publication in extensions-only mode.
        try:
            case.invoke('--components', 'extensions')
        except SystemExit as error:
            print(f'{label}: single-component guard rejected: {error}')
        else:
            raise AssertionError('expected extensions-only guard to reject')
        assert sentinel.exists()
        case.invoke('--components', 'desktop', 'extensions')
        record = case.record()
        spec = json.loads((case.portable.PORTABLE / 'share/extensions/new/extension.json').read_text())
        print(f'{label}: combined update published desktop protocol={record["desktop_protocol"]}, '
              f'extension protocol={spec["protocol"]}, supported={record["desktop_features"]}, '
              f'required={spec["required_features"]}')
        print(f'{label}: previous destination retained={sentinel.exists()}')
        assert record['desktop_protocol'] == 4 and spec['protocol'] == protocol
        assert record['desktop_features'] == [] and spec['required_features'] == features
        assert not sentinel.exists()
    finally:
        case.doCleanups()


probe(5, [], 'protocol mismatch')
probe(4, ['future.v99'], 'feature mismatch')
print('CONFIRMED: production portable control flow publishes both incompatible synthetic bundles.')
