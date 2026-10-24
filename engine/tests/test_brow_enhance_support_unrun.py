"""AUTHORED / UNRUN source-observation contracts for original-brow enhancement.

All coordinates, pixels and model hashes below are deliberately SYNTHETIC test
observations, not genuine detector output, visual acceptance, clinical brow
segmentation or native correctness. The positive fixtures exercise actual
ownership, geometry and photometric admission; only ABI readiness/apply are
doubled. No imports, tests, builds, inference or downloads ran while authoring.
"""
from copy import deepcopy
import hashlib
from unittest.mock import patch
import numpy as np
import pytest
from lumaretouch_engine import brow_enhance_layer as L
from lumaretouch_engine import brow_enhance_state as S
from lumaretouch_engine import skin_colour_support as SKIN
from lumaretouch_engine.face_scope import FACE_OVAL, LIPS, _polygon_field
from lumaretouch_engine.ops.enhance import EYE_RING_LEFT, EYE_RING_RIGHT
from lumaretouch_engine.nose_shape_geometry import NOSE

BUDGET = 512 * 1024 * 1024


def synthetic_observation(size=256):
    """Return (FaceRef, analysis, RGB) with explicit synthetic observed dark brows.

    Source dimensions intentionally differ from the current observation grid.
    Test-only 'verified' metadata exercises ownership validators; it does not
    turn these authored landmarks into actual product inference evidence.
    """
    lm = np.full((478, 3), .5, np.float32)
    lm[:, 2] = 0
    for i, index in enumerate(FACE_OVAL):
        angle = -np.pi/2 + 2*np.pi*i/len(FACE_OVAL)
        lm[index, :2] = [.5+.42*np.cos(angle), .51+.44*np.sin(angle)]
    for ring, centre in ((EYE_RING_LEFT, .29), (EYE_RING_RIGHT, .71)):
        for i, index in enumerate(ring):
            angle = np.pi + 2*np.pi*i/len(ring)
            lm[index, :2] = [centre+.095*np.cos(angle), .425+.024*np.sin(angle)]
    for i, index in enumerate(LIPS):
        angle = np.pi + 2*np.pi*i/len(LIPS)
        lm[index, :2] = [.5+.105*np.cos(angle), .73+.032*np.sin(angle)]
    for i, index in enumerate(NOSE):
        angle = 2*np.pi*i/len(NOSE)
        lm[index, :2] = [.5+.055*np.cos(angle), .55+.095*np.sin(angle)]
    for side, xs in (('left', [.57, .625, .68, .735, .79]),
                     ('right', [.43, .375, .32, .265, .21])):
        upper, lower = L.CHAINS[side]
        ys = np.asarray([.325, .305, .30, .31, .335])
        lm[list(upper), :2] = np.stack((xs, ys), axis=1)
        lm[list(lower), :2] = np.stack((xs, ys+.028), axis=1)
    ref = {'asset_sha256': 'a'*64, 'face_instance_id': 'synthetic-brow-fixture', 'analysis_revision': 3}
    digest = hashlib.sha256(np.ascontiguousarray(lm, dtype='<f4').tobytes()).hexdigest()
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': 'c'*64, 'landmark_digest': digest, 'status': 'verified',
        'source_width': 1024, 'source_height': 1024, 'orientation': 'exif_normalized_once'}
    yy, xx = np.mgrid[:size, :size].astype(np.float32)
    xx += .5
    yy += .5
    base = np.array([.64, .49, .39], np.float32)
    source = np.broadcast_to(base, (size, size, 3)).copy()
    skin = np.full((size, size), .95, np.float32)
    excluded = np.zeros((size, size), np.float32)
    points = lm[:, :2] * [size-1, size-1]
    for upper, lower in L.CHAINS.values():
        polygon = np.concatenate((points[list(upper)], points[list(lower)][::-1]))
        inside, _ = _polygon_field(xx, yy, polygon)
        # Measurable textured dark source, not an all-black polygon or a mask
        # claiming visibility without actual RGB evidence. Skin is NOT required
        # on dark eyebrow hairs; only independently observed forehead needs it.
        gain = .38 + .07*np.sin(xx*.61) + .025*np.cos(yy*.83)
        source[inside] = base * gain[inside, None]
        skin[inside] = .02
    analysis = {'face_ref': deepcopy(ref), 'evidence': evidence, 'landmarks': lm,
        'excluded': excluded, 'skin': skin.copy(), 'face_skin': skin,
        'face_skin_observation': {'contract': SKIN.CONTRACT,
            'source_sha256': ref['asset_sha256'], 'semantic_model_sha256': 'c'*64,
            'producer_width': size, 'producer_height': size}}
    return ref, analysis, source


