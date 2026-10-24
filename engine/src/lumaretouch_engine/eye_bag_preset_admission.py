# SPDX-License-Identifier: GPL-3.0-or-later
"""Preset-only scalar staging, never portable target support or review authority."""
from dataclasses import dataclass
from . import collarbone_derived_preset as GENERAL
from . import creative_derived_source as SOURCE
from . import eye_bag_preserve_scope as EYE

involved = GENERAL.involved



@dataclass(frozen=True)
class ProducerContext:
    """Private host input; each supplied producer is reverified, not trusted."""
    row: dict
    document_id: str
    revision: str
    optics_record: dict | None = None
    reference_record: dict | None = None


def _producers(expected, before, modules, context):
    from . import optics_auto_scope as OA, reference_color_scope as RC
    if context is not None and type(context) is not ProducerContext:
        raise ValueError('Producer context is private typed host evidence, not request metadata')
    if OA.OP not in modules and RC.OP not in modules:
        if context is not None and (context.optics_record is not None or context.reference_record is not None):
            raise ValueError('Unselected preset producer cannot replace any target state')
        return expected
    if type(context) is not ProducerContext:
        raise ValueError('Mixed eye-bag preset needs exact internally retained target producer proofs')
    if type(context.row) is not dict or type(context.document_id) is not str or type(context.revision) not in (str,int):
        raise ValueError('Invalid internally retained producer target identity')
    if OA.OP in modules:
        expected['_optics'] = OA.verify_target(context.optics_record, before, expected,
            context.row, context.document_id, str(context.revision), modules[OA.OP])
    elif context.optics_record is not None:
        raise ValueError('Unselected auto optics cannot replace the target recipe')
    if RC.OP in modules:
        recipe = RC.verify_target(context.reference_record, before, expected,
            context.row, context.document_id, str(context.revision), modules[RC.OP])
        RC.apply_verified(expected, recipe)
    elif context.reference_record is not None:
        raise ValueError('Unselected reference fit cannot replace the target recipe')
    return expected


def _dedicated(state, modules, replace_legacy):
    return type(modules) is dict and EYE.OP in modules and (EYE.S.active(EYE.check_params(modules[EYE.OP])['recipe']) or replace_legacy or SOURCE.record(state) is not None)


def require_modules(state, modules, source_proof=None, *, related_states=(), replace_legacy=False):
    if type(replace_legacy) is not bool:
        raise ValueError('Eye-bag legacy replacement requires an explicit boolean choice')
    if not _dedicated(state, modules, replace_legacy):
        if replace_legacy: raise ValueError('Eye-bag replacement choice requires its selected operation')
        return GENERAL.require_modules(state, modules, source_proof, related_states=related_states)
    from . import collarbone_scope as COLLAR, scope as SC
    if COLLAR.OP in modules and (EYE.S.active(EYE.check_params(modules[EYE.OP])['recipe']) or replace_legacy):
        raise ValueError('Eye-bag and collarbone require separate exact visual preset transactions')
    SC.check_scope(list(modules))
    params = EYE.check_params(modules[EYE.OP])
    from . import enhance_scope as ENHANCE
    if EYE.S.active(params['recipe']) and ENHANCE.OP in modules:
        legacy = ENHANCE.check_params(modules[ENHANCE.OP])['recipe']['amounts']['eye_bags']
        if legacy > 0:
            raise ValueError('Preset selects both legacy and v2 eye-bag effects; deselect one rather than silently discard it')
    EYE.require_target(state)
    original = SOURCE.record(state)
    if SOURCE.record(state) is not None:
        from .creative_document_host import require_photo_return
        from .creative_derived_repairs import validate_stacks
        if EYE.S.active(params['recipe']):
            require_photo_return(original)
            SOURCE.verify_precompute(state, state.get('_precompute'))
            validate_stacks(state)
        proof = EYE.owner_identity(state)['source_proof']
        if proof['creative_source'] != SOURCE.binding(state):
            raise ValueError('Eye-bag preset target belongs to another derived source')
    if source_proof is not None:
        proof = SOURCE.check_row_proof(source_proof)
        if proof != EYE.owner_identity(state)['source_proof']:
            raise ValueError('Eye-bag preset proof differs from current effective source')
    if any(SOURCE.record(other) != original for other in related_states):
        raise ValueError('Eye-bag preset cannot switch immutable source content')
    ordinary = {key: value for key, value in modules.items() if key != EYE.OP}
    clean = GENERAL.require_modules(state, ordinary, source_proof, related_states=related_states) if ordinary else {}
    return {**clean, EYE.OP: params}


def candidate(state, modules, *, local_replace_legacy=False, replace_legacy=False):
    if not _dedicated(state, modules, replace_legacy):
        if replace_legacy: raise ValueError('Eye-bag replacement choice requires its operation')
        return GENERAL.candidate(state, modules, local_replace_legacy=local_replace_legacy)
    clean = require_modules(state, modules, replace_legacy=replace_legacy)
    ordinary = {key: value for key, value in clean.items() if key != EYE.OP}
    out = GENERAL.candidate(state, ordinary, local_replace_legacy=local_replace_legacy) if ordinary else dict(state)
    EYE.install_reviewed(out, clean[EYE.OP], replace_legacy=replace_legacy)
    return out


def require_candidate(before, after, modules, source_proof=None, *, replace_legacy=False, local_replace_legacy=False, producer_context=None):
    if not _dedicated(before, modules, replace_legacy):
        return GENERAL.require_candidate(before, after, modules, source_proof)
    require_modules(before, modules, source_proof, related_states=(after,), replace_legacy=replace_legacy)
    expected = candidate(before, modules, replace_legacy=replace_legacy, local_replace_legacy=local_replace_legacy)
    expected = _producers(expected, before, modules, producer_context)
    from .creative_derived_transfer import _same
    if not _same(expected, after):
        raise ValueError('Eye-bag preset may change selected scalars only, not target support, source, repairs or analysis')
    return after
