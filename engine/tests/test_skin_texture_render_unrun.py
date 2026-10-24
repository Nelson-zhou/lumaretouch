"""AUTHORED / UNRUN: face-only source-reference texture/detail composition.

Synthetic meshes, semantic planes and image arrays are contract fixtures, not
photographic evidence. Named native doubles establish sequencing and dispatch,
not real texture recovery, denoising, sharpening quality or ABI acceptance.
No imports, collection, tests, inference, typecheck, build or execution ran while
authoring. Existing colour/finish/gloss fixtures remain regression contracts.
"""
from copy import deepcopy
from itertools import product
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from test_skin_colour_body_render_unrun import fixture, BUDGET, ACTIVE as COLOUR_RECIPE
from test_skin_finish_render_unrun import colour_double, finish_double, FINISH_RECIPE, render
from test_skin_gloss_render_unrun import gloss_double, GLOSS_RECIPE
from lumaretouch_engine import skin_colour_people as COMPOSE, face_scope as FACE
from lumaretouch_engine import skin_colour_state as COLOUR, skin_finish_state as FINISH
from lumaretouch_engine import skin_gloss_state as GLOSS, skin_texture_state as TEXTURE
from lumaretouch_engine import skin_colour_native as COLOUR_NATIVE, skin_finish_native as FINISH_NATIVE
from lumaretouch_engine import skin_gloss_native as GLOSS_NATIVE, skin_texture_native as TEXTURE_NATIVE
from lumaretouch_engine import skin_colour_body_support as REVIEW
from lumaretouch_engine import people_state as PEOPLE, people_binding as BIND
from lumaretouch_engine import people_snapshot as SNAPSHOT, people_render_runtime as RENDER
from lumaretouch_engine import people_engine_runtime as ENGINE, people_effects as EFFECTS
from lumaretouch_engine import creative_derived_repair_runtime as REPAIRS

TEXTURE_RECIPE = {'version': 1, 'texture': -.6, 'clarity': .4}


def texture_double(current, coverage, texture, clarity, *, reference_rgb, radius, **_kwargs):
    """Bounded nonlinear SOURCE-dependent double, not the detail algorithm."""
    assert current.shape == reference_rgb.shape
    assert coverage.shape == current.shape[:2]
    assert not current.flags.writeable and not reference_rgb.flags.writeable
    assert not coverage.flags.writeable and not np.shares_memory(current, reference_rgb)
    assert type(radius) is int and 4 <= radius <= 256
    # Both controls affect the double independently; no claims about the real
    # native frequency decomposition or perceptual sign follow from this.
    strength = np.float32(.04*texture + .03*clarity)
    return current + (np.float32(1)-current)**2*coverage[..., None]*reference_rgb[..., :1]*strength


def prepare(values, *, colour=COLOUR_RECIPE, finish=FINISH_RECIPE, gloss=GLOSS_RECIPE,
            texture=TEXTURE_RECIPE, others=(), budget=BUDGET, **kwargs):
    state, assets, ref, bank, analysis, _, source = values
    return COMPOSE.prepare(ref, analysis, others, source, colour, finish_recipe=finish,
        gloss_recipe=gloss, texture_recipe=texture, byte_budget=budget,
        people_state=state, body_assets=assets, finish_body_assets=assets, body_bank=bank, **kwargs)


def test_all_neutral_bypasses_source_semantics_geometry_reviews_and_native_dependencies():
    with patch.object(COLOUR_NATIVE, 'apply') as colour, patch.object(FINISH_NATIVE, 'apply') as finish, \
            patch.object(GLOSS_NATIVE, 'apply') as gloss, patch.object(TEXTURE_NATIVE, 'apply') as texture, \
            patch.object(TEXTURE_NATIVE, 'memory_estimate') as admission, patch.object(REVIEW, 'raster') as body, \
            patch.object(COMPOSE, '_texture_geometry') as geometry:
        assert COMPOSE.prepare(None, None, None, None, COLOUR.neutral(),
            finish_recipe=FINISH.neutral(), gloss_recipe=GLOSS.neutral(),
            texture_recipe=TEXTURE.neutral(), byte_budget=0, people_state={'invalid': True},
            body_assets={'stale': True}, finish_body_assets={'stale': True},
            body_bank={'invalid': True}, cancelled='unused invalid callback') == []
    for call in (colour, finish, gloss, texture, admission, body, geometry): call.assert_not_called()


