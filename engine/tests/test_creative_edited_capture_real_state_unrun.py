"""AUTHORED / UNRUN: real host-state and builder reachability contracts.

These fixtures deliberately call the production fresh/capture/snapshot/builder
methods rather than a second handwritten recipe. Engine.__init__, decoding,
inference and rendering are not used. Source bytes are signature-only fixtures,
not valid photos or evidence of numerical, source-decoder or RSS acceptance.
This file was authored by static inspection only and has not been imported/run.
"""
from copy import deepcopy
from hashlib import sha256

import pytest

from lumaretouch_engine import creative_edited_capture as C
from lumaretouch_engine import creative_edited_capture_admission as A
from lumaretouch_engine import people_state as S, virtual_copy_people as VP
from lumaretouch_engine.body_pose_project import bank as body_bank
from lumaretouch_engine.body_pose_render import retained as retained_body
from lumaretouch_engine.export_recipe import build_export_spec
from lumaretouch_engine.local_mask_state import file_stamp
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
from lumaretouch_engine.server import Engine


def _override(asset, *, value=0., scope='all_people', target=None):
    return dict(scope=scope, target_id=asset if target is None else target,
                operation_id='lnx.deform.v1', parameter_path='/slim_face', value=value)


def _host(tmp_path, *, neutral_people=False):
    path = tmp_path / 'original-signature-only.jpg'
    path.write_bytes(b'\xff\xd8not a decodable photo; selection fixture only')
    asset = sha256(path.read_bytes()).hexdigest()
    engine = object.__new__(Engine)  # Never construct a live pipeline or worker.
    fresh = Engine._fresh_doc_state(engine)
    for key, value in fresh.items():
        if key != '_proxy':
            setattr(engine, key, value)
    engine._vram = None
    engine._image_loaded = False
    engine._strength = 0.
    engine._exposure = (.25, 0., 0., 0., 0., 0., 0.)
    row = dict(path=str(path), state=None, document_id='real-state-doc',
               src_w=12, src_h=8, undo=[], redo=[], _people_new_import=False)
    engine._docs, engine._doc_index, engine._doc_path = [row], 0, str(path)
    engine._document_versions().version(row)
    graph = S.empty()
    if neutral_people:
        # A genuine zero-face photograph override makes PeopleHost retain its
        # snapshot without manufacturing an analysis, mask or FaceRef.
        graph['overrides'].append(_override(asset))
    engine._people_graph_owner = PeopleGraphOwner(graph)
    VP.activate(engine, row)
    state = Engine._capture_state(engine)
    row['state'] = state
    return engine, row, state, path, asset


def _snapshot(engine, row, state):
    return engine._state_to_export_snap(
        deepcopy(state), device='cpu', scale=1, upscale_backend='lanczos3',
        sharpen=0., source_path=row['path'],
        people_context=VP.row_context(engine, row),
        people_graph=VP.row_snapshot(engine, row),
        people_document_id=engine._document_versions().version(row).document_id)


