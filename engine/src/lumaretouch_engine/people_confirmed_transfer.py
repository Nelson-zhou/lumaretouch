"""Confirmed anonymous person target selection for the existing batch owner."""
from . import people_state as S
from .people_transfer_adapter import prepare


def confirmed_person(state, face_id):
    links = [x for x in state['links'] if x['face_instance_id'] == face_id and x['state'] == 'confirmed']
    if len(links) != 1: raise ValueError('Source face has no unique user-confirmed person association')
    return links[0]['person_id']


def prepare_confirmed(source_state, target_state, source_ref, target_asset, selection,
                      defaults, *, source_document, target_document, source_owner=None, target_owner=None):
    from .people_transfer_inventory import check_proof
    source_owner = check_proof(source_owner); target_owner = check_proof(target_owner)
    if source_owner['people_scope'] != target_owner['people_scope']:
        raise ValueError('Independent portrait owners require an explicit reviewed face map; matching person IDs are not association evidence')
    source = S.check(source_state); target = S.check(target_state); S.digest(target_asset)
    ref = S.check_ref(source_ref); person = confirmed_person(source,ref['face_instance_id'])
    refs = [S.face_ref(target['faces'][x['face_instance_id']]) for x in target['links']
            if x['person_id'] == person and x['state'] == 'confirmed'
            and target['faces'][x['face_instance_id']]['asset_sha256'] == target_asset
            and target['faces'][x['face_instance_id']]['enabled']]
    if not refs: raise ValueError('Target photo has no explicitly confirmed linked person')
    payload = prepare(source,target,ref,refs,selection,defaults,source_document=source_document,target_document=target_document,
                      source_owner=source_owner,target_owner=target_owner)
    payload['confirmed_person_id'] = person
    payload['target_policy'] = 'confirmed_person_only'
    payload['confirmation_revisions'] = sorted((x['face_instance_id'],x['confirmation_revision']) for x in target['links']
        if x['person_id'] == person and x['state'] == 'confirmed' and x['face_instance_id'] in {r['face_instance_id'] for r in refs})
    return payload
