"""UNRUN: authored canvas view contracts; local Qoder runtime execution required.

No image/render/model dependencies are needed by the guide state/host modules.
Project round trips write only temporary project JSON, never source photos.
"""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from lumaretouch_engine import canvas_guides as G
from lumaretouch_engine import canvas_guides_host as H


def state(position=0.25, visible=True, axis='vertical'):
    return {'visible': visible, 'lines': [{'id': 'guide-1', 'axis': axis, 'position': position}]}


def fixture():
    rows = [{'document_id': 'root', 'path': '/same.raw', 'state': {'exposure': 0.0},
             'undo': [{'exposure': -1.0}], 'redo': [], 'document_revision': 7},
            {'document_id': 'copy', 'path': '/same.raw', 'state': {'exposure': 1.0},
             'undo': [], 'redo': [{'exposure': 2.0}], 'document_revision': 3}]
    versions = SimpleNamespace(workspace='workspace-1')
    engine = SimpleNamespace(_docs=rows, _doc_index=0, _load_id='101', _image_loaded=True,
                             _vram=object(), _project_dirty=False,
                             _document_versions=lambda: versions,
                             _frame_presentation=lambda **_: SimpleNamespace(geometry=123),
                             _project_state=lambda: {'dirty': True})
    events = []
    return engine, H.CanvasGuides(engine, events.append), events


def command(engine, action='set', request_id='request-1', **extra):
    report = H.report(engine)
    request = {'cmd': 'canvas_guides', 'action': action, 'request_id': request_id,
               **{key: report[key] for key in ('document_id', 'workspace', 'revision', 'geometry', 'load_id')}}
    if action == 'set':
        request['state'] = state()
    request.update(extra)
    return request


def result(events):
    return next(event for event in reversed(events) if event['event'] == 'canvas_guides_result')


@pytest.mark.parametrize('position', [-0.01, 1.01, float('nan'), float('inf'), True, '0.5', None, 10**400])
def test_rejects_non_finite_out_of_bounds_and_non_numeric_positions(position):
    with pytest.raises(ValueError):
        G.state(state(position))


def test_validation_is_strict_and_does_not_clamp_or_erase():
    for bad in ({}, {'visible': True}, {'visible': 1, 'lines': []},
                {'visible': True, 'lines': [], 'extra': 1},
                {'visible': True, 'lines': [state()['lines'][0]] * 2},
                state(axis='diagonal'), state() | {'lines': None}):
        with pytest.raises(ValueError):
            G.state(bad)
    assert G.state(state(0))['lines'][0]['position'] == 0
    assert G.state(state(1))['lines'][0]['position'] == 1
    many = {'visible': True, 'lines': [dict(id=f'g-{i}', axis='horizontal', position=0.5) for i in range(129)]}
    with pytest.raises(ValueError):
        G.state(many)


def test_view_history_noops_branching_visibility_and_bounded_ownership():
    original = G.record()
    added = G.change(original, 'set', state())
    assert original == G.record() and added['revision'] == 1
    assert G.change(added, 'set', state()) == added
    hidden = G.change(added, 'set', state(visible=False))
    undone = G.change(hidden, 'undo')
    assert undone['state']['visible'] is True and len(undone['redo']) == 1
    redone = G.change(undone, 'redo')
    assert redone['state'] == hidden['state'] and redone['revision'] > hidden['revision']
    branch = G.change(undone, 'set', state(0.75))
    assert branch['redo'] == [] and branch['state']['lines'][0]['position'] == 0.75
    for i in range(100):
        branch = G.change(branch, 'set', state(i / 100))
    assert len(branch['undo']) == 64
    assert G.change(G.record(), 'undo') == G.record()