@pytest.mark.parametrize('neutral_people', [False, True])
def test_real_host_defaults_reach_preflight_and_complete_builder(tmp_path, neutral_people):
    engine, row, state, path, asset = _host(tmp_path, neutral_people=neutral_people)
    before = deepcopy(state)
    before_graph = engine._people_graph_owner.snapshot()
    version = engine._document_versions().version(row)
    original = path.read_bytes()
    assert set(state) == set(Engine.DOC_FIELDS) | {'_proxy'}
    # A real fresh document always has this packed record. Presence alone must
    # not classify every colour-only source as a retained body edit.
    assert state['_body_pose_bank'] is not None
    assert not retained_body(body_bank(state))
    assert C.preflight_snapshot(engine, row, state, max_bytes=A.MAX_WORK_BYTES)

    snap = _snapshot(engine, row, state)
    assert (snap['people'] is not None) is neutral_people
    if neutral_people:
        assert snap['people']['asset_sha256'] == asset
        assert snap['people']['document_id'] == version.document_id
        assert snap['people']['analyses'] == {}
    selected = A.classify_snapshot(snap)
    assert selected.eligible, selected.reasons
    # The same preparation transition used by the bridge must not erase edits
    # or introduce an unaudited default source/private record.
    prepared, for_document = engine._prepare_export_snapshot(row['path'], snap, True)
    assert for_document is True
    C._verify_inputs(prepared, row['path'], file_stamp(row['path']), (8, 12))
    spec, skipped = build_export_spec(prepared, 8, 12, for_document=for_document)
    assert skipped == []
    assert spec.exposure == state['_exposure']
    assert spec._sky_replacement_immutable_input is None
    assert spec._sky_replacement_replay_key is None
    assert spec._common_recovery_recipe is None
    assert A.validate_spec(spec, prepared, skipped=skipped).eligible
    A.inspect_storage((state, snap, prepared, spec))
    spec._creative_capture_original_source = dict(
        path=row['path'], file_stamp=list(file_stamp(row['path'])),
        asset_sha256=asset, document_id=version.document_id)
    assert A.validate_spec(spec, prepared).eligible
    A.inspect_storage((state, snap, prepared, spec))
    assert state == before
    assert engine._people_graph_owner.snapshot() == before_graph
    assert engine._people_graph_owner.fence == 0
    assert engine._document_versions().version(row) == version
    assert row['undo'] == row['redo'] == []
    assert path.read_bytes() == original


def test_real_neutral_state_stays_legacy_before_new_copy_budget(tmp_path, monkeypatch):
    engine, row, state, _path, _asset = _host(tmp_path)
    state['_exposure'] = (0.,) * 7
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Neutral legacy dispatch reached new copy admission')
    monkeypatch.setattr(A, 'admit_snapshot_copy', forbidden)
    assert not C.preflight_snapshot(engine, row, state, max_bytes=1)


@pytest.mark.parametrize('kind', ['person', 'group', 'foreign_override',
                                 'foreign_analysis_run', 'nondefault', 'numeric_bool'])
def test_real_graph_exclusions_stay_legacy_before_new_copy_budget(tmp_path, monkeypatch, kind):
    engine, row, state, _path, asset = _host(tmp_path)
    graph = S.empty()
    if kind == 'person':
        graph['persons']['person-a'] = {'anonymous': True}
    elif kind == 'group':
        graph['groups']['group-a'] = dict(label='Neutral group', priority=0, face_ids=[])
    elif kind == 'foreign_override':
        graph['overrides'].append(_override('f' * 64))
    elif kind == 'foreign_analysis_run':
        graph['analysis_runs']['f' * 64] = dict(
            detector_limit=32, limit_reached=False, census_complete=False, notice='')
    elif kind == 'nondefault':
        graph['overrides'].append(_override(asset, value=.1))
    else:
        graph['overrides'].append(_override(asset, value=False))
    # Install a schema-checked owner, not a fake graph-returning mock.
    engine._people_graph_owner = PeopleGraphOwner(graph)
    before = engine._people_graph_owner.snapshot()
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Known legacy-only graph reached new copy admission')
    monkeypatch.setattr(A, 'admit_snapshot_copy', forbidden)
    assert not C.preflight_snapshot(engine, row, state, max_bytes=1)
    assert engine._people_graph_owner.snapshot() == before


@pytest.mark.parametrize('key', ['people_support_assets', 'hair_colour_assets', 'hair_colour_evidence'])
def test_detached_store_exclusion_precedes_new_copy_budget(tmp_path, monkeypatch, key):
    engine, row, state, _path, _asset = _host(tmp_path)
    # The cheap selection stage only tests presence. It must neither decode an
    # unneeded store nor mistake it for permission to drop it from legacy work.
    retained = {'unvalidated-selection-sentinel': b'not decoded'}
    setattr(engine, VP.FIELDS[key], retained)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Retained store reached new copy admission')
    monkeypatch.setattr(A, 'admit_snapshot_copy', forbidden)
    assert not C.preflight_snapshot(engine, row, state, max_bytes=1)
    assert getattr(engine, VP.FIELDS[key]) is retained


