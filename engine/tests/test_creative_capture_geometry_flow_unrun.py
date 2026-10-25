"""AUTHORED / UNRUN: capture-only geometry routing, ownership and fence fixtures.

Metadata/decode/render/spec/admission/geometry are MOCKED except the actual
bridge prepare/finish control flow and ordinary canonical asset construction.
Arrays are small ownership/dtype/extent sentinels, NOT numerical geometry parity,
genuine image acceptance or measured memory/RSS evidence. The geometry-core
worker owns independent real-sampler parity fixtures. No tests/product imports
were executed while authoring this file; AST inspection is syntax-only.
"""
import ast
from contextlib import contextmanager, ExitStack
import hashlib
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import mock_open, patch
import weakref

from lumaretouch_engine import creative_edited_capture as bridge
from lumaretouch_engine import creative_edited_capture_admission as admission
from lumaretouch_engine import creative_capture_geometry as geometry
from lumaretouch_engine import creative_edited_capture_sink as sink
from lumaretouch_engine import creative_document_base as base
from lumaretouch_engine import creative_document_import_bounded as importer
from lumaretouch_engine import local_mask_state as masks
from lumaretouch_engine import virtual_copy_people as people
from lumaretouch_engine.creative_document_assets import AssetStore


class _MockSpec:
    """Weak-referenceable routing sentinel, not a real accepted ExportSpec."""


class _GeometryFlow:
    def __init__(self):
        self.path = '/mock-only/geometry-capture.png'
        self.original = b'\x89PNG\r\n\x1a\ngeometry-flow-mock-not-a-valid-image'
        self.source_stamp = (10, 20, 30)
        self.current_stamp = self.source_stamp
        self.rect = (.1, .2, .9, .8)
        self.angle = 23.75
        self.snapshot = {'crop_rect': self.rect, 'crop_rotation': self.angle}
        self.context = {'analyses': {}, **{key: {} for key in people.FIELDS}}
        self.metadata = dict(width=6, height=4, bits=8, orientation=1,
                             working_orientation=1, icc=b'mock-icc')
        self.eligible = True
        self.events = []
        self.versions = []
        self.plan_count = 0
        self.geometry_budget = 777_123
        self.references = {}
        self.cancelled = False
        self.cancel_after_export = False
        self.cancel_after_geometry = False
        self.change_source_after_geometry = False
        self.geometry_error = None
        self.final_plan_error = None
        self.export_geometry = object()
        self.export_shape = (4, 6, 3)
        self.export_dtype = 'float32'
        self.geometry_arguments = None
        self.source_context = None

    def classify(self, snapshot, *, geometry_version=0, finishing_version=0):
        if finishing_version != 0:
            raise AssertionError('This geometry fixture does not model bounded colour finishing')
        self.events.append('classify')
        self.versions.append(('classify', geometry_version))
        return SimpleNamespace(eligible=self.eligible)

    def plan(self, metadata, snapshot, **kwargs):
        self.plan_count += 1
        self.events.append('plan-spec' if 'spec' in kwargs else 'plan-decode')
        self.versions.append(('plan', kwargs.get('geometry_version', 0)))
        if 'spec' in kwargs and self.final_plan_error is not None:
            raise self.final_plan_error
        # Different budgets ensure the bridge uses the definitive spec plan,
        # rather than a stale pre-decode estimate or the entire capture budget.
        return SimpleNamespace(geometry_max_bytes=self.geometry_budget if 'spec' in kwargs else 123_456)

    def validate(self, spec, snapshot, *, skipped=(), geometry_version=0, finishing_version=0):
        if finishing_version != 0:
            raise AssertionError('This geometry fixture does not model bounded colour finishing')
        self.events.append('validate')
        self.versions.append(('validate', geometry_version))

    def decode(self, path, original, **kwargs):
        import numpy as np
        self.events.append('decode')
        self.decode_arguments = (path, original, kwargs['max_pixels'], kwargs['device'])
        value = np.zeros((4, 6, 3), dtype=np.uint8)
        self.references['decoded'] = weakref.ref(value)
        return value

    def prepare_snapshot(self, path, snapshot, for_document):
        self.events.append('prepare-snapshot')
        return snapshot, for_document

    def build(self, snapshot, height, width, *, for_document):
        self.events.append('build-spec')
        self.spec_extent = (height, width, for_document)
        spec = _MockSpec()
        self.references['spec'] = weakref.ref(spec)
        return spec, []

    def render(self, source, spec, *, geometry, progress, provenance):
        import numpy as np
        self.events.append('export')
        self.export_geometry = geometry
        self.export_provenance = provenance
        self.source_context = dict(spec._creative_capture_original_source)
        progress('mock export progress')
        value = np.full(self.export_shape, 0.25, dtype=self.export_dtype)
        self.references['exported'] = weakref.ref(value)
        if self.cancel_after_export:
            self.cancelled = True
        return value, {'mock_control_flow_only': True}

    def rotate(self, rgb, rect, rotation, *, max_bytes, cancelled):
        import numpy as np
        self.events.append('geometry-call')
        if cancelled():
            raise InterruptedError('Mock geometry observed cancellation before work')
        self.events.append('geometry-work')
        self.geometry_arguments = (rect, rotation, max_bytes, rgb.shape, str(rgb.dtype))
        self.geometry_input_matches_export = self.references['exported']() is rgb
        if self.geometry_error is not None:
            raise self.geometry_error
        # Intentionally configured mock extent, not a calculation of rotation.
        value = np.full((5, 7, 3), -0.125, dtype=np.float64)
        self.references['rotated'] = weakref.ref(value)
        if self.change_source_after_geometry:
            self.current_stamp = (10, 20, 31)
        if self.cancel_after_geometry:
            self.cancelled = True
        return value

    def run(self, *, geometry_version=1, omit_version=False):
        self.snapshot.update(crop_rect=self.rect, crop_rotation=self.angle)
        engine = SimpleNamespace(_prepare_export_snapshot=self.prepare_snapshot)
        options = {} if omit_version else {'geometry_version': geometry_version}
        return bridge.prepare(engine, {'path': self.path}, self.snapshot,
            retained_roots=('mock-snapshot-root',), persistent_roots=('mock-host-root',),
            source_stamp=self.source_stamp, document_id='mock-geometry-document',
            max_bytes=512_000_000, cancelled=lambda: self.cancelled, **options)


