"""UNRUN handoff fixtures: bounded global transfers and preset source ownership.

These are implementation candidates for Qoder/CI, not execution evidence.
No renderer, model, asset download, or native pixel result is mocked as accepted.
"""
from copy import deepcopy
from dataclasses import replace
import struct

import pytest

from lumaretouch_engine import creative_derived_source as SOURCE
from lumaretouch_engine import creative_derived_transfer as T
from lumaretouch_engine import scope as SC, preset_controller as P
from lumaretouch_engine import colour_editor_state as CE
from lumaretouch_engine.creative_document_assets import make_asset
from lumaretouch_engine.local_grade_preset_review import PresetReviews


def base(red=0.2):
    return make_asset('rgba', 1, 1, struct.pack('<4f', red, 0.3, 0.4, 1.0))


def state(*, derived=True):
    result = {'_exposure':(0., 0., 0., .1, .2, .3, .4), '_strength':0.,
              '_crop_rect':(0., 0., 1., 1.), '_crop_rotation':0., '_hsl':(0.,)*24}
    if derived: result['_creative_base'] = base()
    return result


def row(tmp_path, value):
    path = tmp_path/'original.bin'; path.write_bytes(b'original-source-provenance')
    return {'document_id':'stable-row', 'path':str(path), 'state':value, 'src_w':1, 'src_h':1}


def preset(modules=None):
    return {'id':'global', 'name':'global', 'kind':'color',
            'modules':modules or {SC.OP_EXPOSURE:{'ev':1.25}}}


def test_allowlist_is_closed_and_global_colour_editor_uses_actual_schema():
    assert SC.DERIVED_PARAMETER_OPS == {
        'lnx.exposure.v1', 'lnx.white_balance.v1', 'lnx.levels.v1', 'lnx.curves.v1',
        'lnx.hsl.v1', 'lnx.extended_tone.v1', 'lnx.photo_detail.v1',
        'lnx.photo_grain.v1', 'lnx.colour_grading.v1', 'lnx.primary_calibration.v1',
        'lnx.selective_colour.v1', 'lnx.colour_editor.v1',
    }
    modules = {SC.OP_EXPOSURE:{'ev':1.25}, SC.COLOUR_EDITOR.OP:{'recipe':CE.neutral()}}
    assert T.require_modules(state(), modules)[SC.COLOUR_EDITOR.OP]['recipe']['scope'] == 'all'
    for scope in ('local', 'global'):
        bad = deepcopy(modules); bad[SC.COLOUR_EDITOR.OP]['recipe']['scope'] = scope
        with pytest.raises(ValueError): T.require_modules(state(), bad)
    bad = deepcopy(modules); bad[SC.COLOUR_EDITOR.OP]['recipe']['source'] = 'claimed-safe'
    with pytest.raises(ValueError): T.require_modules(state(), bad)


@pytest.mark.parametrize('operation', [
    'lnx.skin.v1', 'lnx.blemish.v1', 'lnx.mask.v1', 'lnx.local_grade.v1',
    'lnx.studio_background.v1', 'lnx.id_background.v1', 'lnx.sky_replacement.v1',
    'lnx.optics.v1', 'lnx.optics_auto.v1', 'lnx.reference_color.v1',
    'lnx.semantic_colour.v1', 'lnx.brow_shape.v1', 'lnx.eye_light.v1',
    'lnx.custom_lut.v1', 'unknown.module',
])
def test_neutral_unsupported_modules_never_enter_general_derived_route(operation):
    with pytest.raises(ValueError): T.require_modules(state(), {operation:{}})
    with pytest.raises(ValueError): SC.apply_modules(state(), {operation:{}})


def test_derived_source_proof_restricts_original_target_and_dormant_states(tmp_path):
    derived = state(); proof = SOURCE.row_proof(row(tmp_path, derived)); original = state(derived=False)
    unsupported = {SC.OP_SKIN:{'strength':0.}}
    assert T.require_modules(original, unsupported) is unsupported
    with pytest.raises(ValueError): T.require_modules(original, unsupported, proof)
    with pytest.raises(ValueError): T.require_modules(original, unsupported, related_states=(derived,))
    with pytest.raises(ValueError): SC.restore_modules(original, derived, [SC.OP_SKIN])


