"""AUTHORED / UNRUN: preset-only spill visual review transaction contracts.

The visual ports below are deliberately synthetic. They do not decode a photo,
run the full renderer, infer masks, assess spill quality, or establish native/UI
acceptance. Synthetic source files and compact image hashes test orchestration,
acknowledgment binding and rollback only. No fixtures were imported, collected
or executed during this source-only authoring task.
"""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import struct
from types import SimpleNamespace

import pytest

from lumaretouch_engine import creative_derived_source as SOURCE
from lumaretouch_engine import id_background_state as ID
from lumaretouch_engine import id_background_support as SUPPORT
from lumaretouch_engine import local_grade_preset_review as PR
from lumaretouch_engine import local_mask_state as MASK
from lumaretouch_engine import optics_auto_scope as OA
from lumaretouch_engine import optics_state as OPTICS
from lumaretouch_engine import preset_controller as PC
from lumaretouch_engine import reference_color_scope as RC
from lumaretouch_engine import reference_color_state as REFERENCE
from lumaretouch_engine import scope as SC
from lumaretouch_engine import spill_removal_scope as SPILL
from lumaretouch_engine import spill_transfer_review as REVIEW
from lumaretouch_engine.creative_document_assets import make_asset
from lumaretouch_engine.preset_transaction import PresetApplyError


def digest(value):
    # Only a fixture fingerprint, not a substitute for the renderer identity.
    return sha256(json.dumps(value, sort_keys=True, allow_nan=False,
        default=lambda data: {'fixture_bytes_sha256': sha256(data).hexdigest()}).encode()).hexdigest()


def owned_id(source):
    mask = MASK.empty(); mask['source'] = deepcopy(source)
    mask['recipe']['objects'] = [{'id': 'target-owned', 'name': 'Target range',
        'enabled': True, 'kind': 'brush', 'operation': 'add', 'opacity': 1.,
        'feather': 0., 'points': [[.5, .5]], 'axes': [[.1, 0.], [0., .1]]}]
    value = ID.empty(); value.update(enabled=True, source=deepcopy(source))
    value['support']['subject'] = {'version': 1, 'category': 'subject',
        'reviewed': True, 'mask': mask, 'recipe_sha256': SUPPORT.digest(mask)}
    return ID.check(value)


def preset():
    return {'id': 'spill', 'name': 'Spill scalar review', 'kind': 'custom',
        'modules': {SPILL.OP: {'enabled': True, 'strength': 81.}}}


def fixture(tmp_path, *, derived=False):
    path = tmp_path / 'synthetic-original.bin'; path.write_bytes(b'not-a-decoded-photo')
    state = {'_crop_rect': (0., 0., 1., 1.), '_crop_rotation': 0.,
        '_exposure': (0.,) * 7, '_unselected': 'target-owned'}
    if derived:
        state['_creative_base'] = make_asset('rgba', 32, 24,
            struct.pack('<4f', .2, .3, .4, 1.) * (32 * 24))
    row = {'document_id': 'row-target', 'path': str(path), 'src_w': 32, 'src_h': 24,
        'state': state, 'people': 'target-owned-people', 'undo': [], 'redo': []}
    state['_id_background'] = owned_id(SOURCE.binding(state, str(path), (32, 24)))
    state['_id_background_bundle'] = None
    context = SimpleNamespace(row=row, revision='7', document='loaded', events=[],
        calls=[], replays=[], invalid=[], reviews=PR.PresetReviews(), preset=preset())

    def proof(current, before, candidate, document_id, revision):
        source = SOURCE.row_proof({**current, 'state': before})
        return REVIEW.checked({'version': 1, 'document_id': document_id, 'revision': revision,
            'source_proof': source, 'before_sha256': digest(before),
            'candidate_sha256': digest(candidate), 'before_people_sha256': digest(current['people']),
            'candidate_people_sha256': digest(current['people']), 'source_size': [32, 24],
            'before_output_size': [32, 24], 'after_output_size': [32, 24],
            'parameters': SPILL.params_of(candidate),
            'before': {'mime': 'image/png', 'width': 32, 'height': 24, 'sha256': digest(before)},
            'after': {'mime': 'image/png', 'width': 32, 'height': 24, 'sha256': digest(candidate)}})

    def prepare(current, before, candidate, document_id, revision):
        context.calls.append(('prepare', deepcopy(before), deepcopy(candidate), document_id, revision))
        private = proof(current, before, candidate, document_id, revision)
        public = deepcopy(private)
        for key in ('before', 'after'):
            public[key]['base64'] = 'Zml4dHVyZS1vbmx5'  # Not a rendered PNG.
        return private, public

    def verify(current, before, candidate, document_id, revision, record):
        context.calls.append(('verify', deepcopy(before), deepcopy(candidate), document_id, revision))
        if context.document != document_id or context.revision != revision:
            raise ValueError('Synthetic document or revision changed')
        if REVIEW.checked(record) != proof(current, before, candidate, document_id, revision):
            raise ValueError('Synthetic complete target review changed')
        return record

    def replay(value, **kwargs):
        context.replays.append((deepcopy(value), kwargs))
        row['state'] = deepcopy(value)
        return {'event': 'frame', 'render_ms': 1}

    def advance():
        context.revision = str(int(context.revision) + 1)

    context.prepare = prepare; context.verify = verify
    context.owner = PC.PresetController(PC.PresetPorts(lambda _: None,
        lambda: context.document, lambda: deepcopy(row['state']), replay,
        lambda: ('ok', ''), lambda: {'document_id': context.document},
        lambda: context.invalid.append(True), target_row=lambda: row,
        revision=lambda: context.revision, advance=advance,
        prepare_spill=prepare, verify_spill=verify), context.events.append)
    context.reviews = context.owner.reviews
    return context


