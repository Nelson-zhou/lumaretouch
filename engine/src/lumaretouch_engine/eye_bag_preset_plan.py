# SPDX-License-Identifier: GPL-3.0-or-later
"""Target-owned eye-bag preset admission, not donor anatomy or mask transfer."""
from . import eye_bag_preserve_scope as EYE


def admit(engine, graph, ref, recipe, *, reviewed_aliases=False):
    from .eye_bag_preserve_host import _live
    from . import people_state as P, eye_bag_preserve_support as SUPPORT
    ref = P.check_ref(ref)
    target = {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}
    if type(reviewed_aliases) is not bool:
        raise ValueError('Shared preset admission requires an explicit private planning choice')
    _, row, _, _, _ = _live(engine, graph, target, strict=not reviewed_aliases)
    if EYE.S.active(recipe):
        SUPPORT.resolve(graph, engine._people_support, ref)
    return row


def check_graph(graph, ref, recipe):
    from .people_resolver import resolve
    from . import people_algorithms as A
    values = A.recipes(resolve(graph, ref['face_instance_id'], A.defaults()))
    if EYE.S.check(values[EYE.OP]) != EYE.S.check(recipe):
        raise ValueError('Eye-bag preset graph differs from its exact selected scalar recipe')
    EYE.S.check_coexistence(recipe, values[A.ENHANCE]['eye_bags'])


def coverage(engine, row, graph, ref):
    from .people_resolver import resolve
    from . import people_algorithms as A, eye_bag_preserve_support as SUPPORT
    values = A.recipes(resolve(graph, ref['face_instance_id'], A.defaults()))
    recipe = EYE.S.check(values[EYE.OP])
    item = {'face_ref': ref, 'scope': 'neutral-no-effect', 'ridge_sha256': None, 'sides': []}
    if EYE.S.active(recipe):
        record, key = SUPPORT.resolve(graph, engine._people_support, ref)
        item.update(scope='target-reviewed-ridge', ridge_sha256=key, sides=sorted(record['row']['eyes']))
    return {'version': 1, 'support_transfer': 'none', 'targets': [item]}