class MockNative:
    """Boundary-only common-RGB gain double, NOT a second brow implementation."""
    def __init__(self):
        self.calls = []

    def __call__(self, source, target, amount, *, reference_coverage, radius, cancelled):
        assert source.dtype == target.dtype == reference_coverage.dtype == np.float32
        assert not np.any((target > 0) & (reference_coverage > 0))
        assert np.count_nonzero(reference_coverage) >= 24
        assert 2 <= radius <= 128
        if cancelled():
            raise InterruptedError('Synthetic native cancellation boundary')
        self.calls.append((source.copy(), target.copy(), reference_coverage.copy(), amount, radius))
        linear = np.where(source <= .04045, source/12.92, ((source+.055)/1.055)**2.4)
        linear *= 1-np.float32(.12*amount)*target[..., None]
        encoded = np.where(linear <= .0031308, linear*12.92, 1.055*linear**(1/2.4)-.055)
        # Exact protected pixels avoid a transfer-roundtrip in this boundary
        # double, just as the actual kernel's source-copy invariant requires.
        return np.ascontiguousarray(np.where(target[..., None] > 0, encoded, source), dtype=np.float32)


def prepare_fixture(ref, analysis, source, recipe=None, *, native=None, **kwargs):
    native = MockNative() if native is None else native
    recipe = {'version': 1, 'linked': True, 'left': .6, 'right': .6} if recipe is None else recipe
    with patch.object(L.N, 'available', return_value=True), patch.object(L.N, 'apply', side_effect=native):
        records = L.prepare(ref, analysis, source, recipe, byte_budget=BUDGET, **kwargs)
    return records, native


def _geometry_mask(analysis, shape, side, kind='reference'):
    geometry = L._geometry(analysis['landmarks'], shape, [side])[0]
    yy, xx = np.mgrid[:shape[0], :shape[1]]
    return _polygon_field(xx+.5, yy+.5, geometry[kind])[0]


def _expanded(record, shape):
    result = np.zeros(shape, np.float32)
    y, x, h, w = record.window
    result[y:y+h, x:x+w] = record.delta
    return result


def test_neutral_does_not_require_owner_source_semantics_native_or_budget():
    with patch.object(L.N, 'available', side_effect=AssertionError('Neutral must not probe ABI')):
        assert L.prepare(None, None, None, S.neutral(), byte_budget=0) == []


def test_signed_bilateral_observations_merge_into_one_readonly_source_delta():
    ref, analysis, source = synthetic_observation()
    before = source.copy()
    recipe = {'version': 1, 'linked': False, 'left': -.7, 'right': .8}
    records, native = prepare_fixture(ref, analysis, source, recipe)
    assert len(records) == 1 and len(native.calls) == 2
    record = records[0]
    assert record.stage == 'brow_enhance' and record.face_ref == ref
    assert record.delta.dtype == np.float32 and not record.delta.flags.writeable
    assert record.weights is None and record.amounts is None
    assert not np.shares_memory(record.delta, source)
    delta = _expanded(record, source.shape)
    left = _geometry_mask(analysis, source.shape[:2], 'left', 'polygon')
    right = _geometry_mask(analysis, source.shape[:2], 'right', 'polygon')
    assert np.any(delta[left] > 0) and np.any(delta[right] < 0)
    assert np.all(delta[left] >= 0) and np.all(delta[right] <= 0)
    assert not np.any(delta[~(left | right)])
    assert all(len(f['thirds']) == 3 for f in record.facts['sides'].values())
    np.testing.assert_array_equal(source, before)


def test_semantic_producer_and_durable_dimensions_are_not_current_render_grid():
    ref, analysis, source = synthetic_observation()
    analysis['face_skin_observation']['producer_width'] = 128
    analysis['face_skin_observation']['producer_height'] = 128
    records, _ = prepare_fixture(ref, analysis, source)
    facts = records[0].facts
    assert facts['source_dimensions'] == [1024, 1024]
    assert facts['render_dimensions'] == [256, 256]
    assert facts['forehead_observation']['producer_width'] == 128


