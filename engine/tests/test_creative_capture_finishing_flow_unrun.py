"""AUTHORED / UNRUN: private finishing request and exporter/bridge contracts.

Real recipe builders, request validators, Stage objects and orchestration are
used where specified. Pixel math is separately MOCKED for stage-order tests;
decoder/export-run mocks are control-flow sentinels, not genuine-image or native
parity evidence. Native numeric fixtures belong to the finishing-core tests.
No test, product import, native loading or runtime execution was performed while
authoring this file. AST inspection only checks source syntax/structure.
"""
import ast
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import mock_open, patch

from lumaretouch_engine import creative_capture_finishing_export as request_api
from lumaretouch_engine import creative_capture_finishing as finishing
from lumaretouch_engine import creative_edited_capture as bridge
from lumaretouch_engine import creative_edited_capture_admission as admission
from lumaretouch_engine import creative_document_base as base
from lumaretouch_engine import creative_document_import_bounded as importer
from lumaretouch_engine import export, export_recipe
from lumaretouch_engine import local_mask_state as masks
from lumaretouch_engine import virtual_copy_people as people
from lumaretouch_engine import colour_grading_state as CG, selective_colour_state as SC
from lumaretouch_engine.colour_grading_stage import ColourGradingStage
from lumaretouch_engine.selective_colour_stage import SelectiveColourStage
from lumaretouch_engine.creative_document_assets import AssetStore


def _snapshot(*, grading=True, selective=True):
    from lumaretouch_engine import white_balance_recipe as WB
    from lumaretouch_engine.ops import curves, levels
    cg, sc = CG.neutral(), SC.neutral()
    if grading:
        cg['shadows']['saturation'] = 7.
    if selective:
        sc['ranges']['reds']['cyan'] = 8.
    return dict(strength=0., params=dict(radius=12, eps=6e-4, texture_radius=4,
        broad_gain=0., mid_gain=0., detail_gain=1.), grade=(0., 0., 0., 1.),
        grade_scope='all', exposure=(.3, 0., 0., 0., 0., 0., 0.),
        exposure_ref_k=None, wb_options=WB.default_options(), hsl=(0.,) * 24,
        curves=curves.default_curves(), levels=levels.default_levels(), lut=None,
        lut_amount=0., light={'exposure': 0., 'radius': 24}, light_ops=[], repair_ops=[],
        deform={'amounts': {}, 'built': False},
        enhance={'amounts': {}, 'built': False, 'box': None}, channel=None, precompute=None,
        crop_rect=(0., 0., 1., 1.), crop_rotation=0., device='cpu', scale=1,
        upscale_backend='lanczos3', sharpen=0., _bg={}, colour_grading=cg, selective_colour=sc)


def _spec(*, grading=True, selective=True):
    snapshot = _snapshot(grading=grading, selective=selective)
    spec, skipped = export_recipe.build_export_spec(snapshot, 3, 4, for_document=True)
    if skipped:
        raise AssertionError('The real builder skipped fixture effects: ' + repr(skipped))
    spec._creative_capture_original_source = {
        'path': '/fixture/original.png', 'file_stamp': [1, 2, 3, 4, 5],
        'asset_sha256': 'a' * 64, 'document_id': 'fixture-document'}
    # Exactly the flags export_float establishes before exporter-entry validation.
    spec.float_output = True
    spec.provenance_output = False
    return spec


def _request(spec, **kwargs):
    return request_api.make_request(spec, max_bytes=kwargs.get('max_bytes', 32 * 1024 * 1024),
        width=kwargs.get('width', 4), height=kwargs.get('height', 3))


def _validate(request, spec, *, geometry=((0., 0., 1., 1.), 0.), device='cpu', tile=1024):
    return request_api.validate_request(request, spec, geometry=geometry, device=device, tile=tile)


