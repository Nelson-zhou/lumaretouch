"""AUTHORED ONLY, UNRUN: fixed-grid and evidence/caching regressions.

No acceptance, real-photo calibration or performance claim. To be run only by
an explicitly authorized validation workflow, not this source-only change.
"""
import numpy as np
import pytest

from lumaretouch_engine import picks as PK


@pytest.mark.parametrize('shape', [(9, 9), (240, 40), (40, 240), (1, 99), (99, 1)])
def test_fixed_dhash_is_exactly_eight_rows_of_eight_comparisons(shape):
    h, w = shape
    rgb = np.broadcast_to(np.linspace(0, 255, w)[None, :, None], (h, w, 3)).astype(np.uint8)
    result = PK.dhash64(rgb)
    assert 0 <= result < 2 ** 64
    if w >= 9:
        assert result == 2 ** 64 - 1


def test_uniform_hash_and_exact_area_grid():
    assert PK.dhash64(np.zeros((17, 39, 3), dtype=np.uint8)) == 0
    grid = PK._area_grid(np.full((5, 31), 17.0), 8, 9)
    assert grid.shape == (8, 9)
    assert np.allclose(grid, 17.0)


def test_proxy_leader_never_certifies_best_or_keep():
    m = PK.Measures(path='/a', ratio=0.4, contrast=0.2, sharpness=0.1, eye_open=None)
    value = PK.suggest(m, group=['/a', '/b'], is_leader=True, rank_in_group=0, dup_bits=0)
    assert value['suggest'] == 'review'
    assert value['auto_deleted'] is False and value['auto_trashed'] is False
    assert any(r['kind'] == 'eyes_unknown' for r in value['reasons'])
    assert value['measures']['quality_scope'] == 'decoded-proxy-edge160-not-original-focus'
    assert any('非原片100%' in note for note in value['notes'])


def test_cache_fences_algorithm_scale_sensitivity_source_and_model(tmp_path):
    path = tmp_path / 'source.bin'
    path.write_bytes(b'original')
    sens = {name: 'standard' for name in ('duplicate', 'blur', 'exposure', 'eyes')}
    m = PK.Measures(path=str(path), source_stamp=PK.source_stamp(str(path)))
    pk = {'fingerprint': PK.fingerprint(), 'edge': 512, 'sensitivities': sens,
          'model_dir': None, 'measures': m.for_json()}
    assert PK.reusable(pk, str(path), 512, sens)
    assert not PK.reusable({**pk, 'fingerprint': 'v2'}, str(path), 512, sens)
    assert not PK.reusable(pk, str(path), 1024, sens)
    assert not PK.reusable(pk, str(path), 512, {**sens, 'blur': 'strong'})
    assert not PK.reusable(pk, str(path), 512, sens, '/another-model')
    path.write_bytes(b'replacement-longer')
    assert not PK.reusable(pk, str(path), 512, sens)


def test_cached_raw_precision_does_not_change_ranking():
    m = PK.Measures(path='/a', ratio=0.123456789, contrast=0.023456789,
                    sharpness=0.000001234, under=0.000000123, over=0.987654321)
    restored = PK.restore_measures(m.path, m.for_json())
    assert (restored.ratio, restored.contrast, restored.sharpness, restored.under, restored.over) == (
        m.ratio, m.contrast, m.sharpness, m.under, m.over)
