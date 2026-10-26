"""Owned tiny packaging controls; no Core, tracer or original data runs/deletions."""
import importlib.util
from pathlib import Path
import tarfile
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('archiver', Path(__file__).with_name('archive_evidence.py'))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ArchiveTests(unittest.TestCase):
    def test_hidden_and_vertical_bar_files_roundtrip_without_source_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'evidence'
            leaf = source / 'owned|session'
            leaf.mkdir(parents=True)
            (leaf / '.read-view.json').write_bytes(b'{"authored":true}')
            (leaf / 'journal.jsonl').write_bytes(b'authored\n')
            receipt = module.archive(source, root/'evidence.tar.gz', root/'manifest.json')
            self.assertEqual(len(receipt['files']), 2)
            self.assertTrue(receipt['all_payloads_verified'])
            self.assertEqual((leaf/'.read-view.json').read_bytes(), b'{"authored":true}')
            with tarfile.open(root/'evidence.tar.gz') as archive:
                self.assertEqual(archive.extractfile('native-cache/owned|session/.read-view.json').read(), b'{"authored":true}')

    def test_symlink_is_rejected_before_archive_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'evidence'; source.mkdir()
            (root/'owned-target').write_text('authored')
            (source/'link').symlink_to(root/'owned-target')
            with self.assertRaisesRegex(ValueError, 'nonregular evidence'):
                module.archive(source, root/'evidence.tar.gz', root/'manifest.json')
            self.assertFalse((root/'evidence.tar.gz').exists())

    def test_recursive_output_and_existing_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'evidence'; source.mkdir()
            (source/'fixture').write_text('authored')
            with self.assertRaisesRegex(ValueError, 'outside the evidence'):
                module.archive(source, source/'evidence.tar.gz', root/'manifest.json')
            (root/'evidence.tar.gz').write_text('preserve')
            with self.assertRaisesRegex(ValueError, 'outputs must be new'):
                module.archive(source, root/'evidence.tar.gz', root/'manifest.json')
            self.assertEqual((root/'evidence.tar.gz').read_text(), 'preserve')

    def test_size_bound_and_empty_source_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'evidence'; source.mkdir()
            with self.assertRaisesRegex(ValueError, 'empty'):
                module.archive(source, root/'evidence.tar.gz', root/'manifest.json')
            (source/'fixture').write_text('authored')
            with self.assertRaisesRegex(ValueError, 'size bound'):
                module.archive(source, root/'evidence.tar.gz', root/'manifest.json', max_file=3)
            self.assertFalse((root/'evidence.tar.gz').exists())


if __name__ == '__main__':
    unittest.main()