@pytest.mark.parametrize('enabled', list(product((False, True), repeat=4)))
def test_every_operation_independently_bypasses_its_neutral_native_dependency(enabled):
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double) as colour, \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double) as finish, \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss_double) as gloss, \
            patch.object(TEXTURE_NATIVE, 'apply', side_effect=texture_double) as texture:
        records = prepare(fixture(retained=False),
            colour=COLOUR_RECIPE if enabled[0] else COLOUR.neutral(),
            finish=FINISH_RECIPE if enabled[1] else FINISH.neutral(),
            gloss=GLOSS_RECIPE if enabled[2] else GLOSS.neutral(),
            texture=TEXTURE_RECIPE if enabled[3] else TEXTURE.neutral())
    assert tuple(call.call_count for call in (colour, finish, gloss, texture)) == tuple(map(int, enabled))
    assert len(records) == int(any(enabled))


@pytest.mark.parametrize('enabled', [flags for flags in product((False, True), repeat=3) if any(flags)])
def test_neutral_texture_preserves_existing_colour_finish_gloss_window_delta_and_facts(enabled):
    values = fixture(retained=False); state, assets, ref, bank, analysis, _, source = values
    colour = COLOUR_RECIPE if enabled[0] else COLOUR.neutral()
    finish = FINISH_RECIPE if enabled[1] else FINISH.neutral()
    gloss = GLOSS_RECIPE if enabled[2] else GLOSS.neutral()
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double), \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss_double), \
            patch.object(TEXTURE_NATIVE, 'apply', side_effect=AssertionError('Dormant texture ABI')) as texture, \
            patch.object(TEXTURE_NATIVE, 'memory_estimate', side_effect=AssertionError('Dormant texture admission')), \
            patch.object(COMPOSE, '_texture_geometry', side_effect=AssertionError('Dormant texture scale')):
        old = COMPOSE.prepare(ref, analysis, [], source, colour, finish_recipe=finish,
            gloss_recipe=gloss, byte_budget=BUDGET, people_state=state,
            body_assets=assets, finish_body_assets=assets, body_bank=bank)[0]
        current = prepare(values, colour=colour, finish=finish, gloss=gloss, texture=TEXTURE.neutral())[0]
    texture.assert_not_called()
    assert old.window == current.window and old.facts == current.facts
    np.testing.assert_array_equal(old.delta, current.delta)
    assert 'skin_texture' not in current.facts


