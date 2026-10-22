"""Conservative legacy-to-bank migration; never changes original legacy records.

Only exact retained landmark-owner evidence can auto-bind an existing recipe.
Box-only deform/enhance banks and ownerless active lip recipes are archived for
review, not guessed from current selection. Source-owned recovery stays retained.
"""
from . import people_state as S, people_algorithms as A, people_legacy as L


def migrate(state, legacy, asset_sha256, *, history_ref=None):
    out = S.check(state); S.digest(asset_sha256)
    if any(x['legacy_key']=='_migration_complete' and x['asset_sha256']==asset_sha256 for x in out['unresolved_legacy']):
        return out
    # Idempotence is keyed by retained legacy key/source. Repeated loads must not
    # duplicate old intent, including after an unresolved record was confirmed.
    archived = {(x['legacy_key'],x['asset_sha256']) for x in out['unresolved_legacy']}
    def archive(key,value,owner=None):
        nonlocal out
        if (key,asset_sha256) not in archived:
            out=L.archive(out,legacy_key=key,serialized_intent=value,asset_sha256=asset_sha256,owner_evidence=owner,history_ref=history_ref)
            archived.add((key,asset_sha256))
    def install(op,value,face_id):
        nonlocal out
        for path,amount in A.leaves(value).items():
            key=('face',face_id,op,path)
            # Never overwrite an already edited migrated bank on reopen.
            if not any((x['scope'],x['target_id'],x['operation_id'],x['parameter_path'])==key for x in out['overrides']):
                out=S.set_override(out,'face',face_id,op,path,amount)
    for key,op in zip(('_brow_shape','_nose_shape','_eye_shape','_mouth_shape'),A.GEOMETRY):
        neutral,validator=A.specifications()[op]; value=validator(legacy.get(key))
        if value==neutral: continue
        owner=legacy.get(key+'_owner')
        matches=[f for f in out['faces'].values() if f['asset_sha256']==asset_sha256 and f['evidence']['landmark_digest']==owner]
        archive(key,value,owner)
        if owner and len(matches)==1:
            install(op,value,matches[0]['face_instance_id'])
            row=next(x for x in out['unresolved_legacy'] if x['legacy_key']==key and x['asset_sha256']==asset_sha256)
            if row['status']=='unresolved': row['status']='confirmed';row['binding']=S.face_ref(matches[0]);out['revision']+=1
    # Legacy default was named all-person but only the editing cursor rendered.
    # Promoting it would expand an old edit onto previously unchanged faces.
    # Retain intent until an explicit reviewed face or asset-wide scope is chosen.
    defaults=legacy.get('_deform_default') or {}
    if defaults:
        for kind,amount in defaults.items():
            if '/'+kind not in A.defaults()[A.DEFORM]:raise ValueError('Unknown legacy deform kind')
        archive('_deform_default',defaults)
        if not any(defaults.values()):
            row=next(x for x in out['unresolved_legacy'] if x['legacy_key']=='_deform_default' and x['asset_sha256']==asset_sha256)
            row['status']='retained'
    overrides=legacy.get('_deform_overrides') or []
    if overrides:
        archive('_deform_overrides',overrides)
        next(x for x in out['unresolved_legacy'] if x['legacy_key']=='_deform_overrides' and x['asset_sha256']==asset_sha256)['status']='retained'
        for index,value in enumerate(overrides):archive('_deform_override_'+str(index),value,value.get('box'))
    fallback=(legacy.get('_deform') or {}).get('amounts') or {}
    if any(fallback.values()) and not overrides and not any((legacy.get('_deform_default') or {}).values()): archive('_deform',legacy['_deform'])
    lip=legacy.get('_lip_makeup')
    if lip is not None and A.specifications()[A.LIP][1](lip)!=A.specifications()[A.LIP][0]:
        owner=legacy.get('_lip_makeup_owner')
        if owner is None:
            from . import effect_recovery_state as R
            rows=R.check(legacy.get('_effect_recovery'))['targets']
            owner=next((r['owner'] for r in rows if r['target']=='lip_makeup'),None)
        archive('_lip_makeup',lip,owner)
        landmark=owner.get('landmarks_sha256') if isinstance(owner,dict) and owner.get('source_sha256')==asset_sha256 else owner if isinstance(owner,str) else None
        matches=[f for f in out['faces'].values() if f['asset_sha256']==asset_sha256 and f['evidence']['landmark_digest']==landmark]
        if landmark and len(matches)==1:
            install(A.LIP,A.specifications()[A.LIP][1](lip),matches[0]['face_instance_id'])
            row=next(x for x in out['unresolved_legacy'] if x['legacy_key']=='_lip_makeup' and x['asset_sha256']==asset_sha256)
            row['status']='confirmed';row['binding']=S.face_ref(matches[0]);out['revision']+=1
    enhance=legacy.get('_enhance') or {}
    if any(value for key,value in (enhance.get('amounts') or {}).items() if key!='wrinkle_nasolabial_unlocked'): archive('_enhance',enhance)
    recovery=legacy.get('_effect_recovery')
    if recovery and recovery.get('targets'):
        archive('_effect_recovery',recovery)
        if not any(r['target'] in ('lip_makeup','facial_wrinkles') for r in recovery['targets']):
            row=next(x for x in out['unresolved_legacy'] if x['legacy_key']=='_effect_recovery' and x['asset_sha256']==asset_sha256)
            row['status']='retained'
    manual=legacy.get('_face_manual') or {}
    if manual.get('disabled'):archive('_face_manual',manual)
    archive('_migration_complete',{'version':1})
    marker=next(x for x in out['unresolved_legacy'] if x['legacy_key']=='_migration_complete' and x['asset_sha256']==asset_sha256)
    marker['status']='retained'
    return S.check(out)