def test_candidate_keeps_shared_exposure_subfields_source_and_runtime_identity():
    before = state(); opaque_analysis = object(); before['_target_analysis'] = opaque_analysis
    modules = {SC.OP_EXPOSURE:{'ev':1.25}}
    after = SC.apply_modules(before, modules)
    assert after['_exposure'][1:] == before['_exposure'][1:]
    assert T.require_candidate(before, after, modules) is after
    for key, value in (
        ('_creative_base', base(.7)), ('_target_analysis', object()),
        ('_strength', .1), ('_exposure', (1.25, 0., 0., .9, .2, .3, .4)),
    ):
        changed = {**after, key:value}
        with pytest.raises(ValueError): T.require_candidate(before, changed, modules)
    assert before['_target_analysis'] is opaque_analysis


@pytest.mark.parametrize('rgba', [(0.1, 0.1, 0.1, .5), (1.1, .3, .4, 1.), (-.1, .3, .4, 1.)])
def test_parked_and_dormant_hdr_alpha_sources_refuse_without_clipping(rgba):
    unsupported = state()
    unsupported['_creative_base'] = make_asset('rgba', 1, 1, struct.pack('<4f', *rgba))
    frozen_bytes = unsupported['_creative_base']['content']
    modules = {SC.OP_EXPOSURE:{'ev':1.}}
    with pytest.raises(ValueError): T.require_modules(unsupported, modules)
    with pytest.raises(ValueError): T.require_modules(state(derived=False), modules, related_states=(unsupported,))
    with pytest.raises(ValueError): T.require_candidate(unsupported, dict(unsupported), modules)
    assert unsupported['_creative_base']['content'] is frozen_bytes


@pytest.mark.parametrize('change', ['pixels', 'original', 'removed_base', 'row_identity', 'revision'])
def test_frozen_global_preset_binds_effective_source_provenance_and_context(tmp_path, change):
    value = state(); target = row(tmp_path, value); reviews = PresetReviews()
    result = reviews.prepare(preset(), value, target, 'load-1', '7', None)
    token = result['preflight_token']; changed = deepcopy(value); revision = '7'
    assert result['source_proof'] == SOURCE.row_proof(target)
    if change == 'pixels': changed['_creative_base'] = base(.7)
    elif change == 'original': (tmp_path/'original.bin').write_bytes(b'replaced-original')
    elif change == 'removed_base': changed.pop('_creative_base')
    elif change == 'row_identity': target['document_id'] = 'reimported-row'
    else: revision = '8'
    with pytest.raises(ValueError): reviews.claim(token, 'global', changed, target, 'load-1', revision)
    assert token in reviews.pending


def test_frozen_review_uses_capture_not_stale_parked_state_and_one_use(tmp_path):
    current = state(); target = row(tmp_path, state(derived=False)); reviews = PresetReviews()
    frozen = preset(); result = reviews.prepare(frozen, current, target, 'load-1', '7', None)
    token = result['preflight_token']; frozen['modules'][SC.OP_EXPOSURE]['ev'] = 4.
    record = reviews.claim(token, 'global', current, target, 'load-1', '7')
    assert record['modules'][SC.OP_EXPOSURE]['ev'] == 1.25
    assert record['source_proof']['creative_source']['sha256'] == current['_creative_base']['id'][7:]
    with pytest.raises(ValueError): reviews.claim(token, 'global', current, target, 'load-1', '7')


def test_frozen_review_compares_normalized_stored_parameters(tmp_path):
    current = state(); target = row(tmp_path, current); reviews = PresetReviews()
    # An integer input normalizes to float but is not a different reviewed value.
    token = reviews.prepare(preset({SC.OP_EXPOSURE:{'ev':1}}), current, target,
                            'load-1', '7', None)['preflight_token']
    record = reviews.claim(token, 'global', current, target, 'load-1', '7')
    assert record['modules'][SC.OP_EXPOSURE]['ev'] == 1.


@pytest.mark.parametrize('field', ['modules', 'preset_modules', 'source_proof'])
def test_frozen_claim_rejects_unsupported_or_proofless_record_before_consumption(tmp_path, field):
    value = state(); target = row(tmp_path, value); reviews = PresetReviews()
    token = reviews.prepare(preset(), value, target, 'load-1', '7', None)['preflight_token']
    record = reviews.pending[token]
    if field == 'modules': record['modules'] = {SC.OP_SKIN:{'strength':0.}}
    elif field == 'preset_modules': record['preset']['modules'] = {SC.OP_SKIN:{'strength':0.}}
    else: record.pop('source_proof')
    with pytest.raises(ValueError): reviews.claim(token, 'global', value, target, 'load-1', '7')
    assert token in reviews.pending


