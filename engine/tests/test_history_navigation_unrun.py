"""AUTHORED / UNRUN. Real canonical history + sparse graph owner at explicit ports.

The frame port is a deterministic unit fixture, NOT renderer/GPU/product evidence.
No test or product import in this file was executed during source-only authoring.
"""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import pytest
from lumaretouch_engine import history_navigation as N, people_state as S
from lumaretouch_engine.history_controller import HistoryController, HistoryPorts
from lumaretouch_engine.history_policy import state_signature
from lumaretouch_engine.document_versions import DocumentVersions
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner
from lumaretouch_engine.people_document_history import restore as restore_people


class PortsFixture:
    def __init__(self, limit=4):
        self._image_loaded = True
        self._load_id = 'load-a'
        self._doc_index = 0
        self._docs = [{'document_id': 'doc-a', 'document_revision': 0}]
        self.versions = DocumentVersions()
        graph = S.empty()
        evidence = {'backend': 'fixture', 'detector_model_sha256': 'd'*64,
                    'semantic_model_sha256': None, 'landmark_digest': 'e'*64,
                    'status': 'verified', 'source_width': 128, 'source_height': 128,
                    'orientation': 'exif_normalized_once'}
        self.faces = []
        for asset in ('a'*64, 'b'*64, 'a'*64):
            face = S.new_face(asset, [.1, .1, .6, .6], evidence)
            graph['faces'][face['face_instance_id']] = face
            self.faces.append(face['face_instance_id'])
        self.graph = PeopleGraphOwner(graph)
        self.active = {'_proxy': (10, 20), 'value': 0}
        self.events = []
        self.restores = []
        self.remembered = []
        self.blocked = None
        self._project_dirty = False
        self.history = HistoryController(HistoryPorts(self._history_capture, state_signature,
            self.restore_frame, self._history_guard, self.remember, lambda: deepcopy(self.active),
            lambda: setattr(self, '_project_dirty', True)), self.events.append, lambda: 1000, limit, 700)

    def _document_versions(self): return self.versions
    def _history_controller(self): return self.history
    def _people_managed(self): return True
    def _people_owner(self): return self.graph
    def _history_guard(self, action): return self.blocked
    def _fence_current_document(self): self.versions.advance(self._docs[0])
    def _history_capture(self):
        return {**deepcopy(self.active), '_people_history': self.graph.capture_document('a'*64)}
    def remember(self): self.remembered.append(N.exact((self.active, self.history.undo, self.history.redo)))
    def restore_frame(self, snap, mode):
        self.restores.append(mode)
        if '_people_transition' in snap:
            candidate = restore_people(self.graph, snap['_people_transition'], 'a'*64)
        else:
            candidate = self.graph.stage_document_restore(snap['_people_history'],
                expected_asset_fence=self.graph.asset_fences.get('a'*64, 0),
                expected_association_fence=self.graph.association_fence)
        self.graph.commit(candidate, expected_fence=self.graph.fence)
        self.active = {k: deepcopy(v) for k, v in snap.items() if not k.startswith('_people_')}
        return {'event': 'frame', 'render_ms': 1}
    def edit(self, value, *, coalesce=False):
        before = self._history_capture()
        self.active['value'] = value
        graph = self.graph.snapshot()
        graph['faces'][self.faces[0]]['labels']['edit'] = value
        self.graph.commit(graph, expected_fence=self.graph.fence)
        self.history.record('fixture', before, coalesce=coalesce)
    def request(self, target, rid='navigate'):
        return {'cmd': N.COMMAND, 'action': 'navigate', 'request_id': N.REQUEST_PREFIX + rid,
                'view': N.checkpoint(self)[0], 'target': target}
    def run(self, request):
        N.command(self, request, self.events.append)
        return self.events[-1]


def prepared():
    engine = PortsFixture()
    for value in (1, 2, 3): engine.edit(value)
    return engine


def test_actual_adjacent_undo_redo_and_other_photo_sparse_preservation():
    e = prepared()
    graph = e.graph.snapshot()
    graph['faces'][e.faces[1]]['labels']['later'] = 'keep'
    e.graph.commit(graph, expected_fence=e.graph.fence)
    result = e.run(e.request(0))
    assert result['phase'] == 'applied' and result['completed_steps'] == 3
    assert result['reached']['cursor'] == 0 and e.active['value'] == 0
    assert e.graph.snapshot()['faces'][e.faces[1]]['labels'] == {'later': 'keep'}
    assert e.restores == ['history_undo']*3 and len(e.remembered) == 3
    result = e.run(e.request(3, 'redo'))
    assert result['phase'] == 'applied' and result['completed_steps'] == 3
    assert e.active['value'] == 3 and e.graph.snapshot()['faces'][e.faces[1]]['labels'] == {'later': 'keep'}
    assert e.restores[-3:] == ['history_redo']*3