def test_four_operations_share_one_original_reference_and_publish_one_ordered_delta():
    values = fixture(retained=False); source = values[-1]; before = source.copy()
    calls = []; references = []; outputs = []
    def colour(rgb, coverage, *controls):
        calls.append(('colour', rgb.copy(), coverage.copy()))
        return colour_double(rgb, coverage, *controls)
    def finish(rgb, coverage, *controls):
        calls.append(('finish', rgb.copy(), coverage.copy()))
        return finish_double(rgb, coverage, *controls)
    def gloss(current, coverage, amount, **kwargs):
        references.append(kwargs['reference_rgb'])
        calls.append(('gloss', current.copy(), coverage.copy()))
        result = gloss_double(current, coverage, amount, **kwargs)
        outputs.append(result.copy()); return result
    def texture(current, coverage, *controls, **kwargs):
        references.append(kwargs['reference_rgb'])
        calls.append(('texture', current.copy(), coverage.copy()))
        result = texture_double(current, coverage, *controls, **kwargs)
        outputs.append(result.copy()); return result
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish), \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss), \
            patch.object(TEXTURE_NATIVE, 'apply', side_effect=texture):
        records = prepare(values)
    assert len(records) == 1 and [row[0] for row in calls] == ['colour', 'finish', 'gloss', 'texture']
    record = records[0]; y,x,h,w = record.window
    assert references[0] is references[1]  # One immutable full-source snapshot.
    assert references[0].shape == calls[2][1].shape == calls[3][1].shape == source.shape
    np.testing.assert_array_equal(references[0], source)
    assert not np.shares_memory(references[0], source) and not references[0].flags.writeable
    first = calls[0][1] + (1-calls[0][1])*calls[0][2][..., None]*np.float32(.25)
    np.testing.assert_array_equal(calls[1][1], first)
    second = first + (1-first)**2*calls[1][2][..., None]*np.float32(.4)
    np.testing.assert_array_equal(calls[2][1][y:y+h,x:x+w], second)
    np.testing.assert_array_equal(calls[3][1], outputs[0])
    np.testing.assert_array_equal(record.delta, outputs[1][y:y+h,x:x+w]-source[y:y+h,x:x+w])
    np.testing.assert_array_equal(calls[2][2], calls[3][2])
    # Independent original-based correction cannot replace current-stage input.
    strength = np.float32(.04*TEXTURE_RECIPE['texture']+.03*TEXTURE_RECIPE['clarity'])
    incorrect = outputs[0] + (1-source)**2*calls[3][2][..., None]*source[..., :1]*strength
    assert np.any(np.abs(outputs[1]-incorrect) > 1e-6)
    assert record.stage == 'skin_colour' and not record.delta.flags.writeable
    assert record.facts['operation_order'] == [COLOUR.OP, FINISH.OP, GLOSS.OP, TEXTURE.OP]
    assert record.facts['skin_texture']['estimate_source'] == 'immutable-effective-source-before-colour-finish-and-gloss'
    output, facts = EFFECTS.apply('skin_colour', source, records)
    np.testing.assert_array_equal(output, render(record, source)); assert facts['overlap_pixels'] == 0
    np.testing.assert_array_equal(source, before)


@pytest.mark.parametrize('texture_recipe', [
    {'version': 1, 'texture': -1., 'clarity': 0.},
    {'version': 1, 'texture': 1., 'clarity': 0.},
    {'version': 1, 'texture': 0., 'clarity': 1.},
])
def test_texture_only_or_fine_clarity_only_needs_no_other_cores_or_body_review(texture_recipe):
    state, _, ref, _, analysis, _, source = fixture(retained=False)
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=RuntimeError('Missing colour ABI')) as colour, \
            patch.object(FINISH_NATIVE, 'apply', side_effect=RuntimeError('Missing finish ABI')) as finish, \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=RuntimeError('Missing gloss ABI')) as gloss, \
            patch.object(GLOSS_NATIVE, 'memory_estimate', side_effect=AssertionError('Dormant gloss admission')), \
            patch.object(REVIEW, 'raster', side_effect=AssertionError('No texture body consumer')) as body, \
            patch.object(TEXTURE_NATIVE, 'apply', side_effect=texture_double) as texture:
        records = COMPOSE.prepare(ref, analysis, [], source, COLOUR.neutral(),
            finish_recipe=FINISH.neutral(), gloss_recipe=GLOSS.neutral(),
            texture_recipe=texture_recipe, byte_budget=BUDGET, people_state=state,
            body_assets={'invalid': True}, finish_body_assets={'invalid': True}, body_bank={'invalid': True})
    for call in (colour, finish, gloss, body): call.assert_not_called()
    assert texture.call_count == len(records) == 1
    assert records[0].facts['skin_texture']['scope'] == 'face-only-not-body-skin'
    assert records[0].facts['operation_order'] == [TEXTURE.OP]


def test_reviewed_colour_and_finish_body_pixels_do_not_authorize_texture_or_gloss():
    values = list(fixture(retained=False)); state, assets, ref, bank, analysis, review, source = values
    state, assets = REVIEW.retain(state, assets, ref, bank, analysis, review)
    state, assets = REVIEW.retain(state, assets, ref, bank, analysis, review, family='skin_finish')
    values[:2] = [state, assets]; observed = []
    def texture(current, coverage, *controls, **kwargs):
        observed.append(coverage.copy()); return texture_double(current, coverage, *controls, **kwargs)
    with patch.object(REVIEW.M, 'raster', return_value=np.full(source.shape[:2], 255, np.uint8)), \
            patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double), \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss_double), \
            patch.object(TEXTURE_NATIVE, 'apply', side_effect=texture):
        record = prepare(values)[0]
    expected = FACE.selected_face_skin(analysis['face_skin'], analysis['landmarks']) * (1-analysis['excluded'])
    np.testing.assert_array_equal(observed[0], expected)
    assert observed[0][96,64] == 0 and record.facts['skin_colour']['body_extension']['enabled']
    assert record.facts['skin_finish']['body_extension']['enabled']
    assert record.facts['skin_texture']['scope'] == 'face-only-not-body-skin'


