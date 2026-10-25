# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored full-source fit/projection specifications. All tests UNRUN."""
from pathlib import Path
from unittest import mock
import numpy as np
import pytest
from lumaretouch_engine import hair_unification_runtime as R
from lumaretouch_engine import hair_unification_native as N
from lumaretouch_engine import hair_unification_state as S
from lumaretouch_engine.people_effects import LocalEffect
from lumaretouch_engine.hair_unification_composition import apply_records_np

ROOT = Path(__file__).resolve().parents[2]


def test_neutral_does_not_touch_provider_or_native():
    def unavailable(**_): raise AssertionError('Neutral tried to decode source')
    assert R.prepare_bank({}, 'unused', None, {'entries': []}, byte_budget=0,
                          measurement_source=unavailable) == ((), {})


def test_active_proxy_without_authenticated_provider_is_not_measurement():
    entry = {'resolved': {'irrelevant': 'mocked'}}
    with mock.patch.object(R.R, 'materialize', return_value={'version': 1, 'amount': .5}):
        with pytest.raises(R.HairUnificationRefused, match='显示代理'):
            R.prepare_bank({}, 'a'*64, np.full((8, 8, 3), .4, np.float32),
                           {'entries': [entry]}, byte_budget=1024**3)


def test_explicit_projection_retains_full_reference_counts_and_dimensions():
    source = np.full((8, 8, 3), .4, dtype=np.float32)
    coverage = np.ones((8, 8), dtype=np.float32)
    reference = N.MeasuredReference(1, 16, 16, 128, 128, 128., 128., 128., 1., 0., (0., 0., 0.))
    params = R.Parameters(.5, reference, (8, 8))
    record = LocalEffect({'face_instance_id': 'one'}, S.STAGE, (0, 0, 8, 8), weights=coverage, amounts=params)
    seen = []
    def compose(current, weights, actual, recipe, *, application_shape, origin, cancelled):
        seen.append((actual, application_shape, origin))
        return current.copy()
    with mock.patch.object(N, 'compose', side_effect=compose):
        result, _ = apply_records_np(source, [record])
    assert np.array_equal(result.view(np.uint32), source.view(np.uint32))
    assert seen == [(reference, (8, 8), (0, 0))]
    assert reference.source_width == 16 and reference.selected_pixels == 128
    wrong = LocalEffect(record.face_ref, S.STAGE, record.window, weights=coverage,
                        amounts=R.Parameters(.5, reference, (7, 8)))
    with pytest.raises(ValueError, match='application grid'):
        apply_records_np(source, [wrong])


def test_preview_and_original_export_have_lazy_native_precision_provider():
    project = (ROOT/'engine/src/lumaretouch_engine/hair_unification_project.py').read_text()
    assert 'capture(engine, expected_source=expected' in project
    assert 'capture_original(path, expected_source=expected, expected_stamp=stamp' in project
    host = (ROOT/'engine/src/lumaretouch_engine/people_engine_runtime.py').read_text()
    assert 'hair_unification_source=hair_unification_source' in host
    assert 'full_source_verified=creative is not None' in host
    native = (ROOT/'engine/src/lumaretouch_engine/hair_unification_native.py').read_text()
    assert 'lrt_hair_unification_compose_grid_v1' in native
    assert 'gw, gh, x, y, w, h' in native
