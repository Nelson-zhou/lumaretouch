# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN source contracts, NOT photographic/runtime acceptance.

No product import, test collection/run, build, typecheck or inference occurred
during authoring. Synthetic anatomy/model hashes are explicitly fixtures, not
genuine detection. Only the local-mask raster, existing numeric bag solver and
native blend boundaries are doubled in integration-shaped tests. Actual shape,
owner, geometry, semantic, review validation and delta production are undoubled.
Separate Rust source fixtures cover native algebra; neither set proves runtime.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest

from lumaretouch_engine import people_state as P
from lumaretouch_engine import local_mask_recipe as M
from lumaretouch_engine import eye_bag_preserve_state as S
from lumaretouch_engine import eye_bag_preserve_support as V
from lumaretouch_engine import eye_bag_preserve_layer as L
from lumaretouch_engine import eye_bag_preserve_native as N
from lumaretouch_engine import eye_bag_preserve_project as PROJECT
from lumaretouch_engine.people_support_assets import content_digest
from lumaretouch_engine.third_party.rapidretouch import under_eye as LEGACY

BUDGET = 512*1024**2


def fixture():
    """Deliberately synthetic per-side anatomy for schema/geometry contracts."""
    size = 256
    lm = np.full((478, 3), [.5, .5, 0], dtype='<f4')
    angles = np.linspace(-np.pi/2, 3*np.pi/2, len(LEGACY.FACE_OVAL), endpoint=False)
    lm[LEGACY.FACE_OVAL, :2] = np.column_stack((.5+.38*np.cos(angles), .5+.44*np.sin(angles)))
    lm[13, :2] = [.5, .7]
    for side, spec in LEGACY.EYES.items():
        outer, inner = (.24, .40) if side == 'right' else (.76, .60)
        u = np.linspace(0, 1, len(spec['lid']))
        lm[spec['lid'], :2] = np.column_stack((outer+(inner-outer)*u, .4+.03*np.sin(np.pi*u)))
        upper = spec['contour'][len(spec['lid']):]
        t = np.linspace(1, 0, len(upper)+2)[1:-1]
        lm[upper, :2] = np.column_stack((outer+(inner-outer)*t, .4-.025*np.sin(np.pi*t)))
        iris = spec['iris']
        lm[iris, :2] = [(outer+inner)/2, .4]
        for index, offset in zip(range(iris+1, iris+5), ((.01, 0), (0, .01), (-.01, 0), (0, -.01))):
            lm[index, :2] = lm[iris, :2]+offset
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': 'b'*64,
        'semantic_model_sha256': 'c'*64, 'landmark_digest': hashlib.sha256(lm.tobytes()).hexdigest(),
        'status': 'verified', 'source_width': size, 'source_height': size,
        'orientation': 'exif_normalized_once'}
    face = P.new_face('a'*64, [.10, .04, .90, .96], evidence)
    state = P.empty()
    state['faces'][face['face_instance_id']] = face
    ref = P.face_ref(face)
    analysis = {'face_ref': ref, 'evidence': deepcopy(evidence), 'landmarks': lm,
        'excluded': np.zeros((size, size), np.float32), 'skin': np.ones((size, size), np.float32),
        'face_skin': np.full((size, size), .9, np.float32),
        'face_skin_observation': {'contract': 'mediapipe-face-skin-edit-weight-v1',
            'source_sha256': ref['asset_sha256'], 'semantic_model_sha256': 'c'*64,
            'producer_width': size, 'producer_height': size}}
    return state, ref, analysis, np.full((size, size, 3), .4, np.float32)


def eye(side='right'):
    cx = .32 if side == 'right' else .68
    return {'visible': True, 'unoccluded': True, 'ownership_confirmed': True,
        'recipe': {'version': 1, 'domain': 'source-normalized', 'objects': [
            {'id': side, 'name': 'Synthetic lower-lid review', 'enabled': True,
             'operation': 'add', 'kind': 'brush', 'opacity': 1., 'feather': 0.,
             'points': [[cx, .455]], 'axes': [[.025, 0], [0, .01]]}]}}


def raster_double(recipe, shape):
    """Visible fixed source-edge patch, not a substitute native brush raster."""
    side = recipe['objects'][0]['id']
    cx = .32 if side == 'right' else .68
    yy, xx = np.mgrid[:shape[0], :shape[1]]
    inside = (np.abs((xx+.5)/shape[1]-cx) < .02) & (np.abs((yy+.5)/shape[0]-.455) < .008)
    result = np.zeros(shape, np.uint8)
    result[inside] = 255
    return result


def retained(eyes=None):
    state, ref, analysis, source = fixture()
    with patch.object(M, 'raster', side_effect=raster_double):
        state, bank = V.retain(state, {}, ref, eyes or {'right': eye()}, analysis=analysis, byte_budget=BUDGET)
    return state, bank, ref, analysis, source


@pytest.mark.parametrize('preserve', [0., .5, 1.])
def test_amount_zero_dormant_without_any_source_or_support(preserve):
    with patch.object(V, 'admitted_fields', side_effect=AssertionError('support must remain dormant')):
        assert L.prepare(None, None, None, {'version': 2, 'amount': 0., 'preserve': preserve},
                         people_state=None, support_assets=None, byte_budget=0, cancelled='unused') == []


