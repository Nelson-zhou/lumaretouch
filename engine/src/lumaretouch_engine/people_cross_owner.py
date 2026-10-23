"""Pure reviewed-person replicas, not identity inference or publication authority.

The coordinator must verify actual document owners, sources and replica consensus.
Generation is content identity, not a monotonic fence: protected undo may restore it.
No source pixels, masks, analyses or explicit face overrides are transferred here.
"""
from copy import deepcopy
import hashlib
import json
from . import people_state as S


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _members(value):
    if type(value) is not list or not 2 <= len(value) <= 16:
        raise ValueError('Reviewed association needs 2..16 independent document members')
    documents=set(); scopes=set(); result=[]
    for member in value:
        if type(member) is not dict or set(member)!={'document_id','scope_id','original_sha256','ref'}:
            raise ValueError('Association member needs exact document, scope, original and FaceRef')
        S.token(member['document_id']); S.token(member['scope_id']); S.digest(member['original_sha256'])
        if member['scope_id'] not in ('project',member['document_id']):
            raise ValueError('Association scope must be the project or its exact private document owner')
        S.check_ref(member['ref'])
        if member['document_id'] in documents or member['scope_id'] in scopes:
            raise ValueError('Association permits one face per independent document scope')
        documents.add(member['document_id']); scopes.add(member['scope_id']); result.append(deepcopy(member))
    return sorted(result,key=lambda member:member['document_id'])


def _intent(value):
    if type(value) is not list or not 1 <= len(value) <= 256:
        raise ValueError('Association needs explicit bounded scalar intent')
    from . import people_algorithms as A
    from .people_resolver import materialize
    known=A.defaults(); operations={}; result=[]; seen=set()
    for leaf in value:
        if type(leaf) is not dict or set(leaf)!={'op','path','value'}:
            raise ValueError('Association intent contains scalar leaves only')
        op=leaf['op']; path=leaf['path']; S.token(op); S.parameter_path(path); S.scalar(leaf['value'])
        if op not in known or path not in known[op] or (op,path) in seen:
            raise ValueError('Unknown or repeated association scalar parameter')
        seen.add((op,path)); result.append(deepcopy(leaf))
        operations.setdefault(op,{})[path]={'value':leaf['value']}
    for op, leaves in operations.items():
        neutral,validator=A.specifications()[op]
        materialize({'conflicts':[],'operations':{op:leaves}},op,neutral,validator)
    return sorted(result,key=lambda leaf:(leaf['op'],leaf['path']))


def descriptor(association_id, local_document_id, members, intent):
    S.token(association_id); S.token(local_document_id)
    common={'association_id':association_id,'members':_members(members),'intent':_intent(intent)}
    if local_document_id not in {member['document_id'] for member in common['members']}:
        raise ValueError('Local owner is not a reviewed association member')
    return {'version':1,**common,'local_document_id':local_document_id,
            'generation':hashlib.sha256(_json(common).encode('utf-8')).hexdigest()}


def check_descriptor(value):
    if (type(value) is not dict or set(value)!={'version','association_id','generation','local_document_id','members','intent'}
            or type(value['version']) is not int or value['version']!=1):
        raise ValueError('Unsupported reviewed association capsule')
    S.digest(value['generation'])
    expected=descriptor(value['association_id'],value['local_document_id'],value['members'],value['intent'])
    if _json(value)!=_json(expected):
        raise ValueError('Association capsule is not canonical or its generation changed')
    return expected


def local_member(capsule):
    return next(member for member in capsule['members'] if member['document_id']==capsule['local_document_id'])


def validate_graph(state):
    """Called after structural graph validation; never recursively calls S.check."""
    associations=set()
    for person_id,person in state['persons'].items():
        if 'cross_owner' not in person:continue
        capsule=check_descriptor(person['cross_owner']); member=local_member(capsule)
        if capsule['association_id'] in associations:raise ValueError('Duplicate local association replica')
        associations.add(capsule['association_id'])
        face=state['faces'].get(member['ref']['face_instance_id'])
        if face is None or S.face_ref(face)!=member['ref']:
            raise ValueError('Association local FaceRef is stale or unavailable')
        links=[link for link in state['links'] if link['person_id']==person_id]
        if (len(links)!=1 or links[0]['state']!='confirmed'
                or links[0]['face_instance_id']!=member['ref']['face_instance_id']):
            raise ValueError('Association replica requires its exact confirmed local face link')
        actual=sorted([{'op':entry['operation_id'],'path':entry['parameter_path'],'value':entry['value']}
                       for entry in state['overrides'] if entry['scope']=='person' and entry['target_id']==person_id],
                      key=lambda leaf:(leaf['op'],leaf['path']))
        if _json(actual)!=_json(capsule['intent']):
            raise ValueError('Association person leaves differ from reviewed shared intent')


