# SPDX-License-Identifier: GPL-3.0-or-later
"""Preset-only derived collarbone admission, never a general batch exemption.

This only builds scalar intent. The preset controller still requires complete
mixed-plan images, exact target confirmation and frozen graph publication.
Generic scope installation and derived-transfer allowlists remain unchanged.
"""
from . import creative_derived_transfer as GENERAL
from . import creative_derived_source as SOURCE
from . import collarbone_scope as COLLARBONE

involved = GENERAL.involved


def validate_target(state, recipe):
    """Bind actual canonical derived pixels and existing independent evidence."""
    from .creative_document_host import require_photo_return
    from .creative_derived_repairs import validate_stacks
    base = SOURCE.record(state)
    if base is None:
        raise ValueError('Derived collarbone preset needs its actual immutable composite, not original-file state')
    require_photo_return(base)
    ref = COLLARBONE.require_target(state, recipe)
    identity = COLLARBONE.owner_identity(state)
    proof = identity['source_proof']; expected = SOURCE.binding(state)
    if proof['creative_source'] != expected or proof['asset_sha256'] != expected['sha256'] or ref['asset_sha256'] != expected['sha256']:
        raise ValueError('Derived collarbone preset owner, face and actual source pixels disagree')
    SOURCE.verify_precompute(state, state.get('_precompute'))
    validate_stacks(state)
    return ref


def require_modules(state, modules, source_proof=None, *, related_states=()):
    if not involved(state, source_proof, related_states=related_states) or type(modules) is not dict or COLLARBONE.OP not in modules:
        return GENERAL.require_modules(state, modules, source_proof, related_states=related_states)
    from . import scope as SC
    # This specialized path cannot authorize original/derived rebinding, even
    # if a dormant receipt claims to have reviewed the old composite.
    base = SOURCE.record(state)
    if base is None: raise ValueError('Derived preset proof cannot authorize an original-source target')
    proof = SOURCE.check_row_proof(source_proof) if source_proof is not None else None
    if proof is not None and proof['creative_source'] != SOURCE.binding(state):
        raise ValueError('Preset proof belongs to another effective source')
    for related in related_states:
        if SOURCE.record(related) != base:
            raise ValueError('Derived collarbone preset cannot switch canonical source content')
    SC.check_scope(list(modules))
    ordinary = {op: params for op, params in modules.items() if op != COLLARBONE.OP}
    clean = GENERAL.require_modules(state, ordinary, source_proof, related_states=related_states) if ordinary else {}
    params = COLLARBONE.check_params(modules[COLLARBONE.OP])
    validate_target(state, params['recipe'])
    return {**clean, COLLARBONE.OP: params}


def candidate(state, modules, *, local_replace_legacy=False):
    from .optics_auto_scope import candidate as ordinary_candidate
    if SOURCE.record(state) is None or COLLARBONE.OP not in modules:
        return ordinary_candidate(state, modules, local_replace_legacy=local_replace_legacy)
    clean = require_modules(state, modules)
    ordinary = {op: params for op, params in clean.items() if op != COLLARBONE.OP}
    out = ordinary_candidate(state, ordinary, local_replace_legacy=local_replace_legacy) if ordinary else dict(state)
    # No copied support, source binding, classification, mask or manual trace.
    out[COLLARBONE.FIELD] = clean[COLLARBONE.OP]['recipe']
    out[COLLARBONE.REQUESTED] = True
    return out


def require_candidate(before, after, modules, source_proof=None):
    if SOURCE.record(before) is None or COLLARBONE.OP not in modules:
        return GENERAL.require_candidate(before, after, modules, source_proof)
    require_modules(before, modules, source_proof, related_states=(after,))
    expected = candidate(before, modules)
    if not GENERAL._same(expected, after):
        raise ValueError('Derived collarbone preset may replace reviewed scalars only, not target source, repair, analysis or support')
    return after
