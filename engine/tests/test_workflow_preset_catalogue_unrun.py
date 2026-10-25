"""Authored, NOT executed: genuine-store read-only workflow catalogue contracts.

Fixtures are future verification specifications, not runtime acceptance claims.
"""
import fcntl
import json
import os

import pytest

from lumaretouch_engine import workflow_preset_catalogue as C
from lumaretouch_engine import preset_store as PS
from lumaretouch_engine import preset_organisation_store as PO
from lumaretouch_engine import scope as S
from lumaretouch_engine import workflow_owner_protocol as P


def recipe(pid='my-warm', ev=0.5):
    return {'schema': S.PRESET_SCHEMA, 'id': pid, 'name': 'My warm', 'kind': 'color',
            'author': 'Owner', 'note': 'Saved by the owner',
            'modules': {'lnx.exposure.v1': {'ev': ev}}}


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = tmp_path / 'presets'
    root.mkdir()
    (root / '.organisation.lock').write_bytes(b'')
    monkeypatch.setattr(PS, 'preset_dir', lambda: str(root))
    return root


def write_recipe(root, value=None, filename='saved.json'):
    value = recipe() if value is None else value
    (root / filename).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return value


def codes(result):
    return {item['code'] for item in result['errors']}


def row(result, pid):
    return next(item for item in result['presets'] if item['id'] == pid)


def state_for(*docs):
    builtins = [S.validate_preset(doc, builtin=True) for doc in PS.builtin_docs()]
    return PO.reconcile(PO.empty(), builtins + [S.validate_preset(doc) for doc in docs])


def assert_error(code, operation):
    with pytest.raises(C.CatalogueError) as caught:
        operation()
    assert caught.value.code == code


def test_actual_builtin_and_user_content_have_canonical_fingerprints(store):
    original = write_recipe(store)
    result = C.list_catalogue()
    assert result['schema'] == C.SCHEMA and result['complete'] and not result['errors']
    selected = row(result, original['id'])
    expected = S.validate_preset(original)
    assert selected['preset_sha256'] == P.digest(expected) == C.fingerprint(original['id'])
    assert C.resolve(selected['id'], selected['preset_sha256']) == expected
    assert selected['module_ids'] == ['lnx.exposure.v1']
    assert selected['modules'] == [next(x for x in S.describe() if x['operation_id'] == 'lnx.exposure.v1')]
    assert not selected['workflow_supported'] and selected['support_reason'] == 'preset_owner_not_bound'
    assert all(not item['workflow_supported'] for item in result['presets'])
    assert row(result, 'color-warm')['builtin'] is True
    assert selected['builtin'] is False
    assert 'ev' not in selected and 'content' not in selected


def test_nonexistent_directory_is_builtin_only_and_is_not_created(tmp_path, monkeypatch):
    missing = tmp_path / 'not-yet-created'
    monkeypatch.setattr(PS, 'preset_dir', lambda: str(missing))
    result = C.list_catalogue()
    assert result['complete'] and all(item['builtin'] for item in result['presets'])
    selected = row(result, 'portrait-soft')
    assert C.resolve(selected['id'], selected['preset_sha256'])['builtin'] is True
    assert not missing.exists()


def test_existing_directory_without_lock_is_explicitly_incomplete(store):
    write_recipe(store)
    (store / '.organisation.lock').unlink()
    result = C.list_catalogue()
    assert not result['complete'] and 'catalogue_lock_missing' in codes(result)
    assert not (store / '.organisation.lock').exists()
    assert all(item['builtin'] for item in result['presets'])
    assert_error('catalogue_incomplete', lambda: C.load('color-warm'))


def test_no_read_api_opens_for_write_or_creates_metadata(store, monkeypatch):
    original = write_recipe(store)
    before = {path.name: path.read_bytes() for path in store.iterdir()}
    real_open = os.open
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

    def readonly_open(path, flags, *args, **kwargs):
        assert not flags & write_flags, 'catalogue attempted to write'
        return real_open(path, flags, *args, **kwargs)

    def forbidden(*_args, **_kwargs):
        raise AssertionError('catalogue attempted to initialise or mutate the store')

    monkeypatch.setattr(C.os, 'open', readonly_open)
    monkeypatch.setattr(C.os, 'makedirs', forbidden)
    monkeypatch.setattr(PO, 'write', forbidden)
    monkeypatch.setattr(PS, 'save', forbidden)
    monkeypatch.setattr(PS, 'delete', forbidden)
    result = C.list_catalogue()
    C.load(original['id'])
    sha = C.fingerprint(original['id'])
    C.resolve(original['id'], sha)
    assert result['complete']
    assert before == {path.name: path.read_bytes() for path in store.iterdir()}
    assert not (store / '.organisation.state').exists()


