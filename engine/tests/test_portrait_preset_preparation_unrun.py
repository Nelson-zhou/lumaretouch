"""Authored UNRUN: serial fresh-group preparation and exact recovery receipts.

Mocks check orchestration contracts, not decoding, model output, loaded portrait
owners, native transport, numerical quality, build viability or performance.
No tests, product imports or inference were executed while authoring this file.
"""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from lumaretouch_engine import portrait_preset_preparation as P
from lumaretouch_engine import portrait_preset_batch as G
from lumaretouch_engine import project_recovery_runtime as R


def request(**changes):
    return {'cmd': 'batch', 'action': 'portrait_preset_prepare', 'request_id': 'prepare-1',
            'docs': ['first', 'second'], 'preset_id': 'preset-1', 'preset_sha256': 'a' * 64,
            **changes}


@pytest.fixture
def harness(monkeypatch):
    trace = []
    neutral = {'neutral': True, '_proxy': [10, 10]}
    rows = [{'document_id': name, 'path': '/' + name, 'state': deepcopy(neutral),
             'undo': [], 'redo': [], 'copy_number': 0, 'revision': 1}
            for name in ('editor', 'first', 'second', 'third')]
    runtime = SimpleNamespace(tainted=False, revision=0, reason='')
    owner = SimpleNamespace(capture_document=lambda asset: {'asset': asset, 'faces': []})
    engine = SimpleNamespace(_docs=rows, _doc_index=0, _load_id='editor-load-0',
        _image_loaded=True, _project_dirty=False, _proxy_budget=100,
        _people_active_context=object(), _project_recovery_runtime=runtime,
        _people_owner=lambda: owner, _remember_current=lambda: None,
        _fresh_doc_state=lambda: deepcopy(neutral), EDIT_CMDS=())
    versions = SimpleNamespace(workspace='workspace-1', version=lambda row: row['revision'])
    failures = {}
    batch = SimpleNamespace(versions=versions)
    group = SimpleNamespace(engine=engine, batch=batch)
    group._row = lambda doc: next((i, row) for i, row in enumerate(rows)
                                 if row['document_id'] == doc and i != engine._doc_index)
    monkeypatch.setattr(P, '_preset', lambda *args: {'modules': {'lnx.skin.v1': {}}})
    monkeypatch.setattr(P.SOURCE, 'record', lambda state: None)
    proof = lambda row: {'asset_sha256': row['document_id']}
    monkeypatch.setattr(P.SOURCE, 'row_proof', proof)
    monkeypatch.setattr(P.SOURCE, 'verify_row', lambda row, expected: expected == proof(row) or
                        (_ for _ in ()).throw(ValueError('source changed')))
    monkeypatch.setattr(P.V, 'peek_graph', lambda engine, row: None)

    def dispatch(engine, payload, check):
        check()
        assert payload['cmd'] == 'load_image'
        engine._doc_index = next(i for i, row in enumerate(rows)
                                 if row['document_id'] == payload['document_id'])
        engine._load_id = 'load-' + str(len(trace))
        trace.append(('load', payload['document_id'], engine._load_id))

    class Preparation:
        def __init__(self, engine, row, check):
            check()
            self.row, self.load_id, self.expected = row, engine._load_id, None
            assert P.V.current_row(engine) is row
            trace.append(('bind', row['document_id'], self.load_id))

        def analyse(self):
            assert engine._load_id == self.load_id
            trace.append(('analyse', self.row['document_id'], self.load_id))
            self.row['state'] = {'prepared': True}
            failure = failures.get(self.row['document_id'])
            if failure == 'unknown':
                runtime.tainted = True
                raise ValueError('analysis outcome unknown')
            self.expected = 'owned-current-proof'
            if failure == 'known':
                raise ValueError('not a single face')

        def assert_current(self):
            assert engine._load_id == self.load_id
            assert P.V.current_row(engine) is self.row

        def restore(self):
            self.assert_current()
            assert not runtime.tainted
            trace.append(('restore-target', self.row['document_id'], self.load_id))
            self.row['state'] = deepcopy(neutral)

    def freeze(payload):
        assert P.V.current_row(engine) is rows[0]
        assert all(group._row(doc)[1]['state'] == {'prepared': True} for doc in payload['docs'])
        trace.append(('freeze', tuple(payload['docs']), engine._load_id))
        return {'success': True, 'preflight_token': 'b' * 32, 'targets': payload['docs']}

    monkeypatch.setattr(P, 'dispatch', dispatch)
    monkeypatch.setattr(P, 'SkinPreparation', Preparation)
    group._prepare = freeze
    return SimpleNamespace(engine=engine, group=group, trace=trace, rows=rows,
                           failures=failures, preparation=P.GroupPreparation(group))


