"""Selection-independent geometry identity for rendered-canvas consumers."""
from hashlib import sha256
import json
from . import people_state as S,people_algorithms as A
from . import hair_volume_state as V
from .people_resolver import resolve, materialize


def record(snapshot):
    """Input is export snapshot['people'], never a selected-face legacy mirror."""
    if snapshot is None:return None
    state=S.check(snapshot['state']);asset=S.digest(snapshot['asset_sha256']);faces=[];hair_volume=[]
    for key,face in sorted(state['faces'].items()):
        if face['asset_sha256']!=asset or not face['enabled']:continue
        resolved=resolve(state,key,A.defaults());ops=(A.DEFORM,*A.GEOMETRY)
        volume=materialize(resolved,V.OP,V.neutral(),V.check)
        support=face['local_assets'].get(V.SUPPORT_KIND)
        if V.active(volume) or support is not None:
            # Body consumers also pass graph-only snapshots. The canonical
            # pointer pins the complete immutable support without requiring a
            # second asset bank or replacing its render-time validation here.
            source={'sha256':asset,'width':face['evidence']['source_width'],
                    'height':face['evidence']['source_height']}
            if snapshot.get('creative_source') is not None and snapshot['creative_source']!=source:
                raise ValueError('Hair-volume geometry identity belongs to another effective source')
            hair_volume.append({'face_ref':S.face_ref(face),'source':source,
                                'evidence':face['evidence'],'recipe':volume,'support':support})
        values={op:resolved['operations'].get(op,{}) for op in ops}
        # Provenance/association labels are not geometry; actual values are.
        values={op:{path:item['value'] for path,item in leaves.items()} for op,leaves in values.items()}
        conflicts=[x for x in resolved['conflicts'] if x['operation_id'] in ops]
        if not conflicts and all(values[op]==A.defaults()[op] for op in ops):continue
        faces.append({'face_ref':S.face_ref(face),'evidence':face['evidence'],'values':values,'conflicts':conflicts})
    result={'asset_sha256':asset,'faces':faces,'overlap_policy':'stable_face_id_first_nonzero','composition':'M(E(N(B(A(x)))))'}
    # Do not change any legacy identity bytes when this family contributes
    # neither active geometry nor a current enabled owner's support pointer.
    if hair_volume:result['hair_volume']={'operation_id':V.OP,'faces':hair_volume}
    return result


def digest(snapshot):
    return sha256(json.dumps(record(snapshot),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
