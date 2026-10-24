# SPDX-License-Identifier: GPL-3.0-or-later
"""Aggregate named styles under existing portrait owners, never donor geometry."""
from copy import deepcopy
from dataclasses import replace
import json
from . import people_state as S, people_algorithms as A, virtual_copy_people as V
from . import creative_derived_source as SOURCE, face_style_batch_review as REVIEW
from .batch_preflight import canonical
from .portrait_review_render import snapshot_key


def validate(candidate,refs):
    from .people_resolver import resolve
    from .face_style_recipes import validate_compatibility
    for ref in refs:validate_compatibility(A.recipes(resolve(candidate,ref['face_instance_id'],A.defaults())))


def snapshots(engine,row,before,candidate):
    return {'before':snapshot_key(engine,row,row['state'],before),'after':snapshot_key(engine,row,row['state'],candidate)}


def visuals(engine,rows,targets,public):
    from .people_graph_owner import affected_assets
    if len(targets)>REVIEW.MAX_TARGETS:raise ValueError('At most sixteen named-style targets; no target was omitted')
    plans={}
    for target in targets:
        if target.blocked:continue
        row=rows[target.index];payload=json.loads(target.people_json);identity=V.scope(row);before=V.row_snapshot(engine,row)
        staged=plans.get(identity)
        if staged is not None and staged['before']!=before:raise ValueError('Target owner changed during aggregate preparation')
        candidate=S.check(before if staged is None else staged['candidate'])
        for ref in payload['target_refs']:
            for leaf in payload['parameters']:candidate=S.set_override(candidate,'face',ref['face_instance_id'],leaf['operation_id'],leaf['parameter_path'],leaf['value'])
        refs=([] if staged is None else staged['refs'])+payload['target_refs']
        validate(candidate,refs)
        plans[identity]={'before':before,'candidate':candidate,'refs':refs}
    reviewed={target.document_id for target in targets if not target.blocked}
    for row in rows:
        staged=plans.get(V.scope(row))
        if staged is not None and SOURCE.row_proof(row)['asset_sha256'] in affected_assets(staged['before'],staged['candidate']):
            if engine._document_versions().version(row).document_id not in reviewed:
                raise ValueError('Named style affects an unreviewed shared-source document; review the complete set or use independent copies')
    frozen=[];displays={}
    for target,visible in zip(targets,public):
        if target.blocked:frozen.append(target);continue
        row=rows[target.index];payload=json.loads(target.people_json);staged=plans[V.scope(row)]
        keys=snapshots(engine,row,staged['before'],staged['candidate'])
        record,display=REVIEW.prepare(engine,row,staged['before'],staged['candidate'],target.document_id,str(target.revision),payload['face_style'])
        payload['face_style_visual']=record
        before=json.loads(target.before_json);before['face_style_snapshots']=keys
        frozen.append(replace(target,people_json=canonical(payload),before_json=canonical(before)))
        visible['people_transfer']=deepcopy(payload);displays[target.document_id]=display
    for target in frozen:
        if target.blocked:continue
        row=rows[target.index];payload=json.loads(target.people_json);staged=plans[V.scope(row)]
        if V.row_snapshot(engine,row)!=staged['before']:raise ValueError('Target graph changed during later renders')
        verify(engine,row,staged,target,payload)
    return frozen,displays


def verify(engine,row,scoped,target,payload):
    validate(scoped['candidate'],payload['target_refs'])
    expected=json.loads(target.before_json).get('face_style_snapshots')
    if snapshots(engine,row,scoped['before'],scoped['candidate'])!=expected:
        raise ValueError('Named-style target complete snapshot or support changed; review again')
    REVIEW.verify(engine,row,scoped['before'],scoped['candidate'],target.document_id,str(target.revision),payload['face_style'],payload['face_style_visual'])