@contextmanager
def _flow():
    from lumaretouch_engine import export, export_recipe
    value = _GeometryFlow()
    with ExitStack() as stack:
        stack.enter_context(patch('builtins.open', mock_open(read_data=value.original)))
        stack.enter_context(patch.object(bridge.Path, 'stat',
            return_value=SimpleNamespace(st_size=len(value.original))))
        stack.enter_context(patch.object(admission, 'classify_snapshot', new=value.classify))
        stack.enter_context(patch.object(admission, 'retained_bytes', new=lambda roots: 4096))
        stack.enter_context(patch.object(admission, 'plan_capture', new=value.plan))
        stack.enter_context(patch.object(admission, 'validate_spec', new=value.validate))
        stack.enter_context(patch.object(people, '_context', new=lambda engine, row: value.context))
        stack.enter_context(patch.object(importer, 'inspect_encoded_source',
            new=lambda *args, **kwargs: value.metadata))
        stack.enter_context(patch.object(base, '_working_source', new=value.decode))
        stack.enter_context(patch.object(masks, 'file_stamp', new=lambda path: value.current_stamp))
        stack.enter_context(patch.object(masks, 'source_digest',
            new=lambda path: hashlib.sha256(value.original).hexdigest()))
        stack.enter_context(patch.object(bridge, '_verify_inputs', new=lambda *args: None))
        stack.enter_context(patch.object(export_recipe, 'build_export_spec', new=value.build))
        stack.enter_context(patch.object(export, 'export_float', new=value.render))
        stack.enter_context(patch.object(geometry, 'crop_rotate_np_bounded', new=value.rotate))
        yield value


