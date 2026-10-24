# SPDX-License-Identifier: GPL-3.0-or-later
"""Private scalar planning admission for a complete decoration preset review.

This never grants publication authority or transports support. The complete
mixed transaction mints a separate exact typed authority. AUTHORED / UNRUN.
"""
from . import face_decoration_scope as D


def admit(engine, graph, ref, recipe, *, reviewed_aliases=False):
    from .face_decoration_host import selected, support_status
    from .face_decoration_preset_admission import validate_target
    from . import virtual_copy_people as V, people_state as P
    from .face_decoration_project import require_unaliased
    if type(reviewed_aliases) is not bool:
        raise ValueError('Decoration planning requires an explicit private alias admission')
    ref=P.check_ref(ref); recipe=D.S.check(recipe)
    source,actual=selected(engine,graph,{'scope':'face','target_id':ref['face_instance_id'],'face_ref':ref})
    current=engine._people_preset_capture(); row=V.current_row(engine)
    if validate_target(current,recipe)!=actual:
        raise ValueError('Decoration preset target no longer matches the live selected face')
    if reviewed_aliases:
        if row is None or V.scope(row)!=V.PROJECT:
            raise ValueError('Decoration alias planning requires the existing shared project owner')
    else: require_unaliased(engine,row,{ref['asset_sha256']})
    if D.S.active(recipe):
        ok,reason,_=support_status(engine,graph,source,ref)
        if not ok:raise ValueError(reason)
    return row


def check_scalar_graph(before, candidate, ref):
    """A planning exemption is not permission to change paint or associations."""
    from .people_graph_patch import between
    from .people_state import check_ref
    ref=check_ref(ref)
    if before['association_revision']!=candidate['association_revision']:
        raise ValueError('Mixed preset cannot change retained person associations')
    for change in between(before,candidate):
        if change['collection']!='overrides':
            raise ValueError('Mixed preset cannot create, remove, remap or repaint retained anatomy')
        for side in ('before','after'):
            value=change[side]
            if value is not None and (value['scope']!='face' or value['target_id']!=ref['face_instance_id']):
                raise ValueError('Mixed preset may stage scalars only on its explicit selected face')


def coverage(engine, row, graph, ref, before, *, state=None):
    from .face_decoration_preset_coverage import coverage as complete
    return complete(engine,row,graph,ref,before,state=state)
