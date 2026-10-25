"""AUTHORED / UNRUN: actual prepare/finish control flow and base-source fences.

Decode, metadata inspection, family classification, spec construction, retention
census and rendering are explicitly MOCKED in the flow harness. Its tiny arrays
are ownership sentinels, not evidence of genuine image decoding, accepted host
recipes, numerical parity, real rendering or memory/RSS acceptance. Real host
state/build_export_spec coverage belongs to the independent admission fixtures.

No product import, test or fixture execution was performed while authoring this
file. Syntax-only AST inspection does not execute the imports written below.
"""
import ast
from contextlib import contextmanager, ExitStack
import gc
import hashlib
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import mock_open, patch
import weakref

from lumaretouch_engine import creative_edited_capture as bridge
from lumaretouch_engine import creative_edited_capture_admission as admission
from lumaretouch_engine import creative_edited_capture_sink as sink
from lumaretouch_engine import creative_document_base as base
from lumaretouch_engine import creative_document_import_bounded as importer
from lumaretouch_engine import local_mask_state as masks
from lumaretouch_engine import virtual_copy_people as people
from lumaretouch_engine.creative_document_assets import AssetStore


class _SpecSentinel:
    """Weak-referenceable mock, deliberately NOT an accepted real ExportSpec."""


class _MockFlow:
    """No mock records retain decoded/spec/RGB owners through call_args."""
    def __init__(self):
        self.path = '/mock-only/edited-source.png'
        # Intentionally not a valid encoded image: header/decoder are mocked.
        self.original = b'\x89PNG\r\n\x1a\nmock-control-flow-only'
        self.stamp = (1, 2, 3)
        self.snapshot = {'crop_rect': (0., 0., 1., 1.), 'crop_rotation': 0.}
        self.metadata = dict(width=3, height=2, bits=8, orientation=1,
                             working_orientation=1, icc=b'mock-profile')
        self.retained_roots = ('mock-render-root',)
        self.persistent_roots = ('mock-live-host-root',)
        self.context = {'analyses': {}, **{key: {} for key in people.FIELDS}}
        self.held = 2_345_678
        self.persistent = 1_234_567
        self.eligible = True
        self.decode_shape = (2, 3, 3)
        self.decode_dtype = 'uint8'
        self.events = []
        self.references = {}
        self.plans = []
        self.source_context = None
        self.source_was_live = False
        self.render_error = None
        self.plan_error = None
        self.skipped = []

    def classify(self, snapshot, *, geometry_version=0, finishing_version=0):
        if geometry_version != 0 or finishing_version != 0:
            raise AssertionError('This legacy bridge fixture does not model bounded geometry')
        self.events.append('classify')
        return SimpleNamespace(eligible=self.eligible)

    def retained(self, roots):
        self.events.append('census')
        # The bridge augments the caller's live roots with raw engine banks.
        persistent = (type(roots) is tuple and len(roots) == 3
                      and roots[0] is self.persistent_roots
                      and roots[1] is self.context['analyses'])
        return self.persistent if persistent else self.held

    def inspect(self, original, **kwargs):
        self.events.append('inspect')
        return self.metadata

    def plan(self, metadata, snapshot, **kwargs):
        self.events.append('plan-spec' if 'spec' in kwargs else 'plan-decode')
        # Record scalar budget facts only, never the spec/array arguments.
        self.plans.append((kwargs['retained_bytes'], kwargs['persistent_retained_bytes']))
        if self.plan_error is not None:
            raise self.plan_error
        return SimpleNamespace()

    def decode(self, path, original, **kwargs):
        import numpy as np
        self.events.append('decode')
        self.decode_options = (path, original, kwargs['max_pixels'], kwargs['device'])
        value = np.zeros(self.decode_shape, dtype=self.decode_dtype)
        self.references['decode'] = weakref.ref(value)
        return value

    def prepare_snapshot(self, path, snapshot, for_document):
        self.events.append('prepare-snapshot')
        return snapshot, for_document

    def verify_inputs(self, snapshot, path, stamp, shape):
        self.events.append('verify-inputs')
        self.verified_inputs = (path, stamp, shape)

    def build(self, snapshot, height, width, *, for_document):
        self.events.append('build-spec')
        self.builder_extent = (height, width, for_document)
        value = _SpecSentinel()
        self.references['spec'] = weakref.ref(value)
        return value, self.skipped

    def validate(self, spec, snapshot, **kwargs):
        self.events.append('validate-spec')

    def render(self, source, spec, **kwargs):
        import numpy as np
        self.events.append('render')
        self.source_was_live = (self.references['decode']() is source
                                and self.references['spec']() is spec)
        self.source_context = dict(spec._creative_capture_original_source)
        self.render_options = (kwargs['geometry'], kwargs['provenance'])
        kwargs['progress']('mock progress')
        if self.render_error is not None:
            raise self.render_error
        value = np.full((2, 3, 3), 0.5, dtype=np.float32)
        self.references['rgb'] = weakref.ref(value)
        return value, {'mock_only': True}

    def run(self, **kwargs):
        engine = SimpleNamespace(_prepare_export_snapshot=self.prepare_snapshot)
        return bridge.prepare(engine, {'path': self.path}, self.snapshot,
            retained_roots=self.retained_roots, persistent_roots=self.persistent_roots,
            source_stamp=self.stamp, document_id='mock-document',
            max_bytes=512_000_000, **kwargs)