def prepare(context, **ports):
    return context.reviews.prepare(context.preset, context.row['state'], context.row,
        context.document, context.revision, None,
        **{'prepare_spill': context.prepare, 'verify_spill': context.verify, **ports})


def ack(plan):
    review = plan['spill_transfer']
    return [{'document_id': review['document_id'], 'revision': review['revision'],
        'before_sha256': review['before']['sha256'], 'after_sha256': review['after']['sha256']}]


def claim(context, plan, **kwargs):
    return context.reviews.claim(plan['preflight_token'], context.preset['id'],
        context.row['state'], context.row, context.document, context.revision,
        **{'verify_spill': context.verify, 'spill_review_ack': ack(plan), **kwargs})


def command(context, action, request, **values):
    message = {'cmd': 'preset', 'action': action, 'id': context.preset['id'],
        'document_id': context.document, 'request_id': request, **values}
    context.owner.handle_command(message); context.owner.finish(message)
    return context.events[-1]


@pytest.mark.parametrize('missing', ['both', 'prepare', 'verify'])
def test_spill_prepare_requires_both_full_visual_ports_before_token(tmp_path, missing):
    context = fixture(tmp_path); prior = deepcopy(context.row)
    ports = {key: None for key in ('prepare_spill', 'verify_spill')
             if missing == 'both' or key.startswith(missing)}
    with pytest.raises(ValueError):
        prepare(context, **ports)
    assert not context.reviews.pending and not context.replays and context.row == prior


@pytest.mark.parametrize('derived', [False, True])
def test_preflight_keeps_only_compact_target_evidence_without_writes(tmp_path, derived):
    context = fixture(tmp_path, derived=derived); before = deepcopy(context.row)
    plan = prepare(context); record = context.reviews.pending[plan['preflight_token']]
    assert context.row == before and context.revision == '7' and not context.replays
    assert plan['applies'] == preset()['modules']
    assert record['spill']['source_proof'] == SOURCE.row_proof(context.row)
    assert ('_creative_base' in context.row['state']) is derived
    assert set(record['spill']) == REVIEW.FIELDS
    assert all(set(record['spill'][key]) == {'mime', 'width', 'height', 'sha256'} for key in ('before', 'after'))
    assert all('base64' in plan['spill_transfer'][key] for key in ('before', 'after'))
    assert [entry[0] for entry in context.calls] == ['prepare', 'verify']
    assert context.calls[0][1] == before['state']
    candidate = context.calls[0][2]
    assert candidate['_id_background']['support'] == before['state']['_id_background']['support']
    assert candidate['_id_background']['source'] == before['state']['_id_background']['source']
    assert SPILL.params_of(candidate) == preset()['modules'][SPILL.OP]


