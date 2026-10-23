"""Authored acceptance cases; runtime UNRUN in the implementation environment.

Qoder/local runtime must execute these separately. AST parsing is not a test pass.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from lumaretouch_engine import project_package_archive as A


class PortableArchiveCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.photo = self.root / 'original.jpg'
        self.photo.write_bytes(b'unchanged original bytes')
        self.project = {'project_id': 'stable-project', 'docs': [
            {'document_id': 'stable-doc', 'path': str(self.photo), 'fingerprint': {'path': str(self.photo)},
             'document_history': {'undo': [{'source': str(self.photo)}], 'redo': []}}], 'assets': {}}
        self.dep = {'id': 'source-1', 'type': 'original', 'path': str(self.photo),
                    'include': True, 'licence': 'user-authorized', 'provenance': {'owner': 'user'},
                    'bindings': ['/docs/0/path', '/docs/0/fingerprint/path']}

    def package(self, dependencies=None):
        path = self.root / 'portable.lrtpack'
        A.create_archive(self.project, dependencies or [self.dep], path)
        return path

    def test_roundtrip_preserves_identity_history_and_immutable_inventory(self):
        result = A.restore_archive(self.package(), self.root / 'restored')
        restored = json.loads(Path(result['project_path']).read_text())
        self.assertEqual(restored['docs'][0]['document_id'], 'stable-doc')
        self.assertEqual(restored['docs'][0]['document_history'], self.project['docs'][0]['document_history'])
        self.assertEqual(Path(restored['docs'][0]['path']).read_bytes(), self.photo.read_bytes())
        self.assertEqual(A.readback_restore(result['destination'])['manifest_sha256'], result['manifest_sha256'])

    def test_excluded_dependency_is_explicit_missing_not_live_original(self):
        dep = dict(self.dep, include=False)
        result = A.restore_archive(self.package([dep]), self.root / 'restored')
        restored = json.loads(Path(result['project_path']).read_text())
        self.assertFalse(Path(restored['docs'][0]['path']).exists())
        self.assertEqual(result['missing'][0]['status'], 'excluded')
        self.assertTrue(self.photo.exists())

    def test_no_clobber_and_cancel_leave_original_untouched(self):
        archive = self.package()
        before = archive.read_bytes()
        with self.assertRaises(A.PackageError):
            A.create_archive(self.project, [self.dep], archive)
        with self.assertRaises(A.PackageCancelled):
            A.restore_archive(archive, self.root / 'cancelled', cancel=lambda: True)
        self.assertFalse((self.root / 'cancelled').exists())
        self.assertEqual(before, archive.read_bytes())

    def test_full_sha_expected_failure_is_not_published(self):
        dep = dict(self.dep, sha256_expected='0' * 64)
        with self.assertRaises(A.PackageError):
            A.create_archive(self.project, [dep], self.root / 'bad.lrtpack')
        self.assertFalse((self.root / 'bad.lrtpack').exists())

    def test_traversal_symlink_duplicate_and_case_names_rejected(self):
        for index, names in enumerate((['../escape'], ['/absolute'], ['blobs/../../escape'],
                                      ['manifest.json', 'MANIFEST.JSON'], ['project.json', 'project.json'])):
            path = self.root / f'unsafe-{index}.zip'
            with zipfile.ZipFile(path, 'w') as z:
                for name in names:
                    z.writestr(name, b'{}')
            with self.assertRaises(A.PackageError):
                A.inspect_archive(path)
        path = self.root / 'symlink.zip'
        info = zipfile.ZipInfo('project.json')
        info.external_attr = 0o120777 << 16
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr(info, b'/etc/passwd')
        with self.assertRaises(A.PackageError):
            A.inspect_archive(path)

    def test_equal_bytes_distinct_sources_keep_distinct_restore_paths(self):
        self.project['docs'].append(copy.deepcopy(self.project['docs'][0]))
        self.project['docs'][1]['document_id'] = 'different-doc'
        other = dict(self.dep, id='source-2', bindings=['/docs/1/path', '/docs/1/fingerprint/path'])
        result = A.restore_archive(self.package([self.dep, other]), self.root / 'restored')
        docs = json.loads(Path(result['project_path']).read_text())['docs']
        self.assertNotEqual(docs[0]['path'], docs[1]['path'])
        self.assertEqual(Path(docs[0]['path']).read_bytes(), Path(docs[1]['path']).read_bytes())

    def test_invalid_project_validator_prevents_publication(self):
        def reject(_):
            raise ValueError('schema mismatch')
        with self.assertRaises(ValueError):
            A.restore_archive(self.package(), self.root / 'invalid', project_validator=reject)
        self.assertFalse((self.root / 'invalid').exists())