class RealRequestContracts(unittest.TestCase):
    def test_real_builder_request_is_frozen_and_binds_source_recipes_extent_budget(self):
        spec = _spec()
        request = _request(spec)
        _validate(request, spec)
        self.assertEqual(json.loads(request.source_json), spec._creative_capture_original_source)
        self.assertEqual(json.loads(request.grading_json), spec.colour_grading)
        self.assertEqual(json.loads(request.selective_json), spec.selective_colour)
        self.assertEqual((request.width, request.height, request.max_bytes), (4, 3, 32 * 1024 * 1024))
        with self.assertRaises(FrozenInstanceError):
            request.max_bytes = 1

    def test_each_active_stage_combination_accepts_but_both_neutral_refuse_request(self):
        for cg, sc in ((True, False), (False, True), (True, True)):
            with self.subTest(grading=cg, selective=sc):
                spec = _spec(grading=cg, selective=sc)
                _validate(_request(spec), spec)
        spec = _spec(grading=False, selective=False)
        with self.assertRaisesRegex(ValueError, 'active admitted stage'):
            _validate(_request(spec), spec)

    def test_source_or_selected_recipe_mismatch_refuses_real_spec(self):
        for mutation, reason in (
                (lambda spec: spec._creative_capture_original_source.update(document_id='another-document'),
                 'another original source'),
                (lambda spec: spec.colour_grading['shadows'].update(saturation=8.), 'selected colour recipes'),
                (lambda spec: spec.selective_colour['ranges']['reds'].update(cyan=9.), 'selected colour recipes')):
            spec = _spec()
            request = _request(spec)
            mutation(spec)
            with self.assertRaisesRegex(ValueError, reason):
                _validate(request, spec)

    def test_missing_and_malformed_original_proof_cannot_authorize_request(self):
        spec = _spec()
        del spec._creative_capture_original_source
        with self.assertRaisesRegex(ValueError, 'original-source capture proof'):
            _request(spec)
        spec = _spec()
        spec._creative_capture_original_source['file_stamp'] = [1, 2, 3]
        with self.assertRaises(ValueError):
            _validate(_request(spec), spec)

    def test_invalid_exact_request_shape_refuses_before_spec_admission(self):
        spec = _spec()
        request = _request(spec)
        invalid = [None, dict(version=1), replace(request, version=True), replace(request, version=2),
                   replace(request, max_bytes=True), replace(request, max_bytes=0),
                   replace(request, max_bytes=request_api.MAX_WORK_BYTES + 1),
                   replace(request, width=True), replace(request, width=0),
                   replace(request, height=1.0), replace(request, width=100_000_001)]
        with patch.object(admission, 'validate_spec') as validate:
            for value in invalid:
                with self.assertRaises(ValueError):
                    _validate(value, spec)
            validate.assert_not_called()

    def test_cpu_tile_float_and_provenance_guards_reject_before_render(self):
        for key, value in (('float_output', False), ('provenance_output', True), ('creative_base', {})):
            spec = _spec()
            request = _request(spec)
            setattr(spec, key, value)
            with self.assertRaises(ValueError):
                _validate(request, spec)
        spec = _spec()
        for device, tile in (('cuda', 1024), ('cpu', 512)):
            with self.assertRaises(ValueError):
                _validate(_request(spec), spec, device=device, tile=tile)

    def test_active_finishing_rejects_missing_or_arbitrary_geometry_without_casting(self):
        spec = _spec()
        for geometry in (None, (), ((0., 0., 1., 1.), 23.75), ((0., 0., 1., 1.), 89.5)):
            with self.assertRaises(ValueError):
                _validate(_request(spec), spec, geometry=geometry)
        _validate(_request(spec, width=3, height=4), spec, geometry=((0., 0., 1., 1.), 90.))

    def test_actual_stage_recipe_and_final_extent_are_checked_before_worker(self):
        import numpy as np
        spec = _spec()
        request = _request(spec)
        grading, selective = ColourGradingStage(spec.colour_grading), SelectiveColourStage(spec.selective_colour)
        with patch.object(finishing, 'finish_colour_np_bounded') as worker:
            with self.assertRaisesRegex(ValueError, 'canvas differs'):
                request_api.apply_request(request, np.zeros((4, 3, 3), np.float32), grading, selective,
                                          cancelled=lambda: False)
            grading.recipe['shadows']['saturation'] = 9.
            with self.assertRaisesRegex(ValueError, 'Actual finishing stages differ'):
                request_api.apply_request(request, np.zeros((3, 4, 3), np.float32), grading, selective,
                                          cancelled=lambda: False)
            worker.assert_not_called()

    def test_apply_forwards_exact_stage_objects_and_subbudget_without_revalidating_spec(self):
        import numpy as np
        spec = _spec()
        request = _request(spec)
        grading, selective = ColourGradingStage(spec.colour_grading), SelectiveColourStage(spec.selective_colour)
        pixels = np.zeros((3, 4, 3), dtype=np.float32)
        cancelled = lambda: False
        sentinel = object()
        with patch.object(finishing, 'finish_colour_np_bounded', return_value=sentinel) as worker, patch.object(
                request_api, 'validate_request', side_effect=AssertionError('No final mutated-spec validation')):
            self.assertIs(request_api.apply_request(request, pixels, grading, selective, cancelled=cancelled), sentinel)
            args, kwargs = worker.call_args
            self.assertIs(args[0], pixels)
            self.assertIs(args[1], grading)
            self.assertIs(args[2], selective)
            self.assertEqual(kwargs['max_bytes'], request.max_bytes)
            self.assertIs(kwargs['cancelled'], cancelled)