def test_actual_semantics_anatomy_neighbor_faces_and_unresolved_boxes_protect_texture():
    values = fixture(retained=False); analysis = values[4]; source = values[-1]
    analysis['excluded'][24:30,55:65] = 1
    analysis['face_skin'][32:36,44:50] = 0
    other = deepcopy(analysis); other['landmarks'][:,0] += np.float32(.38)
    other['evidence']['landmark_digest'] = BIND.landmark_digest(other['landmarks'])
    other['face_ref'] = PEOPLE.face_ref(PEOPLE.new_face(values[2]['asset_sha256'], [.65,.1,.95,.45], other['evidence']))
    box = [.25,.15,.32,.35]; observed = []
    def texture(current, coverage, *controls, **kwargs):
        observed.append(coverage.copy()); return texture_double(current, coverage, *controls, **kwargs)
    with patch.object(TEXTURE_NATIVE, 'apply', side_effect=texture):
        record = prepare(values, colour=COLOUR.neutral(), finish=FINISH.neutral(), gloss=GLOSS.neutral(),
            others=[other], protected_boxes=[box])[0]
    coverage = observed[0]
    anatomical = FACE.selected_face_skin(analysis['face_skin'], analysis['landmarks'],
        other_landmarks=[other['landmarks']]) * (1-analysis['excluded'])
    assert np.all(coverage <= anatomical) and np.any(coverage > 0)
    assert np.all(coverage[24:30,55:65] == 0) and np.all(coverage[32:36,44:50] == 0)
    h,w = source.shape[:2]; xs=np.arange(w)[None,:]; ys=np.arange(h)[:,None]
    left,top,right,bottom = np.asarray(box)*[w,h,w,h]
    footprint = (xs+1>=left)&(xs<=right)&(ys+1>=top)&(ys<=bottom)
    assert np.all(coverage[footprint] == 0)
    assert record.facts['other_face_exclusions'] == record.facts['unresolved_neighbour_box_vetoes'] == 1


@pytest.mark.parametrize('missing', ['face_skin', 'excluded'])
def test_missing_face_evidence_does_not_fall_back_to_merged_or_body_skin(missing):
    values = fixture(retained=False); values[4][missing] = None
    if missing == 'face_skin': values[4]['face_skin_observation'] = None
    with patch.object(TEXTURE_NATIVE, 'apply') as texture:
        with pytest.raises(ValueError):
            prepare(values, colour=COLOUR.neutral(), finish=FINISH.neutral(), gloss=GLOSS.neutral())
    texture.assert_not_called()


def test_insufficient_face_support_cannot_borrow_body_pixels_or_run_earlier_solvers():
    values = fixture(retained=True); values[4]['face_skin'][:] = 0
    with patch.object(REVIEW, 'raster') as body, patch.object(COLOUR_NATIVE, 'apply') as colour, \
            patch.object(FINISH_NATIVE, 'apply') as finish, patch.object(GLOSS_NATIVE, 'apply') as gloss, \
            patch.object(TEXTURE_NATIVE, 'apply') as texture:
        with pytest.raises(ValueError, match='target-owned face skin'): prepare(values)
    for call in (body, colour, finish, gloss, texture): call.assert_not_called()