def test_document_switch_same_source_and_guides_do_not_touch_pixel_state_or_fences():
    engine, host, events = fixture()
    before = deepcopy(engine._docs)
    host.handle(command(engine))
    first = H.report(engine)
    assert result(events)['success'] and engine._project_dirty
    assert first['document_id'] == 'root' and first['load_id'] == '101' and first['geometry'] == '123'
    for key in ('state', 'undo', 'redo', 'document_revision'):
        assert engine._docs[0][key] == before[0][key]
    assert engine._docs[1] == before[1]
    engine._doc_index, engine._load_id = 1, '102'
    assert H.report(engine)['lines'] == []
    host.handle(command(engine, request_id='copy-write', state=state(0.75)))
    engine._doc_index, engine._load_id = 0, '103'
    assert H.report(engine)['lines'] == first['lines']
    host.handle(command(engine, 'undo', 'root-undo'))
    assert H.report(engine)['lines'] == []
    assert engine._docs[1][G.KEY]['state']['lines'][0]['position'] == 0.75


@pytest.mark.parametrize('patch', [{'document_id': 'copy'}, {'workspace': 'old-workspace'},
                                  {'load_id': 'old-load'}, {'geometry': None},
                                  {'revision': 99}, {'revision': True}, {'geometry': '999'},
                                  {'state': state(float('nan'))}, {'unknown': True}])
def test_stale_or_malformed_commands_preserve_existing_view_and_recipe(patch):
    engine, host, events = fixture()
    host.handle(command(engine))
    before = deepcopy(engine._docs)
    host.handle(command(engine, request_id='bad-write', **patch))
    assert not result(events)['success']
    assert engine._docs == before


def test_no_active_load_rejects_and_empty_state_read_is_safe():
    engine, host, events = fixture()
    engine._load_id = ''
    host.handle(command(engine))
    assert not result(events)['success']
    assert H.report(engine)['geometry'] is None
    engine._doc_index = -1
    host.handle({'cmd': 'canvas_guides', 'action': 'state', 'request_id': 'read'})
    assert result(events)['success'] and result(events)['canvas_guides']['document_id'] == ''


def test_replayed_undo_is_not_applied_twice_and_fences_survive_receipt_eviction():
    engine, host, events = fixture()
    host.handle(command(engine))
    host.handle(command(engine, request_id='move', state=state(0.5)))
    undo = command(engine, 'undo', 'undo-one')
    host.handle(undo)
    view = deepcopy(engine._docs[0][G.KEY])
    host.handle(undo)
    assert engine._docs[0][G.KEY] == view and result(events)['success']
    for index in range(130):
        host.handle({'cmd': 'canvas_guides', 'action': 'state', 'request_id': f'read-{index}'})
    host.handle(undo)
    assert not result(events)['success'] and engine._docs[0][G.KEY] == view


def test_view_recovery_boundary_counts_only_commits_and_does_not_taint_on_stale_request():
    from lumaretouch_engine.project_recovery_runtime import begin, finish, observe
    engine, _, events = fixture()
    recovery = SimpleNamespace(revision=7, tainted=False, reason=None)
    engine._project_recovery_runtime = recovery
    def emit(event):
        observe(event)
        events.append(event)
    host = H.CanvasGuides(engine, emit)
    for request in (command(engine), command(engine, request_id='stale', revision=99)):
        boundary, wrapped = begin(engine, request, host.handle)
        wrapped(request)
        finish(engine, boundary)
    assert recovery.revision == 8 and not recovery.tainted and recovery.reason is None
    host.handle(command(engine, request_id='noop'))
    assert recovery.revision == 8


def test_pixel_undo_and_redo_leave_guide_history_untouched():
    from lumaretouch_engine.history_controller import HistoryController, HistoryPorts
    engine, host, events = fixture()
    row = engine._docs[0]
    def restore(snapshot, mode):
        row['state'] = deepcopy(snapshot)
        return {'event': 'frame', 'render_ms': 0, 'mode': mode}
    history = HistoryController(HistoryPorts(
        capture=lambda: deepcopy(row['state']), signature=lambda value: json.dumps(value, sort_keys=True),
        restore_frame=restore, guard=lambda _: None, remember_current=lambda: None,
        status=lambda: {'canvas_guides': H.report(engine)}, mark_dirty=lambda: None),
        events.append, clock=lambda: 1, limit=64, group_ms=700)
    history.bind(row)
    host.handle(command(engine))
    view = deepcopy(row[G.KEY])
    history.handle_command({'cmd': 'history', 'action': 'undo'})
    assert row['state']['exposure'] == -1 and row[G.KEY] == view
    history.handle_command({'cmd': 'history', 'action': 'redo'})
    assert row['state']['exposure'] == 0 and row[G.KEY] == view
    pixel = deepcopy(history.report())
    host.handle(command(engine, 'undo', 'guides-undo'))
    assert history.report() == pixel and row['state']['exposure'] == 0


