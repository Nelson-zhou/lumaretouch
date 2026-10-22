"""Actual graph editing adapter; existing receipt/history owner publishes results.

All edits are staged and validated before optional render preparation. This module
never emits success or mutates the engine, so a preparation refusal leaves the
original graph, rendered fields and history untouched.
"""
from . import people_state as S, people_associations as G, people_algorithms as A
from .people_command import validate_envelope
from .people_resolver import resolve, materialize

ACTIONS = ('patch', 'link', 'group', 'face_status', 'manual_add', 'create_person')


def stage(command, state, *, document_id, document_epoch, document_revision,
          asset_sha256, source_dimensions, prepare=None):
    target = validate_envelope(command, state, document_id=document_id, document_epoch=document_epoch, document_revision=document_revision)
    S.digest(asset_sha256)
    if target['scope']=='all_people' and target['target_id']!=asset_sha256:
        raise ValueError('All-people edits must name the captured current photograph')
    if target['scope']=='face' and target['face_ref']['asset_sha256']!=asset_sha256:
        raise ValueError('Face edit belongs to another document source')
    action = command.get('action')
    if action not in ACTIONS: raise ValueError('Unknown people edit action')
    envelope = {'document_id','document_epoch','document_revision','state_revision','association_revision','target','request_id','action','payload'}
    if set(command) != envelope: raise ValueError('Unknown people edit command fields')
    payload = command['payload']; out = S.check(state); created = None
    if type(payload) is not dict: raise ValueError('People action payload must be an object')
    if action == 'patch':
        if set(payload) != {'patches'} or type(payload['patches']) is not list or not 1 <= len(payload['patches']) <= 256:
            raise ValueError('A bounded parameter patch list is required')
        seen = set(); known = A.defaults()
        for patch in payload['patches']:
            if type(patch) is not dict or type(patch.get('unset')) is not bool:
                raise ValueError('Patch requires explicit unset semantics')
            fields = {'operation_id','parameter_path','unset'} | (set() if patch['unset'] else {'value'})
            if set(patch) != fields: raise ValueError('Patch fields do not match unset/value mode')
            op, path = patch['operation_id'], patch['parameter_path']
            if op not in known or path not in known[op] or (op,path) in seen: raise ValueError('Unknown or duplicate portrait parameter')
            seen.add((op,path))
            if not patch['unset']:
                neutral, validator = A.specifications()[op]
                materialize({'conflicts':[], 'operations':{op:{path:{'value':patch['value']}}}},op,neutral,validator)
            out = S.set_override(out,target['scope'],target['target_id'],op,path,patch.get('value'),unset=patch['unset'])
    elif action == 'link':
        if set(payload) != {'face_instance_id','person_id','state','user_confirmed'}: raise ValueError('Invalid association edit')
        if target['scope']!='face' or target['target_id']!=payload['face_instance_id']:raise ValueError('Association target differs from captured face')
        out = G.set_link(out,payload['face_instance_id'],payload['person_id'],payload['state'],user_confirmed=payload['user_confirmed'])
    elif action == 'group':
        if set(payload) != {'group_id','label','priority','face_ids'}: raise ValueError('Invalid group edit')
        out = G.set_group(out,payload['group_id'],label=payload['label'],priority=payload['priority'],face_ids=payload['face_ids'])
    elif action == 'face_status':
        if target['scope'] != 'face' or set(payload)-{'enabled','labels'} or not payload: raise ValueError('Face status needs an explicit face target')
        out = G.set_face_status(out,target['target_id'],**payload)
    elif action == 'create_person':
        if payload: raise ValueError('Anonymous person creation takes no identity information')
        out, created = G.create_person(out)
    else:
        if set(payload) != {'box'}: raise ValueError('Manual addition accepts only a source region')
        width,height = source_dimensions
        evidence = {'backend':'manual_region','detector_model_sha256':None,'semantic_model_sha256':None,
                    'landmark_digest':None,'status':'unresolved','source_width':width,'source_height':height,
                    'orientation':'exif_normalized_once'}
        face = S.new_face(asset_sha256,payload['box'],evidence,manual=True)
        created = face['face_instance_id']; out['faces'][created] = face; out['revision'] += 1; out = S.check(out)
    # Validate registry domains for EVERY affected face, not only selected face.
    # Conflicting group values remain reviewable, but patch cannot publish them
    # as a successful ready render because preparation must refuse the conflict.
    for key in out['faces']:
        resolved = resolve(out,key,A.defaults())
        if not resolved['conflicts']: A.recipes(resolved)
    prepared = prepare(out) if prepare is not None else None
    return {'state':out,'prepared':prepared,'created_id':created,
            'request_id':command['request_id'],'previous_revision':state['revision']}