def test_scale_recalculates_on_render_grid_while_semantic_producer_identity_stays_original():
    values = fixture(retained=False); state, _, ref, _, analysis, _, source = values
    snapshot = SNAPSHOT.capture(state, ref['asset_sha256'], {ref['face_instance_id']: analysis})
    _, _, larger = SNAPSHOT.at_dimensions(snapshot, (384,384), byte_budget=BUDGET)
    observations = []
    def texture(current, coverage, *controls, **kwargs):
        observations.append((current.shape, kwargs['radius'], kwargs['reference_rgb'].copy()))
        return texture_double(current, coverage, *controls, **kwargs)
    with patch.object(TEXTURE_NATIVE, 'apply', side_effect=texture):
        small = prepare(values, colour=COLOUR.neutral(), finish=FINISH.neutral(), gloss=GLOSS.neutral())[0]
        target = np.full((384,384,3), np.float32(.63), np.float32)
        large = COMPOSE.prepare(ref, larger[ref['face_instance_id']], [], target, COLOUR.neutral(),
            texture_recipe=TEXTURE_RECIPE, byte_budget=BUDGET)[0]
    assert observations[1][1] > observations[0][1]
    for record, shape in ((small,source.shape[:2]), (large,target.shape[:2])):
        h,w = shape
        expected = np.ptp(analysis['landmarks'][list(FACE.FACE_OVAL),:2].astype(np.float64)*[w-1,h-1],axis=0)
        radius = int(np.ceil(.08*min(expected))); facts = record.facts['skin_texture']
        assert facts['radius_pixels'] == radius and facts['fine_radius_pixels'] == max(1,radius//4)
        assert facts['reference_dependency_radius_pixels'] == 2*radius
        assert facts['measured_face_span_pixels'] == {'width':expected[0], 'height':expected[1]}
    np.testing.assert_array_equal(observations[1][2], target)
    assert larger[ref['face_instance_id']]['face_skin_observation']['producer_width'] == 128


def test_same_recipe_uses_each_independently_authenticated_target_scale():
    first = fixture(retained=False); second = list(fixture(retained=False))
    second[4]['landmarks'][:,:2] = (second[4]['landmarks'][:,:2]-.5)*np.float32(.8)+.5
    second[4]['evidence']['landmark_digest'] = BIND.landmark_digest(second[4]['landmarks'])
    second_face = PEOPLE.new_face(second[2]['asset_sha256'], [.25,.1,.75,.65], second[4]['evidence'])
    second[2] = PEOPLE.face_ref(second_face); second[4]['face_ref'] = second[2]
    # No colour/finish means the synthetic state/body review is deliberately not
    # a source of texture authority. The target owns its own analysis/ref.
    with patch.object(TEXTURE_NATIVE, 'apply', side_effect=texture_double):
        a = prepare(first, colour=COLOUR.neutral(), finish=FINISH.neutral(), gloss=GLOSS.neutral())[0]
        b = prepare(second, colour=COLOUR.neutral(), finish=FINISH.neutral(), gloss=GLOSS.neutral())[0]
    assert a.face_ref != b.face_ref
    assert a.facts['skin_texture']['recipe'] == b.facts['skin_texture']['recipe']
    assert a.facts['skin_texture']['radius_pixels'] != b.facts['skin_texture']['radius_pixels']


def test_changed_landmark_bytes_refuse_before_anatomy_or_native_work():
    values = fixture(retained=False); values[4]['landmarks'][10,0] += np.float32(.01)
    with patch.object(FACE, 'selected_face_skin') as anatomy, patch.object(TEXTURE_NATIVE, 'apply') as texture:
        with pytest.raises(ValueError, match='retained measured target landmarks'):
            prepare(values, colour=COLOUR.neutral(), finish=FINISH.neutral(), gloss=GLOSS.neutral())
    anatomy.assert_not_called(); texture.assert_not_called()


@pytest.mark.parametrize('scale', [.01, 1000.])
def test_unsupported_measured_scale_refuses_instead_of_radius_clamp_or_proxy(scale):
    values = fixture(retained=False); analysis = values[4]
    analysis['landmarks'][:,:2] = (analysis['landmarks'][:,:2]-.5)*np.float32(scale)+.5
    analysis['evidence']['landmark_digest'] = BIND.landmark_digest(analysis['landmarks'])
    with patch.object(FACE, 'selected_face_skin') as anatomy, patch.object(TEXTURE_NATIVE, 'apply') as texture:
        with pytest.raises(ValueError, match='native radius budget'):
            prepare(values, colour=COLOUR.neutral(), finish=FINISH.neutral(), gloss=GLOSS.neutral())
    anatomy.assert_not_called(); texture.assert_not_called()


def test_combined_source_buffer_budget_precedes_geometry_and_all_native_work():
    values = fixture(retained=False); h,w = values[-1].shape[:2]
    with patch.object(FACE, 'selected_face_skin') as anatomy, patch.object(REVIEW, 'raster') as body, \
            patch.object(COLOUR_NATIVE, 'apply') as colour, patch.object(FINISH_NATIVE, 'apply') as finish, \
            patch.object(GLOSS_NATIVE, 'apply') as gloss, patch.object(TEXTURE_NATIVE, 'apply') as texture:
        with pytest.raises(ValueError, match='memory budget'):
            prepare(values, budget=h*w*(256+64+160)+128*1024*1024)
    for call in (anatomy, body, colour, finish, gloss, texture): call.assert_not_called()


def test_texture_native_pixel_work_cap_precedes_anatomy_body_and_earlier_corrections():
    values = fixture(retained=False)
    with patch.object(TEXTURE_NATIVE, 'memory_estimate', side_effect=MemoryError('Native texture pixel/work cap')) as admission, \
            patch.object(FACE, 'selected_face_skin') as anatomy, patch.object(REVIEW, 'raster') as body, \
            patch.object(COLOUR_NATIVE, 'apply') as colour, patch.object(FINISH_NATIVE, 'apply') as finish, \
            patch.object(GLOSS_NATIVE, 'apply') as gloss, patch.object(TEXTURE_NATIVE, 'apply') as texture:
        with pytest.raises(MemoryError, match='Native texture pixel/work cap'): prepare(values)
    admission.assert_called_once_with(values[-1].shape[:2])
    for call in (anatomy, body, colour, finish, gloss, texture): call.assert_not_called()


def test_shared_gloss_texture_peak_admission_uses_sequential_max_not_sum_of_scratch():
    values = fixture(retained=False); h,w = values[-1].shape[:2]
    # Explicit estimator doubles make the fixed allowance dominate, and show
    # the render budget admits one shared source/current path, not two pipelines.
    estimate = 40*1024*1024
    budget = h*w*(256+64+60)+128*1024*1024+estimate
    with patch.object(GLOSS_NATIVE, 'memory_estimate', return_value=estimate), \
            patch.object(TEXTURE_NATIVE, 'memory_estimate', return_value=estimate), \
            patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double), \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss_double), \
            patch.object(TEXTURE_NATIVE, 'apply', side_effect=texture_double):
        records = prepare(values, budget=budget)
    assert len(records) == 1


