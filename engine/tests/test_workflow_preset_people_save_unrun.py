"""Authored UNRUN: scoped serializer contracts, not inference or save acceptance."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from lumaretouch_engine import people_state as S, virtual_copy_people as V
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
from lumaretouch_engine import workflow_preset_people_save as SAVE

ASSET = 'a' * 64
OTHER = 'b' * 64


def face(asset=ASSET, identity='fixture-face'):
    value = S.new_face(asset, (.1, .1, .8, .8), {
        'backend': 'mediapipe', 'detector_model_sha256': 'c' * 64,
        'semantic_model_sha256': 'd' * 64, 'landmark_digest': 'e' * 64,
        'status': 'verified', 'source_width': 640, 'source_height': 480,
        'orientation': 'exif_normalized_once'})
    value['face_instance_id'] = identity
    return value


def fixture(private=False):
    row = {'document_id': 'target', 'source_asset_id': 'source-target',
        'root_document_id': 'target', 'copy_number': 0, 'path': '/fixture/managed.jpg',
        'fingerprint': {'hash_level': 'full', 'sha256': ASSET},
        'managed_import': {'mode': 'copy', 'content_sha256': ASSET},
        '_people_new_import': False}
    if private:
        row[V.KEY] = {'version': 1, 'people_graph': S.empty(), **{key: {} for key in V.FIELDS}}
    engine = SimpleNamespace(_docs=[row], _doc_index=0,
        _people_graph_owner=PeopleGraphOwner(), _project={})
    V.activate(engine, row)
    saved = {'docs': [{'document_id': 'target', 'source_asset_id': 'source-target'}],
        'source_assets': {'source-target': {'sha256': ASSET}},
        'people_graph': S.empty(), 'assets': {},
        **{key: {} for key in SAVE.PEOPLE_PROJECT_FIELDS if key != 'people_graph'}}
    if private: saved['docs'][0][V.KEY] = deepcopy(row[V.KEY])
    baseline = SAVE.capture(engine, row, saved)
    graph = engine._people_graph_owner.snapshot()
    target = face(); graph['faces'][target['face_instance_id']] = target
    engine._people_graph_owner.commit(graph, expected_fence=engine._people_graph_owner.fence)
    engine._people_cursors[ASSET] = target['face_instance_id']
    engine._people_targets[ASSET] = {'scope': 'face', 'target_id': target['face_instance_id'],
                                     'face_ref': S.face_ref(target)}
    return engine, row, saved, baseline


@pytest.mark.parametrize('private', [False, True])
def test_canonical_scoped_serializer_is_detached_and_preserves_source(private):
    engine, row, saved, baseline = fixture(private)
    expected = SAVE.context(engine, row)
    old_saved = deepcopy(saved)
    old_row = {key: value if key == V.RUNTIME else deepcopy(value) for key, value in row.items()}
    owner, context = engine._people_graph_owner, engine._people_active_context
    fence = owner.fence
    staged = SAVE.stage(engine, saved, deepcopy(saved), row, baseline, expected)
    assert saved == old_saved and row == old_row
    assert engine._people_graph_owner is owner and engine._people_active_context is context
    assert owner.fence == fence and SAVE.context(engine, row) == expected
    assert staged['source_assets'] == saved['source_assets']
    if private:
        assert staged['people_graph'] == saved['people_graph']
        assert staged['docs'][0][V.KEY] == expected
    else:
        assert staged['people_graph'] == expected['people_graph']
        assert staged['people_cursors'] == {ASSET: 'fixture-face'}


def test_expected_context_is_frozen_authority_not_latest_readback():
    engine, row, saved, baseline = fixture()
    expected = SAVE.context(engine, row)
    engine._people_cursors[ASSET] = None
    with pytest.raises(ValueError, match='frozen reviewed'):
        SAVE.stage(engine, saved, saved, row, baseline, expected)


def test_source_or_original_saved_project_change_refuses():
    engine, row, saved, baseline = fixture()
    expected = SAVE.context(engine, row)
    changed = {**saved, 'unrelated': 'changed'}
    with pytest.raises(ValueError, match='original preparation'):
        SAVE.stage(engine, changed, changed, row, baseline, expected)
    row['path'] = '/fixture/substituted.jpg'
    with pytest.raises(ValueError, match='original preparation'):
        SAVE.stage(engine, saved, saved, row, baseline, expected)


def test_foreign_face_change_cannot_be_hidden_in_target_delta():
    before = S.empty(); after = S.empty()
    added = face(OTHER, 'foreign-face'); after['faces'][added['face_instance_id']] = added
    with pytest.raises(ValueError, match='another source'):
        SAVE._graph_delta(before, after, ASSET)


def test_original_landmarks_and_other_source_cursors_are_append_only():
    with pytest.raises(ValueError, match='replaced'):
        SAVE._map_delta({'old': {'face_ref': {'asset_sha256': ASSET}}}, {}, ASSET, landmarks=True)
    with pytest.raises(ValueError, match='another source'):
        SAVE._map_delta({}, {OTHER: 'foreign-face'}, ASSET)
    with pytest.raises(ValueError, match='another source'):
        SAVE._map_delta({}, {'new': {'face_ref': {'asset_sha256': OTHER}}}, ASSET, landmarks=True)


def test_serializer_cannot_classify_another_import():
    engine, row, saved, baseline = fixture()
    engine._docs.append({'document_id': 'not-opened', '_people_new_import': True})
    with pytest.raises(ValueError, match='classify another'):
        SAVE.stage(engine, saved, saved, row, baseline, SAVE.context(engine, row))
