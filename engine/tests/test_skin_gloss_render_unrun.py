"""AUTHORED / UNRUN: face-only gloss in the existing ordered source stage.

Synthetic image/mesh/ownership fixtures and explicitly named native doubles
check routing and composition only. They are not measured face photographs,
highlight-estimator acceptance, inference, native execution or performance QA.
No imports, collection, tests, typecheck, builds or product execution ran here.
"""
from copy import deepcopy
from itertools import product
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from test_skin_colour_body_render_unrun import fixture, BUDGET, ACTIVE as COLOUR_RECIPE
from test_skin_finish_render_unrun import colour_double, finish_double, FINISH_RECIPE, render
from lumaretouch_engine import skin_colour_people as COMPOSE, face_scope as FACE
from lumaretouch_engine import skin_colour_state as COLOUR, skin_finish_state as FINISH, skin_gloss_state as GLOSS
from lumaretouch_engine import skin_colour_native as COLOUR_NATIVE, skin_finish_native as FINISH_NATIVE
from lumaretouch_engine import skin_gloss_native as GLOSS_NATIVE, skin_colour_body_support as REVIEW
from lumaretouch_engine import people_state as PEOPLE, people_binding as BIND
from lumaretouch_engine import people_snapshot as SNAPSHOT, people_render_runtime as RENDER
from lumaretouch_engine import people_engine_runtime as ENGINE, people_effects as EFFECTS
from lumaretouch_engine import creative_derived_repair_runtime as REPAIRS

GLOSS_RECIPE = {'version': 1, 'amount': -.6}


def gloss_double(current, coverage, amount, *, reference_rgb, radius, **_kwargs):
    """Bounded SOURCE-dependent nonlinear double, NOT highlight estimation."""
    assert current.shape == reference_rgb.shape
    assert coverage.shape == current.shape[:2]
    assert not current.flags.writeable and not reference_rgb.flags.writeable
    assert not coverage.flags.writeable and not np.shares_memory(current, reference_rgb)
    assert 2 <= radius <= 256
    return current + ((np.float32(1)-current)**2 * coverage[..., None]
        * reference_rgb[..., :1] * np.float32(.08*amount))


def prepare(values, *, colour=COLOUR_RECIPE, finish=FINISH_RECIPE, gloss=GLOSS_RECIPE,
            others=(), budget=BUDGET, **kwargs):
    state, assets, ref, bank, analysis, _, source = values
    return COMPOSE.prepare(ref, analysis, others, source, colour,
        finish_recipe=finish, gloss_recipe=gloss, byte_budget=budget,
        people_state=state, body_assets=assets, finish_body_assets=assets,
        body_bank=bank, **kwargs)


def test_all_neutral_needs_no_source_semantics_geometry_body_or_native_dependency():
    with patch.object(COLOUR_NATIVE, 'apply') as colour, patch.object(FINISH_NATIVE, 'apply') as finish, \
            patch.object(GLOSS_NATIVE, 'apply') as gloss, patch.object(REVIEW, 'raster') as body, \
            patch.object(COMPOSE, '_gloss_geometry') as geometry:
        assert COMPOSE.prepare(None, None, None, None, COLOUR.neutral(),
            finish_recipe=FINISH.neutral(), gloss_recipe=GLOSS.neutral(), byte_budget=0,
            people_state={'invalid': True}, body_assets={'stale': True},
            finish_body_assets={'stale': True}, body_bank={'invalid': True}) == []
    for call in (colour, finish, gloss, body, geometry): call.assert_not_called()


@pytest.mark.parametrize('enabled', list(product((False, True), repeat=3)))
def test_each_neutral_native_dependency_is_independently_bypassed(enabled):
    values = fixture(retained=False)
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double) as colour, \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double) as finish, \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss_double) as gloss:
        records = prepare(values,
            colour=COLOUR_RECIPE if enabled[0] else COLOUR.neutral(),
            finish=FINISH_RECIPE if enabled[1] else FINISH.neutral(),
            gloss=GLOSS_RECIPE if enabled[2] else GLOSS.neutral())
    assert tuple(call.call_count for call in (colour, finish, gloss)) == tuple(map(int, enabled))
    assert len(records) == int(any(enabled))