def test_inactive_side_needs_anatomical_protection_not_photometric_support():
    ref, analysis, source = synthetic_observation()
    # Unsupported RIGHT brow and forehead must not prevent explicitly unlocked
    # LEFT-only adjustment. Current retained right anatomy still protects it.
    right = _geometry_mask(analysis, source.shape[:2], 'right', 'polygon')
    forehead = _geometry_mask(analysis, source.shape[:2], 'right')
    source[right] = [.64, .49, .39]
    analysis['face_skin'][forehead] = 0
    analysis['excluded'][right | forehead] = 1
    recipe = {'version': 1, 'linked': False, 'left': .5, 'right': 0.}
    records, native = prepare_fixture(ref, analysis, source, recipe)
    assert len(native.calls) == 1
    assert records[0].facts['sides']['right']['reason'] == 'disabled'
    assert not np.any(_expanded(records[0], source.shape)[right | forehead])


def test_all_active_sides_are_observed_before_any_native_call():
    ref, analysis, source = synthetic_observation()
    analysis['face_skin'][_geometry_mask(analysis, source.shape[:2], 'right')] = 0
    native = MockNative()
    with pytest.raises(ValueError, match='forehead'):
        prepare_fixture(ref, analysis, source, native=native)
    assert native.calls == []


@pytest.mark.parametrize('change', ['owner', 'digest', 'backend', 'model', 'observation_source'])
def test_stale_or_synthetic_ownership_is_refused(change):
    ref, analysis, source = synthetic_observation()
    if change == 'owner':
        analysis['face_ref']['analysis_revision'] += 1
    elif change == 'digest':
        analysis['landmarks'][285, 0] += .002
    elif change == 'backend':
        analysis['evidence']['backend'] = 'template'
    elif change == 'model':
        analysis['evidence']['semantic_model_sha256'] = 'e'*64
    else:
        analysis['face_skin_observation']['source_sha256'] = 'd'*64
    with pytest.raises(ValueError):
        prepare_fixture(ref, analysis, source)


def test_merged_skin_never_substitutes_missing_face_skin_observation():
    ref, analysis, source = synthetic_observation()
    analysis.pop('face_skin')
    analysis.pop('face_skin_observation')
    with pytest.raises(ValueError, match='face-skin'):
        prepare_fixture(ref, analysis, source)


def test_wrong_render_grid_never_resizes_semantics_inside_the_layer():
    ref, analysis, source = synthetic_observation()
    analysis['face_skin'] = analysis['face_skin'][::2, ::2].copy()
    with pytest.raises(ValueError, match='render grid'):
        prepare_fixture(ref, analysis, source)


@pytest.mark.parametrize('value', [np.nan, np.inf, -0.01, 1.01])
def test_nonfinite_and_hdr_source_refused_without_clamping(value):
    ref, analysis, source = synthetic_observation()
    source[0, 0, 0] = value
    with pytest.raises(ValueError, match='nonfinite or HDR'):
        prepare_fixture(ref, analysis, source)


@pytest.mark.parametrize('failure', ['skin', 'occluder', 'shadow', 'colour', 'low_contrast'])
def test_actual_reference_and_brow_photometry_are_independently_required(failure):
    ref, analysis, source = synthetic_observation()
    forehead = _geometry_mask(analysis, source.shape[:2], 'left')
    brow = _geometry_mask(analysis, source.shape[:2], 'left', 'polygon')
    yy, xx = np.mgrid[:source.shape[0], :source.shape[1]]
    if failure == 'skin':
        analysis['face_skin'][forehead] = .2
    elif failure == 'occluder':
        analysis['excluded'][forehead] = 1
    elif failure == 'shadow':
        source[forehead & (xx < 175)] *= .55
    elif failure == 'colour':
        source[forehead & ((xx % 2) == 0)] = [.75, .44, .58]
    else:
        source[brow] = [.64, .49, .39]
    native = MockNative()
    with pytest.raises(ValueError):
        prepare_fixture(ref, analysis, source, native=native)
    assert native.calls == []


