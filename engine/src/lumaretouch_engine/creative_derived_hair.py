"""Manual reviewed hair support on actual immutable derived photo sources.

Only existing brush/radial vectors and operator recovery are admitted. Prompted
source-file acquisition is deliberately not replaced with an original-file path.
"""
OPERATION = 'lnx.hair_colour.v1'


def manual_mask(value,*,recovery=False):
    from .hair_colour_assets import mask
    value=mask(value,recovery=recovery)
    if any(obj['kind']=='prompted' for obj in value['objects']):
        raise ValueError('Derived hair support cannot replay original-file prompted selection')
    return value


def request(value):
    from .people_state import token
    if type(value) is not dict or set(value)!={'cmd','request_id','action','people_context','payload'} or value['cmd']!='hair_colour':
        raise ValueError('Derived hair command requires its exact controller envelope')
    token(value['request_id']);action=value['action'];payload=value['payload']
    if type(payload) is not dict:raise ValueError('Derived hair payload must be explicit')
    if action in ('context','clear_support','clear_recovery'):
        if payload!={}:raise ValueError('Hair context/clear accepts no source override')
    elif action in ('preview_support','preview_recovery'):
        if set(payload)!={'mask'}:raise ValueError('Hair preview accepts only owned vectors')
        manual_mask(payload['mask'],recovery=action=='preview_recovery')
    elif action in ('commit_support','commit_recovery'):
        if set(payload)!={'preview_id','confirmed'} or payload['confirmed'] is not True:
            raise ValueError('Hair commit requires its displayed reviewed token')
        token(payload['preview_id'])
    else:raise ValueError('Unadapted derived hair action')


def needed(state,asset):
    from . import hair_colour_state as S, people_algorithms as A
    from .people_resolver import resolve,materialize
    return any(face['asset_sha256']==asset and ('hair_colour' in face['local_assets'] or
        (face['enabled'] and S.active(materialize(resolve(state,key,A.defaults()),S.OPERATION,S.neutral(),S.check))))
        for key,face in state['faces'].items())


def validate(state,assets,evidence,source):
    from . import hair_colour_assets as A, hair_colour_analysis as E, hair_colour_evidence as SAVED
    from .people_state import face_ref
    source=A.source(source)
    evidence_id=None
    if evidence is not None:
        E.check(evidence,source);evidence_id=SAVED.identity(evidence)
    if needed(state,source['sha256']) and evidence is None:
        raise ValueError('Derived hair needs retained measured evidence from this composite')
    for face in state['faces'].values():
        if face['asset_sha256']!=source['sha256'] or A.KIND not in face['local_assets']:continue
        record=A.resolve(state,assets,face_ref(face))
        if record['source']!=source or record['semantic_evidence_sha256']!=evidence_id:
            raise ValueError('Derived hair review/evidence belongs to another effective source')
        manual_mask(record['support']);manual_mask(record['recovery'],recovery=True)


def preview_inputs(engine,state,source):
    from . import hair_colour_project as P, hair_colour_assets as A, hair_colour_evidence as SAVED
    assets=A.check_store(P.store(engine))
    evidence=SAVED.current(engine,source) if needed(state,source['sha256']) else None
    validate(state,assets,evidence,source)
    return {'hair_assets':assets,'hair_evidence':evidence}


def capture(engine,state,snapshot,pc,source):
    from .creative_derived_source import verify,verify_precompute
    from . import hair_colour_project as P, hair_colour_assets as A, hair_colour_analysis as E, hair_colour_evidence as SAVED
    verify(source,state);verify_precompute(state,pc)
    assets=A.check_store(P.store(engine));evidence=None
    if needed(snapshot['state'],source['sha256']):
        evidence=SAVED.for_source(engine.__dict__.get('_hair_colour_evidence',{}),source)
        if evidence is None:
            if pc is None:raise ValueError('Derived hair export lacks measured source evidence')
            evidence=E.capture(pc,source)
    validate(snapshot['state'],assets,evidence,source)
    snapshot['hair_colour_assets']=assets;snapshot['hair_colour_evidence']=E.freeze(evidence)
    return snapshot


def export_inputs(snapshot):
    from . import hair_colour_assets as A, hair_colour_analysis as E
    assets=A.check_store(snapshot.get('hair_colour_assets',{}));evidence=E.freeze(snapshot.get('hair_colour_evidence'))
    if snapshot.get('hair_colour_source_path') is not None:
        raise ValueError('Derived hair export cannot read a physical-original path')
    validate(snapshot['state'],assets,evidence,snapshot['creative_source'])
    return {'hair_assets':assets,'hair_evidence':evidence}
