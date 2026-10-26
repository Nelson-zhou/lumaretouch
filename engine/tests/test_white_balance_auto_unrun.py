"""AUTHORED / UNRUN. Controller/ABI specifications; no acceptance claim."""
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from lumaretouch_engine.white_balance_controller import WhiteBalanceController, WhiteBalancePorts
from lumaretouch_engine import white_balance_auto_native as N


def request(**patch):
    return {'cmd': 'white_balance', 'action': 'auto', 'request_id': 'auto-one', 'document_id': 'doc',
            'input_id': 'a'*64, 'recipe_document_id': 'recipe', 'recipe_revision': '7', **patch}


def fixture(gains=(1.2, 1.0, 0.85), outcome=True, phase='applied'):
    state = {'ev': 1., 'temperature_shift': 500., 'tint_shift': .2, 'contrast': 10.,
             'highlights': 20., 'shadows': 30., 'saturation': 40., 'reference_k': None, 'lit': True,
             'options': {'version': 1, 'algorithm': 'legacy-xyz-ratio-v1', 'picked_gains': [1., 1., 1.]}}
    history = {'undo_steps': 2, 'redo_steps': 1, 'history_max': 64}
    calls, events, settled, verified = [], [], [], []
    def prepare(p):
        if p['input_id'] != 'a'*64 or p['recipe_revision'] != '7':
            raise ValueError('stale input')
        return {k: p[k] for k in ('input_id', 'recipe_document_id', 'recipe_revision')} | {
            'gains': list(gains), 'diagnostic': {'origin': 'classic-statistical-estimate'}}
    def apply(patch):
        calls.append(deepcopy(patch))
        if outcome:
            state['options'] = deepcopy(patch['wb_options'])
        return outcome
    ports = WhiteBalancePorts(lambda: None, lambda: 'doc',
        lambda: {'document_id': 'doc', 'exposure': deepcopy(state), 'history': dict(history)},
        lambda _: pytest.fail('auto used manual apply port'), lambda: phase == 'unknown',
        prepare_auto=prepare, apply_auto=apply, auto_outcome=lambda: phase,
        settle_auto=settled.append, verify_auto=verified.append)
    return WhiteBalanceController(ports, events.append), state, history, calls, events, settled, verified


def test_exact_preparation_replacement_preserves_all_manual_controls_and_waits_for_history():
    c, state, history, calls, events, settled, verified = fixture()
    before = deepcopy(state); p = request()
    assert c.prepare(p); c.handle(p)
    assert not any(e['event'] == 'white_balance_result' for e in events)
    history.update(undo_steps=3, redo_steps=0); c.finish(p)
    assert events[-1]['success'] and events[-1]['phase'] == 'applied'
    assert events[-1]['original_request'] == p and events[-1]['history'] == {k:history[k] for k in ('undo_steps','redo_steps')}
    assert events[-1]['history_limit'] == 64
    assert {k: v for k, v in state.items() if k != 'options'} == {k: v for k, v in before.items() if k != 'options'}
    assert calls[0]['wb_options']['picked_gains'] == [1.2, 1.0, .85]
    assert settled == verified == ['applied']
    assert c.prepare(p) is False; c.finish(p)
    assert events[-1]['replayed'] and len(calls) == 1 and settled[-1] == 'replayed'


def test_noop_stops_before_mutation_fence_and_does_not_apply_or_change_history():
    c, _, history, calls, events, settled, verified = fixture(gains=(1., 1., 1.))
    p = request(); before = {k:history[k] for k in ('undo_steps','redo_steps')}
    assert c.prepare(p) is False; c.finish(p)
    assert events[-1]['no_change'] and events[-1]['phase'] == 'no_change'
    assert events[-1]['history'] == before and not calls
    assert settled == verified == ['no_change']


@pytest.mark.parametrize('patch', [{'input_id': 'b'*64}, {'recipe_revision': '8'}, {'gains': [1, 1, 1]}, {'capture_id': 'fake'}, {'document_id': 'other'}])
def test_stale_and_ui_gain_or_fake_picker_proofs_reject_prewrite(patch):
    c, _, _, calls, events, settled, _ = fixture(); p = request(**patch)
    assert c.prepare(p) is False; c.finish(p)
    assert not events[-1]['success'] and not events[-1]['outcome_unknown'] and events[-1]['no_write']
    assert not calls and settled[-1] == 'rejected'