def test_digest_covers_transition_only_mutation_and_tiny_float_difference():
    e = prepared()
    request = e.request(0)
    e.history.undo[0]['_people_transition']['association_fence'] += 1
    assert e.run(request)['phase'] == 'rejected' and e.restores == []
    request = e.request(0, 'float')
    e.active['value'] += 1e-12
    assert e.run(request)['phase'] == 'rejected' and e.restores == []


@pytest.mark.parametrize('change', ['workspace', 'load', 'revision', 'row', 'branch', 'coalesce'])
def test_stale_exact_owner_or_chain_cannot_replay_ordinal(change):
    e = prepared(); request = e.request(0)
    if change == 'workspace': e.versions.new_workspace()
    if change == 'load': e._load_id = 'load-b'
    if change == 'revision': e._fence_current_document()
    if change == 'row': e._docs[0] = {'document_id': 'doc-b', 'document_revision': 0}
    if change == 'branch': e.history.undo[0], e.history.undo[1] = e.history.undo[1], e.history.undo[0]
    if change == 'coalesce': e.edit(4, coalesce=True)
    assert e.run(request)['phase'] == 'rejected' and e.restores == []


def test_real_same_photo_unrelated_edit_is_preserved_by_adjacent_sparse_patch():
    e = prepared(); graph = e.graph.snapshot()
    # This label was not written by any retained gesture.
    graph['faces'][e.faces[2]]['labels']['unrelated'] = 'retain'
    e.graph.commit(graph, expected_fence=e.graph.fence)
    result = e.run(e.request(1))
    assert result['phase'] == 'applied' and result['reached']['cursor'] == 1
    assert e.graph.snapshot()['faces'][e.faces[2]]['labels']['unrelated'] == 'retain'


def test_prewrite_proxy_refusal_after_one_edge_is_known_partial_not_target_success():
    e = prepared()
    e.history.undo[-2]['_proxy'] = (99, 99)
    result = e.run(e.request(0))
    assert result['phase'] == 'partial' and result['completed_steps'] == 1
    assert result['reached']['cursor'] == 2 and result['success'] is False
    assert result['outcome_unknown'] is False and e.restores == ['history_undo']
    assert e.__dict__.get('_history_navigation_unresolved') is None


def test_render_failure_even_normal_rollback_return_is_unknown_not_known_partial():
    e = prepared(); original = e.restore_frame
    def fail(snapshot, mode):
        frame = original(snapshot, mode)
        if mode == 'history_undo': raise RuntimeError('render failure after graph write')
        return frame
    e.history.ports = replace(e.history.ports, restore_frame=fail)
    result = e.run(e.request(0))
    assert result['phase'] == 'unknown' and result['reached'] is None
    assert result['outcome_unknown'] and not result['success']
    assert result['last_confirmed']['cursor'] == 3
    assert len(e.history.undo) == 3  # This alone must never imply rollback.
    for name, message in [('project', {'action': 'create'}), ('session', {'action': 'open'}), ('history', {'action': 'undo'})]:
        with pytest.raises(ValueError): N.guard(e, name, message)
    N.guard(e, 'project', {'action': 'open'})
    # Merely changing a workspace token is not verified project-open completion.
    e.versions.new_workspace()
    with pytest.raises(ValueError): N.guard(e, 'project', {'action': 'create'})


def test_shared_association_guard_is_not_bypassed_by_target_full_snapshot():
    e = prepared(); graph = e.graph.snapshot()
    graph['persons']['shared'] = {'anonymous': True}
    e.graph.commit(graph, expected_fence=e.graph.fence)
    before = e.graph.snapshot()
    result = e.run(e.request(0))
    assert result['phase'] == 'unknown' and result['reached'] is None
    # Existing canonical shared refusal remains in force; wrapper never retries.
    assert e.graph.snapshot()['persons'] == before['persons']
    assert e.history.undo and result['completed_steps'] == 0


def test_noop_read_retention_budget_and_cached_terminal_do_not_create_steps():
    e = prepared(); view = N.checkpoint(e)[0]
    result = e.run({'cmd': N.COMMAND, 'action': 'state', 'request_id': N.REQUEST_PREFIX + 'read'})
    assert result['phase'] == 'state' and set(result['view']) == N.VIEW_FIELDS
    assert result['view'] == view and e.restores == []
    request = e.request(1)
    result = e.run(request); restores = list(e.restores)
    assert e.run(request) == result and e.restores == restores
    result = e.run(e.request(1, 'noop'))
    assert result['phase'] == 'no_change' and e.restores == restores
    # Individually retained legacy stacks can exceed the combined limit. Refuse
    # navigation rather than silently evicting an endpoint during canonical redo.
    e.history.redo = [deepcopy(e._history_capture()) for _ in range(4)]
    view = N.checkpoint(e)[0]
    with pytest.raises(ValueError): N.plan({'cmd': N.COMMAND, 'action': 'navigate', 'request_id': N.REQUEST_PREFIX + 'wide', 'view': view, 'target': 0})


