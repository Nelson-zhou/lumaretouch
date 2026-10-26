# SPDX-License-Identifier: GPL-3.0-or-later
"""Global recipe leaves in the existing protected portrait batch ledger. UNRUN.

No additional undo store: the marker belongs to exactly the same graph entry.
Only exposure/WB fields are retained; target-local support is fenced, not copied.
"""
from copy import deepcopy
from . import people_state as S, scope, virtual_copy_people as V
from . import eye_bag_preset_alias_history as BASE
from .people_preset_plan import clone_state

KEY = 'portrait_group_global_recipe'
OPS = frozenset(('lnx.exposure.v1', 'lnx.white_balance.v1'))
FIELDS = frozenset(('_exposure', '_exposure_ref_k', '_wb_options'))


def state(engine, row):
    return engine._people_preset_capture() if row is V.current_row(engine) else row['state']


def projection(value):
    return {key: clone_state(value[key]) for key in FIELDS if key in value}


def desired(current, values):
    out = clone_state(current)
    for key in FIELDS:
        out.pop(key, None)
    out.update(clone_state(values))
    return out


def check(entry):
    if KEY not in entry:
        return None
    marker = entry[KEY]
    if (type(marker) is not dict or set(marker) != {'version', 'modules', 'fields', 'members'}
            or type(marker['version']) is not int or marker['version'] != 1
            or type(marker['modules']) is not dict or not marker['modules']
            or set(marker['modules']) - OPS
            or type(marker['fields']) is not list or not marker['fields']
            or marker['fields'] != sorted(set(marker['fields']))
            or any(type(key) is not str or not key.startswith('_') for key in marker['fields'])
            or type(marker['members']) is not dict or not 1 <= len(marker['members']) <= 8
            or entry.get('ops') != ['lnx.people_graph.v1'] or entry.get('people_changes') != []
            or entry.get('policy') != 'protected_scoped_graph'):
        raise ValueError('Malformed mixed portrait group history')
    # A distinct complete authority must never be spliced into another review.
    if any(key.endswith('_review') for key in entry):
        raise ValueError('Mixed group cannot share another protected review marker')
    targets = entry.get('targets', {})
    if (len(targets) != len(marker['members'])
            or {item['document_id'] for item in targets.values()} != set(marker['members'])):
        raise ValueError('Mixed group history changed exact target membership')
    refs = {}
    from .people_batch_ledger import reviewed_refs
    assets = set()
    for target in targets.values():
        S.token(target['document_id'])
        own = reviewed_refs(target)
        if not own or len(own) > 8 or target['asset_sha256'] in assets:
            raise ValueError('Mixed group history requires distinct sources and own bounded faces')
        assets.add(target['asset_sha256'])
        refs.setdefault(target['people_scope'], set()).update(ref['face_instance_id'] for ref in own)
    scopes = entry.get('people_scoped_changes')
    if (type(scopes) is not list or len(scopes) != len(refs)
            or {item['scope'] for item in scopes} != set(refs)):
        raise ValueError('Mixed group history changed graph ownership')
    for plan in scopes:
        for change in plan['changes']:
            key = change.get('key')
            if (change.get('collection') != 'overrides' or type(key) is not list or len(key) != 4
                    or key[0] != 'face' or key[1] not in refs[plan['scope']]
                    or key[2] not in ('lnx.skin_finish.v1', 'lnx.skin_texture.v1')):
                raise ValueError('Mixed group history cannot change observations or other portrait operations')
    for member in marker['members'].values():
        if (type(member) is not dict or set(member) != {'before', 'after', 'dependencies'}
                or type(member['dependencies']) is not dict or set(member['dependencies']) != {'before', 'after'}):
            raise ValueError('Mixed group history requires both recipe sides')
        for side in ('before', 'after'):
            values = member[side]
            if type(values) is not dict or set(values) - FIELDS or '_exposure' not in values:
                raise ValueError('Mixed group history contains non-global recipe data')
            from .white_balance_recipe import normalize_state
            normalize_state(values)
            dep = member['dependencies'].get(side)
            if type(dep) is not dict or set(dep) != {'context_sha256', 'state_sha256'}:
                raise ValueError('Mixed group history lacks complete target dependency fences')
            for digest in dep.values():
                S.digest(digest)
        expected = scope.apply_modules(member['before'], marker['modules'])
        if BASE.stable(projection(expected)) != BASE.stable(member['after']):
            raise ValueError('Mixed group history changes more than approved global modules')
    return marker


def capture(engine, plans, targets, modules, candidates):
    fields = BASE.state_fields(engine)
    members = {}
    for target in targets.values():
        row = engine._document_versions().find(engine._docs, target['document_id'])[1]
        before, after = state(engine, row), candidates[target['document_id']]
        plan = plans[target['people_scope']]
        members[target['document_id']] = {'before': projection(before), 'after': projection(after),
            'dependencies': {side: BASE.dependencies(engine, row, value, graph, fields)
                for side, value, graph in (('before', before, plan['before']), ('after', after, plan['candidate']))}}
    return {'version': 1, 'modules': deepcopy(modules), 'fields': fields, 'members': members}


def verify(engine, entry, plans, targets, *, redo):
    marker = check(entry)
    if marker is None:
        raise ValueError('Mixed group requires its protected canonical history')
    if marker['fields'] != BASE.state_fields(engine):
        raise ValueError('Mixed history durable state contract changed')
    if {item['document_id'] for item in targets.values()} != set(marker['members']):
        raise ValueError('Mixed history target set changed')
    side = 'before' if redo else 'after'
    for target in targets.values():
        found = engine._document_versions().find(engine._docs, target['document_id'])
        if found is None or V.scope(found[1]) != target['people_scope']:
            raise ValueError('Mixed history exact document owner is unavailable')
        row = found[1]; member = marker['members'][target['document_id']]
        if BASE.dependencies(engine, row, state(engine, row), plans[target['people_scope']]['before'], marker['fields']) != member['dependencies'][side]:
            raise ValueError('Mixed history target recipe or own support changed; protected restore refused')
    return marker


def encode_states(entry, assets):
    if KEY not in entry:
        return entry
    from .project import encode
    check(entry); out = deepcopy(entry); dropped = []
    for member in out[KEY]['members'].values():
        for side in ('before', 'after'):
            member[side] = encode(member[side], assets, dropped, KEY + '.' + side)
    if dropped:
        raise ValueError('Mixed group history cannot be saved lossily')
    return out


def decode_states(entry, assets):
    if KEY not in entry:
        return entry
    from .project import decode
    out = deepcopy(entry); dropped = []
    for member in out[KEY]['members'].values():
        for side in ('before', 'after'):
            member[side] = decode(member[side], assets, dropped, KEY + '.' + side)
    if dropped:
        raise ValueError('Mixed group history cannot be restored lossily')
    check(out)
    return out
