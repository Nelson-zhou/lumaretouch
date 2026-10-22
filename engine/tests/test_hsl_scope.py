"""Versioned HSL transfer preserves the existing tuple and pixel algorithm."""
from copy import deepcopy
from types import SimpleNamespace
import json
import numpy as np
import pytest
from lumaretouch_engine import hsl_recipe as H, scope as S
from lumaretouch_engine.ops.hsl import hsl_np


def recipe():
    value = H.default_recipe(); value['bands'][:3] = [20., -15., 10.]
    return value


@pytest.mark.parametrize('value', [True, '1', None, float('nan'), float('inf'), 10**400, 61.])
def test_recipe_rejects_invalid_hue(value):
    r = recipe(); r['bands'][0] = value
    with pytest.raises(ValueError): H.check_recipe(r)


@pytest.mark.parametrize('field,value', [('version', True), ('version', 1.), ('version', 2),
    ('algorithm', 'true-hsl'), ('bands', [0.] * 23), ('bands', [0.] * 25)])
def test_recipe_rejects_unknown_contract(field, value):
    r = recipe(); r[field] = value
    with pytest.raises(ValueError): H.check_recipe(r)


def test_recipe_exact_keys_bounds_and_copy_isolation():
    r = recipe()
    for field in list(r):
        bad = deepcopy(r); del bad[field]
        with pytest.raises(ValueError): H.check_recipe(bad)
    with pytest.raises(ValueError): H.check_recipe({**r, 'extra': 0})
    for index in (1, 2):
        bad = deepcopy(r); bad['bands'][index] = 101
        with pytest.raises(ValueError): H.check_recipe(bad)
    clean = H.check_recipe(r); r['bands'][0] = 0
    assert clean['bands'][0] == 20
    assert H.check_recipe(H.default_recipe()) == H.default_recipe()


def test_scoped_transfer_preserves_pixels_and_other_modules():
    bands = tuple(recipe()['bands']); original = {'_hsl': bands, '_exposure': (1.,)*7, 'keep': object()}
    params = S.params_of(original, [S.OP_HSL]); restored = S.apply_modules(original, params)
    assert restored['_hsl'] == bands and isinstance(restored['_hsl'], tuple)
    assert restored['keep'] is original['keep'] and restored['_exposure'] == original['_exposure']
    pixels = np.linspace(.03, .95, 300, dtype=np.float32).reshape(10, 10, 3)
    np.testing.assert_array_equal(hsl_np(pixels, bands), hsl_np(pixels, restored['_hsl']))
    params[S.OP_HSL]['recipe']['bands'][0] = -10
    assert restored['_hsl'][0] == 20 and original['_hsl'][0] == 20
    bad = {S.OP_EXPOSURE: {'ev': 2}, S.OP_HSL: {'recipe': {**recipe(), 'algorithm': 'unknown'}}}
    with pytest.raises(S.ScopeError): S.apply_modules(original, bad)
    assert original['_exposure'] == (1.,)*7


def test_state_validates_before_mutation_and_keeps_legacy_padding():
    from lumaretouch_engine.server import Engine
    e = Engine('hsl-state'); old = e._capture_state(); bad = deepcopy(old)
    bad['_strength'] = .7; bad['_hsl'] = [float('nan')] + [0.]*23
    with pytest.raises(ValueError): e._apply_state(bad)
    assert e._strength == old['_strength'] and e._hsl == H.NEUTRAL
    old.pop('_hsl'); e._apply_state(old); assert e._hsl == H.NEUTRAL
    old['_hsl'] = [20, 0, 0]; e._apply_state(old)
    assert e._hsl == (20.,) + (0.,)*23


def test_command_scoped_save_roundtrip_and_empty_scope_rejection(monkeypatch, tmp_path):
    from lumaretouch_engine import server
    monkeypatch.setenv('LRT_PRESET_DIR', str(tmp_path)); events = []
    monkeypatch.setattr(server, 'emit', events.append)
    e = server.Engine('hsl-save'); e._hsl = tuple(recipe()['bands']); e._guard_editable = lambda _: None
    e.cmd_preset({'action': 'save', 'id': 'hsl-only', 'module_scope': [S.OP_HSL]})
    result = events[-1]; assert result['event'] == 'preset_saved'
    saved = server.PS.load_file(result['path']); assert list(saved['modules']) == [S.OP_HSL]
    assert saved['modules'][S.OP_HSL]['recipe'] == recipe()
    e.cmd_preset({'action': 'save', 'id': 'empty', 'module_scope': []})
    assert events[-1]['event'] == 'error' and not (tmp_path/'empty.json').exists()


def test_pipeline_hsl_install_failure_is_not_silently_cleared(monkeypatch):
    from lumaretouch_engine import server, vram
    def fail(_): raise RuntimeError('injected HSL installation failure')
    monkeypatch.setattr(vram, 'make_pipeline', lambda *args: SimpleNamespace(fallback=None, set_hsl=fail))
    e = server.Engine('hsl-install'); e._hsl = tuple(recipe()['bands'])
    with pytest.raises(RuntimeError, match='installation failure'):
        e._attach_pipeline(np.zeros((64, 64, 3), np.uint8))
    assert e._hsl == tuple(recipe()['bands'])


