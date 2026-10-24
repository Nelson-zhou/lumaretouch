# SPDX-License-Identifier: GPL-3.0-or-later
"""Target-only coverage disclosure, never portable support or render authority.

The existing batch owner first runs the real full-source candidate renderer.
This helper then describes each target's own attached review using its exact
document state, portrait context and body bank. It cannot grant a body/person
link, copy a source review, or turn a missing descriptor into body coverage.
"""
from . import people_state as P, skin_colour_state as S


def _state(family):
    if family == 'skin_colour':
        return S
    if family == 'skin_finish':
        from . import skin_finish_state
        return skin_finish_state
    raise ValueError('Unknown skin coverage family')


def attached(graph, face_ref, *, family='skin_colour'):
    from .skin_colour_body_support import family_spec
    kind, _ = family_spec(family)
    ref = P.check_ref(face_ref); face = graph['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face) != ref or not face['enabled']:
        label = 'Skin-colour' if family == 'skin_colour' else 'Skin-finish'
        raise ValueError(f'{label} coverage target is missing, disabled or changed')
    return kind in face['local_assets']


def describe(graph, assets, face_ref, body_bank, analysis, recipe, *, family='skin_colour'):
    """Disclosure only; no rasterization, inference, native solve or mutation.

    Neutral intent describes no effect without demanding stale body review,
    preserving the existing ability to reset an unresolved attached extension.
    Active attached evidence must resolve, never silently fall back to face-only.
    """
    state = _state(family)
    ref = P.check_ref(face_ref); has_body = attached(graph, ref, family=family)
    result = {'face_ref': ref, 'scope': 'neutral-no-effect', 'body_review_sha256': None}
    if not state.active(recipe):
        return result
    result['scope'] = 'face-only'
    if has_body:
        from .skin_colour_body_support import resolve
        # Preserve the original colour call/default; finish must explicitly
        # select its own descriptor family, never borrow a colour review.
        resolved = (resolve(graph, assets, ref, body_bank, analysis) if family == 'skin_colour'
                    else resolve(graph, assets, ref, body_bank, analysis, family='skin_finish'))
        if resolved is None:
            raise ValueError('Attached body-skin review was omitted during target resolution')
        _, key = resolved; P.digest(key)
        result.update(scope='face-and-reviewed-body', body_review_sha256=key)
    return result


def for_target(engine, row, candidate, payload, *, family='skin_colour'):
    """Called only after the existing actual full-candidate validation succeeds.

    Portable ``parameters`` stay unchanged. The result is a frozen review DTO,
    separate from preset scalars and the canonical immutable support records.
    """
    state = _state(family)
    if not any(leaf['operation_id'] == state.OP for leaf in payload['parameters']):
        return None
    from . import people_algorithms as A, people_resolver as R
    graph = P.check(candidate); refs = payload['target_refs']
    recipes = {ref['face_instance_id']: A.recipes(R.resolve(graph, ref['face_instance_id'], A.defaults()))[state.OP]
               for ref in refs}
    needs_body = any(attached(graph, ref, family=family) and state.active(recipes[ref['face_instance_id']]) for ref in refs)
    assets = {}; analyses = {}; bank = None
    if needs_body:
        from .full_candidate_render import people_context
        from .body_pose_project import bank as body_bank
        context = people_context(engine, row)
        # Identical image bytes do not authorize another document's support.
        # Use the same exact target-state snapshot owner as the full renderer.
        snapshot = engine._people_export_snapshot(row['state'], row['path'], graph,
            context=context, document_id=payload['target_document']['document_id'])
        if (snapshot is None or snapshot['state'] != graph
                or snapshot.get('document_id') != payload['target_document']['document_id']
                or any(ref['asset_sha256'] != snapshot['asset_sha256'] for ref in refs)):
            label = 'Skin-colour' if family == 'skin_colour' else 'Skin-finish'
            raise ValueError(f'{label} coverage snapshot differs from the reviewed target')
        assets = snapshot.get('support_assets', {}); analyses = snapshot['analyses']
        # Body ownership is document state, not a portrait-context/source bank.
        bank = body_bank(row['state'])
    return {'version': 1, 'support_transfer': 'none', 'targets': [
        describe(graph, assets, ref, bank, analyses.get(ref['face_instance_id']), recipes[ref['face_instance_id']], family=family)
        for ref in refs]}