@contextmanager
def _mock_flow():
    """Use actual bridge functions, explicitly mocked heavyweight collaborators."""
    from lumaretouch_engine import export, export_recipe
    flow = _MockFlow()
    with ExitStack() as stack:
        stack.enter_context(patch('builtins.open', mock_open(read_data=flow.original)))
        stack.enter_context(patch.object(bridge.Path, 'stat',
            return_value=SimpleNamespace(st_size=len(flow.original))))
        stack.enter_context(patch.object(admission, 'classify_snapshot', new=flow.classify))
        stack.enter_context(patch.object(admission, 'retained_bytes', new=flow.retained))
        stack.enter_context(patch.object(admission, 'plan_capture', new=flow.plan))
        stack.enter_context(patch.object(admission, 'validate_spec', new=flow.validate))
        stack.enter_context(patch.object(people, '_context', new=lambda engine, row: flow.context))
        stack.enter_context(patch.object(importer, 'inspect_encoded_source', new=flow.inspect))
        stack.enter_context(patch.object(base, '_working_source', new=flow.decode))
        stack.enter_context(patch.object(masks, 'file_stamp', new=lambda path: flow.stamp))
        stack.enter_context(patch.object(masks, 'source_digest',
            new=lambda path: hashlib.sha256(flow.original).hexdigest()))
        stack.enter_context(patch.object(bridge, '_verify_inputs', new=flow.verify_inputs))
        stack.enter_context(patch.object(export_recipe, 'build_export_spec', new=flow.build))
        stack.enter_context(patch.object(export, 'export_float', new=flow.render))
        yield flow


def _pending(*, persistent=12345, max_bytes=64 * 1024 * 1024):
    import numpy as np
    value = np.full((2, 3, 3), 0.5, dtype=np.float32)
    return bridge.PendingEditedRGB(value, b'mock-original', b'mock-profile', max_bytes, persistent)


def _mock_canonical_sink():
    """Already-canonical storage fixture, NOT the result of a mock transfer."""
    return SimpleNamespace(width=3, height=2,
        sink=bytearray(struct.pack('<4f', 0.125, -0.25, 2.0, 1.0) * 6))