def controller(tmp_path, monkeypatch, stored):
    value = state(); target = row(tmp_path, value); events = []; writes = []
    def replay(candidate, **kwargs):
        if SOURCE.record(candidate) is not None and kwargs.get('mode') == 'preset':
            assert kwargs.get('strict_local') is True
        writes.append(deepcopy(candidate)); value.clear(); value.update(candidate)
        return {'event':'frame', 'render_ms':1}
    ports = P.PresetPorts(lambda _:None, lambda:'load-1', lambda:deepcopy(value), replay,
        lambda:('ok', ''), lambda:{'document_id':'load-1'}, lambda:None,
        target_row=lambda:target, revision=lambda:'7')
    owner = P.PresetController(ports, events.append)
    monkeypatch.setattr(P.PS, 'find', lambda _:deepcopy(stored))
    return owner, value, target, events, writes


def send(owner, events, **extra):
    request = {'cmd':'preset', 'action':'apply', 'request_id':'apply-1',
               'document_id':'load-1', 'id':'global', **extra}
    owner.handle_command(request); owner.finish(request)
    return events[-1], request


def test_actual_stored_preset_not_legacy_request_scope_claims_decides_admission(tmp_path, monkeypatch):
    owner, value, _, events, writes = controller(tmp_path, monkeypatch, preset({SC.OP_SKIN:{'strength':0.}}))
    # Legacy transport permits module_scope, but it cannot sanitize stored skin.
    request = {'cmd':'preset', 'action':'apply', 'id':'global', 'module_scope':[SC.OP_EXPOSURE]}
    owner.handle_command(request)
    assert events[-1]['event'] == 'error' and not writes and value['_strength'] == 0.


def test_completed_receipt_replays_before_fresh_source_or_edit_guard(tmp_path, monkeypatch):
    owner, value, target, events, writes = controller(tmp_path, monkeypatch, preset())
    result, request = send(owner, events)
    assert result['success'] and len(writes) == 1
    assert result['source_proof'] == SOURCE.row_proof(target)
    value['_creative_base'] = base(.7)
    owner.ports = replace(owner.ports, guard=lambda _:'blocked fresh edit', document_id=lambda:'load-2')
    monkeypatch.setattr(P.PS, 'find', lambda _:pytest.fail('receipt replay must not reload a preset'))
    owner.handle_command(request); owner.finish(request)
    assert events[-1]['success'] and events[-1]['replayed'] and len(writes) == 1


def test_unsupported_frozen_preset_rejects_before_claim_and_render(tmp_path, monkeypatch):
    owner, value, target, events, writes = controller(tmp_path, monkeypatch, preset())
    token = owner.reviews.prepare(preset(), value, target, 'load-1', '7', None)['preflight_token']
    owner.reviews.pending[token]['modules'] = {SC.OP_SKIN:{'strength':0.}}
    result, _ = send(owner, events, preflight_token=token)
    assert not result['success'] and not result['outcome_unknown'] and not writes
    assert token in owner.reviews.pending


def test_derived_save_rejects_unsupported_actual_state_before_storage(tmp_path, monkeypatch):
    owner, value, _, _, writes = controller(tmp_path, monkeypatch, preset())
    monkeypatch.setattr(P.PS, 'save', lambda *a, **kw:pytest.fail('unsupported save cannot reach storage'))
    with pytest.raises(ValueError):
        owner.save({'id':'saved', 'name':'saved', 'module_scope':[SC.OP_SKIN]})
    value[CE.KEY] = {**CE.neutral(), 'scope':'local'}
    with pytest.raises(ValueError):
        owner.save({'id':'saved', 'name':'saved', 'module_scope':[SC.COLOUR_EDITOR.OP]})
    assert not writes


def test_cross_image_crop_requires_actual_target_visual_review():
    with pytest.raises(SC.ScopeError):
        SC.check_derived_modules({SC.OP_CROP:SC.params_of({},[SC.OP_CROP])[SC.OP_CROP]})