class MockedStageOrderingContracts(unittest.TestCase):
    """Real Stage identities/orchestration, MOCKED pixel arithmetic only."""
    def test_all_grading_blocks_finish_before_any_selective_block(self):
        import numpy as np
        spec = _spec()
        grading, selective = ColourGradingStage(spec.colour_grading), SelectiveColourStage(spec.selective_colour)
        pixels = np.full((4, 5, 3), .25, dtype=np.float32)
        before = pixels.tobytes()
        calls = []

        def grading_copy(stage, block, *, encoding, cancelled):
            self.assertIs(stage, grading)
            self.assertTrue(block.flags.owndata)
            self.assertLessEqual(block.shape[0] * block.shape[1], 6)
            self.assertEqual(encoding, 'extended-srgb-d65')
            calls.append('CG')
            return block.copy()  # MOCK identity arithmetic, not real grading.

        def selective_copy(stage, block, *, encoding, cancelled):
            self.assertIs(stage, selective)
            self.assertTrue(block.flags.owndata)
            self.assertLessEqual(block.shape[0] * block.shape[1], 6)
            calls.append('SC')
            return block.copy()  # MOCK identity arithmetic, not real selective colour.

        with patch.object(ColourGradingStage, 'apply_np', new=grading_copy), patch.object(
                SelectiveColourStage, 'apply_np', new=selective_copy):
            output = finishing.finish_colour_np_bounded(pixels, grading, selective, block_pixels=6)
        self.assertEqual(calls, ['CG'] * 4 + ['SC'] * 4)
        self.assertIsNot(output, pixels)
        self.assertEqual(pixels.tobytes(), before)

    def test_neutral_stages_return_original_without_pixel_math_or_validation(self):
        import numpy as np
        pixels = np.array([[[float('nan'), float('inf'), 129.]]], dtype=np.float32)
        with patch.object(ColourGradingStage, 'apply_np') as cg, patch.object(SelectiveColourStage, 'apply_np') as sc:
            output = finishing.finish_colour_np_bounded(pixels,
                ColourGradingStage(CG.neutral()), SelectiveColourStage(SC.neutral()))
            self.assertIs(output, pixels)
            cg.assert_not_called()
            sc.assert_not_called()

    def test_full_image_invalid_tail_refuses_before_first_active_stage_call(self):
        import numpy as np
        spec = _spec()
        pixels = np.zeros((4, 5, 3), dtype=np.float32)
        pixels[-1, -1, -1] = float('nan')
        with patch.object(ColourGradingStage, 'apply_np') as cg, patch.object(SelectiveColourStage, 'apply_np') as sc:
            with self.assertRaises(finishing.ColourFinishingError):
                finishing.finish_colour_np_bounded(pixels, ColourGradingStage(spec.colour_grading),
                    SelectiveColourStage(spec.selective_colour), block_pixels=6)
            cg.assert_not_called()
            sc.assert_not_called()

    def test_selective_full_image_gate_sees_complete_mock_grading_output(self):
        import numpy as np
        spec = _spec()
        pixels = np.zeros((4, 5, 3), dtype=np.float32)
        calls = []

        def invalid_last_grading_block(stage, block, *, encoding, cancelled):
            calls.append('CG')
            result = block.copy()
            if len(calls) == 4:
                result[-1, -1, -1] = 129.  # Invalid sentinel, not a colour formula.
            return result

        with patch.object(ColourGradingStage, 'apply_np', new=invalid_last_grading_block), patch.object(
                SelectiveColourStage, 'apply_np') as sc:
            with self.assertRaises(finishing.ColourFinishingError):
                finishing.finish_colour_np_bounded(pixels, ColourGradingStage(spec.colour_grading),
                    SelectiveColourStage(spec.selective_colour), block_pixels=6)
            self.assertEqual(calls, ['CG'] * 4)
            sc.assert_not_called()