@pytest.mark.parametrize('invalid', ['missing', 'empty', 'object', 'duplicate', 'other-target',
    'wrong-revision', 'recipe-hashes', 'swapped-images', 'extra-field'])
def test_ack_must_be_exactly_one_target_and_use_display_image_hashes(tmp_path, invalid):
    context = fixture(tmp_path); plan = prepare(context); value = ack(plan)
    if invalid == 'missing': value = None
    elif invalid == 'empty': value = []
    elif invalid == 'object': value = value[0]
    elif invalid == 'duplicate': value *= 2
    elif invalid == 'other-target': value[0]['document_id'] = 'other'
    elif invalid == 'wrong-revision': value[0]['revision'] = '8'
    elif invalid == 'recipe-hashes':
        value[0]['before_sha256'] = plan['spill_transfer']['before_sha256']
        value[0]['after_sha256'] = plan['spill_transfer']['candidate_sha256']
    elif invalid == 'swapped-images':
        value[0]['before_sha256'], value[0]['after_sha256'] = value[0]['after_sha256'], value[0]['before_sha256']
    else: value[0]['accepted'] = True
    before = deepcopy(context.row)
    with pytest.raises(ValueError): claim(context, plan, spill_review_ack=value)
    assert plan['preflight_token'] in context.reviews.pending
    assert context.row == before and not context.replays and context.revision == '7'


@pytest.mark.parametrize('changed', ['before', 'people', 'source', 'row-identity', 'revision', 'compact-proof', 'verifier'])
def test_frozen_spill_review_cannot_follow_changed_target(tmp_path, changed):
    context = fixture(tmp_path); plan = prepare(context); ports = {}
    if changed == 'before': context.row['state']['_unselected'] = 'later edit outside module scope'
    elif changed == 'people': context.row['people'] = 'changed-target-owned-people'
    elif changed == 'source': (tmp_path / 'synthetic-original.bin').write_bytes(b'replaced')
    elif changed == 'row-identity': context.row['document_id'] = 'replacement-row'
    elif changed == 'revision': context.revision = '8'
    elif changed == 'compact-proof':
        context.reviews.pending[plan['preflight_token']]['spill']['after']['base64'] = 'forbidden-private-pixels'
    else: ports['verify_spill'] = None
    with pytest.raises(ValueError): claim(context, plan, **ports)
    assert plan['preflight_token'] in context.reviews.pending and not context.replays


def test_valid_ack_claim_is_single_use_and_keeps_source_masks_target_owned(tmp_path):
    context = fixture(tmp_path); before = deepcopy(context.row)
    plan = prepare(context); record = claim(context, plan)
    assert record['spill']['parameters'] == preset()['modules'][SPILL.OP]
    assert context.row == before and not context.replays
    with pytest.raises(ValueError): claim(context, plan)


def test_controller_routes_visual_preflight_and_exact_ack_to_strict_apply(tmp_path, monkeypatch):
    context = fixture(tmp_path); monkeypatch.setattr(PC.PS, 'find', lambda _: context.preset)
    before = deepcopy(context.row['state'])
    plan = command(context, 'preflight', 'preflight')
    assert plan['success'] and plan['spill_transfer'] and not context.replays
    result = command(context, 'apply', 'apply', preflight_token=plan['preflight_token'], spill_review_ack=ack(plan))
    assert result['success'] and not result['outcome_unknown'] and context.revision == '8'
    assert len(context.replays) == 1 and context.replays[0][1]['strict_local'] is True
    assert [entry[4] for entry in context.calls if entry[0] == 'verify'] == ['7', '7', '7', '8']
    assert context.calls[-1][1] == before and context.calls[-1][2] == context.row['state']
    assert context.row['state']['_id_background']['support'] == before['_id_background']['support']
    assert context.row['state']['_id_background']['source'] == before['_id_background']['source']
    repeated = command(context, 'apply', 'apply', preflight_token=plan['preflight_token'], spill_review_ack=ack(plan))
    assert repeated['replayed'] and len(context.replays) == 1 and context.revision == '8'


