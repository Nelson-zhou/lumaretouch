"""AUTHORED / UNRUN: no runtime, camera, import or image acceptance claim."""
from copy import deepcopy
import uuid
import pytest
from lumaretouch_engine import ingest_session_protocol as P


def source(path='/incoming/selected-name.CR3', occurrence='shot-1'):
    return {'path': path, 'sha256': 'a' * 64, 'size': 12,
            'stat': ['1', '2', '12', '1780000000000000001', '1780000000000000002'],
            'occurrence_id': occurrence, 'completion': 'completed_transfer'}


def request():
    proof = source()
    return {'cmd': 'ingest_session', 'action': 'import', 'request_id': str(uuid.uuid4()),
            'session_id': str(uuid.uuid4()), 'paths': [proof['path']], 'root': '/managed', 'root_identity': ['1', '2'],
            'completed_sources': [proof]}


def prepared(proof, operation):
    target = '/managed/' + str(uuid.uuid5(uuid.UUID(operation), proof['path'])) + '.cr3'
    return {'source': proof['path'], 'path': target, 'sha256': proof['sha256'],
            'size': proof['size'], 'signature': [int(part) for part in proof['stat']],
            'fingerprint': {'path': target, 'hash_level': 'full', 'sha256': proof['sha256'],
                            'bytes': proof['size']}}


def test_exact_manifest_keeps_large_stat_integers_as_decimal_strings():
    command = request()
    checked = P.command(command)
    assert checked == command and checked is not command
    assert checked['completed_sources'][0]['stat'][3] == '1780000000000000001'
    for replacement in (1780000000000000001, '01', '-1', '1.0'):
        changed = deepcopy(command)
        changed['completed_sources'][0]['stat'][3] = replacement
        with pytest.raises(ValueError):
            P.command(changed)


def test_precommit_pins_exact_copied_bytes_stat_path_and_filename_suffix():
    command = request()
    operation = P.operation_id(command['session_id'], command['request_id'])
    proof = command['completed_sources'][0]
    actual = prepared(proof, operation)
    P.prepared_matches([actual], [proof], command['root'], operation)
    for key, bad in (('source', '/other.CR3'), ('sha256', 'b' * 64), ('size', 11),
                     ('signature', [1, 2, 12, 1780000000000000002, 1780000000000000002]),
                     ('path', '/managed/another.cr3')):
        changed = deepcopy(actual); changed[key] = bad
        with pytest.raises(ValueError):
            P.prepared_matches([changed], [proof], command['root'], operation)


def test_distinct_occurrences_with_equal_bytes_are_not_content_deduplicated():
    first = source('/a/same.CR3', 'one')
    second = source('/b/same.CR3', 'two')
    assert len(P.sources([first, second], [first['path'], second['path']])) == 2
    second['occurrence_id'] = 'one'
    with pytest.raises(ValueError):
        P.sources([first, second], [first['path'], second['path']])


def test_schema_never_accepts_project_switch_force_or_auto_save_flags():
    for key in ('force', 'save', 'project_id', 'trusted_precommit', 'mode'):
        changed = request(); changed[key] = True
        with pytest.raises(ValueError):
            P.command(changed)


def test_uuid_recovery_address_is_deterministic_but_distinct_per_outer_request():
    session, first, second = (str(uuid.uuid4()) for _ in range(3))
    assert P.operation_id(session, first) == P.operation_id(session, first)
    assert P.operation_id(session, first) != P.operation_id(session, second)
    P.identity(P.operation_id(session, first))


def test_arm_limit_is_declared_and_never_silently_clamped():
    request = {'cmd': 'ingest_session', 'action': 'arm', 'request_id': str(uuid.uuid4()),
               'owner': 'workflow', 'expected': {'project_id': 'project', 'workspace': 'workspace',
               'path': '/project.lrt', 'disk_sha256': 'a' * 64}, 'max_operations': 64}
    assert P.command(request)['max_operations'] == 64
    for value in (0, 65, True, 1.0):
        changed = {**request, 'max_operations': value}
        with pytest.raises(ValueError):
            P.command(changed)


@pytest.mark.parametrize('identity', [None, [], ['1'], ['1', '2', '3'], [1, '2'], ['01', '2'], ['-1', '2'], [str(2**64), '2']])
def test_original_directory_identity_is_required(identity):
    value = request()
    value['root_identity'] = identity
    with pytest.raises(ValueError):
        P.command(value)
