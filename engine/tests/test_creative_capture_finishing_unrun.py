"""AUTHORED / UNRUN: private bounded finishing contracts.

Real-library comparisons use the unchanged production stages and require both
packaged libraries. Mocked stage tests establish only allocation/control-flow
contracts, not native arithmetic, full export, photographs, performance or RSS.
No product imports or fixture execution occurred while authoring this file.
"""
import ctypes as C
import gc
from pathlib import Path
import sys
import weakref
from unittest.mock import patch

import numpy as np
import pytest

from lumaretouch_engine import creative_capture_finishing as bounded
from lumaretouch_engine import colour_grading_state as CG, selective_colour_state as SC
from lumaretouch_engine import colour_grading_native as CG_NATIVE, selective_colour_native as SC_NATIVE
from lumaretouch_engine.colour_grading_stage import ColourGradingStage
from lumaretouch_engine.selective_colour_stage import SelectiveColourStage


def stages(grading=True, selective=True, method='relative'):
    cg, sc = CG.neutral(), SC.neutral()
    if grading:
        for index, key in enumerate(CG.RANGES):
            cg[key].update(hue=41.0 + 61 * index, saturation=7.25 + index,
                           luminance=-8.5 + index * 5)
        cg.update(blending=72.5, balance=-19.25)
    if selective:
        sc['method'] = method
        for index, key in enumerate(SC.RANGES):
            sc['ranges'][key].update(cyan=-8.25 + index, magenta=9.25 - index,
                                    yellow=4.5, black=-2.75)
    return ColourGradingStage(cg), SelectiveColourStage(sc)


def sample(height=7, width=11):
    values = np.array([-0.0, 0.0, -0.2, 0.001, 0.18, 0.5, 1.0, 1.25, 3.0], np.float32)
    return np.resize(values, (height, width, 3)).copy()


def assert_identical(actual, expected):
    assert actual.shape == expected.shape
    assert actual.dtype == expected.dtype
    assert actual.tobytes(order='C') == expected.tobytes(order='C')


def require_native():
    for module, name in ((CG_NATIVE, 'liblrt_colour_grading.so'),
                         (SC_NATIVE, 'liblrt_selective_colour.so')):
        if not (Path(module.__file__).parent / 'bin' / name).is_file():
            pytest.skip('Real numerical fixture requires the explicitly packaged ' + name)


@pytest.mark.parametrize('active', [(True, False), (False, True), (True, True)])
@pytest.mark.parametrize('method', ['relative', 'absolute'])
@pytest.mark.parametrize('cap', [1, 7, 65_536])
def test_real_native_stages_are_bitwise_equal(active, method, cap):
    require_native()
    source = sample()
    before = source.tobytes()
    cg, sc = stages(*active, method=method)
    expected = sc.apply_np(cg.apply_np(source))
    actual = bounded.finish_colour_np_bounded(source, cg, sc, block_pixels=cap)
    assert_identical(actual, expected)
    assert actual is not source
    assert actual.flags.c_contiguous
    assert source.tobytes() == before


@pytest.mark.parametrize('shape', [(1, 1), (1, 65_535), (1, 65_536),
                                  (1, 65_537), (65_537, 1), (3, 21_847)])
def test_real_native_block_edges_and_wide_rows(shape):
    require_native()
    source = sample(*shape)
    cg, sc = stages()
    assert_identical(bounded.finish_colour_np_bounded(source, cg, sc),
                     sc.apply_np(cg.apply_np(source)))


@pytest.mark.parametrize('layout', ['negative', 'transpose', 'fortran', 'channels', 'broadcast'])
def test_real_native_strided_sources(layout):
    require_native()
    owner = sample()
    source = {'negative': lambda: owner[::-1, ::-2],
              'transpose': lambda: owner.transpose(1, 0, 2),
              'fortran': lambda: np.asfortranarray(owner),
              'channels': lambda: owner[:, :, ::-1],
              'broadcast': lambda: np.broadcast_to(owner[:1, :1], owner.shape)}[layout]()
    source.flags.writeable = False
    cg, sc = stages()
    assert_identical(bounded.finish_colour_np_bounded(source, cg, sc, block_pixels=5),
                     sc.apply_np(cg.apply_np(source)))
    assert not source.flags.writeable


def test_real_tiny_active_controls_keep_existing_f32_conversion_and_signed_zero():
    require_native()
    cg, sc = stages(False, False)
    cg.recipe['global']['saturation'] = 1e-100
    sc.recipe['ranges']['reds']['cyan'] = 1e-100
    cg.active = sc.active = True
    source = sample()
    expected = sc.apply_np(cg.apply_np(source))
    assert_identical(bounded.finish_colour_np_bounded(source, cg, sc, block_pixels=3), expected)