@pytest.mark.parametrize('finish_recipe', [FINISH.neutral(), FINISH_RECIPE])
def test_neutral_gloss_keeps_existing_colour_finish_roi_delta_and_facts(finish_recipe):
    values = fixture(retained=False); state, assets, ref, bank, analysis, _, source = values
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double), \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=AssertionError('Dormant gloss core')) as gloss, \
            patch.object(COMPOSE, '_gloss_geometry', side_effect=AssertionError('Dormant gloss scale')):
        old = COMPOSE.prepare(ref, analysis, [], source, COLOUR_RECIPE,
            finish_recipe=finish_recipe, byte_budget=BUDGET, people_state=state,
            body_assets=assets, finish_body_assets=assets, body_bank=bank)[0]
        current = prepare(values, finish=finish_recipe, gloss=GLOSS.neutral())[0]
    gloss.assert_not_called()
    assert old.window == current.window and old.facts == current.facts
    np.testing.assert_array_equal(old.delta, current.delta)


def test_colour_finish_gloss_is_one_ordered_delta_using_full_original_reference():
    values = fixture(retained=False); source = values[-1]; before = source.copy()
    analysis = values[4]; landmarks_before = analysis['landmarks'].copy(); calls = []
    def colour(rgb, coverage, *controls):
        calls.append(('colour', rgb.copy(), coverage.copy()))
        return colour_double(rgb, coverage, *controls)
    def finish(rgb, coverage, *controls):
        calls.append(('finish', rgb.copy(), coverage.copy()))
        return finish_double(rgb, coverage, *controls)
    def gloss(current, coverage, amount, *, reference_rgb, radius):
        calls.append(('gloss', current.copy(), coverage.copy(), reference_rgb.copy(), radius))
        np.testing.assert_array_equal(reference_rgb, source)
        assert current.shape == source.shape  # Not the nonzero coverage ROI.
        assert np.any(current != reference_rgb)
        return gloss_double(current, coverage, amount, reference_rgb=reference_rgb, radius=radius)
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish), \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss):
        records = prepare(values)
    assert len(records) == 1 and [item[0] for item in calls] == ['colour', 'finish', 'gloss']
    record = records[0]; y,x,h,w = record.window
    first = calls[0][1] + (1-calls[0][1])*calls[0][2][..., None]*np.float32(.25)
    np.testing.assert_array_equal(calls[1][1], first)
    second = first + (1-first)**2*calls[1][2][..., None]*np.float32(.4)
    np.testing.assert_array_equal(calls[2][1][y:y+h,x:x+w], second)
    expected = calls[2][1] + (1-calls[2][1])**2*calls[2][2][..., None]*source[..., :1]*np.float32(.08*GLOSS_RECIPE['amount'])
    np.testing.assert_array_equal(record.delta, expected[y:y+h,x:x+w]-source[y:y+h,x:x+w])
    # An independently original-based gloss delta would produce another result.
    independent = (1-source[y:y+h,x:x+w])**2*calls[2][2][y:y+h,x:x+w,None]*source[y:y+h,x:x+w,:1]*np.float32(.08*GLOSS_RECIPE['amount'])
    assert np.any(np.abs(record.delta-(second-source[y:y+h,x:x+w]+independent)) > 1e-6)
    assert record.stage == 'skin_colour' and not record.delta.flags.writeable
    assert record.facts['operation_order'] == [COLOUR.OP, FINISH.OP, GLOSS.OP]
    assert record.facts['skin_gloss']['reference_dependency_radius_pixels'] == 2*calls[2][4]
    assert record.facts['skin_gloss']['estimate_source'] == 'immutable-effective-source-before-colour-and-finish'
    output, facts = EFFECTS.apply('skin_colour', source, records)
    np.testing.assert_array_equal(output, render(record, source))
    assert facts['overlap_pixels'] == 0
    np.testing.assert_array_equal(source, before)
    np.testing.assert_array_equal(analysis['landmarks'], landmarks_before)


def test_gloss_only_ignores_both_body_review_banks_and_unavailable_other_cores():
    state, _, ref, _, analysis, _, source = fixture(retained=False)
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=RuntimeError('Missing colour ABI')) as colour, \
            patch.object(FINISH_NATIVE, 'apply', side_effect=RuntimeError('Missing finish ABI')) as finish, \
            patch.object(REVIEW, 'raster', side_effect=AssertionError('No gloss body consumer')) as body, \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss_double):
        records = COMPOSE.prepare(ref, analysis, [], source, COLOUR.neutral(),
            finish_recipe=FINISH.neutral(), gloss_recipe=GLOSS_RECIPE, byte_budget=BUDGET,
            people_state=state, body_assets={'invalid': True},
            finish_body_assets={'invalid': True}, body_bank={'invalid': True})
    for call in (colour, finish, body): call.assert_not_called()
    assert records[0].facts['skin_gloss']['scope'] == 'face-only-not-body-skin'
    assert records[0].facts['operation_order'] == [GLOSS.OP]


