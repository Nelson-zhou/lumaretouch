"""Authored UNRUN: bounded save intent, not inference/durability/photo acceptance."""
from copy import deepcopy
import pytest
from lumaretouch_engine import people_state as S, virtual_copy_people as V
from lumaretouch_engine import workflow_auto_portrait_save as SAVE

ASSET = 'a' * 64
MODULES = {'lnx.skin_finish.v1': {'recipe': {'version': 1, 'whitening': .2, 'rosiness': .1}}}


def prepared():
    graph = S.empty()
    for identity, landmark in [('face-a', 'b'), ('face-b', 'c')]:
        face = S.new_face(ASSET, (.1, .1, .8, .8), {
            'backend': 'mediapipe', 'detector_model_sha256': 'd' * 64,
            'semantic_model_sha256': 'e' * 64, 'landmark_digest': landmark * 64,
            'status': 'verified', 'source_width': 640, 'source_height': 480,
            'orientation': 'exif_normalized_once'})
        face['face_instance_id'] = identity
        graph['faces'][identity] = face
    graph['analysis_runs'][ASSET] = {'detector_limit': 8, 'limit_reached': False,
                                     'census_complete': False, 'notice': 'fixture only'}
    context = {'version': 1, 'people_graph': graph, **{key: {} for key in V.FIELDS}}
    return context, [S.face_ref(face) for face in graph['faces'].values()]


def test_candidate_all_verified_instances_without_copying_observations():
    context, refs = prepared(); prior = deepcopy(context)
    result = SAVE.candidate(context, ASSET, refs, MODULES)
    assert context == prior
    assert result['faces'] == context['people_graph']['faces']
    assert result['analysis_runs'] == context['people_graph']['analysis_runs']
    assert {item['target_id'] for item in result['overrides']} == {'face-a', 'face-b'}
    assert {item['operation_id'] for item in result['overrides']} == {'lnx.skin_finish.v1'}


@pytest.mark.parametrize('bad', ['omitted', 'duplicate', 'foreign', 'limit', 'manual', 'edited', 'group'])
def test_candidate_refuses_ambiguous_or_already_owned_targets(bad):
    context, refs = prepared(); graph = context['people_graph']
    if bad == 'omitted': refs.pop()
    elif bad == 'duplicate': refs[1] = deepcopy(refs[0])
    elif bad == 'foreign': refs[0]['asset_sha256'] = 'f' * 64
    elif bad == 'limit': graph['analysis_runs'][ASSET]['limit_reached'] = True
    elif bad == 'manual': graph['faces']['face-a']['manual'] = True
    elif bad == 'edited': context['people_graph'] = S.set_override(graph, 'face', 'face-a', 'lnx.skin_finish.v1', '/whitening', .1)
    elif bad == 'group': graph['groups']['existing'] = {'label': 'existing', 'priority': 1, 'face_ids': ['face-a']}
    with pytest.raises(ValueError): SAVE.candidate(context, ASSET, refs, MODULES)


@pytest.mark.parametrize('module', ['lnx.skin.v1', 'lnx.unknown.v1'])
def test_complete_recipe_is_rejected_not_silently_truncated(module):
    context, refs = prepared()
    with pytest.raises(ValueError):
        SAVE.candidate(context, ASSET, refs, {**MODULES, module: {}})