@pytest.mark.parametrize('phase', ['no_write', 'rolled_back', 'unknown'])
def test_existing_transaction_failure_requires_exact_private_outcome(phase):
    c, _, _, _, events, settled, verified = fixture(outcome=False, phase=phase); p = request()
    assert c.prepare(p); c.handle(p); c.finish(p)
    r = events[-1]
    assert not r['success'] and r['outcome_unknown'] == (phase == 'unknown')
    assert settled[-1] == ('rejected' if phase == 'no_write' else phase)
    if phase == 'rolled_back':
        assert r['before'] == r['after'] and r['before_history'] == r['history'] and verified == ['rolled_back']


def test_history_failure_never_becomes_success_or_safe_replay():
    c, _, _, _, events, settled, _ = fixture(); p = request()
    assert c.prepare(p); c.handle(p); c.finish(p, 'history failure')
    assert events[-1]['phase'] == 'unknown' and events[-1]['requires_reload'] and settled[-1] == 'unknown'


def test_fixed_binary_abi_and_strict_reply(monkeypatch):
    monkeypatch.setattr(N, 'available', lambda: True)
    sent = []
    reply = {'version': 1, 'policy': N.POLICY, 'samples': 1024, 'accepted': 1024,
             'stable_tiles': 16, 'spread': 0., 'illuminant': [1., 1., 1.], 'gains': [1., 1., 1.]}
    def run(*args, **kwargs):
        sent.append(kwargs['input'])
        return SimpleNamespace(returncode=0, stdout=json.dumps(reply).encode(), stderr=b'')
    monkeypatch.setattr(N.subprocess, 'run', run)
    assert N.calculate([(0.2, 0.2, 0.2, 1., 0.)]*1024, [1., 1., 1.])['gains'] == [1., 1., 1.]
    assert len(sent[0]) == 41000 and sent[0][:8] == b'LRTAWB01'
    reply['gains'] = [4.01, 1., 1.]
    with pytest.raises(ValueError):
        N.calculate([(0.2, 0.2, 0.2, 1., 0.)]*1024, [1., 1., 1.])


def test_missing_helper_is_unavailable_not_a_python_fallback(monkeypatch):
    monkeypatch.setattr(N, 'available', lambda: False)
    with pytest.raises(ValueError, match='Rust'):
        N.calculate([(0.2, 0.2, 0.2, 1., 0.)]*1024, [1., 1., 1.])


@pytest.mark.parametrize('crop,rotated', [((100, 100, 101, 101), (1, 1)), ((0, 0, 31, 200), (200, 31)), ((0, 0, 200, 31), (200, 31))])
def test_large_proxy_cannot_upscale_tiny_crop_into_independent_statistics(crop, rotated):
    from lumaretouch_engine.white_balance_auto_sampling import require_support
    spec = SimpleNamespace(width=4096, height=4096, integer_crop=crop, rotated=rotated)
    with pytest.raises(ValueError, match='32×32'):
        require_support(spec)


@pytest.mark.parametrize('owner', ['auto', 'flip'])
def test_project_create_cannot_launder_unknown_live_recipe_or_taint(monkeypatch, owner):
    from lumaretouch_engine import white_balance_auto_recovery as A, final_canvas_flip_recovery as F
    from lumaretouch_engine import project_package_project_commands as P
    recovery = A if owner == 'auto' else F
    marker = '_white_balance_auto_unresolved' if owner == 'auto' else '_final_canvas_flip_unresolved_workspace'
    versions = SimpleNamespace(workspace='original')
    runtime = SimpleNamespace(tainted=True, reason=recovery.UNKNOWN_REASON, revision=7)
    rows = [{'unconfirmed': object()}]
    e = SimpleNamespace(_project_recovery_runtime=runtime, _document_versions=lambda: versions, _docs=rows,
                        PROJECT_KEYS={'action','name','directory'}, PROJECT_ACTIONS=('create','state'))
    setattr(e, marker, 'original')
    monkeypatch.setattr(P.PJ, 'new_project', lambda *_: pytest.fail('unknown state reached project creation'))
    with pytest.raises(ValueError, match='不能用作恢复'):
        P.handle(e, {'action':'create','name':'new','directory':'/fixture'}, lambda _: None, None)
    assert e._docs is rows and runtime.tainted and runtime.revision == 7
    versions.workspace = 'changed-id-only'
    with pytest.raises(ValueError): recovery.guard_create(e)  # A fresh ID is not restoration.
    runtime.tainted = False; runtime.reason = None
    recovery.guard_create(e)  # Clean state after a real open is not globally banned.