class ExportEntryContracts(unittest.TestCase):
    def test_export_float_sets_flags_and_forwards_private_request(self):
        import numpy as np
        spec = _spec()
        spec.float_output = False
        spec.provenance_output = True
        request = _request(spec)
        with patch.object(export, '_run_export', return_value=('mock pixels', {})) as run:
            export.export_float(np.zeros((3, 4, 3), np.uint16), spec,
                geometry=((0., 0., 1., 1.), 0.), provenance=False, capture_finishing=request)
            self.assertTrue(spec.float_output)
            self.assertFalse(spec.provenance_output)
            self.assertIs(run.call_args.kwargs['capture_finishing'], request)
            self.assertEqual(run.call_args.kwargs['bits'], 16)

    def test_generic_no_request_route_forwards_none_without_private_validation(self):
        import numpy as np
        spec = _spec()
        with patch.object(export, '_export_image_impl', return_value=('mock pixels', {})) as impl, patch.object(
                request_api, 'validate_request') as validate:
            export.export_float(np.zeros((3, 4, 3), np.uint8), spec,
                                geometry=((0., 0., 1., 1.), 0.), provenance=False)
            self.assertIsNone(impl.call_args.kwargs['capture_finishing'])
            validate.assert_not_called()

    def test_private_creative_source_refuses_before_any_resolver(self):
        import numpy as np
        spec = _spec()
        request = _request(spec)
        spec.creative_base = {}
        with patch.object(base, 'require_rebound_spec') as rebound, patch.object(base, 'export_source') as resolve, patch.object(
                export, '_export_image_impl') as impl:
            with self.assertRaisesRegex(export.ExportError, 'cannot resolve a creative source'):
                export._run_export(np.zeros((3, 4, 3), np.uint8), spec, device='cpu', tile=1024,
                    progress=None, bits=8, geometry=((0., 0., 1., 1.), 0.), capture_finishing=request)
            rebound.assert_not_called()
            resolve.assert_not_called()
            impl.assert_not_called()

    def test_invalid_request_fails_at_impl_entry_before_clock_source_access_or_prepasses(self):
        spec = _spec()
        invalid = replace(_request(spec), version=2)
        with patch.object(export.time, 'perf_counter') as clock, patch.object(type(spec), 'check') as check:
            with self.assertRaisesRegex(ValueError, 'Unknown private'):
                export._export_image_impl(object(), spec, device='cpu', tile=1024, progress=None,
                    bits=8, geometry=((0., 0., 1., 1.), 0.), capture_finishing=invalid)
            clock.assert_not_called()
            check.assert_not_called()