def test_actual_colour_finish_body_reviews_never_widen_gloss_coverage():
    values = list(fixture(retained=False)); state, assets, ref, bank, analysis, review, source = values
    state, assets = REVIEW.retain(state, assets, ref, bank, analysis, review)
    state, assets = REVIEW.retain(state, assets, ref, bank, analysis, review, family='skin_finish')
    values[:2] = [state, assets]; observed = []
    def gloss(current, coverage, amount, **kwargs):
        observed.append(coverage.copy())
        return gloss_double(current, coverage, amount, **kwargs)
    with patch.object(REVIEW.M, 'raster', return_value=np.full(source.shape[:2], 255, np.uint8)), \
            patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double), \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss):
        record = prepare(values)[0]
    expected = FACE.selected_face_skin(analysis['face_skin'], analysis['landmarks']) * (1-analysis['excluded'])
    np.testing.assert_array_equal(observed[0], expected)
    assert observed[0][96,64] == 0
    assert record.facts['skin_colour']['body_extension']['enabled']
    assert record.facts['skin_finish']['body_extension']['enabled']
    assert record.facts['skin_gloss']['scope'] == 'face-only-not-body-skin'


def test_real_anatomical_selector_semantics_other_face_and_unresolved_boxes_protect_gloss():
    values = fixture(retained=False); analysis = values[4]; source = values[-1]
    analysis['excluded'][24:30,55:65] = 1
    other = deepcopy(analysis); other['landmarks'][:,0] += np.float32(.38)
    other['evidence']['landmark_digest'] = BIND.landmark_digest(other['landmarks'])
    other_face = PEOPLE.new_face(values[2]['asset_sha256'], [.65,.1,.95,.45], other['evidence'])
    other['face_ref'] = PEOPLE.face_ref(other_face)
    box = [.25,.15,.32,.35]; observed = []
    def gloss(current, coverage, amount, **kwargs):
        observed.append(coverage.copy()); return gloss_double(current, coverage, amount, **kwargs)
    with patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss):
        record = prepare(values, colour=COLOUR.neutral(), finish=FINISH.neutral(),
            others=[other], protected_boxes=[box])[0]
    coverage = observed[0]
    anatomical = FACE.selected_face_skin(analysis['face_skin'], analysis['landmarks'],
        other_landmarks=[other['landmarks']]) * (1-analysis['excluded'])
    assert np.all(coverage <= anatomical) and np.any(coverage > 0)
    assert np.all(coverage[24:30,55:65] == 0)
    h,w = source.shape[:2]; xs=np.arange(w)[None,:]; ys=np.arange(h)[:,None]
    left,top,right,bottom = np.asarray(box)*[w,h,w,h]
    footprint = (xs+1>=left)&(xs<=right)&(ys+1>=top)&(ys<=bottom)
    assert np.all(coverage[footprint] == 0)
    assert record.facts['other_face_exclusions'] == 1
    assert record.facts['unresolved_neighbour_box_vetoes'] == 1


@pytest.mark.parametrize('missing', ['face_skin', 'excluded'])
def test_missing_target_face_evidence_never_falls_back_to_merged_skin_or_body(missing):
    values = fixture(retained=False); values[4][missing] = None
    if missing == 'face_skin': values[4]['face_skin_observation'] = None
    with patch.object(GLOSS_NATIVE, 'apply') as gloss:
        with pytest.raises(ValueError): prepare(values, colour=COLOUR.neutral(), finish=FINISH.neutral())
    gloss.assert_not_called()


def test_insufficient_face_support_cannot_borrow_reviewed_body_pixels():
    values = fixture(retained=True); values[4]['face_skin'][:] = 0
    with patch.object(REVIEW, 'raster') as body, patch.object(COLOUR_NATIVE, 'apply') as colour, \
            patch.object(FINISH_NATIVE, 'apply') as finish, patch.object(GLOSS_NATIVE, 'apply') as gloss:
        with pytest.raises(ValueError, match='target-owned face skin'): prepare(values)
    for call in (body, colour, finish, gloss): call.assert_not_called()


