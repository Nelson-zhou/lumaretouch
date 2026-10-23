"""AUTHORED / UNRUN: current project replicas, not historical consensus.

These fixtures require the local product test environment; no product import,
test execution, model operation or acceptance was performed while authoring.
"""
from copy import deepcopy
import pytest
from lumaretouch_engine import people_state as S, people_cross_owner as C
from lumaretouch_engine import people_algorithms as A
from lumaretouch_engine.people_cross_owner_project import validate_project


def project_pair():
    graphs = []; members = []
    for index, identity in enumerate(('first', 'second')):
        asset = str(index + 1) * 64
        graph = S.empty()
        face = S.new_face(asset, [0.1, 0.1, 0.8, 0.9], {
            'backend': 'mediapipe', 'detector_model_sha256': 'a' * 64,
            'semantic_model_sha256': None, 'landmark_digest': 'b' * 64,
            'status': 'verified', 'source_width': 200, 'source_height': 300,
            'orientation': 'exif_normalized_once'})
        graph['faces'][face['face_instance_id']] = face
        graphs.append(graph)
        members.append({'document_id': identity, 'scope_id': identity,
                        'original_sha256': asset, 'ref': S.face_ref(face)})
    op = A.DEFORM; path, value = next(iter(A.defaults()[op].items()))
    intent = [{'op': op, 'path': path, 'value': value}]
    rows = []
    for graph, member in zip(graphs, members):
        identity = member['document_id']
        graph = C.create(graph, 'association', C.descriptor('association', identity, members, intent))
        rows.append({'document_id': identity, 'fingerprint': {'hash_level': 'full',
                     'sha256': member['original_sha256']}, 'active_version': 'active',
                     'versions': [{'id': 'active', 'recipe': {}}],
                     'people_context': {'people_graph': graph}})
    return {'docs': rows, 'people_graph': S.empty()}


def test_consistent_current_pair():
    assert validate_project(project_pair()) == {
        'association': {'status': 'retained_consistent', 'suspended_documents': []}}


def test_private_replica_cannot_be_copied_into_another_owner():
    project = project_pair()
    project['docs'][1]['people_context'] = deepcopy(project['docs'][0]['people_context'])
    with pytest.raises(ValueError, match='another portrait owner'):
        validate_project(project)


def test_missing_document_suspends_without_erasing_retained_membership():
    project = project_pair(); project['docs'].pop()
    before = deepcopy(project)
    assert validate_project(project)['association']['suspended_documents'] == ['second']
    assert project == before


def test_current_member_missing_replica_rejects_half_unlink():
    project = project_pair()
    context = project['docs'][1]['people_context']
    context['people_graph'] = C.unlink(context['people_graph'], 'association')
    with pytest.raises(ValueError, match='missing its accepted replica'):
        validate_project(project)


def test_dormant_source_suspends_not_rebinds():
    project = project_pair()
    project['docs'][1]['versions'][0]['recipe']['_creative_base'] = {'id': 'sha256:' + 'c' * 64}
    assert validate_project(project)['association']['status'] == 'suspended'


def test_divergent_current_generation_rejected():
    project = project_pair(); context = project['docs'][1]['people_context']
    graph = context['people_graph']; capsule = graph['persons']['association']['cross_owner']
    intent = deepcopy(capsule['intent']); intent[0]['value'] = 0.1
    changed = C.descriptor('association', 'second', capsule['members'], intent)
    context['people_graph'] = C.update(graph, 'association', changed)
    with pytest.raises(ValueError, match='divergent accepted generations'):
        validate_project(project)


def test_old_generations_in_history_do_not_compete_with_current_owners():
    project = project_pair()
    project['people_batch_history'] = {'older': {'people_graph': S.empty()}}
    project['docs'][0]['versions'].append({'id': 'old', 'recipe': {'people_graph': S.empty()}})
    assert validate_project(project)['association']['status'] == 'retained_consistent'


def test_unavailable_original_fingerprint_suspends():
    project = project_pair(); project['docs'][1]['fingerprint'] = {}
    assert validate_project(project)['association']['suspended_documents'] == ['second']
