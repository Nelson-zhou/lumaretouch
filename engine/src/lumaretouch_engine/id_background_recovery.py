"""Consumer-bound ID-stage recovery evidence; no independent history or masks.

Durable intent remains normalized recovery vectors. Runtime fingerprints are
throwaway review/export evidence and never become project bitmap snapshots.
"""
from copy import deepcopy
import numpy as np
from . import id_background_state as I, effect_recovery_state as S
from . import creative_derived_source as D, local_mask_state as M

TARGET = 'id_background'


def retained(value):
    return any(row['target'] == TARGET for row in S.check(value)['targets'])


def enabled(value):
    return any(row['target'] == TARGET and row['enabled'] for row in S.check(value)['targets'])


def validate_state(owner, value):
    value=S.check(value)
    if not retained(value):return value
    if isinstance(owner,dict) and 'id_background' in owner and '_id_background' in owner:
        raise ValueError('ID recovery cannot choose between simultaneous compositor aliases')
    recipe=I.check(owner.get('id_background',owner.get('_id_background')) if isinstance(owner,dict)
                   else getattr(owner,'_id_background',None))
    if recipe['source'] is not None and value['source'] != recipe['source']:
        raise ValueError('ID recovery vectors and compositor belong to different sources')
    if I.active(recipe) and recipe['source'] is None:
        raise ValueError('ID recovery needs an independently reviewed compositor source')
    return value


def context(engine, *, require_active=False):
    from . import id_background_runtime as R, creative_derived_id_background as C
    recipe=I.check(getattr(engine,'_id_background',None)); active=I.active(recipe)
    if require_active and not active:raise ValueError('Enable the reviewed ID background before adding recovery strokes')
    source=D.binding(engine) if D.record(engine) is not None else M.bind_source(engine)
    if recipe['source'] is not None and recipe['source'] != source:
        raise ValueError('ID recovery consumer belongs to another effective source')
    value={'source':source,'recipe':recipe,
           'asset':C._asset_identity(recipe,getattr(engine,'_id_background_bundle',None)),
           'active':active}
    if active:
        pipe=engine._vram
        key,_,pixels,_,_=R._live_input(engine,recipe)
        if (type(pixels) is not np.ndarray or pixels.dtype != np.float32
                or pixels.shape != (pipe.h,pipe.w,3) or not np.isfinite(pixels).all()
                or np.any(pixels<0) or np.any(pixels>1)):
            raise ValueError('ID recovery requires finite actual SDR source pixels, without clipping')
        proof=R._stage_proof(pipe.id_background)
        if key != getattr(pipe,'_id_background_key',None) or proof != getattr(pipe,'_id_background_field_proof',None):
            raise ValueError('ID recovery consumer needs fresh checked preparation')
        if not proof[0] or proof[1] is not None or proof[2] is None:
            raise ValueError('ID recovery consumer has no complete checked stage')
        # Strict preparation may reinstall identical tensors. Their allocation
        # identity is not review content; actual field bytes and source are.
        value.update(input_key=key,input_sha256=C._hash(pixels),
                     fields_sha256=proof[2][-1],shape=list(pipe.id_background.shape),
                     deformation=C._deformation_key(pipe),activity=C._activity_key(engine))
    return deepcopy(value)


def export_prepare(spec):
    """ID full-resolution preparation runs before the recovery raster owner."""
    spec._id_recovery_consumer=None
    if not enabled(spec.effect_recovery):return
    recipe=I.check(spec.id_background)
    validate_state({'id_background':recipe},spec.effect_recovery)
    from . import creative_derived_id_background as C, id_background_runtime as R
    proof={'recipe':recipe,'asset':C._asset_identity(recipe,spec.id_background_bundle),
           'source':S.check(spec.effect_recovery)['source'],'active':I.active(recipe)}
    if proof['active']:
        R.finish_export(spec)
        proof['fields']=R._prepared_proof(spec,spec.id_background_prepared)
    spec._id_recovery_consumer=deepcopy(proof)


def verify_export(spec):
    if not enabled(spec.effect_recovery):return
    expected=getattr(spec,'_id_recovery_consumer',None)
    if expected is None:raise ValueError('ID recovery lacks its full-resolution consumer proof')
    from . import creative_derived_id_background as C, id_background_runtime as R
    recipe=I.check(spec.id_background)
    actual={'recipe':recipe,'asset':C._asset_identity(recipe,spec.id_background_bundle),
            'source':S.check(spec.effect_recovery)['source'],'active':I.active(recipe)}
    validate_state({'id_background':recipe},spec.effect_recovery)
    if actual['active']:actual['fields']=R._prepared_proof(spec,spec.id_background_prepared)
    if actual!=expected:raise ValueError('ID recovery source, asset, recipe or full compositor fields changed')


def assert_consumer(engine, stage):
    expected=getattr(stage,'id_recovery_context',None)
    if expected is not None and context(engine)!=expected:
        raise ValueError('ID recovery consumer changed during reviewed application')
