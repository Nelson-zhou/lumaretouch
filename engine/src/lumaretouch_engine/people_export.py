"""Adapt the existing export owner; never a second export/batch engine."""
from copy import copy
from . import people_state as S, people_support_assets as ASSETS
from . import people_algorithms as A


def fastpath_blocker(snapshot):
    """A neutral legacy mirror cannot bypass retained per-person intent.

    A genuinely neutral detection census remains eligible for passthrough.
    Unknown/conflicting requests and owned assets must enter checked preparation,
    where refusal is visible rather than exporting an unedited original.
    """
    if snapshot is None:return False
    from . import people_resolver as R
    state=S.check(snapshot['state']);asset=S.digest(snapshot['asset_sha256'])
    if any(row['asset_sha256']==asset and row['status']=='unresolved' for row in state['unresolved_legacy']):return True
    defaults=A.defaults();specs=A.specifications()
    faces=[face for face in state['faces'].values() if face['asset_sha256']==asset and face['enabled']]
    if not faces and any(row['scope']=='all_people' and row['target_id']==asset and row['value']!=defaults.get(row['operation_id'],{}).get(row['parameter_path']) for row in state['overrides']):return True
    for face in faces:
        if face['local_assets']:return True
        try:values=A.recipes(R.resolve(state,face['face_instance_id'],defaults))
        except ValueError:return True
        if any(value!=specs[operation][0] for operation,value in values.items()):return True
    return False


def isolated_snapshot(snapshot,*,for_document):
    """Retained legacy mirrors are not a second copy of a bank's visual effects."""
    people=snapshot.get('people')
    if people is None:return snapshot
    if not for_document:raise ValueError('People graph must be frozen for this exact target photo')
    S.check(people['state']);S.digest(people['asset_sha256']);ASSETS.check_store(people.get('support_assets',{}))
    snap=dict(snapshot)
    for key,op in zip(('brow_shape','nose_shape','eye_shape','mouth_shape'),A.GEOMETRY):
        snap[key]=A.specifications()[op][0];snap[key+'_owner']=None
    snap.update(lip_makeup=A.specifications()[A.LIP][0],deform={'amounts':{},'built':False},deform_defer=False,
                enhance={'amounts':{},'built':False},enhance_defer=False)
    from . import effect_recovery_state as R
    recovery=R.check(snap.get('effect_recovery'))
    recovery['targets']=[row for row in recovery['targets'] if row['target'] not in ('lip_makeup','facial_wrinkles','eye_light','blush_makeup','lipstick','eyeliner','eyelash','brow_makeup','iris_makeup')]
    if not recovery['targets']:recovery=R.empty()
    snap['effect_recovery']=recovery
    return snap


def prepare(spec,source,repaired):
    if getattr(spec,'people',None) is None:return None
    from .people_engine_runtime import prepare_export
    from .cpu_memory_budget import available_estimate
    snapshot=spec.people
    recovery=ASSETS.raster(snapshot['state'],snapshot.get('support_assets',{}),snapshot['asset_sha256'],source.shape[:2])
    return prepare_export(snapshot,source,repaired,byte_budget=available_estimate(),recovery_assets=recovery,body_pose=getattr(spec,'body_pose',None),body_source_path=getattr(spec,'body_pose_source_path',None))


def verify_source(snapshot,path):
    body=snapshot.get('body_pose')
    if body is not None:
        from .local_mask_state import source_digest
        if source_digest(path)!=body['source']['sha256']:raise ValueError('Frozen body observations belong to another source asset')
    people=snapshot.get('people')
    if people is None:return
    from .local_mask_state import source_digest
    if source_digest(path)!=people['asset_sha256']:raise ValueError('Frozen people graph belongs to another source asset')