def test_neutral_is_same_object_without_pixel_scan_or_native_even_nonfinite():
    source = sample()[::-1, ::-1]
    source[0, 0] = [np.nan, np.inf, -0.0]
    source.flags.writeable = False
    cg, sc = stages(False, False)
    with patch.object(np, 'isfinite', side_effect=AssertionError('Neutral scan')), \
         patch.object(np, 'abs', side_effect=AssertionError('Neutral scan')), \
         patch.object(CG_NATIVE, 'native', side_effect=AssertionError('Neutral native')), \
         patch.object(SC_NATIVE, 'native', side_effect=AssertionError('Neutral native')):
        plan = bounded.inspect_colour_finishing(source, cg, sc)
        assert bounded.finish_colour_np_bounded(source, cg, sc) is source
    assert plan.output_allocation_bytes == plan.block_workspace_bytes == 0
    assert not source.flags.writeable


def test_mock_calls_are_owning_bounded_and_stage_major_with_one_private_raster():
    source, cap = sample(5, 19), 7
    before = source.tobytes()
    cg, sc = stages()
    events, full_allocations = [], []
    real_empty = np.empty

    def allocate(shape, *args, **kwargs):
        value = real_empty(shape, *args, **kwargs)
        if tuple(shape) == source.shape:
            full_allocations.append(weakref.ref(value))
        return value

    def check(pixels, name, encoding):
        assert encoding == 'extended-srgb-d65'
        assert 0 < pixels.size // 3 <= cap
        assert pixels.dtype == np.float32
        assert pixels.base is None and pixels.flags.owndata
        assert pixels.flags.c_contiguous and pixels.flags.aligned
        assert not np.shares_memory(source, pixels)
        events.append(name)

    def grading(self, pixels, *, encoding, cancelled):
        check(pixels, 'cg', encoding)
        return pixels + np.float32(0.125)

    def selective(self, pixels, *, encoding, cancelled):
        check(pixels, 'sc', encoding)
        return pixels * np.float32(2)

    with patch.object(np, 'empty', side_effect=allocate), \
         patch.object(ColourGradingStage, 'apply_np', new=grading), \
         patch.object(SelectiveColourStage, 'apply_np', new=selective):
        actual = bounded.finish_colour_np_bounded(source, cg, sc, block_pixels=cap)
    assert events == sorted(events)
    assert events.count('cg') == events.count('sc') > 1
    assert len(full_allocations) == 1 and full_allocations[0]() is actual
    assert_identical(actual, (source + np.float32(0.125)) * np.float32(2))
    assert source.tobytes() == before


def test_mock_native_abi_observes_disjoint_buffers_and_unchanged_f32_parameters():
    """Real wrappers, identity-copy fake native: ABI coverage, NOT numeric parity."""
    source, cap = sample(), 7
    cg, sc = stages()
    events = []
    expected = {'cg': np.array(CG.scalars(cg.recipe), dtype=np.float32).tobytes(),
                'sc': np.array(SC.scalars(sc.recipe), dtype=np.float32).tobytes()}

    class FakeNative:
        def call(self, name, inp, out, count, recipe, mode):
            a = C.cast(inp, C.c_void_p).value
            b = C.cast(out, C.c_void_p).value
            c = C.cast(recipe, C.c_void_p).value
            assert mode == 1 and 0 < count <= cap
            size, params = count * 12, len(expected[name])
            assert a % 4 == b % 4 == c % 4 == 0
            assert a + size <= b or b + size <= a
            assert c + params <= b or b + size <= c
            assert C.string_at(recipe, params) == expected[name]
            C.memmove(out, inp, size)
            events.append(name)
            return 0

        def lrt_colour_grading_apply(self, *args):
            return self.call('cg', *args)

        def lrt_selective_colour_apply(self, *args):
            return self.call('sc', *args)

    fake = FakeNative()
    with patch.object(CG_NATIVE, 'native', return_value=fake), \
         patch.object(SC_NATIVE, 'native', return_value=fake):
        actual = bounded.finish_colour_np_bounded(source, cg, sc, block_pixels=cap)
    assert_identical(actual, source)
    assert events == sorted(events)
    assert events.count('cg') == events.count('sc') > 1


