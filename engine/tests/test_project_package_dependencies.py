"""AUTHORED_UNRUN: local runtime owner must execute; AST parsing is not a pass."""
import unittest
from lumaretouch_engine import project_package_dependencies as D


class PackageDependencyCases(unittest.TestCase):
    def project(self):
        return {'schema_version':'lrt.project.v23','assets':{},'writer':{'engine':'test'},
            'source_assets':{'source/a':{'path':'/original.jpg','fingerprint':{'path':'/original.jpg','hash_level':'full','sha256':'a'*64}}},
            'docs':[{'source_asset_id':'source/a','document_id':'stable','path':'/original.jpg',
                     'fingerprint':{'path':'/original.jpg'},'document_history':{'undo':[
                         {'_sky_replacement':{'asset':{'path':'/sky.png','sha256':'b'*64}}}], 'redo':[]}}]}

    def test_inventory_includes_inactive_history_and_explicit_selection(self):
        rows = D.inventory(self.project(), False, True)
        self.assertEqual(len(rows),2)
        self.assertFalse(rows[0]['include'])
        self.assertIn('/source_assets/source~1a/path',rows[0]['bindings'])
        self.assertTrue(rows[1]['include'])
        self.assertIn('/docs/0/document_history/undo/0/_sky_replacement/asset/path',rows[1]['bindings'])

    def test_manifest_cannot_rebind_unrelated_path_or_change_fingerprint(self):
        project = self.project()
        rows = D.inventory(project,True,True)
        D.validate_inventory(project, rows)
        rows[0]['bindings'].append('/name')
        with self.assertRaises(ValueError): D.validate_inventory(project, rows)
        rows = D.inventory(project,True,True)
        rows[0].update(status='bundled',sha256='c'*64)
        with self.assertRaises(ValueError): D.validate_inventory(project,rows)

    def test_models_are_evidence_not_file_discovery(self):
        project = self.project()
        project['people']={'detector_model_sha256':'d'*64,'model_path':'/never-read.bin'}
        evidence = D.model_inventory(project)
        self.assertEqual(evidence['status'],'not-bundled')
        self.assertEqual(len(evidence['retained_evidence']),2)
        self.assertEqual(len(D.inventory(project)),2)
