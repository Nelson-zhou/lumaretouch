# SPDX-License-Identifier: GPL-3.0-or-later
"""History/project validation through existing graph and support owners. UNRUN."""
from . import hair_smoothing_state as S


def validate_leaf(path, value):
    if path != '/amount':
        raise ValueError('Hair smoothing intent cannot carry source pixels, support or consent')
    S.check({'version': 1, 'amount': value})


def require_face_scope(scope):
    if scope != 'face':
        raise ValueError('Hair smoothing is current-photo/current-face only; shared inheritance is not authorized')


def validate_graph(state):
    from . import people_state as P
    state = P.check(state)
    for row in state['overrides']:
        if row['operation_id'] == S.OP:
            validate_leaf(row['parameter_path'], row['value']); require_face_scope(row['scope'])
    return state


def validate_records(value):
    if isinstance(value, dict):
        for name in ('people_graph', '_people_state'):
            if name in value:
                validate_graph(value[name])
        if value.get('operation_id') == S.OP and 'parameter_path' in value:
            validate_leaf(value['parameter_path'], value['value']); require_face_scope(value.get('scope'))
        for child in value.values():
            validate_records(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            validate_records(child)


def validate_project(value):
    """Nearest document-owned immutable banks; historical owners are not rebound."""
    from . import people_state as P
    from . import hair_smoothing_support as C
    from .people_support_assets import content_digest
    validate_records(value)
    def visit(node, assets, hair_assets, evidence):
        if isinstance(node, dict):
            assets = node.get('people_support_assets', assets)
            hair_assets = node.get('hair_colour_assets', hair_assets)
            evidence = node.get('hair_colour_evidence', evidence)
            if type(assets) is not dict or type(hair_assets) is not dict or type(evidence) is not dict:
                raise ValueError('Hair smoothing history lost its document-owned support banks')
            if 'people_support_assets' in node:
                for key, record in assets.items():
                    if type(record) is dict and record.get('row', {}).get('target') == S.KIND:
                        C.check_record(record)
                        if content_digest(record) != key:
                            raise ValueError('Hair smoothing retained support hash changed')
                        C.retained_support(record, hair_assets, evidence)
            if 'face_instance_id' in node and S.KIND in node.get('local_assets', {}):
                ref = P.check_ref(P.face_ref(node)); descriptor = node['local_assets'][S.KIND]
                record = C.check_record(assets.get(descriptor.get('content_sha256')))
                if (descriptor != {'owner': ref, 'kind': S.KIND, 'content_sha256': content_digest(record)}
                        or record['face_ref'] != ref):
                    raise ValueError('Hair smoothing historical support belongs to another exact face')
                C.retained_support(record, hair_assets, evidence)
            if node.get('_people_history') is not None:
                from .people_document_history import scoped_state
                validate_graph(scoped_state(node['_people_history']))
            for name, child in node.items():
                if name not in ('people_support_assets', 'hair_colour_assets', 'hair_colour_evidence'):
                    visit(child, assets, hair_assets, evidence)
        elif isinstance(node, (list, tuple)):
            for child in node:
                visit(child, assets, hair_assets, evidence)
    visit(value, {}, {}, {})


def refuse_transfer(*args, **kwargs):
    raise ValueError('Hair smoothing cannot transfer nonzero preset/cohort/alias intent without independent target support and review')


def refuse_recovery(*args, **kwargs):
    raise ValueError('Hair smoothing has its own visible-hair review; generic face recovery cannot authorize it')


def require_parked_transition(before, candidate):
    from .hair_smoothing_host import _hair_smoothing_signature
    if _hair_smoothing_signature(before) != _hair_smoothing_signature(candidate):
        raise ValueError('Parked hair smoothing changes require that target\'s own source/support/crop review')
    return candidate


def require_unreviewed_transition(before, candidate):
    """Transfer/preset staging cannot activate or replace independently owned review.

    Exact explicit zero of an existing target is allowed without transferring any
    support. Adding donor pointers, changing a nonzero recipe, or rebinding an
    active owner requires the dedicated current-target review transaction.
    """
    from .hair_smoothing_host import _hair_smoothing_signature
    left, right = _hair_smoothing_signature(before), _hair_smoothing_signature(candidate)
    if left == right:
        return candidate
    for key in set(left) | set(right):
        old, new = left.get(key), right.get(key)
        if old == new:
            continue
        if new is None or new['amount'] != 0:
            raise ValueError('Nonzero hair smoothing transfer requires independent target support/crop review')
        if old is None:
            if new['support'] is not None:
                raise ValueError('Hair smoothing donor support cannot transfer with a neutral parameter')
        elif (new['face_ref'] != old['face_ref'] or new['evidence'] != old['evidence']
                or new['support'] not in (None, old['support'])):
            raise ValueError('Hair smoothing transfer cannot replace retained ownership, even when amount is zero')
    return candidate
