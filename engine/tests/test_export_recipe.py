"""Shared recipe construction must retain every currently implemented layer."""
import numpy as np
import pytest
from test_export_per_image_recipe import _batch_snap, _mk_session
from lumaretouch_engine.export_recipe import build_export_spec
from lumaretouch_engine.vram import RepairOp, LightOp
from lumaretouch_engine.face import FacePrecompute
from lumaretouch_engine.ops.lut import bake
from lumaretouch_engine.ops.curves import default_curves


def test_existing_engine_delegates_to_one_pure_recipe_builder(monkeypatch):
    from lumaretouch_engine import export_recipe
    calls = []
    sentinel = (object(), ['reported'])
    def builder(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel
    monkeypatch.setattr(export_recipe, 'build_export_spec', builder)
    snap = _batch_snap()
    assert _mk_session([])._export_snapshot(snap, 20, 30, for_document=True) is sentinel
    assert calls == [((snap, 20, 30), {'for_document': True})]


def test_all_existing_active_layers_survive_shared_construction():
    pytest.importorskip("torch")  # real mask resampling uses the existing tensor runtime
    snap = _batch_snap()
    weight = np.full((8, 10), 255, np.uint8)
    points = np.zeros((478, 3), np.float32)
    face = FacePrecompute(points, {'skin': np.ones((8, 10), np.float32)}, 'fixture', 0., 0.)
    curve = default_curves(); curve['red'] = [[0., .05], [1., .95]]
    lut = bake(lambda x: x*.9, 17)
    snap.update(strength=.2, repair_ops=[RepairOp(7, weight)],
        light_ops=[LightOp(8, weight, -1)], light={'exposure': .2, 'radius': 3},
        deform={'amounts': {'slim_face': .2}, 'built': True},
        enhance={'amounts': {'sclera': .3}, 'built': True},
        precompute=face, channel='skin', grade_scope='brush', grade_mask=weight,
        lut=lut, lut_amount=.4, curves=curve, hsl=(.1,) + (0.,)*23,
        _bg={'active': True, 'matte': weight, 'bg': [.1, .2, .3]},
        scale=1, sharpen=0)
    spec, skipped = build_export_spec(snap, 16, 20, for_document=True)
    assert skipped == []
    assert spec.strength == .2 and spec.cube is lut and spec.lut_amount == .4
    assert spec.curves == curve and spec.exposure == snap['exposure'] and spec.hsl == snap['hsl']
    assert spec.repair[0].op_id == 7 and spec.repair[0].weight.shape == (16, 20)
    assert spec.repair[0].params == snap['repair_ops'][0].params
    assert spec.light[0].op_id == 8 and spec.light[0].sign == -1
    assert spec.light[0].weight.shape == (16, 20)
    assert (spec.light[0].weight == 255).all()
    assert spec.light_exposure == .2 and spec.light_radius == 3
    assert spec.deform_amounts == {'slim_face': .2} and spec.enhance == {'sclera': .3}
    np.testing.assert_array_equal(spec.landmarks, points)
    assert spec.channel == 'skin' and spec.mask_names == ['skin']
    assert spec.masks.shape == (1, 16, 20) and (spec.masks == 1).all()
    assert spec.grade_scope == 'brush' and spec.grade_mask.shape == (16, 20)
    assert spec.bg_matte.shape == (16, 20) and spec.bg_ref == (.1, .2, .3)
    assert spec.scale == 1 and spec.sharpen_amount == 0
    assert snap['repair_ops'][0].weight.shape == (8, 10)  # source not resized in place
