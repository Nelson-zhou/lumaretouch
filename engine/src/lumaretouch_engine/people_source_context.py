"""Source-scoped history proof without weakening shared association protection."""
import hashlib
import json

from . import people_state as S, people_algorithms as A
from .people_graph_owner import document_slice
from .people_resolver import resolve


def digest(state, asset):
    state=S.check(state);S.digest(asset)
    local=document_slice(state,asset)
    local.pop('association_revision')
    faces=set(local['faces'])
    links=[row for row in state['links'] if row['face_instance_id'] in faces]
    persons={row['person_id'] for row in links}
    groups={key:value for key,value in state['groups'].items() if faces.intersection(value['face_ids'])}
    shared=[row for row in state['overrides'] if
            (row['scope']=='person' and row['target_id'] in persons) or
            (row['scope']=='group' and row['target_id'] in groups)]
    defaults=A.defaults()
    resolved={}
    for key in sorted(faces):
        value=resolve(state,key,defaults)
        resolved[key]={'operations':value['operations'],'conflicts':value['conflicts']}
    payload={'version':1,'source':local,'links':links,
             'persons':{key:state['persons'][key] for key in sorted(persons)},
             'groups':groups,'shared_overrides':shared,'resolved':resolved}
    raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return hashlib.sha256(b'lumaretouch-portrait-source-context-v1\0'+raw).hexdigest()