def test_serial_real_load_identity_and_freeze_only_after_editor_return(harness):
    h = harness
    result = h.preparation.run(request())
    assert result['success'] and result['editor_restored']
    assert result['outcome_unknown'] is False
    assert [entry[:2] for entry in h.trace] == [
        ('load', 'first'), ('bind', 'first'), ('analyse', 'first'),
        ('load', 'second'), ('bind', 'second'), ('analyse', 'second'),
        ('load', 'editor'), ('freeze', ('first', 'second'))]
    assert h.trace[1][2] != h.trace[4][2]
    assert result['editor_load_id'] == h.engine._load_id
    previous = deepcopy(h.trace)
    assert h.preparation.run(request()) == result
    assert h.trace == previous  # Exact replay is a receipt read, not more inference.


def test_known_partial_restores_failed_target_then_editor_without_freeze(harness):
    h = harness
    h.failures['second'] = 'known'
    result = h.preparation.run(request(docs=['first', 'second', 'third']))
    assert result['success'] is False and result['outcome_unknown'] is False
    assert result['editor_restored'] is True and result['no_write'] is False
    assert [row['status'] for row in result['preparation_results']] == ['prepared', 'failed', 'not_started']
    assert h.rows[1]['state'] == {'prepared': True}
    assert h.rows[2]['state'] == h.rows[3]['state']
    assert h.trace[-2][0:2] == ('restore-target', 'second')
    assert h.trace[-1][0:2] == ('load', 'editor')
    assert not any(entry[0] == 'freeze' for entry in h.trace)


def test_tainted_attempt_stays_unknown_and_exact_replay_never_retries(harness):
    h = harness
    h.failures['second'] = 'unknown'
    result = h.preparation.run(request())
    assert result['outcome_unknown'] is True and result['editor_restored'] is False
    assert result['no_write'] is False
    assert h.engine._project_recovery_runtime.tainted
    previous = deepcopy(h.trace)
    assert h.preparation.run(request()) == result
    assert previous == h.trace
    assert not any(entry[0] in ('freeze', 'restore-target') for entry in h.trace)


def test_mismatched_claim_cannot_become_known_no_write(harness):
    h = harness
    h.failures['first'] = 'unknown'
    h.preparation.run(request())
    group = object.__new__(G.PortraitPresetBatch)
    group.engine, group.preparation = h.engine, h.preparation
    group._prune = lambda: None
    group.batch = SimpleNamespace(editor=SimpleNamespace(guard=lambda label: None),
        preflight=SimpleNamespace(emit_result=lambda payload, result: result))
    changed = request(docs=['third'])
    result = group.handle(changed)
    assert result['outcome_unknown'] is True
    assert result['no_write'] is False and result['editor_restored'] is False
    assert result['portrait_preset_docs'] == ['third']


@pytest.mark.parametrize('no_write,expected_revision', [(True, 0), (False, 1)])
def test_private_known_restored_boundary_settles_without_taint(monkeypatch, no_write, expected_revision):
    runtime = SimpleNamespace(tainted=False, revision=0, reason='')
    engine = SimpleNamespace(_project_recovery_runtime=runtime, EDIT_CMDS=())
    payload = request()
    boundary = {'message': payload, 'engine': engine, 'started': True,
                'returned': True, 'failed': True}
    monkeypatch.setattr(R._local, 'boundary', boundary, raising=False)
    P.observe_outcome(engine, payload, {'outcome_unknown': False,
        'editor_restored': True, 'no_write': no_write})
    R.finish(engine, boundary)
    assert runtime.tainted is False and runtime.revision == expected_revision


def test_json_flags_or_equal_but_nonidentical_request_cannot_settle_recovery(monkeypatch):
    runtime = SimpleNamespace(tainted=False, revision=0, reason='')
    engine = SimpleNamespace(_project_recovery_runtime=runtime, EDIT_CMDS=())
    payload = request()
    boundary = {'message': payload, 'engine': engine, 'started': True,
                'returned': True, 'failed': True}
    monkeypatch.setattr(R._local, 'boundary', boundary, raising=False)
    P.observe_outcome(engine, deepcopy(payload), {'outcome_unknown': False,
        'editor_restored': True, 'no_write': True})
    assert 'portrait_preparation_outcome' not in boundary
    R.finish(engine, boundary)
    assert runtime.tainted is True
