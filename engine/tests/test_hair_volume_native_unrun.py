# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN numerical fixtures; never builds/installs a native library."""
from pathlib import Path
import numpy as np
import pytest
from lumaretouch_engine import hair_volume_native as N
from lumaretouch_engine import hair_volume_state as S
from lumaretouch_engine.hair_volume_field import HairVolumeField, whole_source_shape
from test_hair_volume_contract_unrun import fixture


@pytest.fixture
def prepared():
    if not (Path(N.__file__).parent / 'bin/liblrt_hair_volume.so').is_file():
        pytest.skip('Explicit native packaging has not been authorized/performed')
    _, _, _, _, record = fixture()
    recipe = S.neutral(); recipe['crown']['amount'] = 1
    recipe['sides'].update(left=1., right=1.)
    return HairVolumeField(record, recipe, (1001, 1001))


def test_native_inverse_preserves_direction_and_fixed_regions(prepared):
    # Interior plateau query has a constant exact translation, not full-head scaling.
    points = np.array([[500.37, 180.13], [180.37, 500.13], [820.37, 500.13],
                       [500., 600.], [500., 350.], [300., 500.], [700., 500.], [500., 850.]])
    result = prepared.evaluate(points)
    np.testing.assert_allclose(result[:3], [[0., -10.], [-5., 0.], [5., 0.]], atol=1e-7)
    assert np.array_equal(result[3:], np.zeros((5, 2)))
    assert prepared.facts['head_size_uniform_scale'] is False
    assert prepared.facts['runtime_quality_accepted'] is False


def test_native_owned_arrays_are_immutable_and_borrowed_input_is_unmodified(prepared):
    points = np.array([[500.37, 180.13], [275.17, 300.23]], np.float64)
    before = points.copy(); result = N.evaluate(prepared.state, points)
    assert np.array_equal(points, before) and points.flags.writeable
    with pytest.raises(ValueError): result.setflags(write=True)
    with pytest.raises(ValueError): prepared.state.setflags(write=True)
    with pytest.raises(ValueError): prepared.render_scale.setflags(write=True)


def test_proxy_conjugates_both_scales_and_retains_off_grid_coordinates(prepared):
    proxy = HairVolumeField(prepared.record, prepared.recipe, (512, 512))
    source_points = np.array([[500.37, 180.13], [275.17, 300.23], [999.37, 999.13], [1000., 1000.]])
    scale = np.array([511/1000, 511/1000])
    np.testing.assert_allclose(proxy.evaluate(source_points*scale), prepared.evaluate(source_points)*scale,
                               atol=1e-7)
    with pytest.raises(ValueError): whole_source_shape(prepared.source, (512, 256))
    with pytest.raises(ValueError): proxy.evaluate(np.array([[511.01, 10.]]))


def test_native_forged_state_and_out_of_domain_are_not_clipped(prepared):
    bad = np.array(prepared.state); bad[0] = 99
    with pytest.raises(ValueError): N.evaluate(bad, [])
    with pytest.raises(ValueError): N.evaluate(prepared.state, [[-1e-5, 200.]])
    with pytest.raises(ValueError): N.evaluate(prepared.state, [[1000.00001, 200.]])
    assert N.evaluate(prepared.state, []).shape == (0, 2)
