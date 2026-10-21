"""Repair and semantic smoothing must compose without a float-to-u8 round trip."""
import numpy as np
import pytest
from dataclasses import replace
from test_export import src, brush, H, W, MIN_TILE, MAX_TILE
from lumaretouch_engine.export import ExportSpec, export_image, apply_repair_full, _MaskCarrier
from lumaretouch_engine.vram import PreviewPipeline, RepairOp


def carrier(masks):
    c = _MaskCarrier(masks, np.zeros((478, 3), np.float32))
    c._carrier_names = ['skin']
    return c


def test_float_source_accepts_matching_masks_without_quantization():
    pytest.importorskip('torch')
    rgb = src(64, 80).astype(np.float32) / 255 + np.float32(0.000123)
    pipe = PreviewPipeline('cpu', 80, 64)
    pipe.load_rgb_f32(rgb)
    before = pipe.src_f32.clone()
    pipe.load_face(carrier(np.ones((1, 64, 80), np.float32)))
    assert pipe.src_u8 is None
    assert np.array_equal(pipe.src_f32.numpy(), before.numpy())
    with pytest.raises(ValueError, match='掩膜尺寸'):
        pipe.load_face(carrier(np.ones((1, 32, 80), np.float32)))


def test_masks_still_require_a_loaded_source():
    pytest.importorskip('torch')
    pipe = PreviewPipeline('cpu', 80, 64)
    with pytest.raises(RuntimeError):
        pipe.load_face(carrier(np.ones((1, 64, 80), np.float32)))


def test_repair_and_channel_export_match_live_chain_and_tiles():
    pytest.importorskip('torch')
    rgb = src()
    mask = np.zeros((1, H, W), np.float32)
    mask[:, 35:260, 40:390] = .7
    repair = [RepairOp(1, brush())]
    spec = ExportSpec(strength=.6, radius=8, texture_radius=3,
                      repair=repair, channel='skin', masks=mask,
                      mask_names=['skin'], landmarks=np.zeros((478,3), np.float32))
    one, _ = export_image(rgb, spec, device='cpu', tile=MAX_TILE)
    tiles, stats = export_image(rgb, spec, device='cpu', tile=MIN_TILE)
    assert stats['tiles'] > 1 and stats['applied'] == 1
    d = np.abs(one.astype(np.int16)-tiles.astype(np.int16)).max(axis=-1)
    assert d.max() <= 1 and (d>0).mean() <= .005
    pipe = PreviewPipeline('cpu', W, H)
    pipe.load_rgb_u8(rgb)
    pipe.set_repair_ops(repair)
    pipe.load_face(carrier(mask))
    pipe.render(.6, radius=8, texture_radius=3, channel='skin')
    assert np.array_equal(one, pipe.read_back()[...,:3])
    repaired, _ = apply_repair_full(rgb, repair, 'cpu')
    outside = mask[0] == 0
    expected = np.rint(np.clip(repaired,0,1)*255).astype(np.uint8)
    assert np.array_equal(one[outside], expected[outside])
    no_repair, _ = export_image(rgb, replace(spec,repair=[]),device='cpu',tile=MAX_TILE)
    no_skin, _ = export_image(rgb, replace(spec,strength=0),device='cpu',tile=MAX_TILE)
    assert np.any(one != no_repair) and np.any(one != no_skin)

from test_protocol import engine, _brush_rle, _collect_until, _read_frame
from lumaretouch_engine.shm import FrameShm
from PIL import Image


def test_protocol_exports_repair_with_active_skin_channel(engine, tmp_path):
    pytest.importorskip('torch')
    path = tmp_path / 'input.png'
    Image.fromarray(src()).save(path)
    engine.send(cmd='hello')
    engine.wait_for('ready')
    engine.send(cmd='set_device', device='cpu')
    engine.wait_for('device_set')
    engine.send(cmd='load_image', path=str(path), strength=0)
    meta = engine.wait_for('shm_ready', timeout=60)
    engine.wait_for('image_ready', timeout=60)
    engine.send(cmd='precompute', backend='synthetic')
    engine.wait_for('precompute_ready', timeout=30)
    engine.send(cmd='inpaint', action='add', rle=_brush_rle(H,W,H//2,W//2,8), feather=2)
    engine.wait_for('inpaint_done', timeout=30)
    engine.send(cmd='set_strength', value=.6, channel='skin', radius=8, texture_radius=3)
    engine.wait_for('params_set', timeout=30)
    # Read the latest published frame, not an earlier queued load-image event.
    peer = FrameShm(meta['name'])
    try:
        live = _read_frame(engine, peer, H, W)
        engine.send(cmd='export', out_dir=str(tmp_path/'out'), format='png', tile=256)
        done, _ = _collect_until(engine, 'export_done')
        assert done['failed'] == 0 and done['total'] == 1, done
        with Image.open(done['images'][0]['out']) as im:
            got = np.array(im.convert('RGB'))
        delta = np.abs(got.astype(np.int16)-live.astype(np.int16))
        assert delta.max() <= 1 and np.any(got != src())
    finally:
        peer.close()