@pytest.mark.parametrize('invalid', [None, []])
def test_controller_rejects_missing_ack_without_advancing_or_consuming_token(tmp_path, invalid):
    context = fixture(tmp_path); plan = prepare(context); before = deepcopy(context.row)
    result = command(context, 'apply', 'bad-ack', preflight_token=plan['preflight_token'], spill_review_ack=invalid)
    assert not result['success'] and not result['outcome_unknown']
    assert not context.replays and context.row == before and context.revision == '7'
    assert plan['preflight_token'] in context.reviews.pending


def test_direct_apply_cannot_bypass_visual_preflight(tmp_path, monkeypatch):
    context = fixture(tmp_path); monkeypatch.setattr(PC.PS, 'find', lambda _: context.preset)
    result = command(context, 'apply', 'direct')
    assert not result['success'] and not result['outcome_unknown']
    assert not context.replays and context.revision == '7'


@pytest.mark.parametrize('acknowledgment', [None, [], [{'document_id': 'loaded'}]])
def test_nonspill_apply_rejects_ack_field_even_when_null(tmp_path, monkeypatch, acknowledgment):
    context = fixture(tmp_path)
    context.preset = {**context.preset, 'modules': {SC.OP_EXPOSURE: {'ev': 1.}}}
    monkeypatch.setattr(PC.PS, 'find', lambda _: context.preset)
    result = command(context, 'apply', 'unexpected-ack', spill_review_ack=acknowledgment)
    assert not result['success'] and not result['outcome_unknown'] and not context.replays


@pytest.mark.parametrize('changed', ['unselected', 'people', 'spill-parent', 'revision'])
def test_post_replay_changes_roll_back_inside_existing_preset_boundary(tmp_path, changed):
    context = fixture(tmp_path); plan = prepare(context); before = deepcopy(context.row['state'])
    replay = context.owner.ports.replay

    def changed_replay(value, **kwargs):
        frame = replay(value, **kwargs)
        if kwargs['mode'] == 'preset':
            if changed == 'unselected': context.row['state']['_unselected'] = 'unexpected post-render edit'
            elif changed == 'people': context.row['people'] = 'changed people after render'
            elif changed == 'spill-parent': context.row['state']['_id_background']['edge'] = 3.
            else: context.revision = '9'
        return frame

    context.owner.ports = replace(context.owner.ports, replay=changed_replay)
    with pytest.raises(PresetApplyError) as error:
        context.owner.apply({'id': 'spill', 'preflight_token': plan['preflight_token'], 'spill_review_ack': ack(plan)})
    assert error.value.rolled_back is (changed != 'people')
    assert error.value.requires_reload is (changed == 'people')
    assert context.row['state'] == before
    assert [entry[1]['mode'] for entry in context.replays] == ['preset', 'preset_rollback']
    assert context.replays[0][1]['strict_local'] is True
    assert bool(context.invalid) is (changed == 'people')
    assert not context.row['undo'] and not context.row['redo']
    assert not any(event.get('event') == 'preset_applied' for event in context.events)


def test_spill_review_sees_final_optics_and_reference_recipes_before_claim_and_apply(tmp_path, monkeypatch):
    context = fixture(tmp_path)
    context.row['state']['_optics'] = OPTICS.empty()
    context.row['state'][REFERENCE.KEY] = REFERENCE.empty()
    context.row['state']['_reference_color_bundle'] = None
    optical = OPTICS.empty(); optical['perspective']['rotation'] = 2.
    reference = REFERENCE.empty()
    context.preset['modules'].update({OA.OP: OA.params_of(context.row['state']),
        RC.OP: RC.params_of(context.row['state'])})
    monkeypatch.setattr(PR.OR, 'prepare', lambda *args, **kwargs: ({'recipe': deepcopy(optical)}, {'fixture_only': True}))
    monkeypatch.setattr(OA, 'verify_target', lambda *args, **kwargs: deepcopy(optical))
    monkeypatch.setattr(RC, 'verify_target', lambda *args, **kwargs: deepcopy(reference))
    native_apply_reference = RC.apply_verified

    def install_reference(state, recipe):
        native_apply_reference(state, recipe)
        state['_reference_color_bundle'] = {'fixture_final_reference': True}

    monkeypatch.setattr(RC, 'apply_verified', install_reference)
    context.owner.ports = replace(context.owner.ports,
        prepare_optics=lambda *args: {'fixture_only': True},
        prepare_reference=lambda *args: {'recipe': deepcopy(reference)})
    plan = prepare(context, prepare_optics=context.owner.ports.prepare_optics,
        prepare_reference=context.owner.ports.prepare_reference)
    context.owner.apply({'id': 'spill', 'preflight_token': plan['preflight_token'], 'spill_review_ack': ack(plan)})
    assert len(context.replays) == 1
    for _, before, candidate, _, _ in context.calls:
        assert before['_optics'] == OPTICS.empty()
        assert before['_reference_color_bundle'] is None
        assert candidate['_optics'] == optical
        assert candidate['_reference_color_bundle'] == {'fixture_final_reference': True}


