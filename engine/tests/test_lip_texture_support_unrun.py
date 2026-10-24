# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN synthetic support contracts, not photographic acceptance.

No imports, collection, test execution, inference, build or typecheck were run
while authoring. Synthetic landmarks deliberately exercise real admission and
support code; only native available/apply are doubled. The routing double does
not implement, prove, or stand in for the paired-flank Rust algorithm.
"""
from copy import deepcopy
import hashlib
from unittest.mock import patch
import numpy as np
import pytest
from lumaretouch_engine import lip_texture_layer as L, lip_texture_native as N
from lumaretouch_engine import lip_texture_state as S
from lumaretouch_engine.lip_makeup_geometry import INNER
from lumaretouch_engine.ops.enhance import LIP_CHAIN_UPPER, LIP_CHAIN_LOWER

ACTIVE = {'version':1,'amount':.6}
BUDGET = 512*1024**2


def synthetic_observation(size=256):
    """Independent synthetic geometry/RGB; no learned or real-person evidence.

    Durable1024 and current size differ intentionally. Integration fixtures may
    explicitly declare a different durable source; never silently rebind a real
    source. No face_skin plane or lipstick review is supplied or required.
    """
    lm = np.full((478,3),[.5,.45,0.],dtype='<f4')
    t = np.linspace(0,np.pi,11)
    outer_x = np.linspace(.22,.78,11)
    inner_x = np.linspace(.25,.75,11)
    lm[list(LIP_CHAIN_UPPER),:2] = np.column_stack((outer_x,.65-.10*np.sin(t)))
    lm[list(LIP_CHAIN_LOWER),:2] = np.column_stack((outer_x,.65+.12*np.sin(t)))
    lm[list(INNER[:11]),:2] = np.column_stack((inner_x,.65-.015*np.sin(t)))
    lower = (INNER[0],*reversed(INNER[10:]))
    lm[list(lower),:2] = np.column_stack((inner_x,.65+.015*np.sin(t)))
    lm[33,:2],lm[133,:2],lm[263,:2],lm[362,:2] = [.28,.32],[.39,.32],[.72,.32],[.61,.32]
    ref = {'asset_sha256':'a'*64,'face_instance_id':'synthetic-lip-face','analysis_revision':0}
    evidence = {'backend':'mediapipe','detector_model_sha256':'b'*64,'semantic_model_sha256':'c'*64,
                'landmark_digest':hashlib.sha256(lm.tobytes()).hexdigest(),'status':'verified',
                'source_width':1024,'source_height':1024,'orientation':'exif_normalized_once'}
    yy,xx = np.mgrid[:size,:size]
    source = np.empty((size,size,3),np.float32)
    source[:] = [.55,.22,.28]
    # Intentionally synthetic existing dark stripes, not generated real anatomy.
    stripe = ((xx % max(6,size//24)) == 0) & (yy > size*.56) & (yy < size*.76)
    source[stripe] *= np.float32(.82)
    analysis = {'face_ref':deepcopy(ref),'evidence':evidence,'landmarks':lm,
                'excluded':np.zeros((size,size),np.float32),'skin':None}
    return ref,analysis,source


def native_double(calls):
    """Bounded linear-gain routing mark, deliberately NOT the furrow algorithm."""
    def apply(source_rgb,coverage,amount,*,across,radius,cancelled=None):
        assert source_rgb.dtype == coverage.dtype == np.float32
        assert not source_rgb.flags.writeable and not coverage.flags.writeable
        assert source_rgb.shape[:2] == coverage.shape
        assert abs(float(np.linalg.norm(across))-1) < 1e-6
        eligible = L._full_support(coverage,radius)
        assert np.any(eligible)
        if cancelled is not None and cancelled():
            raise InterruptedError('Synthetic native cancellation')
        calls.append({'source':source_rgb.copy(),'coverage':coverage.copy(),
                      'across':tuple(across),'radius':radius,'amount':amount})
        linear = np.where(source_rgb <= .04045,source_rgb/12.92,((source_rgb+.055)/1.055)**2.4)
        gain = np.float32(1+.025*amount)
        lifted = linear*gain
        encoded = np.where(lifted <= .0031308,lifted*12.92,1.055*lifted**(1/2.4)-.055)
        return np.ascontiguousarray(np.where(eligible[...,None],encoded,source_rgb),dtype=np.float32)
    return apply


def prepare(ref,analysis,source,**kwargs):
    calls = []
    with patch.object(N,'available',return_value=True), patch.object(N,'apply',side_effect=native_double(calls)):
        records = L.prepare(ref,analysis,source,ACTIVE,byte_budget=BUDGET,**kwargs)
    return records,calls


def test_real_support_owner_and_source_are_used_without_makeup_or_face_skin():
    ref,analysis,source = synthetic_observation()
    before = source.copy()
    records,calls = prepare(ref,analysis,source)
    assert len(records) == len(calls) == 1
    record = records[0]
    assert record.stage == 'lip_texture' and record.face_ref == ref
    assert record.facts['source_dimensions'] == [1024,1024]
    assert record.facts['render_dimensions'] == [256,256]
    assert record.facts['changed_pixels'] > 0
    assert record.facts['reason'] is None
    assert not record.delta.flags.writeable
    y,x,h,w = record.window
    np.testing.assert_array_equal(calls[0]['source'],source[y:y+h,x:x+w])
    np.testing.assert_array_equal(source,before)
    assert 'face_skin' not in analysis and 'reviewed' not in analysis


def test_neutral_needs_no_source_analysis_memory_or_native():
    with patch.object(N,'available',side_effect=AssertionError('neutral native load')):
        assert L.prepare(None,None,None,S.neutral(),byte_budget=0) == []


@pytest.mark.parametrize('fault',['owner','digest','synthetic','semantic','missing_veto','veto_shape','veto_nan','veto_range','hdr','alpha','nonfloat'])
def test_untrusted_source_refuses_before_native(fault):
    ref,analysis,source = synthetic_observation()
    if fault == 'owner': analysis['face_ref']['asset_sha256'] = 'd'*64
    elif fault == 'digest': analysis['landmarks'][0,0] += .001
    elif fault == 'synthetic': analysis['evidence']['status'] = 'synthetic'
    elif fault == 'semantic': analysis['evidence']['semantic_model_sha256'] = None
    elif fault == 'missing_veto': analysis['excluded'] = None
    elif fault == 'veto_shape': analysis['excluded'] = np.zeros((1,1),np.float32)
    elif fault == 'veto_nan': analysis['excluded'][0,0] = np.nan
    elif fault == 'veto_range': analysis['excluded'][0,0] = 2
    elif fault == 'hdr': source[0,0,0] = 1.1
    elif fault == 'alpha': source = np.concatenate((source,source[...,:1]),axis=2)
    elif fault == 'nonfloat': source = (source*255).astype(np.uint8)
    with patch.object(N,'apply',side_effect=AssertionError('untrusted source reached native')) as native:
        with pytest.raises(ValueError): L.prepare(ref,analysis,source,ACTIVE,byte_budget=BUDGET)
    native.assert_not_called()


@pytest.mark.parametrize('opening',[0.,.015])
def test_actual_closed_line_and_open_cavity_remain_exactly_protected(opening):
    ref,analysis,source = synthetic_observation()
    t = np.linspace(0,np.pi,11)
    analysis['landmarks'][list(INNER[:11]),1] = .65-opening*np.sin(t)
    analysis['landmarks'][list((INNER[0],*reversed(INNER[10:]))),1] = .65+opening*np.sin(t)
    analysis['evidence']['landmark_digest'] = hashlib.sha256(analysis['landmarks'].tobytes()).hexdigest()
    records,calls = prepare(ref,analysis,source)
    y,x,h,w = records[0].window
    seam_y,seam_x = int(.65*256),int(.5*256)
    assert calls[0]['coverage'][seam_y-y,seam_x-x] == 0
    assert not np.any(records[0].delta[seam_y-y,seam_x-x])


@pytest.mark.parametrize('fault',['point','short','backtracking','inversion','outside','clipped','too_small'])
def test_degenerate_inner_or_outer_geometry_never_becomes_teeth_permission(fault):
    ref,analysis,source = synthetic_observation()
    lm = analysis['landmarks']
    if fault == 'point': lm[list(INNER),:2] = [.5,.65]
    elif fault == 'short': lm[list(INNER),0] = .5+(lm[list(INNER),0]-.5)*.2
    elif fault == 'backtracking': lm[80,0] = lm[82,0]
    elif fault == 'inversion': lm[13,1] = .69
    elif fault == 'outside': lm[13,1] = .50
    elif fault == 'clipped': lm[:,0] -= .23
    elif fault == 'too_small': lm[:,:2] = .5+(lm[:,:2]-.5)*.2
    analysis['evidence']['landmark_digest'] = hashlib.sha256(lm.tobytes()).hexdigest()
    with patch.object(N,'apply',side_effect=AssertionError('invalid geometry reached native')):
        with pytest.raises(ValueError): L.prepare(ref,analysis,source,ACTIVE,byte_budget=BUDGET)


def test_soft_semantic_veto_does_not_remove_geometric_unit_plateaus():
    ref,analysis,source = synthetic_observation()
    analysis['excluded'][:] = .05
    records,calls = prepare(ref,analysis,source)
    assert np.count_nonzero(calls[0]['coverage'] == 1) > 20
    assert records[0].facts['sides']['upper']['eligible_centers'] >= 4


@pytest.mark.parametrize('rgb',[[.15,.15,.15],[.0005,.35,.35],[.99,.35,.35]])
def test_source_without_native_reliable_rgb_is_unsupported_not_no_furrows(rgb):
    ref,analysis,source = synthetic_observation()
    source[:] = rgb
    with patch.object(N,'apply',side_effect=AssertionError('unreliable RGB reached native')) as native:
        with pytest.raises(ValueError,match='support'):
            L.prepare(ref,analysis,source,ACTIVE,byte_budget=BUDGET)
    native.assert_not_called()


def test_known_occlusion_foreign_face_and_insufficient_footprint_refuse_explicitly():
    ref,analysis,source = synthetic_observation()
    with patch.object(N,'apply',side_effect=AssertionError('protected surface reached native')):
        with pytest.raises(ValueError):
            L.prepare(ref,analysis,source,ACTIVE,byte_budget=BUDGET,protected_boxes=[(.2,.5,.8,.8)])
        analysis['excluded'][:] = 1
        with pytest.raises(ValueError): L.prepare(ref,analysis,source,ACTIVE,byte_budget=BUDGET)
    ref,analysis,source = synthetic_observation(size=80)
    with patch.object(N,'apply',side_effect=AssertionError('narrow support reached native')):
        with pytest.raises(ValueError,match='support|footprint'):
            L.prepare(ref,analysis,source,ACTIVE,byte_budget=BUDGET)


def test_full_square_permission_never_bridges_holes_or_image_edges():
    coverage = np.ones((25,25),np.float32)
    coverage[12,14] = 0
    valid = L._full_support(coverage,2)
    assert not valid[12,12] and not np.any(valid[:6]) and not np.any(valid[-6:])
    coverage[12,14] = 1
    assert L._full_support(coverage,2)[12,12]


def test_measured_roll_changes_axis_without_rotating_or_replacing_source_rgb():
    ref,analysis,source = synthetic_observation()
    angle = np.deg2rad(20.)
    rotation = np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    lm = analysis['landmarks']
    lm[:,:2] = (lm[:,:2]-.5)@rotation.T+.5
    analysis['evidence']['landmark_digest'] = hashlib.sha256(lm.tobytes()).hexdigest()
    records,calls = prepare(ref,analysis,source)
    np.testing.assert_allclose(calls[0]['across'],[np.cos(angle),np.sin(angle)],atol=1e-6)
    y,x,h,w = records[0].window
    np.testing.assert_array_equal(calls[0]['source'],source[y:y+h,x:x+w])


@pytest.mark.parametrize('fault',['protected','darken','chromaticity'])
def test_invalid_native_changes_are_rejected_before_effect_publication(fault):
    ref,analysis,source = synthetic_observation()
    def invalid(rgb,coverage,amount,*,across,radius,cancelled=None):
        result = rgb.copy()
        if fault == 'protected':
            result[0,0] += .005
        else:
            y,x = np.argwhere(L._full_support(coverage,radius))[0]
            if fault == 'darken': result[y,x] -= .005
            else: result[y,x,0] += .005
        return result
    with patch.object(N,'available',return_value=True),patch.object(N,'apply',side_effect=invalid):
        with pytest.raises(ValueError): L.prepare(ref,analysis,source,ACTIVE,byte_budget=BUDGET)


def test_valid_native_identity_is_no_eligible_furrows_not_failed_geometry():
    ref,analysis,source = synthetic_observation()
    with patch.object(N,'available',return_value=True), patch.object(N,'apply',side_effect=lambda rgb,*a,**k:rgb.copy()):
        record = L.prepare(ref,analysis,source,ACTIVE,byte_budget=BUDGET)[0]
    assert record.facts['reason'] == 'no_eligible_dark_furrows'
    assert record.facts['sides']['upper']['eligible_centers'] >= 4
    assert not np.any(record.delta)


def test_complete_original_grid_rebuild_uses_actual_pixels_not_proxy_upscaling():
    small_ref,small_analysis,small = synthetic_observation(size=256)
    large_ref,large_analysis,large = synthetic_observation(size=512)
    small_records,small_calls = prepare(small_ref,small_analysis,small)
    large_records,large_calls = prepare(large_ref,large_analysis,large)
    assert large_records[0].window[2] > small_records[0].window[2]
    assert large_calls[0]['radius'] > small_calls[0]['radius']
    assert large_records[0].facts['source_dimensions'] == [1024,1024]
    y,x,h,w = large_records[0].window
    np.testing.assert_array_equal(large_calls[0]['source'],large[y:y+h,x:x+w])


def test_budget_cancellation_and_unavailable_native_never_publish():
    ref,analysis,source = synthetic_observation()
    with pytest.raises(ValueError,match='budget'):
        L.prepare(ref,analysis,source,ACTIVE,byte_budget=1)
    with pytest.raises(InterruptedError):
        L.prepare(ref,analysis,source,ACTIVE,byte_budget=BUDGET,cancelled=lambda:True)
    with patch.object(N,'available',return_value=False):
        with pytest.raises(RuntimeError,match='unavailable'):
            L.prepare(ref,analysis,source,ACTIVE,byte_budget=BUDGET)
