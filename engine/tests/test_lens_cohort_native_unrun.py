# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: transport/lifecycle fixtures, not numerical acceptance.

Nothing in this file was imported or executed during authoring. Mock success is
not evidence for FFT correctness, lens quality, runtime, memory RSS or 24MP
feasibility. Real-native tests require an explicit opt-in and packaged artifact.
"""
import ast
import ctypes as C
import gc
import os
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from lumaretouch_engine import lens_cohort_native as N


def settings(**changes):
    result = {'version': 1, 'aperture': 'circular_disk', 'max_radius_px': 0.0,
              'focus_near': 0.2, 'focus_far': 0.3, 'depth_falloff': 0.5,
              'occlusion_tolerance': 0.0, 'rotation_radians': 0.0}
    result.update(changes)
    return result


def pixels(width=7, height=3):
    return b''.join(struct.pack('<4f', (i % 31) / 32, (i % 17) / 32,
                                (i % 11) / 16, 1.0)
                    for i in range(width * height))


def limits(width, height, *, scratch=2 * 1024**2):
    return N.default_budgets(width, height, max_scratch_bytes=scratch,
                             reserved_repair_pairs=0)


def render(source, width=7, height=3, **changes):
    arguments = {'manual_depth': 32768 / 65535, 'manual_depth_acknowledged': True,
                 'budgets': limits(width, height), 'max_live_bytes': 128 * 1024**2}
    arguments.update(changes)
    return N.render(source, width, height, settings(), **arguments)


class MockNative:
    """Copies source tiles only. This fixture implements NO lens algorithm."""
    def __init__(self):
        self.calls = []
        self.create_code = self.finish_code = 0
        self.fail_tile = None
        self.change_plan = None
        self.source_address = self.refinement_address = None
        self.inside_native_tile = False
        self.destroy_count = 0

    def lrt_lens_cohort_create_v2(self, source, source_len, refinement, refinement_len,
                                 width, height, native_settings, budget,
                                 out_job, out_plan, cancel, context):
        self.calls.append('create')
        self.source_address = C.cast(source, C.c_void_p).value
        self.refinement_address = C.cast(refinement, C.c_void_p).value
        self.native_settings = native_settings
        if cancel(context):
            return 4
        if self.create_code:
            return self.create_code
        assert source_len == width * height * 4
        assert refinement_len in (0, width * height)
        # Validate the whole source before creating a mock handle. No snapshot.
        for i in range(width * height):
            if source[4 * i + 3] != 1 or not all(0 <= source[4 * i + j] <= 1 for j in range(3)):
                return 3
            if refinement_len and not -1 <= refinement[i] <= 1:
                return 3
        self.source, self.width, self.height = source, width, height
        plan = C.cast(out_plan, C.POINTER(N.NativePlan)).contents
        plan.abi_version, plan.struct_size, plan.math_identity = N.ABI, C.sizeof(N.NativePlan), N.MATH_IDENTITY
        plan.width, plan.height, plan.source_pixels = width, height, width * height
        plan.validation_pixels = width * height
        plan.classification_pixels = width * height * 3
        plan.tile_width, plan.tile_height = min(width, N.TILE_SIDE), min(height, N.TILE_SIDE)
        plan.tile_columns = (width + plan.tile_width - 1) // plan.tile_width
        plan.tile_count = plan.tile_columns * ((height + plan.tile_height - 1) // plan.tile_height)
        plan.borrowed_source_bytes = plan.sink_bytes = width * height * 16
        plan.borrowed_refinement_bytes = refinement_len * 4
        plan.output_tile_bytes = plan.tile_width * plan.tile_height * 16
        plan.owned_plan_bytes = 1024**2
        plan.required_scratch_bytes = 2 * 1024**2
        plan.repair_candidate_reservation = plan.direct_pair_upper_bound = budget.reserved_repair_pairs
        if self.change_plan:
            self.change_plan(plan)
        C.cast(out_job, C.POINTER(C.c_void_p))[0] = 123
        self.plan = plan
        return 0

    def lrt_lens_cohort_render_next_v2(self, job, index, output, output_len, cancel, context):
        self.calls.append(('tile', index))
        self.inside_native_tile = True
        try:
            if cancel(context):
                return 4
        finally:
            self.inside_native_tile = False
        if self.fail_tile == index:
            return 7
        gc.collect()  # A temporary source must still be alive after create.
        x = index % self.plan.tile_columns * self.plan.tile_width
        y = index // self.plan.tile_columns * self.plan.tile_height
        tw, th = min(self.plan.tile_width, self.width - x), min(self.plan.tile_height, self.height - y)
        assert output_len == tw * th * 4
        for row in range(th):
            for column in range(tw):
                for channel in range(4):
                    output[(row * tw + column) * 4 + channel] = self.source[
                        ((y + row) * self.width + x + column) * 4 + channel]
        return 0

    def lrt_lens_cohort_finish_v2(self, job):
        self.calls.append('finish')
        return self.finish_code

    def lrt_lens_cohort_destroy_v2(self, job):
        self.calls.append('destroy')
        self.destroy_count += 1
        self.source = None


@pytest.fixture
def native(monkeypatch):
    value = MockNative()
    monkeypatch.setattr(N, '_query_runtime', lambda: value)
    return value


def test_layout_matches_frozen_c_contract():
    assert C.sizeof(N.NativeSettings) == 44
    assert C.sizeof(N.NativeBudget) == 72
    assert C.sizeof(N.NativePlan) == 232
    assert N.NativeSettings.manual_depth.offset == 36
    assert N.NativeSettings.manual_depth_ack.offset == 40
    assert N.NativeBudget.max_fft_butterflies.offset == 8
    assert N.NativePlan.width.offset == 16
    assert N.NativePlan.output_tile_bytes.offset == 224


def test_scalar_settings_do_not_migrate_recipe_or_accept_unknown_fields():
    original = settings()
    assert N.normalize_settings(original) == original
    assert N.normalize_settings(original) is not original
    for invalid in (settings(version=2), settings(version=True), settings(extra=1),
                    settings(aperture='gaussian'), settings(max_radius_px=True),
                    settings(max_radius_px=float('nan')), settings(depth_falloff=0)):
        with pytest.raises(ValueError):
            N.normalize_settings(invalid)


def test_source_pointer_is_borrowed_exactly_not_copied(native):
    source = pixels()
    expected_address = N._borrow(source, len(source), 'fixture').pointer
    correction = struct.pack('<21f', *([0.0] * 21))
    result = render(source, refinement=correction)
    assert native.source_address == C.cast(expected_address, C.c_void_p).value
    assert native.refinement_address == C.cast(N._borrow(correction, len(correction), 'fixture').pointer, C.c_void_p).value
    assert result.rgba == source and result.rgba is not source
    assert type(result.rgba) is bytes
    assert result.memory['source_copy_bytes'] == 0
    assert result.memory['borrowed_refinement_bytes'] == len(correction)
    assert native.calls == ['create', ('tile', 0), 'finish', 'destroy']
    assert native.destroy_count == 1


def test_temporary_input_survives_native_callback_and_gc(native):
    result = render(pixels())
    assert result.rgba == pixels()
    assert native.destroy_count == 1


def test_tile_boundaries_cover_full_grid_and_tail_rows(native):
    width, height = 255, 255
    source = pixels(width, height)
    result = render(source, width, height)
    assert result.rgba == source
    assert native.calls == ['create', ('tile', 0), ('tile', 1), ('tile', 2), ('tile', 3), 'finish', 'destroy']
    assert result.memory['tile_payload_bytes_copied'] == len(source)
    assert result.memory['output_tile_bytes'] == 254 * 254 * 16


def test_manual_constant_is_actual_retained_depth_and_explicit(native):
    result = render(pixels())
    assert native.native_settings.manual_depth == C.c_float(32768 / 65535).value
    assert native.native_settings.manual_depth_ack == 1
    assert result.abi == 2 and result.math_identity == 0x00020001
    for changes in ({'manual_depth_acknowledged': False}, {'manual_depth_acknowledged': 1},
                    {'manual_depth': True}, {'manual_depth': float('nan')}, {'manual_depth': 1.01}):
        with pytest.raises(ValueError):
            render(pixels(), **changes)


def test_mutable_subclass_wrong_length_and_array_inputs_are_refused(native):
    class BytesSubclass(bytes):
        pass
    for source in (bytearray(pixels()), memoryview(pixels()), BytesSubclass(pixels()), pixels()[:-1], None):
        with pytest.raises(ValueError):
            render(source)
    for correction in (bytearray(84), memoryview(bytes(84)), bytes(83)):
        with pytest.raises(ValueError):
            render(pixels(), refinement=correction)
    assert native.calls == []


def test_wrong_labels_and_disabled_module_do_not_return_identity(native):
    for arguments in ({'encoding': 'encoded-srgb'}, {'premultiplied': False},
                      {'depth_convention': 'near-one-far-zero'}):
        with pytest.raises(ValueError):
            render(pixels(), **arguments)
    with pytest.raises(N.LensCohortUnavailable):
        render(pixels(), enabled=False)
    assert N.capability(enabled=False)['available'] is False
    assert native.calls == []


def test_native_rejects_last_pixel_before_any_tile(native):
    for last in ((0.1, 0.2, 0.3, 0.5), (1.01, 0.2, 0.3, 1.0),
                 (float('nan'), 0.2, 0.3, 1.0), (-0.1, 0.2, 0.3, 1.0)):
        with pytest.raises(N.LensCohortRejected, match='unsupported pixels'):
            render(pixels()[:-16] + struct.pack('<4f', *last))
    with pytest.raises(N.LensCohortRejected):
        render(pixels(), refinement=struct.pack('<21f', *([0.0] * 20 + [1.01])))
    assert native.calls == ['create'] * 5
    assert native.destroy_count == 0


def test_default_budgets_and_memory_helpers_are_pure_and_explicit():
    work = N.default_budgets(6000, 4000)
    assert work['max_sink_bytes'] == 384_000_000
    assert work['max_support_probes'] == 192_000_000
    assert work['reserved_repair_pairs'] <= work['max_direct_pairs'] <= 250_000_000
    a = N.memory_estimate(6000, 4000, native_scratch_bytes=123)
    b = N.memory_estimate(6000, 4000, with_refinement=True, native_scratch_bytes=123)
    assert a['source_copy_bytes'] == 0
    assert a['freeze_peak_bytes'] == 3 * 384_000_000 + N.PYTHON_OVERHEAD_ALLOWANCE_BYTES
    assert a['render_peak_bytes'] == 2 * 384_000_000 + 254 * 254 * 16 + 123 + N.PYTHON_OVERHEAD_ALLOWANCE_BYTES
    assert b['peak_live_bytes'] - a['peak_live_bytes'] == 96_000_000
    assert a['additional_peak_bytes'] + a['borrowed_input_bytes'] == a['peak_live_bytes']


def test_budget_errors_are_not_clamped_or_reduced(native):
    for changes in ({'max_fft_butterflies': N.MAX_FFT_BUTTERFLIES + 1},
                    {'max_direct_pairs': N.MAX_DIRECT_PAIRS + 1},
                    {'reserved_repair_pairs': N.MAX_DIRECT_PAIRS + 1},
                    {'max_sink_bytes': True}, {'max_scratch_bytes': -1}):
        budget = limits(7, 3)
        budget.update(changes)
        with pytest.raises(ValueError):
            render(pixels(), budgets=budget)
    with pytest.raises(ValueError):
        render(pixels(), budgets={})
    assert native.calls == []


def test_create_admission_and_final_bytes_peak_are_checked_before_native(native):
    with pytest.raises(MemoryError):
        render(pixels(), max_live_bytes=1)
    byte_count = len(pixels())
    with pytest.raises(MemoryError):
        render(pixels(), budgets=limits(7, 3, scratch=0),
               max_live_bytes=2 * byte_count + N.PYTHON_OVERHEAD_ALLOWANCE_BYTES)
    assert native.calls == []


def test_planned_render_peak_refusal_destroys_before_any_tile(native):
    width = height = 255
    estimate = N.memory_estimate(width, height, native_scratch_bytes=2 * 1024**2)
    admitted = max(estimate['create_peak_bytes'], estimate['freeze_peak_bytes'])
    assert admitted < estimate['render_peak_bytes']
    with pytest.raises(MemoryError, match='planned render'):
        render(pixels(width, height), width, height, max_live_bytes=admitted)
    assert native.calls == ['create', 'destroy']


@pytest.mark.parametrize('field,value', [('width', 99), ('math_identity', 1),
                                        ('tile_width', 1), ('sink_bytes', 1),
                                        ('required_scratch_bytes', 128 * 1024**2)])
def test_incompatible_plan_is_never_used(native, field, value):
    native.change_plan = lambda plan: setattr(plan, field, value)
    with pytest.raises(N.LensCohortUnavailable):
        render(pixels())
    assert native.calls == ['create', 'destroy']


def test_error_after_a_successful_tile_discards_full_candidate(native):
    native.fail_tile = 1
    with pytest.raises(N.LensCohortRejected):
        render(pixels(255, 1), 255, 1)
    assert native.calls == ['create', ('tile', 0), ('tile', 1), 'destroy']


def test_finish_is_mandatory_and_failure_destroys(native):
    native.finish_code = 8
    with pytest.raises(N.LensCohortRejected):
        render(pixels())
    assert native.calls[-2:] == ['finish', 'destroy']
    assert native.destroy_count == 1


def test_callback_exception_is_preserved_and_destroys(native):
    problem = RuntimeError('fixture cancellation source broke')
    def cancelled():
        if native.inside_native_tile:
            raise problem
        return False
    with pytest.raises(RuntimeError) as observed:
        render(pixels(), cancelled=cancelled)
    assert observed.value is problem
    assert native.calls[-1] == 'destroy' and 'finish' not in native.calls


def test_cancel_after_finish_before_publication_still_discards(native):
    with pytest.raises(InterruptedError):
        render(pixels(), cancelled=lambda: native.destroy_count > 0)
    assert native.calls[-2:] == ['finish', 'destroy']


def test_native_cancel_and_resource_status_have_specific_errors(native):
    for code, exception in ((4, InterruptedError), (5, MemoryError), (6, N.LensCohortRejected)):
        native.create_code = code
        with pytest.raises(exception):
            render(pixels())
    assert native.calls == ['create'] * 3 and native.destroy_count == 0


def test_missing_runtime_is_fail_closed_even_when_neutral(monkeypatch):
    def missing():
        raise N.LensCohortUnavailable('fixture missing packaged module')
    monkeypatch.setattr(N, '_query_runtime', missing)
    capability = N.capability()
    assert not capability['available'] and capability['kernels'] == ()
    assert capability['abi'] == 2 and capability['math_identity'] == 0x00020001
    with pytest.raises(N.LensCohortUnavailable):
        render(pixels())


@pytest.mark.parametrize('abi,math_id,missing', [(1, N.MATH_IDENTITY, False),
                                               (2, 1, False), (2, N.MATH_IDENTITY, True)])
def test_loader_refuses_wrong_abi_math_or_missing_symbols(monkeypatch, tmp_path,
                                                        abi, math_id, missing):
    class Function:
        def __init__(self, value):
            self.value = value
        def __call__(self, *arguments):
            return self.value
    package = tmp_path / 'package'
    artifact = package / 'bin' / 'liblrt_lens_cohort.so'
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b'fixture, not a native executable')
    monkeypatch.setattr(N, '__file__', str(package / 'lens_cohort_native.py'))
    library = SimpleNamespace(lrt_lens_cohort_abi=Function(abi),
                              lrt_lens_cohort_math_identity=Function(math_id))
    if not missing:
        for suffix in ('create', 'render_next', 'finish', 'destroy'):
            setattr(library, 'lrt_lens_cohort_' + suffix + '_v2', Function(0))
    loads = []
    def loader(path):
        loads.append(path)
        return library
    monkeypatch.setattr(N.C, 'CDLL', loader)
    N._query_runtime.cache_clear()
    try:
        with pytest.raises(N.LensCohortUnavailable):
            N._query_runtime()
        assert loads == [str(artifact)]
    finally:
        N._query_runtime.cache_clear()


def test_external_symlink_is_not_an_alternate_library_search(monkeypatch, tmp_path):
    package = tmp_path / 'package'
    artifact = package / 'bin' / 'liblrt_lens_cohort.so'
    artifact.parent.mkdir(parents=True)
    external = tmp_path / 'outside.so'
    external.write_bytes(b'fixture, not a native executable')
    artifact.symlink_to(external)
    monkeypatch.setattr(N, '__file__', str(package / 'lens_cohort_native.py'))
    def no_load(_path):
        raise AssertionError('No external artifact should be loaded')
    monkeypatch.setattr(N.C, 'CDLL', no_load)
    N._query_runtime.cache_clear()
    try:
        with pytest.raises(N.LensCohortUnavailable):
            N._query_runtime()
    finally:
        N._query_runtime.cache_clear()


@pytest.mark.parametrize('implementation,byteorder', [('pypy', 'little'), ('cpython', 'big')])
def test_unsupported_borrow_runtime_is_rejected(monkeypatch, implementation, byteorder):
    monkeypatch.setattr(N, 'sys', SimpleNamespace(
        implementation=SimpleNamespace(name=implementation), byteorder=byteorder))
    with pytest.raises(N.LensCohortUnavailable):
        N._host_support()


def test_result_metadata_cannot_be_mutated(native):
    result = render(pixels())
    with pytest.raises(TypeError):
        result.plan['width'] = 99
    with pytest.raises(TypeError):
        result.memory['peak_live_bytes'] = 0
    with pytest.raises(AttributeError):
        result.rgba = b''


def test_source_contract_has_no_numpy_full_input_copy_or_v1_call():
    path = Path(N.__file__)
    text = path.read_text()
    tree = ast.parse(text)
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert not any('numpy' in ast.unparse(node) or 'lens_aperture_native' in ast.unparse(node)
                   for node in imports)
    assert not any(isinstance(node, ast.Attribute) and node.attr == 'from_buffer_copy'
                   for node in ast.walk(tree))
    assert 'PyBytes_AsString' in text and 'C.c_void_p' in text
    assert 'lrt_lens_cohort_finish_v2' in text
    assert 'liblrt_lens_cohort.so' in text


REAL_NATIVE = os.environ.get('LRT_TEST_LENS_COHORT_NATIVE') == '1'


@pytest.mark.skipif(not REAL_NATIVE, reason='Explicit packaged ABI-2 artifact opt-in required; no build')
def test_real_native_neutral_full_source_bytes_and_finish():
    source = pixels(255, 3)
    result = render(source, 255, 3)
    assert result.rgba == source and result.rgba is not source
    assert result.memory['tiles_completed'] == 2
    assert result.plan['validation_pixels'] == 765


@pytest.mark.skipif(not REAL_NATIVE, reason='Explicit packaged ABI-2 artifact opt-in required; no build')
def test_real_native_last_pixel_hdr_alpha_nan_are_rejected_before_publication():
    for last in ((1.2, 0.2, 0.3, 1.0), (0.1, 0.2, 0.3, 0.5),
                 (float('nan'), 0.2, 0.3, 1.0)):
        with pytest.raises(N.LensCohortRejected):
            render(pixels()[:-16] + struct.pack('<4f', *last))