def _overrides(person_id,capsule):
    return [{'scope':'person','target_id':person_id,'operation_id':leaf['op'],
             'parameter_path':leaf['path'],'value':deepcopy(leaf['value'])} for leaf in capsule['intent']]


def validate_owner(state, asset_sha256, document_id):
    """Return relevant replica IDs, bound to an independently supplied owner ID.

    This local check does not establish project-wide replica consensus, freshness
    of source files, or permission to publish a multi-owner mutation.
    """
    state=S.check(state); S.digest(asset_sha256); accepted=set()
    for person_id,person in state['persons'].items():
        capsule=person.get('cross_owner')
        if capsule is None or local_member(capsule)['ref']['asset_sha256']!=asset_sha256:continue
        if document_id is None or capsule['local_document_id']!=document_id:
            raise ValueError('Reviewed person replica belongs to another document owner')
        S.token(document_id); accepted.add(person_id)
    return accepted


def create(state, person_id, capsule):
    out=S.check(state); S.token(person_id); capsule=check_descriptor(capsule)
    if person_id in out['persons']:raise ValueError('Association person already exists')
    ref=local_member(capsule)['ref']; face_id=ref['face_instance_id']
    if face_id not in out['faces'] or S.face_ref(out['faces'][face_id])!=ref:
        raise ValueError('Association needs the independently owned current face')
    if any(link['face_instance_id']==face_id and link['state']=='confirmed' for link in out['links']):
        raise ValueError('Unlink existing person explicitly before creating a reviewed association')
    out['revision']+=1; out['association_revision']+=1
    out['persons'][person_id]={'anonymous':True,'cross_owner':capsule}
    out['links'].append({'face_instance_id':face_id,'person_id':person_id,'state':'confirmed',
                         'confirmation_revision':out['association_revision']})
    out['overrides'].extend(_overrides(person_id,capsule))
    return S.check(out)


def update(state, person_id, capsule):
    out=S.check(state); capsule=check_descriptor(capsule)
    previous=out['persons'].get(person_id,{}).get('cross_owner')
    if previous is None:raise ValueError('Unknown reviewed association replica')
    if any(_json(previous[key])!=_json(capsule[key]) for key in ('association_id','local_document_id','members')):
        raise ValueError('Scalar updates cannot change reviewed membership')
    out['persons'][person_id]['cross_owner']=capsule
    out['overrides']=[entry for entry in out['overrides'] if not(entry['scope']=='person' and entry['target_id']==person_id)]
    out['overrides'].extend(_overrides(person_id,capsule)); out['revision']+=1; out['association_revision']+=1
    return S.check(out)


def unlink(state, person_id):
    out=S.check(state)
    if 'cross_owner' not in out['persons'].get(person_id,{}):raise ValueError('Unknown reviewed association replica')
    del out['persons'][person_id]
    out['links']=[link for link in out['links'] if link['person_id']!=person_id]
    out['overrides']=[entry for entry in out['overrides'] if not(entry['scope']=='person' and entry['target_id']==person_id)]
    out['revision']+=1; out['association_revision']+=1
    return S.check(out)


def detach_copy(state):
    """Keep the copied appearance, without inventing membership for a new owner."""
    out=S.check(state)
    for person_id,person in list(out['persons'].items()):
        if 'cross_owner' not in person:continue
        face_id=local_member(person['cross_owner'])['ref']['face_instance_id']
        explicit={(entry['operation_id'],entry['parameter_path']) for entry in out['overrides']
                  if entry['scope']=='face' and entry['target_id']==face_id}
        # Exactly one confirmed person is guaranteed by graph validation; its
        # leaves win over group/all leaves unless a face override already wins.
        for leaf in person['cross_owner']['intent']:
            if (leaf['op'],leaf['path']) not in explicit:
                out['overrides'].append({'scope':'face','target_id':face_id,'operation_id':leaf['op'],
                                         'parameter_path':leaf['path'],'value':deepcopy(leaf['value'])})
        out=unlink(out,person_id)
    return S.check(out)
