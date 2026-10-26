# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Receipt lifetime fixtures, no actual engine/image mutation."""
from types import SimpleNamespace
import pytest
from lumaretouch_engine import upscale_restore_host as H
from lumaretouch_engine import upscale_restore_stage as S


def command():
    return {'version': 1, 'operation_id': S.OPERATION, 'action': 'cancel',
            'request_id': 'cancel', 'session_id': 'session', 'token': None,
            'owner': {'document_id': 'document', 'document_epoch': 'epoch', 'document_revision': '4',
                      'source': {'sha256': 'a'*64, 'width': 4, 'height': 3, 'orientation': 'exif_normalized_once'}}}


def test_receipt_query_never_executes_an_unknown_write():
    service = H.Service(SimpleNamespace(), lambda event: None)
    result = service.receipt(command())
    assert result['phase'] == 'unknown' and result['outcome_unknown']
    assert not service.writes and service.uncertain is None


def test_same_write_replays_receipt_without_reexecuting(monkeypatch):
    service = H.Service(SimpleNamespace(), lambda event: None)
    calls = []
    def cancel(value):
        calls.append(value)
        return H._receipt(value, outcome='cancelled', message='fixture')
    monkeypatch.setattr(service, '_cancel', cancel)
    first = service.submit(command())
    second = service.submit(command())
    assert first == second and len(calls) == 1


def test_reused_identity_with_different_exact_content_is_refused():
    service = H.Service(SimpleNamespace(), lambda event: None)
    service._save(command(), H._receipt(command(), outcome='cancelled'))
    changed = command()
    changed['session_id'] = 'another'
    with pytest.raises(ValueError):
        service.submit(changed)


def test_entered_unknown_blocks_other_writes_and_cannot_be_cancelled():
    service = H.Service(SimpleNamespace(), lambda event: None)
    service.uncertain = {'command': {'request_id': 'previous'}}
    with pytest.raises(ValueError):
        service._cancel(command())
    with pytest.raises(ValueError):
        service._guard()
    service.maintain()
    assert service.uncertain is not None


def test_outer_never_started_rejection_settles_exact_write_receipt():
    engine = SimpleNamespace()
    events = []
    request = {'cmd': 'upscale_restore', 'action': 'submit', 'request_id': 'cancel', 'command': command()}
    H.dispatch_rejected(request, 'blocked fixture', False, events.append, engine=engine)
    result = events.pop()
    assert set(result) == {'event', 'request_id', 'status', 'receipt'}
    assert result['receipt']['phase'] == 'done' and result['receipt']['outcome'] == 'rejected'
    assert H.service(engine, events.append).receipt(command()) == result['receipt']


def test_write_capacity_never_evicts_original_unknown_proof(monkeypatch):
    service = H.Service(SimpleNamespace(), lambda event: None)
    original = command()
    service._save(original, H._receipt(original, phase='unknown'))
    from lumaretouch_engine import light_glow_host as shared_host
    monkeypatch.setattr(shared_host, 'MAX_WRITES', 1)
    other = {**original, 'request_id': 'other'}
    with pytest.raises(ValueError):
        service.submit(other)
    assert service._known(original)['phase'] == 'unknown'


def test_upscale_owner_is_existing_review_transaction_not_second_history():
    from lumaretouch_engine.light_glow_host import Service as SharedService
    assert issubclass(H.Service, SharedService)
    assert H.Service.command_name == 'upscale_restore'
    assert H.Service.event_name == 'upscale_restore_result'


def test_model_recipe_does_not_accept_sharpen_resize_or_arbitrary_weights():
    assert S.recipe({'version': 1, 'model_id': S.MODEL})['model_id'] == S.MODEL
    for recipe in ({'version': 1, 'model_id': 'lanczos3'},
                   {'version': 1, 'model_id': S.MODEL, 'sharpen': .5},
                   {'version': 1, 'model_id': S.MODEL, 'weights_path': '/tmp/arbitrary'}):
        with pytest.raises(ValueError):
            S.recipe(recipe)


def test_write_requires_before_after_exact_explicit_new_image():
    value = command()
    value.update(action='apply', token='token', reviewed=True, return_mode='new_image',
                 recipe_sha256='a'*64, result_source_sha256='b'*64,
                 before_sha256='c'*64, after_sha256='d'*64)
    assert S.write_command(value) == value
    for field, replacement in (('return_mode', 'replace'), ('reviewed', False),
                               ('after_sha256', None), ('operation_id', 'lnx.light_glow.v1')):
        changed = dict(value, **{field: replacement})
        with pytest.raises(ValueError):
            S.write_command(changed)


def test_first_model_profile_refuses_larger_full_sources_without_downsampling(monkeypatch):
    monkeypatch.setattr(S.sources, 'require', lambda value: value)
    monkeypatch.setattr(S.shared, '_admit', lambda needed, budget: None)
    def source(width, height):
        return SimpleNamespace(owner={'source': {'width': width, 'height': height}}, retained_bytes=0)
    S.admit_source(source(16, 16), object())
    S.admit_source(source(1024, 1024), object())
    for width, height in ((15, 16), (16, 15), (1025, 16), (16, 1025), (4000, 3000)):
        with pytest.raises(ValueError):
            S.admit_source(source(width, height), object())