class CaptureGeometryFlowContracts(unittest.TestCase):
    def test_opted_in_unsnapped_rotation_defers_only_geometry_to_bounded_owner(self):
        with _flow() as flow:
            pending = flow.run()
            self.assertIsNone(flow.export_geometry)
            self.assertFalse(flow.export_provenance)
            self.assertTrue(flow.geometry_input_matches_export)
            self.assertEqual(flow.geometry_arguments,
                (flow.rect, flow.angle, flow.geometry_budget, (4, 6, 3), 'float32'))
            self.assertEqual(pending.rgb.shape, (5, 7, 3))
            self.assertEqual(str(pending.rgb.dtype), 'float64')
            self.assertIs(flow.references['rotated'](), pending.rgb)
            self.assertEqual(flow.events.count('export'), 1)
            self.assertEqual(flow.events.count('geometry-work'), 1)
            self.assertLess(flow.events.index('plan-spec'), flow.events.index('export'))
            self.assertLess(flow.events.index('export'), flow.events.index('geometry-work'))

    def test_version_is_forwarded_to_both_plans_classification_and_spec_validation(self):
        with _flow() as flow:
            flow.run(geometry_version=1)
            self.assertEqual(flow.versions, [('classify', 1), ('plan', 1),
                                            ('validate', 1), ('plan', 1)])

    def test_default_and_explicit_old_geometry_modes_keep_export_geometry_tuple(self):
        # Eligibility is mocked true here to isolate dispatch, not to assert
        # that the old real admission accepts an unsnapped recipe.
        for omit in (False, True):
            with self.subTest(omit_version=omit), _flow() as flow:
                pending = flow.run(geometry_version=0, omit_version=omit)
                self.assertEqual(flow.export_geometry, (flow.rect, flow.angle))
                self.assertNotIn('geometry-call', flow.events)
                self.assertIs(pending.rgb, flow.references['exported']())
                self.assertTrue(all(version == 0 for _, version in flow.versions))

    def test_snapped_angles_and_identity_do_not_enter_the_new_geometry_owner(self):
        for angle in (0., 90., -90., 180., 89.9, -89.9):
            with self.subTest(angle=angle), _flow() as flow:
                flow.angle = angle
                if angle == 0.:
                    flow.rect = (0., 0., 1., 1.)
                pending = flow.run()
                self.assertEqual(flow.export_geometry, (flow.rect, angle))
                self.assertNotIn('geometry-call', flow.events)
                self.assertIs(pending.rgb, flow.references['exported']())

    def test_unsnapped_boundary_angles_enter_new_owner_not_approximate_quarter_turn(self):
        for angle in (.5, 89.5, -89.5):
            with self.subTest(angle=angle), _flow() as flow:
                flow.angle = angle
                flow.run()
                self.assertIsNone(flow.export_geometry)
                self.assertEqual(flow.geometry_arguments[1], angle)

    def test_ineligible_post_geometry_family_stops_before_decode_or_partial_render(self):
        # Actual active-CG/SC admission is covered elsewhere. This verifies that
        # a declined family is not retried here with those effects silently off.
        with _flow() as flow, patch('builtins.open') as opened:
            flow.eligible = False
            flow.snapshot['colour_grading'] = {'mock_active': True}
            self.assertIsNone(flow.run())
            self.assertEqual(flow.events, ['classify'])
            opened.assert_not_called()

    def test_definitive_plan_refusal_happens_before_export_and_geometry(self):
        with _flow() as flow:
            flow.final_plan_error = admission.CaptureBudgetExceeded('mock final geometry plan refusal')
            with self.assertRaisesRegex(admission.CaptureBudgetExceeded, 'final geometry plan'):
                flow.run()
            self.assertNotIn('export', flow.events)
            self.assertNotIn('geometry-call', flow.events)

    def test_deferred_geometry_refuses_proxy_canvas_wrong_channels_or_changed_precision(self):
        for shape, dtype in (((2, 3, 3), 'float32'), ((4, 6, 4), 'float32'),
                             ((4, 6, 3), 'float64'), ((4, 6, 3), 'uint8')):
            with self.subTest(shape=shape, dtype=dtype), _flow() as flow:
                flow.export_shape, flow.export_dtype = shape, dtype
                with self.assertRaisesRegex(ValueError, 'exact full-source float32 export canvas'):
                    flow.run()
                self.assertEqual(flow.events.count('export'), 1)
                self.assertNotIn('geometry-call', flow.events)

    def test_geometry_failure_propagates_without_export_retry_or_partial_pending(self):
        with _flow() as flow:
            flow.geometry_error = ValueError('mock bounded geometry failure')
            with self.assertRaisesRegex(ValueError, 'bounded geometry failure'):
                flow.run()
            self.assertEqual(flow.events.count('export'), 1)
            self.assertEqual(flow.events.count('geometry-work'), 1)

    def test_original_provenance_and_source_context_survive_deferred_geometry(self):
        with _flow() as flow:
            pending = flow.run()
            self.assertEqual(pending.original, flow.original)
            self.assertEqual(pending.icc, flow.metadata['icc'])
            self.assertEqual(pending.persistent_retained_bytes, 4096)
            self.assertEqual(flow.decode_arguments, (flow.path, flow.original, 24, 'cpu'))
            self.assertEqual(flow.spec_extent, (4, 6, True))
            self.assertEqual(flow.source_context, {
                'path': flow.path, 'file_stamp': list(flow.source_stamp),
                'asset_sha256': hashlib.sha256(flow.original).hexdigest(),
                'document_id': 'mock-geometry-document'})

    def test_cancel_after_export_stops_before_geometry_work_and_never_interns(self):
        with _flow() as flow, patch.object(AssetStore, 'intern') as intern:
            flow.cancel_after_export = True
            with self.assertRaises(InterruptedError):
                flow.run()
            self.assertNotIn('geometry-work', flow.events)
            intern.assert_not_called()

    def test_cancel_after_geometry_never_returns_pending_or_interns(self):
        with _flow() as flow, patch.object(AssetStore, 'intern') as intern:
            flow.cancel_after_geometry = True
            with self.assertRaises(InterruptedError):
                flow.run()
            self.assertEqual(flow.events.count('geometry-work'), 1)
            intern.assert_not_called()

    def test_final_original_file_fence_occurs_after_bounded_geometry(self):
        with _flow() as flow, patch.object(AssetStore, 'intern') as intern:
            flow.change_source_after_geometry = True
            with self.assertRaisesRegex(ValueError, 'Original changed'):
                flow.run()
            self.assertEqual(flow.events.count('geometry-work'), 1)
            intern.assert_not_called()

    def test_new_asset_extent_comes_from_final_float64_geometry_not_original_metadata(self):
        with _flow() as flow:
            pending = flow.run()
        seen = []

        def inspect(rgb, **kwargs):
            seen.append(('inspect', rgb.shape, str(rgb.dtype)))
            return SimpleNamespace(freeze_bytes_after_source_release=2 * 5 * 7 * 16)

        def convert(rgb, **kwargs):
            seen.append(('convert', rgb.shape, str(rgb.dtype)))
            # Already canonical tiny storage fixture, NOT simulated transfer math.
            return SimpleNamespace(width=7, height=5,
                sink=bytearray(struct.pack('<4f', 0.125, -0.25, 2.0, 1.0) * 35))

        with patch.object(sink, 'inspect_rgb_sink', new=inspect), patch.object(
                sink, 'capture_rgb_sink', new=convert), patch.object(AssetStore, 'intern') as intern:
            record = bridge.finish(pending)
            intern.assert_not_called()
        self.assertEqual(seen, [('inspect', (5, 7, 3), 'float64'),
                                ('convert', (5, 7, 3), 'float64')])
        self.assertEqual((record['width'], record['height']), (7, 5))
        self.assertEqual(len(record['content']), 7 * 5 * 16)
        self.assertEqual(record['original'], pending.original)
        self.assertEqual(record['icc'], pending.icc)
        self.assertIs(type(record['content']), bytes)
        self.assertIsNone(pending.rgb)