@pytest.mark.parametrize('field,value', [('amount', True), ('preserve', False), ('amount', -.1),
    ('preserve', 1.01), ('amount', float('nan')), ('preserve', float('inf')), ('version', True)])
def test_strict_version_scalar_fields(field, value):
    with pytest.raises(ValueError):
        S.check({**S.neutral(), field: value})


def test_default_preservation_and_explicit_legacy_coexistence():
    assert S.neutral() == {'version': 2, 'amount': 0., 'preserve': 1.}
    assert S.check_coexistence(S.neutral(), .9) == S.neutral()
    with pytest.raises(ValueError):
        S.check_coexistence({**S.neutral(), 'amount': .1}, .1)
    for path in ('/eyes', '/mask', '/version'):
        with pytest.raises(ValueError):
            PROJECT.validate_leaf(path, 0)


def test_record_rejects_eye_light_no_confirmation_and_nonbrush_placeholder():
    state, bank, ref, _, _ = retained()
    record, _ = V.resolve(state, bank, ref)
    wrong = deepcopy(record); wrong['row']['target'] = 'eye_light_visibility'
    with pytest.raises(ValueError): V.check_record(wrong)
    wrong = deepcopy(record); wrong['row']['eyes']['right']['visible'] = False
    with pytest.raises(ValueError): V.check_record(wrong)
    wrong = deepcopy(record); wrong['row']['eyes']['right']['recipe']['objects'] = []
    with pytest.raises(ValueError): V.check_record(wrong)


def test_exact_face_digest_source_and_immutable_bank_ownership():
    state, bank, ref, _, _ = retained()
    record, key = V.resolve(state, bank, ref)
    assert content_digest(record) == key
    record['row']['eyes']['right']['visible'] = False
    assert bank[key]['row']['eyes']['right']['visible'] is True
    other = deepcopy(ref); other['analysis_revision'] += 1
    with pytest.raises(ValueError): V.resolve(state, bank, other)
    altered = deepcopy(state)
    altered['faces'][ref['face_instance_id']]['evidence']['landmark_digest'] = 'd'*64
    with pytest.raises(ValueError): V.resolve(altered, bank, ref)


def test_current_eyes_map_replaces_not_merges_and_old_bytes_survive():
    state, bank, ref, analysis, _ = retained({'right': eye(), 'left': eye('left')})
    _, old_key = V.resolve(state, bank, ref)
    with patch.object(M, 'raster', side_effect=raster_double):
        updated, updated_bank = V.retain(state, bank, ref, {'left': eye('left')},
            analysis=analysis, byte_budget=BUDGET)
    current, key = V.resolve(updated, updated_bank, ref)
    assert set(current['row']['eyes']) == {'left'}
    assert key != old_key and old_key in updated_bank and old_key in bank


@pytest.mark.parametrize('kind', ['empty', 'outside', 'feather-only', 'wrong-side'])
def test_nonusable_manual_rasters_refuse(kind):
    state, ref, analysis, _ = fixture()
    def bad(recipe, shape):
        value = raster_double(recipe, shape)
        if kind == 'empty': value.fill(0)
        if kind == 'outside': value[:] = 255
        if kind == 'feather-only': value[value > 0] = 254
        if kind == 'wrong-side': value = np.fliplr(value).copy()
        return value
    with patch.object(M, 'raster', side_effect=bad), pytest.raises(ValueError):
        V.retain(state, {}, ref, {'right': eye()}, analysis=analysis, byte_budget=BUDGET)


def test_known_occlusion_and_competing_person_refuse_review():
    state, ref, analysis, _ = fixture()
    analysis['excluded'][:] = 1
    with patch.object(M, 'raster', side_effect=raster_double), pytest.raises(ValueError):
        V.retain(state, {}, ref, {'right': eye()}, analysis=analysis, byte_budget=BUDGET)
    analysis['excluded'][:] = 0
    other = P.new_face(ref['asset_sha256'], [.29, .43, .35, .48], analysis['evidence'])
    other['enabled'] = False
    state['faces'][other['face_instance_id']] = other
    with patch.object(M, 'raster', side_effect=raster_double), pytest.raises(ValueError):
        V.retain(state, {}, ref, {'right': eye()}, analysis=analysis, byte_budget=BUDGET)


def test_whole_source_grid_rejects_tile_and_upsampling():
    state, bank, ref, analysis, _ = retained()
    for shape in ((128, 256), (512, 512)):
        with pytest.raises(ValueError):
            V.raster(state, bank, ref, shape, analysis=analysis, byte_budget=BUDGET)