def test_organisation_rename_and_trash_match_existing_overlay(store):
    first, second = recipe(), recipe('second')
    write_recipe(store, first, 'first.json')
    write_recipe(store, second, 'second.json')
    state = state_for(first, second)
    state['items'][first['id']]['name'] = 'Current display name'
    state['items'][second['id']]['deleted'] = True
    (store / '.organisation.state').write_bytes(PO.encoded(state))
    result = C.list_catalogue()
    assert result['complete']
    selected = row(result, first['id'])
    expected = {**S.validate_preset(first), 'name': 'Current display name'}
    assert selected['name'] == expected['name']
    assert C.resolve(first['id'], selected['preset_sha256']) == expected
    assert second['id'] not in {item['id'] for item in result['presets']}
    assert_error('preset_not_found', lambda: C.load(second['id']))


@pytest.mark.parametrize('field,value', [('name', 'Changed'), ('author', 'Other author'),
                                       ('note', 'Changed note'), ('kind', 'custom')])
def test_content_or_metadata_change_invalidates_pin(store, field, value):
    original = write_recipe(store)
    sha = C.fingerprint(original['id'])
    write_recipe(store, {**original, field: value})
    assert_error('preset_changed', lambda: C.resolve(original['id'], sha))


def test_module_change_and_organisation_rename_invalidate_pin(store):
    original = write_recipe(store)
    sha = C.fingerprint(original['id'])
    write_recipe(store, recipe(ev=0.7))
    assert_error('preset_changed', lambda: C.resolve(original['id'], sha))
    write_recipe(store, original)
    state = state_for(original)
    state['items'][original['id']]['name'] = 'Renamed'
    (store / '.organisation.state').write_bytes(PO.encoded(state))
    assert_error('preset_changed', lambda: C.resolve(original['id'], sha))


def test_equivalent_json_formatting_and_detached_result_do_not_change_pin(store):
    original = write_recipe(store)
    sha = C.fingerprint(original['id'])
    (store / 'saved.json').write_text(json.dumps(original, sort_keys=True, indent=4), encoding='utf-8')
    resolved = C.resolve(original['id'], sha)
    resolved['modules']['lnx.exposure.v1']['ev'] = 4.0
    assert C.resolve(original['id'], sha)['modules']['lnx.exposure.v1']['ev'] == 0.5


def test_disappeared_file_cannot_rebase_selected_preset(store):
    original = write_recipe(store)
    sha = C.fingerprint(original['id'])
    (store / 'saved.json').unlink()
    assert_error('preset_not_found', lambda: C.resolve(original['id'], sha))


@pytest.mark.parametrize('value', [None, '', '../escape', '.hidden', 'WithSpace ', 23, recipe()])
def test_no_manual_recipe_or_nonexact_id_authority(store, value):
    assert_error('invalid_preset_id', lambda: C.load(value))
    assert_error('invalid_preset_id', lambda: C.fingerprint(value))


@pytest.mark.parametrize('value', [None, '', 'A' * 64, 'g' * 64, 0, {'sha': 'a' * 64}])
def test_pin_shape_is_strict(store, value):
    assert_error('invalid_preset_sha256', lambda: C.resolve('color-warm', value))


@pytest.mark.parametrize('raw,code', [
    ('not JSON', 'malformed_json'),
    ('{"schema":"a","schema":"b"}', 'duplicate_json_key'),
    ('{"number":NaN}', 'nonfinite_json'),
    ('<script>alert(1)</script>', 'executable_content'),
])
def test_malformed_entries_are_reported_not_silently_omitted(store, raw, code):
    original = write_recipe(store)
    (store / 'broken.json').write_text(raw, encoding='utf-8')
    result = C.list_catalogue()
    assert not result['complete'] and code in codes(result)
    assert row(result, original['id'])['id'] == original['id']
    assert any(item['file'] == 'broken.json' for item in result['errors'])
    assert_error('catalogue_incomplete', lambda: C.load(original['id']))


def test_unknown_modules_are_not_pruned_into_a_fake_valid_recipe(store):
    invalid = recipe()
    invalid['modules']['imaginary.module.v1'] = {'strength': 1}
    write_recipe(store, invalid)
    result = C.list_catalogue()
    assert not result['complete']
    assert invalid['id'] not in {item['id'] for item in result['presets']}


def test_duplicate_user_ids_are_removed_as_ambiguous(store):
    original = write_recipe(store, recipe(ev=0.3), 'one.json')
    write_recipe(store, recipe(ev=0.7), 'two.json')
    result = C.list_catalogue()
    assert not result['complete'] and 'duplicate_preset_id' in codes(result)
    assert original['id'] not in {item['id'] for item in result['presets']}
    assert_error('catalogue_incomplete', lambda: C.load(original['id']))


def test_user_cannot_override_builtin_provenance(store):
    write_recipe(store, recipe('color-warm'))
    result = C.list_catalogue()
    assert not result['complete'] and 'duplicate_preset_id' in codes(result)
    assert row(result, 'color-warm')['builtin'] is True
    assert_error('catalogue_incomplete', lambda: C.load('color-warm'))