def test_partial_recovery_boundary_does_not_taint_but_unknown_does():
    e = prepared(); e._project_recovery_runtime = SimpleNamespace(revision=4, tainted=False, reason=None)
    boundary = {'message': {'cmd': N.COMMAND, 'action': 'navigate'}, 'started': True,
                'history_navigation_phase': 'partial'}
    assert N.finish(e, boundary)
    assert e._project_recovery_runtime.revision == 5 and not e._project_recovery_runtime.tainted
    boundary['history_navigation_phase'] = 'unknown'
    assert N.finish(e, boundary) and e._project_recovery_runtime.tainted


def test_proved_navigation_after_save_marks_dirty_without_new_history_entry():
    e = prepared(); e._project_dirty = False
    result = e.run(e.request(1))
    assert result['phase'] == 'applied' and e._project_dirty
    assert len(e.history.undo) + len(e.history.redo) == 3
    e._project_dirty = False
    assert e.run(e.request(1, 'same-cursor'))['phase'] == 'no_change'
    assert not e._project_dirty
    stale = e.request(0, 'stale-no-write'); stale['view']['digest'] = '0'*64
    assert e.run(stale)['phase'] == 'rejected' and not e._project_dirty


def test_known_partial_after_save_marks_dirty_only_for_proved_edges():
    e = prepared(); e.history.undo[-2]['_proxy'] = (99, 99); e._project_dirty = False
    result = e.run(e.request(0))
    assert result['phase'] == 'partial' and result['completed_steps'] == 1 and e._project_dirty


def test_post_fence_source_checkpoint_failure_has_no_stale_current_reached_claim():
    e = prepared(); e._project_dirty = False; request = e.request(0)
    capture = e._history_capture
    def source_changed_after_fence():
        if e.versions.version(e._docs[0]).revision != int(request['view']['revision']):
            raise ValueError('Source missing/changed while rebuilding exact people binding')
        return capture()
    e._history_capture = source_changed_after_fence
    result = e.run(request)
    assert result['phase'] == 'unknown' and result['reached'] is None
    assert result['last_confirmed'] == request['view'] and result['completed_steps'] == 0
    assert e.versions.version(e._docs[0]).revision == int(request['view']['revision']) + 1
    assert e.restores == [] and not e._project_dirty  # No guessed mutation success.


@pytest.mark.parametrize('command', ['hand_shape', 'background_material_library', 'creative_selection',
    'ingest_session', 'workflow_owner', 'torso_length', 'waist_length', 'head_size', 'body_slim',
    'photo_grain_state', 'colour_editor_preview', 'virtual_copy', 'project_recovery', 'managed_import',
    'canvas_guides', 'project_package', 'source_relocation', 'preset_organisation',
    'light_glow_cancel_read', 'upscale_restore_cancel_read', 'lens_blur_cancel_read',
    'portrait_crop_cancel', 'expression_replacement_cancel', 'eye_bag_cancel',
    'sample_library_cancel', 'semantic_colour_cancel'])
def test_namespace_rejects_foreign_reads_before_reader_controllers_and_executor(command):
    import json
    request = {'cmd': command, 'action': 'state', 'request_id': N.REQUEST_PREFIX + 'fixture'}
    assert not N.reader_namespace_allowed(json.dumps(request))
    with pytest.raises(ValueError): N.admit_namespace(request)
    request['request_id'] = 'ordinary-id'
    assert N.reader_namespace_allowed(json.dumps(request))
    N.admit_namespace(request)


def test_namespace_includes_nested_target_capture_and_operation_id_aliases():
    import json
    for alias in ['target_request_id', 'capture_id', 'operation_id', 'original_request_id', 'id']:
        request = {'cmd': 'color_picker_capture', 'request_id': 'ordinary-id',
                   'payload': {alias: N.REQUEST_PREFIX + 'fixture'}}
        assert not N.reader_namespace_allowed(json.dumps(request))
        with pytest.raises(ValueError): N.admit_namespace(request)
    e = prepared(); request = e.request(0)
    assert N.reader_namespace_allowed(json.dumps(request))
    N.admit_namespace(request)
    request['request_id'] = 'ordinary-id'
    with pytest.raises(ValueError): N.plan(request)