def test_measured_radius_is_rebuilt_for_the_target_grid_not_transferred_from_proxy():
    values = fixture(retained=False); state, _, ref, _, analysis, _, source = values
    snapshot = SNAPSHOT.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    _, _, larger = SNAPSHOT.at_dimensions(snapshot, (384,384), byte_budget=BUDGET)
    observations = []
    def gloss(current, coverage, amount, **kwargs):
        observations.append((current.shape, kwargs['radius'], kwargs['reference_rgb'].copy()))
        return gloss_double(current, coverage, amount, **kwargs)
    with patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss):
        small = prepare(values, colour=COLOUR.neutral(), finish=FINISH.neutral())[0]
        target = np.full((384,384,3), np.float32(.63), np.float32)
        large = COMPOSE.prepare(ref, larger[ref['face_instance_id']], [], target, COLOUR.neutral(),
            gloss_recipe=GLOSS_RECIPE, byte_budget=BUDGET)[0]
    assert observations[1][1] > observations[0][1]
    for record, shape in ((small,source.shape[:2]), (large,target.shape[:2])):
        h,w = shape
        expected = np.ptp(analysis['landmarks'][list(FACE.FACE_OVAL),:2].astype(np.float64)*[w-1,h-1],axis=0)
        assert record.facts['skin_gloss']['radius_pixels'] == int(np.ceil(.025*min(expected)))
        assert record.facts['skin_gloss']['measured_face_span_pixels'] == {'width':expected[0], 'height':expected[1]}
    np.testing.assert_array_equal(observations[1][2], target)
    assert larger[ref['face_instance_id']]['face_skin_observation']['producer_width'] == 128


def test_changed_landmark_bytes_refuse_before_anatomy_and_any_native_solver():
    values = fixture(retained=False); values[4]['landmarks'][10,0] += np.float32(.01)
    with patch.object(FACE, 'selected_face_skin') as anatomy, \
            patch.object(COLOUR_NATIVE, 'apply') as colour, patch.object(GLOSS_NATIVE, 'apply') as gloss:
        with pytest.raises(ValueError, match='retained measured target landmarks'): prepare(values)
    for call in (anatomy, colour, gloss): call.assert_not_called()


def test_extra_full_source_gloss_budget_is_admitted_before_anatomy_or_body_work():
    values = fixture(retained=False); h,w = values[-1].shape[:2]
    with patch.object(FACE, 'selected_face_skin') as anatomy, patch.object(REVIEW, 'raster') as body, \
            patch.object(COLOUR_NATIVE, 'apply') as colour, patch.object(GLOSS_NATIVE, 'apply') as gloss:
        with pytest.raises(ValueError, match='memory budget'):
            prepare(values, budget=h*w*(256+64)+128*1024*1024)
    for call in (anatomy, body, colour, gloss): call.assert_not_called()


def test_native_pixel_work_admission_precedes_anatomy_and_colour_finish_work():
    values = fixture(retained=False)
    with patch.object(GLOSS_NATIVE, 'memory_estimate', side_effect=MemoryError('Native pixel/work cap')) as admission, \
            patch.object(FACE, 'selected_face_skin') as anatomy, patch.object(REVIEW, 'raster') as body, \
            patch.object(COLOUR_NATIVE, 'apply') as colour, patch.object(FINISH_NATIVE, 'apply') as finish, \
            patch.object(GLOSS_NATIVE, 'apply') as gloss:
        with pytest.raises(MemoryError, match='Native pixel/work cap'): prepare(values)
    admission.assert_called_once_with(values[-1].shape[:2])
    for call in (anatomy, body, colour, finish, gloss): call.assert_not_called()


@pytest.mark.parametrize('scale', [.01, 1000.])
def test_unreliable_or_oversized_measured_face_scale_refuses_without_radius_clamp(scale):
    values = fixture(retained=False); analysis=values[4]
    analysis['landmarks'][:,:2] = (analysis['landmarks'][:,:2]-.5)*np.float32(scale)+.5
    analysis['evidence']['landmark_digest'] = BIND.landmark_digest(analysis['landmarks'])
    with patch.object(FACE, 'selected_face_skin') as anatomy, patch.object(GLOSS_NATIVE, 'apply') as gloss:
        with pytest.raises(ValueError, match='native radius budget'): prepare(values)
    anatomy.assert_not_called(); gloss.assert_not_called()