def test_cheap_candidate_never_scans_unadmitted_numeric_bank():
    class Unadmitted:
        def __bool__(self):
            raise AssertionError('Numeric bank truthiness was inspected')
        def __iter__(self):
            raise AssertionError('Numeric bank was iterated')
        def __array__(self, *_args, **_kwargs):
            raise AssertionError('Numeric bank was converted')
    context = {key: {} for key in VP.FIELDS}
    context['analyses'] = Unadmitted()
    assert C._plain_graph_candidate(S.empty(), context, 'a' * 64)


@pytest.mark.parametrize('disabled', [False, True])
def test_raw_shadowed_or_disabled_intent_cannot_reach_copy_gate(disabled):
    from lumaretouch_engine.people_export import fastpath_blocker
    asset = 'a' * 64
    graph = S.empty()
    graph['faces']['face-a'] = dict(
        face_instance_id='face-a', asset_sha256=asset, analysis_revision=0,
        box=[.1, .1, .6, .8], manual=False, enabled=not disabled,
        labels={}, local_assets={}, evidence=dict(
            backend='mediapipe', detector_model_sha256='d' * 64,
            semantic_model_sha256=None, landmark_digest='e' * 64,
            status='verified', source_width=12, source_height=8,
            orientation='exif_normalized_once'))
    if disabled:
        graph['overrides'].append(_override(asset, value=.2, scope='face', target='face-a'))
    else:
        graph['overrides'].extend((
            _override(asset, value=.2),
            _override(asset, value=0., scope='face', target='face-a')))
    graph = S.check(graph)
    # The generic passthrough selector only sees resolved enabled-face edits;
    # the private capture cohort must also preserve dormant/raw ownership.
    assert not fastpath_blocker({'state': graph, 'asset_sha256': asset})
    assert not C._plain_graph_candidate(graph, {key: {} for key in VP.FIELDS}, asset)


def test_precopy_admission_receives_persistent_raw_analysis_bank(tmp_path, monkeypatch):
    engine, row, state, _path, _asset = _host(tmp_path)
    retained = {'unused-original-analysis': b'owned analysis storage'}
    engine._people_analyses = retained
    real_admit = A.admit_snapshot_copy
    observed = []
    def record(roots, **options):
        observed.append(roots)
        return real_admit(roots, **options)
    monkeypatch.setattr(A, 'admit_snapshot_copy', record)
    assert C.preflight_snapshot(engine, row, state, max_bytes=A.MAX_WORK_BYTES)
    assert len(observed) == 1
    assert any(root is retained for root in observed[0])
    assert engine._people_analyses is retained


def test_missing_precompute_face_stays_legacy_before_new_copy_budget(tmp_path, monkeypatch):
    engine, row, state, _path, asset = _host(tmp_path)
    graph = S.empty()
    evidence = dict(backend='mediapipe', detector_model_sha256='d' * 64,
                    semantic_model_sha256=None, landmark_digest='e' * 64,
                    status='verified', source_width=12, source_height=8,
                    orientation='exif_normalized_once')
    graph['faces']['face-a'] = dict(
        face_instance_id='face-a', asset_sha256=asset, analysis_revision=0,
        box=[.1, .1, .6, .8], evidence=evidence, manual=False, enabled=True,
        labels={}, local_assets={})
    engine._people_graph_owner = PeopleGraphOwner(graph)
    assert state['_precompute'] is None
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Known unavailable census reached new copy admission')
    monkeypatch.setattr(A, 'admit_snapshot_copy', forbidden)
    assert not C.preflight_snapshot(engine, row, state, max_bytes=1)