class PrepareFlowContracts(unittest.TestCase):
    def test_unsupported_family_returns_before_read_census_decode_or_render(self):
        with _mock_flow() as flow, patch('builtins.open') as opened:
            flow.eligible = False
            self.assertIsNone(flow.run())
            self.assertEqual(flow.events, ['classify'])
            opened.assert_not_called()

    def test_non_jpeg_png_dispatches_before_metadata_decode_or_render(self):
        with _mock_flow() as flow, patch('builtins.open', mock_open(read_data=b'II*\0mock-TIFF')):
            self.assertIsNone(flow.run())
            self.assertNotIn('inspect', flow.events)
            self.assertNotIn('decode', flow.events)
            self.assertNotIn('render', flow.events)

    def test_orientation_disagreement_returns_before_decode_without_reinterpretation(self):
        with _mock_flow() as flow:
            flow.metadata['orientation'] = 6
            self.assertIsNone(flow.run())
            self.assertIn('inspect', flow.events)
            self.assertNotIn('plan-decode', flow.events)
            self.assertNotIn('decode', flow.events)

    def test_plan_refusal_precedes_decode_and_never_becomes_legacy_retry(self):
        with _mock_flow() as flow:
            flow.plan_error = admission.CaptureBudgetExceeded('mock refusal')
            with self.assertRaisesRegex(admission.CaptureBudgetExceeded, 'mock refusal'):
                flow.run()
            self.assertNotIn('decode', flow.events)
            self.assertNotIn('render', flow.events)

    def test_mock_full_decode_and_export_keep_owners_until_render_then_release_them(self):
        with _mock_flow() as flow:
            pending = flow.run()
            gc.collect()
            self.assertTrue(flow.source_was_live)
            self.assertIsNone(flow.references['decode']())
            self.assertIsNone(flow.references['spec']())
            self.assertIs(flow.references['rgb'](), pending.rgb)
            self.assertEqual(flow.builder_extent, (2, 3, True))
            self.assertEqual(flow.decode_options, (flow.path, flow.original, 6, 'cpu'))
            self.assertEqual(flow.verified_inputs, (flow.path, flow.stamp, (2, 3)))
            self.assertEqual(flow.render_options, (((0., 0., 1., 1.), 0.), False))
            self.assertEqual(flow.source_context, {
                'path': flow.path, 'file_stamp': list(flow.stamp),
                'asset_sha256': hashlib.sha256(flow.original).hexdigest(),
                'document_id': 'mock-document'})
            self.assertEqual(pending.original, flow.original)
            self.assertEqual(pending.icc, flow.metadata['icc'])
            self.assertEqual(pending.persistent_retained_bytes, flow.persistent)
            self.assertEqual(flow.plans, [(flow.held, flow.persistent)] * 2)
            self.assertLess(flow.events.index('plan-decode'), flow.events.index('decode'))
            self.assertLess(flow.events.index('validate-spec'), flow.events.index('plan-spec'))
            self.assertLess(flow.events.index('plan-spec'), flow.events.index('render'))

    def test_wrong_decoded_extent_or_sample_precision_aborts_before_render(self):
        for shape, dtype in (((1, 3, 3), 'uint8'), ((2, 3, 3), 'float32')):
            with self.subTest(shape=shape, dtype=dtype), _mock_flow() as flow:
                flow.decode_shape, flow.decode_dtype = shape, dtype
                with self.assertRaisesRegex(ValueError, 'decode'):
                    flow.run()
                self.assertNotIn('render', flow.events)

    def test_real_owner_census_charges_raw_engine_banks_before_decode(self):
        import numpy as np
        real_census = admission.retained_bytes
        # This one uses the real bounded storage census, but family selection,
        # source metadata and engine context are still explicitly mocked. It
        # stops before decode/build_spec and is not a real host-state fixture.
        with _mock_flow() as flow, patch.object(admission, 'retained_bytes', new=real_census):
            flow.context['analyses']['plane'] = np.ones((3, 4), dtype=np.float32)
            flow.context['people_support_assets']['mock-bytes'] = b'a' * 64
            roots = (flow.persistent_roots, flow.context['analyses'],
                     tuple(flow.context[key] for key in people.FIELDS))
            expected = real_census(roots)
            self.assertGreaterEqual(expected, 3 * 4 * 4 + 64)
            flow.plan_error = RuntimeError('stop after real bounded census')
            with self.assertRaisesRegex(RuntimeError, 'stop after real bounded census'):
                flow.run()
            self.assertEqual(flow.plans[0][1], expected)
            self.assertGreaterEqual(flow.plans[0][0], expected)
            self.assertNotIn('decode', flow.events)

    def test_changed_provenance_fails_after_decode_before_prepare(self):
        with _mock_flow() as flow, patch.object(masks, 'source_digest', return_value='0' * 64):
            with self.assertRaisesRegex(ValueError, 'immutable provenance'):
                flow.run()
            self.assertIn('decode', flow.events)
            self.assertNotIn('prepare-snapshot', flow.events)

    def test_skipped_edits_are_not_dropped_even_with_mock_validator(self):
        with _mock_flow() as flow:
            flow.skipped = ['mock missing effect']
            with self.assertRaisesRegex(ValueError, 'cannot omit current edits'):
                flow.run()
            self.assertNotIn('render', flow.events)

    def test_render_failure_propagates_without_strategy_fallback(self):
        with _mock_flow() as flow:
            flow.render_error = RuntimeError('mock renderer failed')
            with self.assertRaisesRegex(RuntimeError, 'mock renderer failed'):
                flow.run()
            self.assertEqual(flow.events.count('decode'), 1)
            self.assertEqual(flow.events.count('render'), 1)

    def test_cancel_before_source_read_does_not_decode_or_intern(self):
        with _mock_flow() as flow, patch('builtins.open') as opened, patch.object(AssetStore, 'intern') as intern:
            with self.assertRaises(InterruptedError):
                flow.run(cancelled=lambda: True)
            opened.assert_not_called()
            self.assertNotIn('decode', flow.events)
            intern.assert_not_called()