@pytest.mark.parametrize('failure', [RuntimeError('Missing gloss ABI'), MemoryError('Native budget'), InterruptedError('Cancelled')])
def test_gloss_failure_publishes_no_partial_colour_finish_delta(failure):
    values = fixture(retained=False); before = values[-1].copy()
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double), \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=failure):
        with pytest.raises(type(failure)): prepare(values)
    np.testing.assert_array_equal(values[-1], before)


def test_cancellation_after_finish_never_calls_gloss_or_publishes():
    values = fixture(retained=False); cancelled = [False]
    def finish(*args, **kwargs):
        output = finish_double(*args, **kwargs); cancelled[0] = True; return output
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish), patch.object(GLOSS_NATIVE, 'apply') as gloss:
        with pytest.raises(InterruptedError): prepare(values, cancelled=lambda: cancelled[0])
    gloss.assert_not_called()


def test_runtime_original_uint16_and_derived_float_export_share_one_source_consumer():
    values = fixture(retained=False); state, assets, ref, _, analysis, _, source = values
    state['links'] = []; state['persons'] = {}; key=ref['face_instance_id']
    for operation, path, value in ((COLOUR.OP,'/temperature',.2), (FINISH.OP,'/whitening',.4), (GLOSS.OP,'/amount',-.5)):
        state = PEOPLE.set_override(state, 'face', key, operation, path, value)
    snapshot = SNAPSHOT.capture(state, ref['asset_sha256'], {key:analysis})
    snapshot.update(document_id='gloss-document', support_assets=assets)
    original = np.full(source.shape, 12345, np.uint16)
    working = original.astype(np.float32)/65535
    derived = {**snapshot, 'creative_source': {'sha256':ref['asset_sha256'], 'width':128, 'height':128}}
    field = SimpleNamespace(fields=(None,None,None,None), resident_bytes=lambda:0)
    geometry = SimpleNamespace(delta=np.zeros((1,128,128,2),np.float32), owner=np.zeros((128,128),np.int32))
    compositor = COMPOSE.prepare; received=[]
    def compose(*args, **kwargs):
        received.append(args[3].copy()); assert kwargs['gloss_recipe']['amount'] == -.5
        assert 'gloss_body_assets' not in kwargs
        return compositor(*args, **kwargs)
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double), \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss_double), \
            patch.object(RENDER.A, 'build_geometry', return_value=field), \
            patch.object(RENDER.E, 'prepare', return_value=[]), \
            patch.object(RENDER, 'combine', return_value=geometry) as common, \
            patch.object(COMPOSE, 'prepare', side_effect=compose) as once, \
            patch('lumaretouch_engine.eye_light_people.prepare', return_value=[]), \
            patch('lumaretouch_engine.hair_colour_runtime.prepare_bank', return_value=((),{})):
        exported = ENGINE.prepare_export(snapshot, original, None, byte_budget=BUDGET, document_id='gloss-document')
        derived_export = ENGINE.prepare_export(derived, working, None, byte_budget=BUDGET, document_id='gloss-document')
    assert once.call_count == common.call_count == 2
    assert len(exported.effects) == len(derived_export.effects) == 1
    np.testing.assert_array_equal(received[0], working)
    np.testing.assert_array_equal(received[1], working)
    np.testing.assert_array_equal(exported.effects[0].delta, derived_export.effects[0].delta)


