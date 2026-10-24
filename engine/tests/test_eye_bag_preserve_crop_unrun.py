# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Native spatial display and source replay contracts only."""
import ast
import base64
import io
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from lumaretouch_engine import eye_bag_preserve_crop as C


def test_native_png_has_exact_crop_pixels_without_spatial_resampling():
    pixels = np.arange(18*20*3, dtype=np.float32).reshape(18, 20, 3) / np.float32(1080)
    image, length = C._png(pixels, [3, 4, 7, 5])
    raw = base64.b64decode(image['base64'])
    with Image.open(io.BytesIO(raw)) as shown:
        actual = np.asarray(shown)
    expected = np.floor(pixels[4:9, 3:10]*np.float32(255)+np.float32(.5)).astype(np.uint8)
    assert np.array_equal(actual, expected) and image['width'] == 7 and image['height'] == 5
    assert length == len(raw)


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -.01, 1.01])
def test_display_rejects_invalid_or_extended_values_instead_of_clipping(bad):
    pixels = np.zeros((4, 4, 3), np.float32); pixels[1, 1, 0] = bad
    with pytest.raises(ValueError): C._png(pixels, [0, 0, 4, 4])


def test_cancellation_before_encoding_and_replay_leaves_input_unchanged():
    pixels = np.zeros((4, 4, 3), np.float32); before = pixels.copy()
    with pytest.raises(InterruptedError): C._png(pixels, [0, 0, 4, 4], lambda: True)
    assert np.array_equal(pixels, before)


def test_neutral_repair_returns_same_full_float_source():
    pixels = np.zeros((4, 4, 3), np.float32)
    assert C.repaired_pixels(pixels, {'_repair_ops': [], '_redo_ops': []}, byte_budget=1) is pixels


def test_module_uses_shared_source_and_existing_full_replay_not_proxy_or_resize():
    source = Path(C.__file__).read_text()
    tree = ast.parse(source)
    assert not any(isinstance(n, ast.Attribute) and n.attr in ('resize', 'thumbnail', 'analysis_rgb') for n in ast.walk(tree))
    assert 'from .spill_removal_paint_source import source_pixels' in source
    assert 'from .repair_replay import replay_repair_t' in source
    assert 'resample_field(original.weight, (h, w), uint8=True)' in source
    assert 'validate_stacks(current)' in source
    assert 'no thumbnail substitution' in source


def test_documented_resource_admission_constants():
    assert C.MAX_EDGE == 2048 and C.MAX_CROP_PIXELS == 4_000_000
    assert C.MAX_SOURCE_PIXELS == 32_000_000
    assert C.MAX_PNG_BYTES == 4*1024**2 and C.MAX_TOTAL_PNG_BYTES == 8*1024**2


@pytest.mark.parametrize('analysis', [None, {}, {'skin': None}, {'skin': [0]}])
def test_missing_analysis_plane_is_explicit_refusal(analysis):
    with pytest.raises(ValueError, match='semantic support'):
        C.rectangles({}, analysis, {'width': 4, 'height': 4})


@pytest.mark.parametrize('rect', [[-1, 0, 1, 1], [0, -1, 1, 1], [3, 3, 2, 1], [0, 0, 1.5, 1], [0, 0, 0, 1]])
def test_source_pixel_edge_bounds_are_not_silently_clamped_by_array_slicing(rect):
    with pytest.raises(ValueError, match='source-pixel edge bounds'):
        C._png(np.zeros((4, 4, 3), np.float32), rect)


def test_source_last_pixel_is_retained_at_right_bottom_edge():
    pixels = np.zeros((4, 4, 3), np.float32); pixels[3, 3] = [1, .5, 0]
    image, _ = C._png(pixels, [3, 3, 1, 1])
    with Image.open(io.BytesIO(base64.b64decode(image['base64']))) as shown:
        assert np.asarray(shown).tolist() == [[[255, 128, 0]]]


def test_small_repair_24mp_not_categorically_rejected_by_full_frame_budget():
    from lumaretouch_engine import eye_bag_crop_memory as M
    from lumaretouch_engine.repair_record import RepairOp
    from lumaretouch_engine.ops.clone_stamp import VERSION
    recipe = {'version': VERSION, 'points': [[.5,.5]], 'offset': [.01,0],
        'axes': [[.001,0],[0,.001]], 'hardness': 1, 'opacity': 1}
    op = RepairOp(1, np.zeros((1,1),np.uint8), recipe, 'clone_stamp')
    needed = M.requirement((4000,6000), op)
    assert M.base_bytes((4000,6000)) < needed < 4_000_000_000
    assert M.admit((4000,6000),4_000_000_000,op) == needed


def test_oversized_solver_roi_is_still_refused_without_context_reduction():
    from lumaretouch_engine import eye_bag_crop_memory as M
    from lumaretouch_engine.repair_record import RepairOp
    op = RepairOp(1,np.full((2000,2000),255,np.uint8))
    with pytest.raises(ValueError, match='phase/ROI'):
        M.admit((2000,2000),512*1024**2,op)