class GeometryVersionSourceContracts(unittest.TestCase):
    """Static source structure only, not executed base/host integration."""
    def _function(self, module, name):
        tree = ast.parse(Path(module.__file__).read_text())
        return next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == name)

    def _defaults(self, function):
        return {arg.arg: value for arg, value in zip(function.args.kwonlyargs,
                                                    function.args.kw_defaults)}

    def test_capture_default_stays_zero_and_bridge_geometry_defaults_stay_zero(self):
        capture = self._function(base, 'capture_current_asset')
        self.assertEqual(ast.literal_eval(self._defaults(capture)['edited_capture_version']), 0)
        for name in ('preflight_snapshot', 'prepare'):
            function = self._function(bridge, name)
            self.assertEqual(ast.literal_eval(self._defaults(function)['geometry_version']), 0)

    def test_only_explicit_capture_versions_two_and_three_map_to_new_geometry_mode(self):
        capture = self._function(base, 'capture_current_asset')
        mappings = [node for node in ast.walk(capture) if isinstance(node, ast.IfExp)
                    and ast.unparse(node.test) == 'edited_capture_version in (2, 3)'
                    and isinstance(node.body, ast.Constant) and node.body.value == 1
                    and isinstance(node.orelse, ast.Constant) and node.orelse.value == 0]
        self.assertTrue(mappings)
        for name in ('preflight_snapshot', 'prepare_edited'):
            call = next(node for node in ast.walk(capture)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == name)
            self.assertIn('geometry_version', {item.arg for item in call.keywords})

    def test_classifier_plan_and_validation_receive_explicit_geometry_version(self):
        for name in ('preflight_snapshot', 'prepare'):
            function = self._function(bridge, name)
            calls = [node for node in ast.walk(function)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                     and node.func.id in ('classify_snapshot', 'plan_capture', 'validate_spec')]
            self.assertTrue(calls)
            for call in calls:
                keywords = {item.arg: ast.unparse(item.value) for item in call.keywords}
                self.assertEqual(keywords['geometry_version'], 'geometry_version')

    def test_generic_exporter_does_not_import_the_capture_only_geometry_module(self):
        from lumaretouch_engine import export
        source = Path(export.__file__).read_text()
        self.assertNotIn('creative_capture_geometry', source)
        function = self._function(export, 'export_float')
        self.assertNotIn('geometry_version', self._defaults(function))

    def test_final_base_document_and_file_fence_remains_after_finish_before_intern(self):
        capture = self._function(base, 'capture_current_asset')
        branch = next(node for node in ast.walk(capture)
                      if isinstance(node, ast.If) and ast.unparse(node.test) == 'pending is not None')
        finish = next(node for node in ast.walk(branch)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                      and node.func.id == 'finish_edited')
        fence = next(node for node in branch.body if isinstance(node, ast.If)
                     and 'file_stamp(path)' in ast.unparse(node.test)
                     and '_document_versions().version(row)' in ast.unparse(node.test))
        intern = next(node for node in ast.walk(branch)
                      if isinstance(node, ast.Call) and ast.unparse(node.func) == 'assets.intern')
        self.assertLess(finish.lineno, fence.lineno)
        self.assertLess(fence.lineno, intern.lineno)
        self.assertTrue(any(isinstance(node, ast.Raise) for node in fence.body))


if __name__ == '__main__':
    unittest.main()
