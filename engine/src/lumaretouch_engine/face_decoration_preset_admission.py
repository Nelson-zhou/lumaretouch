# SPDX-License-Identifier: GPL-3.0-or-later
"""Preset-only decoration scalar staging; never broad derived transfer authority."""
from . import eye_bag_preset_admission as GENERAL, creative_derived_source as SOURCE
from . import face_decoration_scope as D
involved=GENERAL.involved
ProducerContext=GENERAL.ProducerContext


def validate_target(state, recipe):
    ref=D.require_target(state,recipe)
    base=SOURCE.record(state)
    if base is not None:
        from .creative_document_host import require_photo_return
        from .creative_derived_repairs import validate_stacks
        require_photo_return(base); SOURCE.verify_precompute(state,state.get('_precompute')); validate_stacks(state)
        proof=D.owner_identity(state)['source_proof']; binding=SOURCE.binding(state)
        if proof['creative_source']!=binding or ref['asset_sha256']!=binding['sha256']:
            raise ValueError('Decoration preset owner and actual immutable composite differ')
    return ref


def require_modules(state, modules, source_proof=None, *, related_states=(), replace_legacy=False):
    if type(modules) is not dict or D.OP not in modules:
        return GENERAL.require_modules(state,modules,source_proof,related_states=related_states,replace_legacy=replace_legacy)
    from .scope import check_scope
    check_scope(list(modules))
    params=D.check_params(modules[D.OP]); validate_target(state,params['recipe'])
    if source_proof is not None and SOURCE.check_row_proof(source_proof)!=D.owner_identity(state)['source_proof']:
        raise ValueError('Decoration preset source proof differs from current owner')
    if any(SOURCE.record(other)!=SOURCE.record(state) for other in related_states):
        raise ValueError('Decoration preset cannot replace immutable source content')
    ordinary={op:p for op,p in modules.items() if op!=D.OP}
    clean=GENERAL.require_modules(state,ordinary,source_proof,related_states=related_states,replace_legacy=replace_legacy) if ordinary else {}
    if not ordinary and replace_legacy: raise ValueError('Unexpected legacy replacement choice')
    return {**clean,D.OP:params}


def candidate(state, modules, *, local_replace_legacy=False, replace_legacy=False):
    if D.OP not in modules:
        return GENERAL.candidate(state,modules,local_replace_legacy=local_replace_legacy,replace_legacy=replace_legacy)
    clean=require_modules(state,modules,replace_legacy=replace_legacy)
    ordinary={op:p for op,p in clean.items() if op!=D.OP}
    out=GENERAL.candidate(state,ordinary,local_replace_legacy=local_replace_legacy,replace_legacy=replace_legacy) if ordinary else dict(state)
    out[D.FIELD]=clean[D.OP]['recipe']; out[D.REQUESTED]=True
    return out


def require_candidate(before, after, modules, source_proof=None, *, replace_legacy=False, local_replace_legacy=False, producer_context=None):
    if D.OP not in modules:
        return GENERAL.require_candidate(before,after,modules,source_proof,replace_legacy=replace_legacy,
            local_replace_legacy=local_replace_legacy,producer_context=producer_context)
    require_modules(before,modules,source_proof,related_states=(after,),replace_legacy=replace_legacy)
    expected=candidate(before,modules,local_replace_legacy=local_replace_legacy,replace_legacy=replace_legacy)
    expected=GENERAL._producers(expected,before,modules,producer_context)
    from .creative_derived_transfer import _same
    if not _same(expected,after):
        raise ValueError('Decoration preset may change chosen scalars only, never support, analysis, source or repairs')
    return after