def test_real_decoder_align8_grid_is_not_rejected_by_one_pixel_aspect_heuristic():
    state, ref, analysis, _ = fixture()
    face = state['faces'][ref['face_instance_id']]
    face['evidence']['source_width'] = 6048
    face['evidence']['source_height'] = 4024
    analysis['evidence'] = deepcopy(face['evidence'])
    for name in ('skin', 'face_skin', 'excluded'):
        value = 0. if name == 'excluded' else .9
        analysis[name] = np.full((680, 1024), value, np.float32)
    analysis['face_skin_observation'].update(producer_width=1024, producer_height=680)
    # Admission only: these synthetic plane values do not prove real inference
    # or that pixels actually came from a canonical decoder.
    _, _, _, observation = V._admission(state, ref, analysis, (680, 1024), BUDGET)
    assert observation['producer_width'] == 1024


def test_precise_coverage_and_unreviewed_side_facts():
    state, bank, ref, analysis, source = retained()
    with patch.object(M, 'raster', side_effect=raster_double):
        coverage, facts = V.raster(state, bank, ref, source.shape[:2], analysis=analysis, byte_budget=BUDGET)
    assert not coverage.flags.writeable and np.count_nonzero(coverage == 1) >= 4
    assert facts['sides']['left'] == {'reviewed': False, 'reason': 'unreviewed-side-unchanged'}
    assert facts['automatic_ridge_detection'] is False


def numeric_double(source, corrected, coverage, preserve, *, cancelled=None):
    """Documented opacity algebra only, not Rust or legacy solver acceptance."""
    out = (source.astype(np.float64)+(corrected.astype(np.float64)-source)
           *(1-float(preserve)*coverage[..., None])).astype(np.float32)
    out[(coverage == 1) & (preserve == 1)] = source[(coverage == 1) & (preserve == 1)]
    out[np.all(corrected == source, axis=2)] = source[np.all(corrected == source, axis=2)]
    return out


@pytest.mark.parametrize('preserve', [0., .5, 1.])
def test_layer_protects_only_bag_delta_and_keeps_real_source_roi(preserve):
    state, bank, ref, analysis, source = retained()
    before = source.copy(); calls = []
    def solve(rgb, geometry, params):
        assert params.dark_circles == 0 and params.eye_bags == .6
        calls.append(rgb.shape)
        rgb[:] += np.float32(.02)  # Explicit routing marker, not bag correction.
    solver = SimpleNamespace(EYES=LEGACY.EYES, _eye_geometry=LEGACY._eye_geometry,
        Params=LEGACY.Params, SURROUND=LEGACY.SURROUND, _correct_eye=solve)
    with patch.object(M, 'raster', side_effect=raster_double), patch.object(L, '_solver', return_value=solver), \
            patch.object(N, 'available', return_value=True), patch.object(N, 'apply', side_effect=numeric_double):
        records = L.prepare(ref, analysis, source, {'version': 2, 'amount': .6, 'preserve': preserve},
            people_state=state, support_assets=bank, byte_budget=BUDGET)
        coverage, _ = V.raster(state, bank, ref, source.shape[:2], analysis=analysis, byte_budget=BUDGET)
    assert len(records) == len(calls) == 1
    row = records[0]; y, x, h, w = row.window
    assert row.delta.shape == (h, w, 3) and not row.delta.flags.writeable
    assert row.stage == 'eye_bag_preserve' and row.facts['reviewed_eyes'] == ['right']
    core = coverage[y:y+h, x:x+w] == 1
    np.testing.assert_allclose(row.delta[core], np.float32(.02*(1-preserve)), atol=1e-7, rtol=0)
    if preserve == 1: assert np.all(row.delta[core] == 0)
    np.testing.assert_array_equal(source, before)
    assert row.facts['runtime_quality_accepted'] is False


def test_hdr_rgba_budget_and_cancellation_refuse_before_solver():
    state, bank, ref, analysis, source = retained()
    active = {**S.neutral(), 'amount': .5}
    with patch.object(L, '_solver', side_effect=AssertionError('must refuse first')):
        for bad in (source+1, source.astype(np.float64), np.concatenate((source, source[..., :1]), axis=2)):
            with pytest.raises(ValueError):
                L.prepare(ref, analysis, bad, active, people_state=state, support_assets=bank, byte_budget=BUDGET)
        with pytest.raises(ValueError):
            L.prepare(ref, analysis, source, active, people_state=state, support_assets=bank, byte_budget=0)
        with pytest.raises(InterruptedError):
            L.prepare(ref, analysis, source, active, people_state=state, support_assets=bank,
                      byte_budget=BUDGET, cancelled=lambda: True)


def test_legacy_solver_pin_is_exact_and_unmodified():
    root = Path(__file__).resolve().parents[1]/'src/lumaretouch_engine'
    assert hashlib.sha256((root/'third_party/rapidretouch/under_eye.py').read_bytes()).hexdigest() == L.SOLVER_SHA256


@pytest.mark.parametrize('bad', [True, float('nan'), -.01, 1.01])
def test_native_bridge_rejects_invalid_scalar_without_loading(bad):
    with patch.object(N, 'native', side_effect=AssertionError('invalid native call')):
        with pytest.raises(ValueError):
            N.apply(np.zeros((1, 1, 3), np.float32), np.zeros((1, 1, 3), np.float32),
                    np.ones((1, 1), np.float32), bad)
