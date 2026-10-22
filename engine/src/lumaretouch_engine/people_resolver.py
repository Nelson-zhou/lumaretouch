"""One sparse inheritance resolver for UI, preview, export and transfer.

Only confirmed anonymous links inherit person intent. Editable labels do not
imply identity, age or gender facts. Equal-priority conflicting groups refuse.
"""
from copy import deepcopy
from . import people_state as S


def resolve(state, face_id, defaults):
    state = S.check(state)
    if face_id not in state['faces']: raise ValueError('Unknown face instance')
    # defaults: operation_id -> {JSON pointer: scalar}; caller validates domains.
    values = {}
    for operation, leaves in defaults.items():
        S.token(operation)
        for path, value in leaves.items():
            S.parameter_path(path); S.scalar(value)
            values[(operation, path)] = {'value': value, 'scope': 'default', 'target_id': None, 'overridden': False}
    persons = {x['person_id'] for x in state['links'] if x['face_instance_id'] == face_id and x['state'] == 'confirmed'}
    groups = {k: v['priority'] for k, v in state['groups'].items() if face_id in v['face_ids']}
    candidates = {}
    for entry in state['overrides']:
        scope, target = entry['scope'], entry['target_id']
        eligible = (scope == 'all_people' and target == state['faces'][face_id]['asset_sha256']) or (scope == 'face' and target == face_id) or (scope == 'person' and target in persons) or (scope == 'group' and target in groups)
        if not eligible: continue
        rank = {'all_people': (0, 0), 'group': (1, groups.get(target, 0)), 'person': (2, 0), 'face': (3, 0)}[scope]
        key = (entry['operation_id'], entry['parameter_path'])
        candidates.setdefault(key, []).append((rank, entry))
    conflicts = []
    for key, choices in candidates.items():
        rank = max(x[0] for x in choices)
        winners = sorted((x[1] for x in choices if x[0] == rank), key=lambda x: x['target_id'] or '')
        first = winners[0]
        # bool and number are distinct parameter domains, even though Python == overlaps.
        if any(type(x['value']) != type(first['value']) or x['value'] != first['value'] for x in winners[1:]):
            values.pop(key, None)
            conflicts.append({'operation_id': key[0], 'parameter_path': key[1], 'reason': 'ambiguous_group_precedence', 'target_ids': [x['target_id'] for x in winners]})
            continue
        values[key] = {'value': deepcopy(first['value']), 'scope': first['scope'],
                       'target_id': first['target_id'], 'contributing_targets': [x['target_id'] for x in winners],
                       'overridden': first['scope'] == 'face'}
    operations = {}
    for (operation, path), value in sorted(values.items()): operations.setdefault(operation, {})[path] = value
    return {'face_ref': S.face_ref(state['faces'][face_id]), 'operations': operations,
            'conflicts': conflicts, 'state_revision': state['revision'],
            'association_revision': state['association_revision']}


def materialize(resolved, operation_id, neutral, validator):
    """Rebuild one existing operation recipe without rewriting its algorithm."""
    if any(x['operation_id'] == operation_id for x in resolved['conflicts']):
        raise ValueError('Resolve conflicting groups before rendering this operation')
    recipe = deepcopy(neutral)
    for pointer, record in resolved['operations'].get(operation_id, {}).items():
        parts = [x.replace('~1', '/').replace('~0', '~') for x in pointer[1:].split('/')]
        node = recipe
        for part in parts[:-1]:
            if type(node) is not dict or part not in node: raise ValueError('Unknown operation parameter path')
            node = node[part]
        if type(node) is not dict or parts[-1] not in node: raise ValueError('Unknown operation parameter leaf')
        if type(node[parts[-1]]) in (dict, list): raise ValueError('Only scalar parameters may inherit')
        node[parts[-1]] = deepcopy(record['value'])
    return validator(recipe)
