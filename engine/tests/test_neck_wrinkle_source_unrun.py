"""UNRUN source-contract fixtures. No product imports during authoring."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1] / 'src' / 'lumaretouch_engine'


class NeckSourceContracts(unittest.TestCase):
    def source(self, name):
        return (ROOT / (name + '.py')).read_text()

    def test_factories_are_only_source_authority(self):
        source = self.source('neck_wrinkle_source')
        self.assertIn('type(resolver) is not SourceResolver', source)
        self.assertIn('resolver._token is not _TOKEN', source)
        self.assertIn('F.capture(engine, expected_source=source', source)
        self.assertIn('F.capture_original', source)
        self.assertIn('export_source(base', source)
        self.assertNotIn('spec.source', source)

    def test_neutral_export_does_not_require_capture(self):
        tree = ast.parse(self.source('neck_wrinkle_source'))
        fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == 'from_export')
        self.assertIsInstance(fn.body[1], ast.If)
        self.assertIsInstance(fn.body[1].body[0], ast.Return)
        self.assertIsNone(fn.body[1].body[0].value.value)

    def test_ordered_original_repair_vectors(self):
        source = self.source('neck_wrinkle_source_capture')
        self.assertIn('for op in operations:', source)
        self.assertIn('materialize([op]', source)
        self.assertIn('replay_repair_t(cur, full)', source)
        self.assertNotIn('clip(', source)
        self.assertNotIn('resize(', source)
        self.assertIn('_freeze(rgb, source', source)

    def test_source_proof_and_analysis_ownership(self):
        source = self.source('neck_wrinkle_source')
        self.assertIn("engine._people_analyses.get(source['sha256'], {})", source)
        self.assertIn('SNAP.at_dimensions(frozen', source)
        self.assertIn("'analyses': {ref['face_instance_id']: raw}", source)
        self.assertIn("'repair_sha256': resolver.repair_sha256", source)
        self.assertIn("'input_sha256': captured.input_sha256", source)
        self.assertIn('np.frombuffer(captured.content', source)

    def test_history_contains_metadata_not_fitted_pixels(self):
        source = self.source('neck_wrinkle_inputs')
        self.assertIn("'active_sha256': R.digest_ops(active, [], bound)", source)
        self.assertIn("'repair_sha256': R.digest_ops(active, redo, bound)", source)
        self.assertNotIn('base64', source)
        self.assertNotIn('np.', source)