class FinishFlowContracts(unittest.TestCase):
    def test_pending_is_consumed_before_admission_and_cannot_be_reused_after_refusal(self):
        pending = _pending()

        def refuse(rgb, **kwargs):
            self.assertIsNone(pending.rgb)
            raise sink.EditedCaptureBudgetExceeded('mock conversion budget refusal')

        with patch.object(sink, 'inspect_rgb_sink', new=refuse), patch.object(
                sink, 'capture_rgb_sink') as capture, patch.object(bridge, 'make_asset') as make:
            with self.assertRaises(sink.EditedCaptureBudgetExceeded):
                bridge.finish(pending)
            capture.assert_not_called()
            make.assert_not_called()
            with self.assertRaisesRegex(ValueError, 'consumed'):
                bridge.finish(pending)

    def test_immutable_freeze_budget_is_admitted_before_conversion(self):
        pending = _pending()
        available = (pending.max_bytes - len(pending.original) - len(pending.icc)
                     - bridge.FINAL_RESERVE - pending.persistent_retained_bytes)
        with patch.object(sink, 'inspect_rgb_sink', return_value=SimpleNamespace(
                freeze_bytes_after_source_release=available + 1)), patch.object(
                sink, 'capture_rgb_sink') as capture, patch.object(bridge, 'make_asset') as make:
            with self.assertRaisesRegex(ValueError, 'immutable freeze'):
                bridge.finish(pending)
            self.assertIsNone(pending.rgb)
            capture.assert_not_called()
            make.assert_not_called()

    def test_persistent_host_storage_and_provenance_reduce_both_conversion_budgets(self):
        pending = _pending(persistent=9_876_543)
        expected = (pending.max_bytes - len(pending.original) - len(pending.icc)
                    - bridge.FINAL_RESERVE - pending.persistent_retained_bytes)
        output = _mock_canonical_sink()
        with patch.object(sink, 'inspect_rgb_sink', return_value=SimpleNamespace(
                freeze_bytes_after_source_release=192)) as inspect, patch.object(
                sink, 'capture_rgb_sink', return_value=output) as capture:
            record = bridge.finish(pending)
            self.assertEqual(inspect.call_args.kwargs['max_bytes'], expected)
            self.assertEqual(capture.call_args.kwargs['max_bytes'], expected)
        self.assertEqual(record['original'], pending.original)
        self.assertEqual(record['icc'], pending.icc)

    def test_actual_finish_creates_independent_immutable_bytes_without_intern(self):
        pending = _pending()
        source_ref = weakref.ref(pending.rgb)
        output = _mock_canonical_sink()
        before = bytes(output.sink)
        events = []

        def inspect(rgb, **kwargs):
            self.assertIsNone(pending.rgb)
            events.append('inspect')
            return SimpleNamespace(freeze_bytes_after_source_release=192)

        def capture(rgb, **kwargs):
            self.assertIsNone(pending.rgb)
            self.assertIs(source_ref(), rgb)
            events.append('capture')
            return output

        with patch.object(sink, 'inspect_rgb_sink', new=inspect), patch.object(
                sink, 'capture_rgb_sink', new=capture), patch.object(AssetStore, 'intern') as intern:
            record = bridge.finish(pending)
            intern.assert_not_called()
        gc.collect()
        self.assertIsNone(source_ref())
        self.assertEqual(events, ['inspect', 'capture'])
        self.assertIs(type(record['content']), bytes)
        self.assertEqual(record['content'], before)
        output.sink[0] ^= 1
        self.assertEqual(record['content'], before)
        with self.assertRaisesRegex(ValueError, 'consumed'):
            bridge.finish(pending)

    def test_finish_never_claims_to_release_an_external_source_alias(self):
        pending = _pending()
        external_alias = pending.rgb
        source_before = external_alias.tobytes()
        with patch.object(sink, 'inspect_rgb_sink', return_value=SimpleNamespace(
                freeze_bytes_after_source_release=192)), patch.object(
                sink, 'capture_rgb_sink', return_value=_mock_canonical_sink()):
            bridge.finish(pending)
        self.assertIsNone(pending.rgb)
        self.assertEqual(external_alias.tobytes(), source_before)

    def test_precancel_consumes_pending_but_never_converts_makes_or_interns(self):
        pending = _pending()
        # Real sink inspection polls cancellation before native loading.
        with patch.object(sink, 'capture_rgb_sink') as capture, patch.object(
                bridge, 'make_asset') as make, patch.object(AssetStore, 'intern') as intern:
            with self.assertRaises(InterruptedError):
                bridge.finish(pending, cancelled=lambda: True)
            self.assertIsNone(pending.rgb)
            capture.assert_not_called()
            make.assert_not_called()
            intern.assert_not_called()

    def test_cancel_after_conversion_or_after_freeze_never_makes_or_interns(self):
        for cancel_poll in (1, 2):
            pending = _pending()
            calls = []

            def cancelled():
                calls.append(None)
                return len(calls) >= cancel_poll

            # Mock sink methods do not poll; these counts target finish's own
            # pre-freeze and pre-make_asset fences, not native cancellation.
            with patch.object(sink, 'inspect_rgb_sink', return_value=SimpleNamespace(
                    freeze_bytes_after_source_release=192)), patch.object(
                    sink, 'capture_rgb_sink', return_value=_mock_canonical_sink()), patch.object(
                    bridge, 'make_asset') as make, patch.object(AssetStore, 'intern') as intern:
                with self.assertRaises(InterruptedError):
                    bridge.finish(pending, cancelled=cancelled)
                self.assertEqual(len(calls), cancel_poll)
                self.assertIsNone(pending.rgb)
                make.assert_not_called()
                intern.assert_not_called()