@pytest.mark.parametrize('failure', [RuntimeError('Missing texture ABI'), MemoryError('Texture resource budget'), InterruptedError('Cancelled')])
def test_texture_failure_never_publishes_partial_colour_finish_gloss(failure):
    values = fixture(retained=False); before = values[-1].copy()
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double), \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss_double), \
            patch.object(TEXTURE_NATIVE, 'apply', side_effect=failure):
        with pytest.raises(type(failure)): prepare(values)
    np.testing.assert_array_equal(values[-1], before)


def test_cancellation_after_gloss_never_calls_texture_or_publishes_a_record():
    values = fixture(retained=False); cancelled = [False]
    def gloss(*args, **kwargs):
        output = gloss_double(*args, **kwargs); cancelled[0] = True; return output
    with patch.object(COLOUR_NATIVE, 'apply', side_effect=colour_double), \
            patch.object(FINISH_NATIVE, 'apply', side_effect=finish_double), \
            patch.object(GLOSS_NATIVE, 'apply', side_effect=gloss), patch.object(TEXTURE_NATIVE, 'apply') as texture:
        with pytest.raises(InterruptedError): prepare(values, cancelled=lambda: cancelled[0])
    texture.assert_not_called()


@pytest.mark.parametrize('change', [
    lambda source: np.concatenate([source,np.ones((*source.shape[:2],1),np.float32)],axis=2),
    lambda source: source+np.float32(1),
    lambda source: np.full_like(source,np.nan),
])
def test_alpha_hdr_and_nonfinite_sources_refuse_before_texture(change):
    values = list(fixture(retained=False)); values[-1] = change(values[-1])
    with patch.object(TEXTURE_NATIVE, 'apply') as texture:
        with pytest.raises(ValueError):
            prepare(values, colour=COLOUR.neutral(), finish=FINISH.neutral(), gloss=GLOSS.neutral())
    texture.assert_not_called()