def test_black_and_bright_source_are_not_new_brow_targets():
    ref, analysis, source = synthetic_observation()
    brow = _geometry_mask(analysis, source.shape[:2], 'left', 'polygon')
    yy, xx = np.mgrid[:source.shape[0], :source.shape[1]]
    black = brow & ((xx % 11) == 0)
    bright = brow & ((xx % 11) == 1)
    source[black] = 0
    source[bright] = [.64, .49, .39]
    records, _ = prepare_fixture(ref, analysis, source)
    assert not np.any(_expanded(records[0], source.shape)[black | bright])


def test_protected_retained_neighbour_box_veto_is_not_a_new_person_target():
    ref, analysis, source = synthetic_observation()
    native = MockNative()
    # Parent must include disabled faces too; this low-level interface accepts
    # their exact boxes, without guessing identity from render enablement.
    with pytest.raises(ValueError):
        prepare_fixture(ref, analysis, source, native=native,
                        protected_boxes=[(.55, .24, .83, .38)])
    assert native.calls == []
    records, _ = prepare_fixture(ref, analysis, source, protected_boxes=[(.02, .78, .15, .94)])
    assert records[0].facts['protected_face_boxes'] == 1


def test_memory_admission_precedes_image_sized_geometry_and_native_readiness():
    ref, analysis, source = synthetic_observation()
    with patch.object(L, '_geometry', side_effect=AssertionError('No geometry before base admission')):
        with pytest.raises(ValueError, match='memory budget before allocation'):
            L.prepare(ref, analysis, source, {'version': 1, 'linked': True, 'left': .5, 'right': .5}, byte_budget=1)
    with patch.object(L.N, 'memory_estimate', return_value=BUDGET), \
            patch.object(L, '_observe', side_effect=AssertionError('No raster before native admission')):
        with pytest.raises(ValueError, match='memory budget before allocation'):
            L.prepare(ref, analysis, source, {'version': 1, 'linked': True, 'left': .5, 'right': .5}, byte_budget=BUDGET)


def test_cancelled_observation_never_calls_native_or_publishes_partial_layer():
    ref, analysis, source = synthetic_observation()
    native = MockNative()
    with pytest.raises(InterruptedError):
        prepare_fixture(ref, analysis, source, native=native, cancelled=lambda: True)
    assert native.calls == []


def test_native_readiness_refusal_has_no_python_lookalike_fallback():
    ref, analysis, source = synthetic_observation()
    with patch.object(L.N, 'available', return_value=False), \
            patch.object(L.N, 'apply', side_effect=AssertionError('Unavailable kernel must not run')):
        with pytest.raises(RuntimeError, match='unavailable'):
            L.prepare(ref, analysis, source, {'version': 1, 'linked': True, 'left': .5, 'right': .5}, byte_budget=BUDGET)


@pytest.mark.parametrize('failure', ['nan', 'hdr', 'dtype', 'protected', 'colour', 'direction'])
def test_malformed_native_rgb_is_rejected_without_publishing(failure):
    ref, analysis, source = synthetic_observation()
    def invalid(rgb, target, amount, **kwargs):
        out = MockNative()(rgb, target, amount, **kwargs)
        if failure == 'nan':
            out[0, 0, 0] = np.nan
        elif failure == 'hdr':
            out[0, 0, 0] = 1.01
        elif failure == 'dtype':
            out = out.astype(np.float64)
        elif failure == 'protected':
            out[target == 0] *= .9
        elif failure == 'colour':
            out[..., 0][target > 0] *= .9
        else:
            out = rgb * (1+target[..., None]*np.float32(.1))
        return out
    with pytest.raises(ValueError):
        prepare_fixture(ref, analysis, source, native=invalid)


def test_rebuilding_larger_observed_source_does_not_enlarge_a_previous_delta():
    small_ref, small_analysis, small_source = synthetic_observation(256)
    big_ref, big_analysis, big_source = synthetic_observation(512)
    small, small_native = prepare_fixture(small_ref, small_analysis, small_source)
    big, big_native = prepare_fixture(big_ref, big_analysis, big_source)
    assert small_ref == big_ref
    np.testing.assert_array_equal(small_analysis['landmarks'], big_analysis['landmarks'])
    assert big[0].window[2] > small[0].window[2]
    assert big[0].window[3] > small[0].window[3]
    assert big_native.calls[0][4] > small_native.calls[0][4]
    assert big[0].facts['sides']['left']['target_pixels'] > small[0].facts['sides']['left']['target_pixels']