@contextmanager
def _bridge_flow(*, active=True, budget=777_123):
    """Real builder/request validation; MOCK source decode and export execution."""
    import numpy as np
    snapshot = _snapshot(grading=active, selective=active)
    original = b'\x89PNG\r\n\x1a\nnot-an-image-control-flow-fixture'
    stamp = (1, 2, 3, 4, 5)
    flow = SimpleNamespace(snapshot=snapshot, request=None, option_present=False, budget=budget,
        stamp=stamp, changed=False, cancelled=False, after_render_cancel=False, change_source=False,
        plans=[], rendered=0, source_context=None)
    context = {'analyses': {}, **{key: {} for key in people.FIELDS}}

    def plan(*args, **kwargs):
        flow.plans.append((kwargs.get('geometry_version', 0), kwargs.get('finishing_version', 0)))
        return SimpleNamespace(finishing_max_bytes=budget if 'spec' in kwargs else 123_456,
                               output_width=4, output_height=3, geometry_max_bytes=555_555)

    def run_export(source, spec, **kwargs):
        flow.rendered += 1
        flow.request = kwargs.get('capture_finishing')
        if flow.request is not None:
            request_api.validate_request(flow.request, spec, geometry=kwargs['geometry'],
                device=kwargs['device'], tile=kwargs['tile'])
        flow.source_context = deepcopy(spec._creative_capture_original_source)
        flow.changed = flow.change_source
        flow.cancelled = flow.after_render_cancel
        return np.full((3, 4, 3), .25, np.float32), {'mock_only': True}

    def observe_export(source, spec, **kwargs):
        flow.option_present = 'capture_finishing' in kwargs
        return original_export(source, spec, **kwargs)

    original_export = export.export_float
    engine = SimpleNamespace(_prepare_export_snapshot=lambda path, snap, document: (snap, document))
    flow.run = lambda version=1: bridge.prepare(engine, {'path': '/mock/original.png'}, snapshot,
        retained_roots=(), persistent_roots=(), source_stamp=stamp, document_id='mock-document',
        max_bytes=512_000_000, geometry_version=1, finishing_version=version,
        cancelled=lambda: flow.cancelled)
    with ExitStack() as stack:
        stack.enter_context(patch('builtins.open', mock_open(read_data=original)))
        stack.enter_context(patch.object(bridge.Path, 'stat', return_value=SimpleNamespace(st_size=len(original))))
        stack.enter_context(patch.object(people, '_context', return_value=context))
        stack.enter_context(patch.object(admission, 'retained_bytes', return_value=4096))
        stack.enter_context(patch.object(admission, 'plan_capture', new=plan))
        stack.enter_context(patch.object(importer, 'inspect_encoded_source', return_value=dict(
            width=4, height=3, bits=8, orientation=1, working_orientation=1, icc=b'mock-icc')))
        stack.enter_context(patch.object(base, '_working_source', side_effect=lambda *args, **kwargs: np.zeros((3, 4, 3), np.uint8)))
        stack.enter_context(patch.object(masks, 'file_stamp', side_effect=lambda path: (1, 2, 3, 4, 6) if flow.changed else stamp))
        stack.enter_context(patch.object(masks, 'source_digest', return_value=hashlib.sha256(original).hexdigest()))
        stack.enter_context(patch.object(bridge, '_verify_inputs'))
        stack.enter_context(patch.object(export, '_run_export', new=run_export))
        stack.enter_context(patch.object(export, 'export_float', new=observe_export))
        yield flow


class BridgeFinishingDispatchContracts(unittest.TestCase):
    def test_opted_in_active_recipe_uses_final_plan_subbudget_and_original_proof(self):
        with _bridge_flow() as flow:
            pending = flow.run()
            self.assertTrue(flow.option_present)
            self.assertEqual(flow.request.max_bytes, flow.budget)
            self.assertEqual((flow.request.width, flow.request.height), (4, 3))
            self.assertEqual(json.loads(flow.request.source_json), flow.source_context)
            self.assertEqual(flow.plans, [(1, 1), (1, 1)])
            self.assertEqual(pending.rgb.shape, (3, 4, 3))

    def test_neutral_final_plan_and_old_version_omit_request_entirely(self):
        for active, budget, version in ((False, 0, 1), (True, 777_123, 0)):
            with self.subTest(active=active, version=version), _bridge_flow(active=active, budget=budget) as flow, patch.object(
                    request_api, 'make_request', wraps=request_api.make_request) as make:
                flow.run(version)
                self.assertFalse(flow.option_present)
                self.assertIsNone(flow.request)
                make.assert_not_called()

    def test_final_original_fence_and_cancellation_still_prevent_publication(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel), _bridge_flow() as flow, patch.object(AssetStore, 'intern') as intern:
                flow.after_render_cancel = cancel
                flow.change_source = not cancel
                with self.assertRaises(InterruptedError if cancel else ValueError):
                    flow.run()
                self.assertEqual(flow.rendered, 1)
                intern.assert_not_called()