class BaseIntegrationSourceContracts(unittest.TestCase):
    """Static source ordering only, not executed real-host integration."""
    def _capture_function(self):
        tree = ast.parse(Path(base.__file__).read_text())
        return next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'capture_current_asset')

    def _pending_branch(self):
        function = self._capture_function()
        return next(node for node in ast.walk(function)
                    if isinstance(node, ast.If) and ast.unparse(node.test) == 'pending is not None')

    def test_frozen_and_snapshot_are_deleted_before_finish(self):
        branch = self._pending_branch()
        deletes = [(index, {target.id for target in node.targets if isinstance(target, ast.Name)})
                   for index, node in enumerate(branch.body) if isinstance(node, ast.Delete)]
        finish = next(index for index, node in enumerate(branch.body)
                      if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                      and isinstance(node.value.func, ast.Name) and node.value.func.id == 'finish_edited')
        self.assertTrue(any(index < finish and {'frozen', 'snap'} <= names
                            for index, names in deletes))

    def test_persistent_state_is_explicitly_passed_and_default_strategy_stays_legacy(self):
        function = self._capture_function()
        defaults = dict(zip((arg.arg for arg in function.args.kwonlyargs), function.args.kw_defaults))
        self.assertEqual(ast.literal_eval(defaults['edited_capture_version']), 0)
        prepare = next(node for node in ast.walk(function)
                       if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                       and node.func.id == 'prepare_edited')
        keywords = {item.arg: ast.unparse(item.value) for item in prepare.keywords}
        self.assertEqual(keywords['retained_roots'], '(state, frozen, snap)')
        self.assertEqual(keywords['persistent_roots'], '(state,)')

    def test_cancellation_and_final_file_document_fences_precede_intern_and_return(self):
        branch = self._pending_branch()
        finish = next(index for index, node in enumerate(branch.body)
                      if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                      and ast.unparse(node.value.func) == 'finish_edited')
        poll = next(index for index, node in enumerate(branch.body)
                    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                    and ast.unparse(node.value.func) == 'poll')
        fence = next(index for index, node in enumerate(branch.body)
                     if isinstance(node, ast.If) and 'file_stamp(path)' in ast.unparse(node.test)
                     and '_document_versions().version(row)' in ast.unparse(node.test))
        condition = branch.body[fence].test
        self.assertIsInstance(condition, ast.BoolOp)
        self.assertIsInstance(condition.op, ast.Or)
        self.assertEqual(ast.unparse(condition),
            'LM.file_stamp(path) != before or engine._document_versions().version(row) != version')
        self.assertTrue(any(isinstance(node, ast.Raise) for node in branch.body[fence].body))
        intern = next(index for index, node in enumerate(branch.body)
                      if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                      and ast.unparse(node.value.func) == 'assets.intern')
        returned = next(index for index, node in enumerate(branch.body) if isinstance(node, ast.Return))
        self.assertLess(finish, poll)
        self.assertLess(poll, fence)
        self.assertLess(fence, intern)
        self.assertLess(intern, returned)

    def test_snapshot_preflight_happens_before_deepcopy(self):
        function = self._capture_function()
        preflight = next(node for node in ast.walk(function)
                         if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                         and node.func.id == 'preflight_snapshot')
        copy = next(node for node in ast.walk(function)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == 'deepcopy')
        self.assertLess(preflight.lineno, copy.lineno)

    def test_neutral_and_existing_creative_sources_keep_their_separate_route(self):
        function = self._capture_function()
        branch = next(node for node in ast.walk(function)
                      if isinstance(node, ast.If)
                      and any(isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                              and child.func.id == 'prepare_edited'
                              for statement in node.body for child in ast.walk(statement)))
        self.assertEqual(ast.unparse(branch.test),
                         'edited_capture_version in (1, 2, 3) and record is None and (not neutral)')


if __name__ == '__main__':
    unittest.main()