@pytest.mark.parametrize('value', [np.nan, np.inf, -np.inf, 128.001, -128.001])
def test_late_invalid_source_rejects_before_any_stage_call_or_full_output(value):
    source = sample()
    source[-1, -1, -1] = value
    cg, sc = stages()
    with patch.object(np, 'empty', side_effect=AssertionError('Premature allocation')), \
         patch.object(ColourGradingStage, 'apply_np', side_effect=AssertionError('Premature CG')), \
         patch.object(SelectiveColourStage, 'apply_np', side_effect=AssertionError('Premature SC')):
        with pytest.raises(bounded.ColourFinishingError, match='unsupported values'):
            bounded.finish_colour_np_bounded(source, cg, sc, block_pixels=5)


def test_all_cg_completes_then_invalid_intermediate_refuses_before_any_sc():
    source = sample()
    cg, sc = stages()
    calls = []

    def grading(self, pixels, **kwargs):
        calls.append(pixels.size // 3)
        return np.full_like(pixels, 129.0)

    with patch.object(ColourGradingStage, 'apply_np', new=grading), \
         patch.object(SelectiveColourStage, 'apply_np', side_effect=AssertionError('SC must not start')):
        with pytest.raises(bounded.ColourFinishingError, match='unsupported values'):
            bounded.finish_colour_np_bounded(source, cg, sc, block_pixels=5)
    assert sum(calls) == source.shape[0] * source.shape[1]


def test_neutral_sc_does_not_add_an_output_headroom_check_or_clip():
    source = sample()
    cg, sc = stages(True, False)
    with patch.object(ColourGradingStage, 'apply_np',
                      new=lambda self, pixels, **kw: np.full_like(pixels, 129.0)):
        result = bounded.finish_colour_np_bounded(source, cg, sc, block_pixels=3)
    assert np.all(result == np.float32(129.0))


def test_all_numeric_validation_stays_bounded():
    source, cap = sample(19, 27), 5
    cg, sc = stages()
    real_finite, real_abs = np.isfinite, np.abs

    def finite(value, *args, **kwargs):
        if type(value) is np.ndarray:
            assert value.size <= cap * 3
        return real_finite(value, *args, **kwargs)

    def absolute(value, *args, **kwargs):
        if type(value) is np.ndarray:
            assert value.size <= cap * 3
        return real_abs(value, *args, **kwargs)

    with patch.object(np, 'isfinite', side_effect=finite), \
         patch.object(np, 'abs', side_effect=absolute), \
         patch.object(ColourGradingStage, 'apply_np', new=lambda self, p, **kw: p.copy()), \
         patch.object(SelectiveColourStage, 'apply_np', new=lambda self, p, **kw: p.copy()):
        actual = bounded.finish_colour_np_bounded(source, cg, sc, block_pixels=cap)
    assert_identical(actual, source)


def test_plan_accounts_for_large_backing_one_output_and_named_scratch():
    owner = sample(31, 47)
    source = owner[3:10, 9:20]
    cg, sc = stages()
    plan = bounded.inspect_colour_finishing(source, cg, sc, block_pixels=11)
    assert plan.version == bounded.FINISHING_VERSION
    assert plan.source_owner_id == id(owner)
    assert plan.source_storage_bytes == owner.nbytes
    assert plan.source_bytes == source.nbytes
    assert plan.output_allocation_bytes == source.size * 4
    assert plan.block_workspace_bytes == 64 * 11
    assert plan.peak_bytes == (owner.nbytes + source.nbytes + 64 * 11
                              + bounded.ARRAY_WORKSPACE_RESERVE + bounded.METADATA_RESERVE)
    assert not plan.runtime_verified


@pytest.mark.parametrize('kind', [bytes, bytearray])
def test_known_buffer_backing_charges_unused_owner_bytes(kind):
    storage = kind(4096)
    source = np.frombuffer(memoryview(storage)[32:512], dtype='=f4', count=18,
                           offset=12).reshape(2, 3, 3)
    plan = bounded.inspect_colour_finishing(source, *stages())
    assert plan.source_owner_id == id(storage)
    assert plan.source_storage_bytes == len(storage)


def test_broadcast_view_uses_actual_owner_size_not_logical_extent():
    owner = np.zeros((1, 1, 3), np.float32)
    source = np.broadcast_to(owner, (7, 11, 3))
    plan = bounded.inspect_colour_finishing(source, *stages())
    assert plan.source_storage_bytes == 12
    assert plan.output_allocation_bytes == 12 * 7 * 11


def test_budget_one_byte_less_rejects_before_scan_or_allocation():
    source, pair = sample(), stages()
    plan = bounded.inspect_colour_finishing(source, *pair, block_pixels=7)
    assert bounded.inspect_colour_finishing(source, *pair, block_pixels=7,
        max_bytes=plan.peak_bytes).peak_bytes == plan.peak_bytes
    with patch.object(np, 'isfinite', side_effect=AssertionError('Premature scan')), \
         patch.object(np, 'empty', side_effect=AssertionError('Premature allocation')):
        with pytest.raises(bounded.ColourFinishingBudgetExceeded):
            bounded.finish_colour_np_bounded(source, *pair, block_pixels=7,
                                             max_bytes=plan.peak_bytes - 1)


@pytest.mark.parametrize('dtype', [np.uint8, np.uint16, np.float64,
                                  np.dtype('>f4' if sys.byteorder == 'little' else '<f4')])
def test_no_silent_integer_float64_or_endian_conversion(dtype):
    with pytest.raises(bounded.ColourFinishingError, match='float32'):
        bounded.inspect_colour_finishing(sample().astype(dtype), *stages())


def test_unknown_backing_subclasses_and_unsafe_stride_wrappers_reject():
    class Foreign(np.ndarray):
        pass
    source = sample()
    for invalid in (source.view(Foreign), np.lib.stride_tricks.as_strided(source,
                    shape=(1000, 1000, 3), strides=source.strides)):
        with pytest.raises(bounded.ColourFinishingError):
            bounded.inspect_colour_finishing(invalid, *stages())


@pytest.mark.parametrize('cap', [0, -1, True, 65_537, 1.0])
def test_invalid_block_bound_rejects(cap):
    with pytest.raises(bounded.ColourFinishingError):
        bounded.inspect_colour_finishing(sample(), *stages(), block_pixels=cap)


def test_stale_stage_active_or_instance_method_injection_rejects():
    cg, sc = stages()
    cg.active = False
    with pytest.raises(bounded.ColourFinishingError, match='disagree'):
        bounded.inspect_colour_finishing(sample(), cg, sc)
    cg, sc = stages()
    cg.apply_np = lambda pixels, **kw: pixels
    with pytest.raises(bounded.ColourFinishingError, match='exact existing'):
        bounded.inspect_colour_finishing(sample(), cg, sc)


@pytest.mark.parametrize('failure', ['cg', 'sc', 'sc-validation', 'cancel-after-cg', 'cancel-after-sc'])
def test_failures_keep_original_and_do_not_retain_full_private_output_in_traceback(failure):
    source, cap = sample(), 5
    before = source.tobytes()
    cg, sc = stages()
    full_refs, calls, cancelled = [], {'cg': 0, 'sc': 0}, [False]
    real_empty = np.empty

    def allocate(shape, *args, **kwargs):
        value = real_empty(shape, *args, **kwargs)
        if tuple(shape) == source.shape:
            full_refs.append(weakref.ref(value))
        return value

    def invoke(name, pixels):
        calls[name] += 1
        if failure == name and calls[name] == 2:
            raise RuntimeError('Mock stage failure')
        if failure == 'cancel-after-' + name:
            cancelled[0] = True
        return np.full_like(pixels, 129.0) if failure == 'sc-validation' and name == 'cg' else pixels.copy()

    with patch.object(np, 'empty', side_effect=allocate), \
         patch.object(ColourGradingStage, 'apply_np', new=lambda self, p, **kw: invoke('cg', p)), \
         patch.object(SelectiveColourStage, 'apply_np', new=lambda self, p, **kw: invoke('sc', p)):
        with pytest.raises((RuntimeError, bounded.ColourFinishingError, InterruptedError)) as retained_error:
            bounded.finish_colour_np_bounded(source, cg, sc, block_pixels=cap,
                                             cancelled=lambda: cancelled[0])
    # Intentionally keep the exception/traceback live during this check.
    assert retained_error.value is not None
    gc.collect()
    assert len(full_refs) == 1 and full_refs[0]() is None
    assert source.tobytes() == before


def test_cancel_before_admission_never_allocates_or_calls_native():
    source, pair = sample(), stages()
    with patch.object(np, 'empty', side_effect=AssertionError('Cancelled allocation')):
        with pytest.raises(InterruptedError):
            bounded.finish_colour_np_bounded(source, *pair, cancelled=lambda: True)


def test_recipe_drift_detected_without_mutating_source():
    source = sample()
    before = source.tobytes()
    cg, sc = stages()

    def mutate(self, pixels, **kwargs):
        sc.recipe['ranges']['reds']['cyan'] = 37.0
        return pixels.copy()

    with patch.object(ColourGradingStage, 'apply_np', new=mutate), \
         patch.object(SelectiveColourStage, 'apply_np', side_effect=AssertionError('Drifted SC')):
        with pytest.raises(bounded.ColourFinishingError, match='changed'):
            bounded.finish_colour_np_bounded(source, cg, sc, block_pixels=5)
    assert source.tobytes() == before