class FinishingSourceContracts(unittest.TestCase):
    def _function(self, module, name):
        tree = ast.parse(Path(module.__file__).read_text())
        return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)

    def test_private_validation_occurs_once_at_impl_entry_not_at_final_stage(self):
        function = self._function(export, '_export_image_impl')
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == 'validate_request']
        self.assertEqual(len(calls), 1)
        first = function.body[0]
        self.assertIsInstance(first, ast.If)
        self.assertEqual(ast.unparse(first.test), 'capture_finishing is not None')
        self.assertIn(calls[0], list(ast.walk(first)))
        apply = self._function(request_api, 'apply_request')
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                             and node.func.id == 'validate_request' for node in ast.walk(apply)))

    def test_generic_branch_retains_grading_then_selective_and_private_branch_uses_same_stages(self):
        function = self._function(export, '_export_image_impl')
        branch = next(node for node in ast.walk(function)
                      if isinstance(node, ast.If) and ast.unparse(node.test) == 'capture_finishing is None')
        calls = [node.value for node in branch.body if isinstance(node, ast.Assign)]
        self.assertEqual([ast.unparse(node.func) for node in calls],
                         ['colour_grading_stage.apply_np', 'selective_colour_stage.apply_np'])
        apply = next(node for statement in branch.orelse for node in ast.walk(statement)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                     and node.func.id == 'apply_request')
        self.assertEqual([ast.unparse(arg) for arg in apply.args],
                         ['capture_finishing', 'out', 'colour_grading_stage', 'selective_colour_stage'])

    def test_strategy_three_is_explicit_and_old_defaults_remain_zero(self):
        capture = self._function(base, 'capture_current_asset')
        defaults = dict(zip((arg.arg for arg in capture.args.kwonlyargs), capture.args.kw_defaults))
        self.assertEqual(ast.literal_eval(defaults['edited_capture_version']), 0)
        for name in ('preflight_snapshot', 'prepare_edited'):
            call = next(node for node in ast.walk(capture) if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name) and node.func.id == name)
            keywords = {item.arg: ast.unparse(item.value) for item in call.keywords}
            self.assertEqual(keywords['finishing_version'], '1 if edited_capture_version == 3 else 0')
            self.assertEqual(keywords['geometry_version'], '1 if edited_capture_version in (2, 3) else 0')
        for name in ('preflight_snapshot', 'prepare'):
            function = self._function(bridge, name)
            defaults = dict(zip((arg.arg for arg in function.args.kwonlyargs), function.args.kw_defaults))
            self.assertEqual(ast.literal_eval(defaults['finishing_version']), 0)

    def test_final_document_file_fence_and_neutral_route_remain_outside_finishing(self):
        capture = self._function(base, 'capture_current_asset')
        branch = next(node for node in ast.walk(capture)
                      if isinstance(node, ast.If) and ast.unparse(node.test) == 'pending is not None')
        fence = next(node for node in branch.body if isinstance(node, ast.If)
                     and '_document_versions().version(row)' in ast.unparse(node.test))
        self.assertIn('LM.file_stamp(path) != before', ast.unparse(fence.test))
        intern = next(node for node in ast.walk(branch) if isinstance(node, ast.Call)
                      and ast.unparse(node.func) == 'assets.intern')
        self.assertLess(fence.lineno, intern.lineno)
        route = next(node for node in ast.walk(capture) if isinstance(node, ast.If)
                     and any(isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                             and child.func.id == 'prepare_edited'
                             for statement in node.body for child in ast.walk(statement)))
        self.assertIn('not neutral', ast.unparse(route.test))
        self.assertIn('record is None', ast.unparse(route.test))


if __name__ == '__main__':
    unittest.main()