def test_original_uint16_and_derived_float_exports_use_full_source_and_one_common_consumer():
    values = fixture(retained=False); state, assets, ref, _, analysis, _, source = values
    state['links'] = []; state['persons'] = {}; key = ref['face_instance_id']
    # The retained semantic producer is 128px, but this synthetic source owner
    # has a 384px original. Export must rebuild, never enlarge a preview delta.
    for evidence in (state['faces'][key]['evidence'],analysis['evidence']):
        evidence['source_width'] = evidence['source_height'] = 384
    for operation,path,value in ((COLOUR.OP,'/temperature',.2), (FINISH.OP,'/whitening',.4),
                                (GLOSS.OP,'/amount',-.5), (TEXTURE.OP,'/texture',-.6), (TEXTURE.OP,'/clarity',.4)):
        state = PEOPLE.set_override(state,'face',key,operation,path,value)
    snapshot = SNAPSHOT.capture(state,ref['asset_sha256'],{key:analysis})
    snapshot.update(document_id='texture-document',support_assets=assets)
    original = np.full((384,384,3),12345,np.uint16); working = original.astype(np.float32)/65535
    derived = {**snapshot,'creative_source':{'sha256':ref['asset_sha256'],'width':384,'height':384}}
    field = SimpleNamespace(fields=(None,None,None,None),resident_bytes=lambda:0)
    geometry = SimpleNamespace(delta=np.zeros((1,384,384,2),np.float32),owner=np.zeros((384,384),np.int32))
    compositor = COMPOSE.prepare; received = []
    def compose(*args, **kwargs):
        received.append(args[3].copy()); assert kwargs['texture_recipe'] == TEXTURE_RECIPE
        assert 'texture_body_assets' not in kwargs
        return compositor(*args, **kwargs)
    with patch.object(COLOUR_NATIVE,'apply',side_effect=colour_double), \
            patch.object(FINISH_NATIVE,'apply',side_effect=finish_double), \
            patch.object(GLOSS_NATIVE,'apply',side_effect=gloss_double), \
            patch.object(TEXTURE_NATIVE,'apply',side_effect=texture_double) as native, \
            patch.object(RENDER.A,'build_geometry',return_value=field), \
            patch.object(RENDER.E,'prepare',return_value=[]), \
            patch.object(RENDER,'combine',return_value=geometry) as common, \
            patch.object(COMPOSE,'prepare',side_effect=compose) as once, \
            patch('lumaretouch_engine.eye_light_people.prepare',return_value=[]), \
            patch('lumaretouch_engine.hair_colour_runtime.prepare_bank',return_value=((),{})):
        exported = ENGINE.prepare_export(snapshot,original,None,byte_budget=BUDGET,document_id='texture-document')
        derived_export = ENGINE.prepare_export(derived,working,None,byte_budget=BUDGET,document_id='texture-document')
    assert once.call_count == common.call_count == 2
    assert len(exported.effects) == len(derived_export.effects) == 1
    for received_source in received: np.testing.assert_array_equal(received_source,working)
    for call in native.call_args_list:
        assert call.args[0].shape == (384,384,3)
        np.testing.assert_array_equal(call.kwargs['reference_rgb'],working)
    for prepared in (exported,derived_export):
        fact = prepared.effects[0].facts
        assert fact['semantic_observation']['producer_width'] == 128
        assert fact['skin_texture']['radius_pixels'] > COMPOSE._texture_geometry(analysis,(128,128))[0]
    np.testing.assert_array_equal(exported.effects[0].delta,derived_export.effects[0].delta)