def crop_ports(context):
    def prepare_crop(row, candidate, document_id, revision):
        return {'candidate': digest(candidate), 'revision': revision}, {'fixture_only': True}

    def verify_crop(row, candidate, document_id, revision, record):
        if record != {'candidate': digest(candidate), 'revision': revision}:
            raise ValueError('Synthetic crop proof changed')

    context.owner.ports = replace(context.owner.ports, prepare_crop=prepare_crop, verify_crop=verify_crop)
    return {'prepare_crop': prepare_crop, 'verify_crop': verify_crop}


@pytest.mark.parametrize('value', [None, []])
def test_nonspill_review_refuses_ack_presence_before_consuming_crop_token(tmp_path, value):
    context = fixture(tmp_path)
    context.preset['modules'] = {SC.OP_CROP: {'rect_normalized': [0., 0., 1., 1.], 'rotation_degrees': 0.}}
    plan = prepare(context, **crop_ports(context))
    assert 'spill_transfer' not in plan and not context.calls
    with pytest.raises(ValueError):
        context.owner.apply({'id': 'spill', 'preflight_token': plan['preflight_token'], 'spill_review_ack': value})
    assert plan['preflight_token'] in context.reviews.pending and not context.replays
    assert context.revision == '7'


def test_spill_ack_does_not_replace_existing_xmp_or_crop_review_contracts(tmp_path):
    context = fixture(tmp_path)
    context.preset['modules'][SC.OP_CROP] = {'rect_normalized': [0., 0., 1., 1.], 'rotation_degrees': 0.}
    context.preset['xmp_import'] = {'source_sha256': 'e' * 64,
        'report': {'source_sha256': 'e' * 64, 'report_sha256': 'f' * 64}}
    xmp_calls = []

    def prepare_xmp(row, before, candidate, document_id, revision, source_sha256):
        private = {'revision': revision, 'before_recipe': digest(before), 'candidate_recipe': digest(candidate),
            'before': {'sha256': 'c' * 64}, 'after': {'sha256': 'd' * 64}}
        return private, {'fixture_only': True}

    def verify_xmp(row, before, candidate, document_id, revision, source_sha256, record):
        xmp_calls.append(revision)
        if (source_sha256 != 'e' * 64 or record['revision'] != revision
                or record['before_recipe'] != digest(before) or record['candidate_recipe'] != digest(candidate)):
            raise ValueError('Synthetic XMP proof changed')

    ports = crop_ports(context)
    context.owner.ports = replace(context.owner.ports, prepare_xmp=prepare_xmp, verify_xmp=verify_xmp)
    plan = prepare(context, **ports, prepare_xmp=prepare_xmp, verify_xmp=verify_xmp)
    assert plan['crop_transfer'] == {'fixture_only': True} and plan['xmp_transfer'] == {'fixture_only': True}
    arguments = {'id': 'spill', 'preflight_token': plan['preflight_token'], 'spill_review_ack': ack(plan)}
    with pytest.raises(ValueError): context.owner.apply(arguments)
    assert plan['preflight_token'] in context.reviews.pending and not context.replays
    result = context.owner.apply({**arguments, 'xmp_review_ack': {'source_sha256': 'e' * 64,
        'report_sha256': 'f' * 64, 'before_sha256': 'c' * 64, 'after_sha256': 'd' * 64}})
    assert result['source_proof'] == SOURCE.row_proof(context.row)
    assert len(context.replays) == 1 and context.revision == '8'
    assert xmp_calls == ['7', '7', '8']