@pytest.mark.parametrize('derived', [False, True])
def test_runtime_gloss_reference_is_effective_repaired_source_not_unrepaired_or_processed(derived):
    values=fixture(retained=False); state, _, ref, _, analysis, _, source=values
    state['links']=[]; state['persons']={}; key=ref['face_instance_id']
    for operation,path,value in ((COLOUR.OP,'/temperature',.2),(FINISH.OP,'/whitening',.3),(GLOSS.OP,'/amount',.5)):
        state=PEOPLE.set_override(state,'face',key,operation,path,value)
    repaired=np.full_like(source,.52)
    creative={'sha256':ref['asset_sha256'],'width':128,'height':128}
    kwargs=({'creative_source':creative,'creative_repair_evidence':
        REPAIRS.make_evidence(creative,source,repaired,'f'*64)} if derived else {})
    field=SimpleNamespace(fields=(None,None,None,None),resident_bytes=lambda:0)
    geometry=SimpleNamespace(delta=np.zeros((1,128,128,2),np.float32),owner=np.zeros((128,128),np.int32))
    def gloss(current,coverage,amount,*,reference_rgb,radius):
        np.testing.assert_array_equal(reference_rgb,repaired)
        assert np.any(reference_rgb!=source) and np.any(current!=reference_rgb)
        return gloss_double(current,coverage,amount,reference_rgb=reference_rgb,radius=radius)
    with patch.object(COLOUR_NATIVE,'apply',side_effect=colour_double), \
            patch.object(FINISH_NATIVE,'apply',side_effect=finish_double), \
            patch.object(GLOSS_NATIVE,'apply',side_effect=gloss) as native, \
            patch.object(RENDER.A,'build_geometry',return_value=field), \
            patch.object(RENDER.E,'prepare',return_value=[]), \
            patch.object(RENDER,'combine',return_value=geometry), \
            patch('lumaretouch_engine.eye_light_people.prepare',return_value=[]), \
            patch('lumaretouch_engine.hair_colour_runtime.prepare_bank',return_value=((),{})):
        prepared=RENDER.prepare(state,ref['asset_sha256'],source,{key:analysis},
            byte_budget=BUDGET,document_id='gloss-document',repaired=repaired,**kwargs)
    assert native.call_count == 1 and len(prepared.effects) == 1


def test_gloss_source_effect_does_not_introduce_a_second_warp():
    torch=pytest.importorskip('torch')
    from lumaretouch_engine import people_pipeline as PIPE
    values=fixture(retained=False); source=values[-1]
    with patch.object(COLOUR_NATIVE,'apply',side_effect=colour_double), \
            patch.object(FINISH_NATIVE,'apply',side_effect=finish_double), \
            patch.object(GLOSS_NATIVE,'apply',side_effect=gloss_double):
        records=prepare(values)
    h,w=source.shape[:2]
    pipe=SimpleNamespace(h=h,w=w,device='cpu',people_origin=(0,0),
        people_prepared=SimpleNamespace(effects=tuple(records),recovery={}))
    tensor=torch.from_numpy(source.copy()).permute(2,0,1)[None]
    with patch.object(PIPE,'warp',side_effect=AssertionError('Unexpected additional skin warp')) as warp:
        output=PIPE.source_effect(pipe,'skin_colour',tensor)
    warp.assert_not_called()
    np.testing.assert_allclose(output[0].permute(1,2,0).numpy(),render(records[0],source),rtol=0,atol=1e-7)


def test_original_and_derived_preview_route_through_shared_prepare_without_new_body_port():
    torch = pytest.importorskip('torch')
    values=fixture(retained=False); state, _, ref, _, analysis, _, source=values
    state['links']=[]; state['persons']={}; key=ref['face_instance_id']
    state=PEOPLE.set_override(state,'face',key,GLOSS.OP,'/amount',.5)
    proxy=np.full(source.shape,102,np.uint8); working=proxy.astype(np.float32)/255
    pipe=SimpleNamespace(src_f32=torch.from_numpy(working).permute(2,0,1)[None],repair_base=None)
    creative={'sha256':ref['asset_sha256'],'width':128,'height':128}
    field=SimpleNamespace(fields=(None,None,None,None),resident_bytes=lambda:0)
    geometry=SimpleNamespace(delta=np.zeros((1,128,128,2),np.float32),owner=np.zeros((128,128),np.int32))
    # Repair verifier is an explicitly named routing double, not provenance QA.
    with patch.object(GLOSS_NATIVE,'apply',side_effect=gloss_double), \
            patch.object(RENDER.A,'build_geometry',return_value=field), \
            patch.object(RENDER.E,'prepare',return_value=[]), \
            patch.object(RENDER,'combine',return_value=geometry), \
            patch('lumaretouch_engine.creative_derived_repair_runtime.verify_pipeline',return_value=None), \
            patch('lumaretouch_engine.eye_light_people.prepare',return_value=[]), \
            patch('lumaretouch_engine.hair_colour_runtime.prepare_bank',return_value=((),{})):
        original=ENGINE.prepare_preview(pipe,state,ref['asset_sha256'],{key:analysis},byte_budget=BUDGET,document_id='gloss-document')
        derived=ENGINE.prepare_preview(pipe,state,ref['asset_sha256'],{key:analysis},byte_budget=BUDGET,
            document_id='gloss-document',creative_source=creative,creative_proxy=proxy)
    assert len(original.effects) == len(derived.effects) == 1
    np.testing.assert_array_equal(original.effects[0].delta,derived.effects[0].delta)