def project_fixture(tmp_path):
    from lumaretouch_engine import project as P
    project = P.new_project('guides', str(tmp_path))
    path = str(tmp_path / 'missing-source.raw')
    digest = hashlib.sha256(b'unchanged-source').hexdigest()
    fp = {'path': path, 'bytes': 16, 'sha256': digest, 'head_sha256': digest,
          'hash_level': 'full', 'mtime_ns': 10, 'readonly': True}
    row = P.add_doc(project, path, None, fp=fp, version_id='live')
    return P, project, row


def test_project_roundtrip_preserves_visibility_positions_and_separate_histories(tmp_path):
    from lumaretouch_engine import virtual_copy_storage as VC
    P, project, root = project_fixture(tmp_path)
    root['canvas_guides'] = G.change(G.change(G.record(), 'set', state()), 'set', state(visible=False))
    child = VC.create_copy(project, root['document_id'])
    assert child['canvas_guides']['state'] == root['canvas_guides']['state']
    assert child['canvas_guides']['undo'] == child['canvas_guides']['redo'] == []
    assert child['canvas_guides']['revision'] == 0
    child['canvas_guides'] = G.change(child['canvas_guides'], 'set', state(0.8))
    path = str(tmp_path / 'guides.lrproject.json')
    P.save(project, path)
    loaded = P.load(path)
    assert loaded['docs'] == project['docs']
    assert loaded['schema_version'] == 'lrt.project.v23'
    runtime = {}
    G.restore_row(loaded['docs'][0], runtime)
    assert runtime[G.KEY] == root['canvas_guides']
    assert G.change(runtime[G.KEY], 'undo')['state']['visible'] is True
    runtime[G.KEY]['state']['lines'][0]['position'] = 0.1
    assert root['canvas_guides']['state']['lines'][0]['position'] == 0.25
    assert child['canvas_guides']['state']['lines'][0]['position'] == 0.8


@pytest.mark.parametrize('bad', [None, {}, {'version': 2},
    {'version': 1, 'revision': 0, 'state': state(float('nan')), 'undo': [], 'redo': []},
    {'version': 1, 'revision': 0, 'state': state(), 'undo': [None], 'redo': []}])
def test_corrupt_project_guides_reject_instead_of_silently_resetting(tmp_path, bad):
    P, project, root = project_fixture(tmp_path)
    root['canvas_guides'] = bad
    before = deepcopy(project)
    with pytest.raises(P.ProjectError, match='canvas guides'):
        P.validate(project)
    assert repr(project) == repr(before)
    target = {G.KEY: G.change(G.record(), 'set', state(0.75))}
    before_target = deepcopy(target)
    with pytest.raises(ValueError):
        G.restore_row(root, target)
    assert target == before_target


def test_legacy_missing_view_metadata_is_neutral_and_never_added_to_pixel_contract():
    runtime = {}
    G.restore_row({}, runtime)
    assert runtime[G.KEY] == G.record()
    path = Path(__file__).parents[1] / 'src/lumaretouch_engine/server.py'
    source = path.read_text()
    tree = ast.parse(source)
    engine = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Engine')
    for node in engine.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('DOC_FIELDS', 'EDIT_CMDS') for t in node.targets):
            assert 'canvas_guides' not in ast.get_source_segment(source, node)
        if isinstance(node, ast.FunctionDef) and node.name in ('_capture_state', '_apply_state'):
            assert 'canvas_guides' not in ast.get_source_segment(source, node)