@pytest.mark.parametrize('rollback_fails', [False, True])
def test_preset_render_failure_rolls_back_or_disables_session(monkeypatch, rollback_fails):
    from lumaretouch_engine import server
    events = []; monkeypatch.setattr(server, 'emit', events.append)
    monkeypatch.setattr(server.PS, 'find', lambda _: {'id': 'hsl', 'kind': 'custom', 'name': 'HSL',
                                                   'modules': {S.OP_HSL: {'recipe': recipe()}}})
    e = server.Engine('hsl-preset-failure'); e._guard_editable = lambda _: None
    e._vram = object(); previous = e._capture_state()
    def replay(state, **kw):
        e._apply_state(state)
        if rollback_fails or kw['mode'] == 'preset': raise RuntimeError('injected render failure')
        return {'event': 'frame', 'mode': kw['mode']}
    e._replay_state = replay; e.cmd_preset({'action': 'apply', 'id': 'hsl'})
    assert events[-1]['event'] == 'error' and not any(v['event'] == 'preset_applied' for v in events)
    assert e._hsl == previous['_hsl']
    assert (e._vram is None) == rollback_fails


def test_frozen_hsl_batch_and_scoped_undo_preserve_later_exposure():
    from test_batch_sync_controller import fixture
    c, rows, _, events, _, _ = fixture(); rows[0]['state']['_hsl'] = tuple(recipe()['bands'])
    c.handle_command({'action': 'preflight', 'docs': [1], 'module_scope': [S.OP_HSL], 'request_id': 'review'})
    token = events[-1]['preflight_token']; rows[0]['state']['_hsl'] = H.NEUTRAL
    c.versions.advance(rows[0]); c.handle_command({'action': 'commit', 'preflight_token': token, 'request_id': 'commit'})
    result = events[-1]; assert result['event'] == 'batch_result' and result['request_id'] == 'commit'
    assert result['success'] and rows[1]['state']['_hsl'] == tuple(recipe()['bands'])
    rows[1]['state']['_exposure'] = (2., 0., 0., 0., 0., 0., 0.)
    c.handle_command({'action': 'undo', 'batch_id': result['batch_id']})
    assert rows[1]['state']['_hsl'] == H.NEUTRAL and rows[1]['state']['_exposure'][0] == 2


def test_registry_has_exact_neutral_and_existing_ranges():
    from pathlib import Path
    registry = json.loads((Path(__file__).resolve().parents[2]/'docs/p0/registry-extensions.json').read_text())
    entry = next(e for e in registry['entries'] if e['operation_id'] == S.OP_HSL)
    assert entry['neutral'] == H.default_recipe() and entry['parameter_key'] == 'recipe'
    assert entry['hard_range'] == {'band_count': 8, 'values_per_band': 3, 'dh': [-60, 60], 'ds': [-100, 100], 'dl': [-100, 100]}


def test_preset_match_tracks_only_hsl_and_recovers_when_restored():
    from lumaretouch_engine.server import Engine
    e = Engine('hsl-match'); e._hsl = tuple(recipe()['bands'])
    e._preset_last = {'id': 'hsl', 'name': 'HSL', 'ops': [S.OP_HSL],
                      'params': S.params_of(e._capture_state(), [S.OP_HSL])}
    expected = {'id': 'hsl', 'name': 'HSL'}
    e._exposure = (1., 0., 0., 0., 0., 0., 0.); assert e._preset_last_applied() == expected
    e._hsl = H.NEUTRAL; assert e._preset_last_applied() is None
    e._hsl = tuple(recipe()['bands']); assert e._preset_last_applied() == expected


def test_hsl_batch_target_conflict_duplicate_receipt_and_undo_conflict():
    from test_batch_sync_controller import fixture
    c, rows, _, events, _, _ = fixture(); rows[0]['state']['_hsl'] = tuple(recipe()['bands'])
    c.handle_command({'action': 'preflight', 'docs': [1, 2], 'module_scope': [S.OP_HSL], 'request_id': 'review'})
    token = events[-1]['preflight_token']; rows[1]['state']['_hsl'] = (30.,) + H.NEUTRAL[1:]
    c.versions.advance(rows[1])
    c.handle_command({'action': 'commit', 'preflight_token': token, 'request_id': 'first'})
    result = events[-1]; assert result['success'] and result['targets'] == [2]
    assert rows[1]['state']['_hsl'][0] == 30
    history = deepcopy(rows[2]['undo'])
    c.handle_command({'action': 'commit', 'preflight_token': token, 'request_id': 'duplicate'})
    assert events[-1]['replayed'] and rows[2]['undo'] == history
    rows[2]['state']['_hsl'] = (5.,) + H.NEUTRAL[1:]; c.versions.advance(rows[2])
    c.handle_command({'action': 'undo', 'batch_id': result['batch_id'], 'request_id': 'undo'})
    assert events[-1]['restored'] == [] and events[-1]['conflicts'][0]['index'] == 2
    assert rows[2]['state']['_hsl'][0] == 5


def test_batch_double_render_failure_invalidates_without_parked_writes():
    from dataclasses import replace
    from test_batch_sync_controller import fixture
    c, rows, current, events, _, _ = fixture(); rows[0]['state']['_hsl'] = tuple(recipe()['bands'])
    c.handle_command({'action': 'preflight', 'docs': [1, 2], 'module_scope': [S.OP_HSL], 'request_id': 'review'})
    token = events[-1]['preflight_token']; current[0] = 1; parked = deepcopy(rows[2]); invalidated = []
    def fail(state, **kwargs): raise RuntimeError('injected HSL render and rollback failure')
    c.editor = replace(c.editor, replay=fail, invalidate=lambda: invalidated.append(True))
    c.handle_command({'action': 'commit', 'preflight_token': token, 'request_id': 'commit'})
    assert not events[-1]['success'] and invalidated == [True]
    assert rows[2] == parked and c.ledger == {}
