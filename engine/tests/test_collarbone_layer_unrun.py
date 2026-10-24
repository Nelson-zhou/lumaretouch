# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN source-owned layer contract fixtures.

Synthetic source/ownership evidence and native boundary doubles are not actual
Rust, model, CPU/GPU, image-quality or product runtime acceptance.
"""
from types import SimpleNamespace, MappingProxyType
from unittest.mock import patch
import numpy as np
import pytest
from lumaretouch_engine import collarbone_layer as L, collarbone_native as N
from lumaretouch_engine import collarbone_state as STATE
from lumaretouch_engine import skin_colour_body_support as S
from test_collarbone_support_unrun import retained, fixture, FAMILY

BUDGET = 512*1024**2


def pixels():
    source = np.full((64, 64, 3), .4, np.float32)
    source.setflags(write=False)
    return source


def native_result(*, value=.01, origin=(24, 32), shape=(8, 16), admitted=128):
    field = np.full(shape, value, np.float32); field.setflags(write=False)
    return SimpleNamespace(field=field, origin=origin, source_shape=(64, 64),
                           report=MappingProxyType({'supported_pixels': admitted, 'status': 'measured-source-contrast'}))


def prepare(source=None, *, amount=.6, result=None, budget=BUDGET, cancelled=None):
    state, assets, ref, bank, analysis, _ = retained()
    source = pixels() if source is None else source
    result = native_result() if result is None else result
    with patch.object(S.M, 'raster', return_value=np.full(source.shape[:2], 255, np.uint8)), \
         patch.object(N, 'memory_estimate', return_value=1024), \
         patch.object(N, 'available', return_value=True), \
         patch.object(N, 'prepare', return_value=result) as native:
        layers = L.prepare(ref, analysis, source, {'version': 1, 'amount': amount},
            people_state=state, body_assets=assets, body_bank=bank, byte_budget=budget,
            cancelled=cancelled)
    return layers, native, (state, assets, ref, bank, analysis)


def test_neutral_does_not_need_source_support_native_or_memory():
    with patch.object(N, 'prepare') as native, patch.object(S, 'resolve') as support:
        assert L.prepare(None, None, None, STATE.neutral(), people_state=None,
            body_assets=None, body_bank=None, byte_budget=0) == []
    native.assert_not_called(); support.assert_not_called()


def test_roi_log_field_and_amount_are_separate_from_original_source_rgb():
    source = pixels(); layers, native, (_, assets, _, _, _) = prepare(source)
    assert len(layers) == 1
    layer = layers[0]
    assert layer.stage == 'collarbone' and layer.window == (32, 24, 8, 16)
    assert layer.delta is None and layer.chroma_shift is None
    assert layer.log_gain.shape == (8, 16, 1) and not layer.log_gain.flags.writeable
    assert layer.amounts == {'amount': .6}
    assert native.call_args.args[0] is source
    assert native.call_args.args[2] == next(iter(assets.values()))['row']['review']['clavicle']['curves']
    assert 'amount' not in native.call_args.kwargs and len(native.call_args.args) == 3
    assert layer.facts['source_dimensions'] == layer.facts['render_dimensions'] == [64, 64]
    assert layer.facts['runtime_quality_accepted'] is False
    assert type(layer.facts['native_report']) is dict


def test_amount_change_does_not_reclassify_or_reestimate_from_current_corrected_pixels():
    a, one, _ = prepare(amount=.2); b, two, _ = prepare(amount=.9)
    np.testing.assert_array_equal(a[0].log_gain, b[0].log_gain)
    assert one.call_args.args[2] == two.call_args.args[2]
    assert a[0].amounts != b[0].amounts


@pytest.mark.parametrize('fault', ['nan', 'hdr', 'negative', 'float64', 'rgb8'])
def test_non_sdr_or_wrong_type_never_becomes_a_convenience_clip_or_rgb8_source(fault):
    source = np.full((64, 64, 3), .4, np.float32)
    if fault == 'float64': source = source.astype(np.float64)
    elif fault == 'rgb8': source = np.full((64, 64, 3), 128, np.uint8)
    else: source[40, 30, 0] = {'nan': np.nan, 'hdr': 1.1, 'negative': -.1}[fault]
    with pytest.raises(ValueError): prepare(source)


@pytest.mark.parametrize('fault', ['mutable', 'nan', 'over-bound', 'wrong-shape',
                                  'wrong-source', 'negative-origin', 'out-of-frame', 'protected'])
def test_native_result_cannot_publish_unowned_or_unbounded_source_fields(fault):
    result = native_result()
    if fault == 'mutable': result.field.setflags(write=True)
    elif fault == 'nan': result = native_result(value=np.nan)
    elif fault == 'over-bound': result = native_result(value=N.MAX_LOG_GAIN+.01)
    elif fault == 'wrong-shape': result.field = np.zeros((8, 16, 1), np.float32)
    elif fault == 'wrong-source': result.source_shape = (32, 32)
    elif fault == 'negative-origin': result.origin = (-1, 32)
    elif fault == 'out-of-frame': result.origin = (60, 60)
    else: result.origin = (5, 5)
    with pytest.raises(ValueError): prepare(result=result)


@pytest.mark.parametrize('value,admitted', [(0, 0), (0, 128), (.01, 0)])
def test_flat_or_unobserved_anatomy_refuses_positive_intent_instead_of_fake_success(value, admitted):
    result = native_result(value=value, admitted=admitted)
    with pytest.raises(ValueError, match='No observed source clavicle contrast'):
        prepare(result=result)


@pytest.mark.parametrize('admitted', [None, -1, True, 127, 129, '128'])
def test_missing_or_invalid_admission_report_is_not_observability(admitted):
    with pytest.raises(ValueError, match='diagnostics'):
        prepare(result=native_result(admitted=admitted))


def test_missing_operation_specific_support_never_falls_back_to_body_or_face():
    state, assets, ref, bank, analysis, _ = fixture()
    with patch.object(N, 'prepare') as native:
        with pytest.raises(ValueError, match='own body/anatomy review'):
            L.prepare(ref, analysis, pixels(), {'version': 1, 'amount': .4},
                people_state=state, body_assets=assets, body_bank=bank, byte_budget=BUDGET)
    native.assert_not_called()


def test_short_budget_refuses_before_raster_or_native_allocation():
    state, assets, ref, bank, analysis, _ = retained()
    with patch.object(S, 'raster') as raster, patch.object(N, 'prepare') as native:
        with pytest.raises(ValueError, match='memory budget'):
            L.prepare(ref, analysis, pixels(), {'version': 1, 'amount': .4},
                people_state=state, body_assets=assets, body_bank=bank, byte_budget=0)
    raster.assert_not_called(); native.assert_not_called()


def test_window_memory_refuses_before_raster_and_native_prepare():
    state, assets, ref, bank, analysis, _ = retained()
    with patch.object(S, 'raster') as raster, patch.object(N, 'prepare') as native, \
         patch.object(N, 'memory_estimate', return_value=BUDGET):
        with pytest.raises(ValueError, match='window and halo'):
            L.prepare(ref, analysis, pixels(), {'version': 1, 'amount': .4},
                people_state=state, body_assets=assets, body_bank=bank, byte_budget=BUDGET)
    raster.assert_not_called(); native.assert_not_called()


def test_aspect_mismatch_is_rejected_before_native_window_admission():
    state, assets, ref, bank, analysis, _ = retained()
    with patch.object(N, 'memory_estimate') as estimate:
        with pytest.raises(ValueError):
            L.prepare(ref, analysis, np.full((32, 64, 3), .4, np.float32),
                {'version': 1, 'amount': .4}, people_state=state, body_assets=assets,
                body_bank=bank, byte_budget=BUDGET)
    estimate.assert_not_called()


def test_cancellation_stops_before_any_support_or_native_work():
    with patch.object(N, 'prepare') as native, patch.object(S, 'resolve') as support:
        with pytest.raises(InterruptedError): L.prepare(None, None, None,
            {'version': 1, 'amount': .5}, people_state=None, body_assets=None,
            body_bank=None, byte_budget=0, cancelled=lambda: True)
    native.assert_not_called(); support.assert_not_called()