@pytest.mark.parametrize('derived', [False, True])
def test_texture_original_reference_is_effective_repaired_source_not_unrepaired_or_processed(derived):
    values = fixture(retained=False); state, _, ref, _, analysis, _, source = values
    state['links']=[]; state['persons']={}; key=ref['face_instance_id']
    for operation,path,value in ((COLOUR.OP,'/temperature',.2),(FINISH.OP,'/whitening',.3),
                                (GLOSS.OP,'/amount',.5),(TEXTURE.OP,'/texture',.5)):
        state=PEOPLE.set_override(state,'face',key,operation,path,value)
    repaired = np.full_like(source,.52); creative = {'sha256':ref['asset_sha256'],'width':128,'height':128}
    kwargs = ({'creative_source':creative,'creative_repair_evidence':
        REPAIRS.make_evidence(creative,source,repaired,'f'*64)} if derived else {})
    field = SimpleNamespace(fields=(None,None,None,None),resident_bytes=lambda:0)
    geometry = SimpleNamespace(delta=np.zeros((1,128,128,2),np.float32),owner=np.zeros((128,128),np.int32))
    def texture(current,coverage,*controls,**kwargs):
        reference = kwargs['reference_rgb']; np.testing.assert_array_equal(reference,repaired)
        assert np.any(reference!=source) and np.any(current!=reference)
        return texture_double(current,coverage,*controls,**kwargs)
    with patch.object(COLOUR_NATIVE,'apply',side_effect=colour_double), \
            patch.object(FINISH_NATIVE,'apply',side_effect=finish_double), \
            patch.object(GLOSS_NATIVE,'apply',side_effect=gloss_double), \
            patch.object(TEXTURE_NATIVE,'apply',side_effect=texture) as native, \
            patch.object(RENDER.A,'build_geometry',return_value=field), \
            patch.object(RENDER.E,'prepare',return_value=[]), \
            patch.object(RENDER,'combine',return_value=geometry), \
            patch('lumaretouch_engine.eye_light_people.prepare',return_value=[]), \
            patch('lumaretouch_engine.hair_colour_runtime.prepare_bank',return_value=((),{})):
        prepared = RENDER.prepare(state,ref['asset_sha256'],source,{key:analysis},
            byte_budget=BUDGET,document_id='texture-document',repaired=repaired,**kwargs)
    assert native.call_count == len(prepared.effects) == 1


def test_original_and_derived_preview_share_the_same_full_source_texture_port():
    torch = pytest.importorskip('torch')
    values = fixture(retained=False); state, _, ref, _, analysis, _, source = values
    state['links']=[]; state['persons']={}; key=ref['face_instance_id']
    state = PEOPLE.set_override(state,'face',key,TEXTURE.OP,'/texture',.5)
    proxy = np.full(source.shape,102,np.uint8); working = proxy.astype(np.float32)/255
    pipe = SimpleNamespace(src_f32=torch.from_numpy(working).permute(2,0,1)[None],repair_base=None)
    creative = {'sha256':ref['asset_sha256'],'width':128,'height':128}
    field = SimpleNamespace(fields=(None,None,None,None),resident_bytes=lambda:0)
    geometry = SimpleNamespace(delta=np.zeros((1,128,128,2),np.float32),owner=np.zeros((128,128),np.int32))
    # Explicit provenance-routing double is not evidence of real repair QA.
    with patch.object(TEXTURE_NATIVE,'apply',side_effect=texture_double) as native, \
            patch.object(RENDER.A,'build_geometry',return_value=field), \
            patch.object(RENDER.E,'prepare',return_value=[]), \
            patch.object(RENDER,'combine',return_value=geometry), \
            patch('lumaretouch_engine.creative_derived_repair_runtime.verify_pipeline',return_value=None), \
            patch('lumaretouch_engine.eye_light_people.prepare',return_value=[]), \
            patch('lumaretouch_engine.hair_colour_runtime.prepare_bank',return_value=((),{})):
        original = ENGINE.prepare_preview(pipe,state,ref['asset_sha256'],{key:analysis},
            byte_budget=BUDGET,document_id='texture-document')
        derived = ENGINE.prepare_preview(pipe,state,ref['asset_sha256'],{key:analysis},
            byte_budget=BUDGET,document_id='texture-document',creative_source=creative,creative_proxy=proxy)
    assert native.call_count == 2 and len(original.effects) == len(derived.effects) == 1
    for call in native.call_args_list:
        assert call.args[0].shape == source.shape
        np.testing.assert_array_equal(call.kwargs['reference_rgb'],working)
    np.testing.assert_array_equal(original.effects[0].delta,derived.effects[0].delta)