def test_preset_cannot_self_declare_builtin(store):
    write_recipe(store, {**recipe(), 'builtin': True})
    result = C.list_catalogue()
    assert not result['complete'] and all(item['builtin'] for item in result['presets'])


def test_corrupt_organisation_is_reported_without_rewriting(store):
    write_recipe(store)
    payload = b'{"schema":"unexpected"}'
    (store / '.organisation.state').write_bytes(payload)
    result = C.list_catalogue()
    assert not result['complete'] and result['errors']
    assert (store / '.organisation.state').read_bytes() == payload
    assert_error('catalogue_incomplete', lambda: C.load('color-warm'))


def test_symlink_directory_and_nonregular_entries_are_not_followed(store, tmp_path):
    outside = tmp_path / 'outside.json'
    outside.write_text(json.dumps(recipe()), encoding='utf-8')
    (store / 'linked.json').symlink_to(outside)
    (store / 'directory.json').mkdir()
    os.mkfifo(store / 'pipe.json')
    result = C.list_catalogue()
    assert not result['complete']
    assert {item['file'] for item in result['errors']} == {'linked.json', 'directory.json', 'pipe.json'}
    assert all(item['builtin'] for item in result['presets'])


def test_symlink_root_is_not_treated_as_an_empty_store(store, tmp_path, monkeypatch):
    linked = tmp_path / 'linked-presets'
    linked.symlink_to(store, target_is_directory=True)
    monkeypatch.setattr(PS, 'preset_dir', lambda: str(linked))
    assert C.list_catalogue()['complete'] is False


def test_busy_existing_lock_is_nonblocking_and_explicit(store):
    fd = os.open(store / '.organisation.lock', os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = C.list_catalogue()
        assert not result['complete'] and 'catalogue_busy' in codes(result)
    finally:
        os.close(fd)


def test_same_thread_store_lock_nesting_is_supported(store):
    write_recipe(store)
    with PO.catalogue_lock(str(store)):
        assert C.list_catalogue()['complete']


def test_file_replacement_during_read_is_rejected(store, tmp_path, monkeypatch):
    write_recipe(store)
    outside = tmp_path / 'replacement.json'
    outside.write_text(json.dumps(recipe(ev=0.9)), encoding='utf-8')
    real_stat = os.stat

    def changed_stat(path, *args, **kwargs):
        if path == 'saved.json':
            return real_stat(outside)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(C.os, 'stat', changed_stat)
    result = C.list_catalogue()
    assert not result['complete'] and 'catalogue_changed' in codes(result)


def test_bounded_preset_count_and_directory_scan_are_not_complete(store, monkeypatch):
    write_recipe(store)
    monkeypatch.setattr(C, 'MAX_PRESETS', len(PS.builtin_docs()))
    assert 'preset_count_limit' in codes(C.list_catalogue())
    monkeypatch.setattr(C, 'MAX_PRESETS', 256)
    monkeypatch.setattr(C, 'MAX_DIRECTORY_ENTRIES', 1)
    assert 'directory_entry_limit' in codes(C.list_catalogue())


def test_malformed_reads_still_consume_aggregate_byte_budget(store, monkeypatch):
    # Leave room for genuine builtin canonical content while making the two
    # malformed reads together exceed the independent file-read budget.
    budget = sum(len(P.encoded(S.validate_preset(doc, builtin=True), sorted_keys=True))
                 for doc in PS.builtin_docs()) + 100
    monkeypatch.setattr(C, 'MAX_TOTAL_BYTES', budget)
    (store / 'a.json').write_bytes(b'{' * (budget // 2 + 1))
    (store / 'b.json').write_bytes(b'{' * (budget // 2 + 1))
    result = C.list_catalogue()
    assert not result['complete']
    assert 'malformed_json' in codes(result) and 'entry_byte_limit' in codes(result)


def test_metadata_response_is_bounded_and_does_not_claim_completeness(store, monkeypatch):
    monkeypatch.setattr(C, 'MAX_RESPONSE_BYTES', 512)
    result = C.list_catalogue()
    assert not result['complete'] and result['presets'] == []
    assert 'catalogue_response_limit' in codes(result)
    assert len(P.encoded(result, sorted_keys=True)) <= C.MAX_RESPONSE_BYTES


def test_json_shape_bound_is_explicit(store, monkeypatch):
    monkeypatch.setattr(C, 'MAX_JSON_NODES', 4)
    write_recipe(store)
    result = C.list_catalogue()
    assert not result['complete'] and 'json_structure_limit' in codes(result)


def test_surrogate_diagnostic_names_remain_encodable():
    issue = C._issue(ValueError('bad \udcff'), 'bad-\udcff.json')
    assert P.encoded(issue, sorted_keys=True)
    assert '\\udcff' in issue['file'] and '\\udcff' in issue['message']
