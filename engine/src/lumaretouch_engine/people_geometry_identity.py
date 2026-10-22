"""Selection-independent geometry identity for rendered-canvas consumers."""
from hashlib import sha256
import json
from . import people_state as S,people_algorithms as A
from .people_resolver import resolve


def record(snapshot):
    """Input is export snapshot['people'], never a selected-face legacy mirror."""
    if snapshot is None:return None
    state=S.check(snapshot['state']);asset=S.digest(snapshot['asset_sha256']);faces=[]
    for key,face in sorted(state['faces'].items()):
        if face['asset_sha256']!=asset or not face['enabled']:continue
        resolved=resolve(state,key,A.defaults());ops=(A.DEFORM,*A.GEOMETRY)
        values={op:resolved['operations'].get(op,{}) for op in ops}
        # Provenance/association labels are not geometry; actual values are.
        values={op:{path:item['value'] for path,item in leaves.items()} for op,leaves in values.items()}
        conflicts=[x for x in resolved['conflicts'] if x['operation_id'] in ops]
        if not conflicts and all(values[op]==A.defaults()[op] for op in ops):continue
        faces.append({'face_ref':S.face_ref(face),'evidence':face['evidence'],'values':values,'conflicts':conflicts})
    return {'asset_sha256':asset,'faces':faces,'overlap_policy':'stable_face_id_first_nonzero','composition':'M(E(N(B(A(x)))))'}


def digest(snapshot):
    return sha256(json.dumps(record(snapshot),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
