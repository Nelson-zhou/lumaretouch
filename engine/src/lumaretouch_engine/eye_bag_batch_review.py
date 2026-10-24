# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit per-target scalar choices and complete target image evidence. UNRUN.

This family owns no masks, anatomy, transaction, token or history stack.
"""
from copy import deepcopy
import json
from . import eye_bag_preserve_state as EYE, collarbone_transfer_review as VISUAL
from . import people_state as S

MAX_TARGETS = 16
checked = VISUAL.checked


def choice(value):
    if (type(value) is not dict or set(value) != {'version', 'replace_legacy'}
            or type(value['version']) is not int or value['version'] != 1
            or type(value['replace_legacy']) is not bool):
        raise ValueError('Eye-bag batch needs an explicit per-target legacy replacement choice')
    return deepcopy(value)


def options(value, selected):
    if (selected.get('target_policy') != 'explicit_face_map' or 'face_style' in selected
            or EYE.OP not in selected.get('selection', {})
            or type(value) is not dict or set(value) != {'version', 'targets'}
            or type(value['version']) is not int or value['version'] != 1
            or type(value['targets']) is not list or not 1 <= len(value['targets']) <= MAX_TARGETS):
        raise ValueError('Eye-bag review requires ordinary explicit target face maps and selected v2 leaves')
    ids = []
    for item in value['targets']:
        if type(item) is not dict or set(item) != {'document_id', 'replace_legacy'}:
            raise ValueError('Every eye-bag target needs only its document and replacement choice')
        ids.append(S.token(item['document_id']))
        choice({'version': 1, 'replace_legacy': item['replace_legacy']})
    expected = [item['target']['document']['document_id'] for item in selected['targets']]
    if len(set(ids)) != len(ids) or set(ids) != set(expected):
        raise ValueError('Eye-bag choices must exactly cover the reviewed target documents')
    return deepcopy(value)


def for_document(selected, document):
    value = options(selected['eye_bag'], selected)
    item = next(item for item in value['targets'] if item['document_id'] == document)
    return choice({'version': 1, 'replace_legacy': item['replace_legacy']})


def coverage_checked(value, refs):
    if (type(value) is not dict or set(value) != {'version', 'support_transfer', 'targets'}
            or type(value['version']) is not int or value['version'] != 1
            or value['support_transfer'] != 'none' or type(value['targets']) is not list
            or len(value['targets']) != len(refs) or not 1 <= len(refs) <= 128):
        raise ValueError('Eye-bag coverage must retain every exact target FaceRef without support transfer')
    seen = set()
    for item, ref in zip(value['targets'], refs):
        ref = S.check_ref(ref)
        if (type(item) is not dict or set(item) != {'face_ref', 'scope', 'ridge_sha256', 'sides'}
                or item['face_ref'] != ref or ref['face_instance_id'] in seen
                or type(item['sides']) is not list or any(type(side) is not str or side not in ('left', 'right') for side in item['sides'])
                or item['sides'] != sorted(set(item['sides']))):
            raise ValueError('Eye-bag coverage requires exact independent target side ownership')
        seen.add(ref['face_instance_id'])
        if item['scope'] == 'neutral-no-effect':
            if item['ridge_sha256'] is not None or item['sides']:
                raise ValueError('Neutral eye-bag coverage cannot claim active support')
        elif item['scope'] == 'target-reviewed-ridge':
            S.digest(item['ridge_sha256'])
            if not item['sides']: raise ValueError('Active eye-bag coverage needs at least one reviewed side')
        else: raise ValueError('Unknown eye-bag support scope')
    return deepcopy(value)


def required(plan):
    params = plan.params().get('_people_transfer')
    return (type(params) is dict and params.get('mode') != 'persistent_association'
            and type(params.get('options')) is dict and 'eye_bag' in params['options'])


def records(plan):
    """Validate actual frozen intent, not an incoming acknowledgment flag."""
    if not required(plan): return None
    from .people_batch_transfer import options as check_options
    from .batch_preflight import canonical
    selected = plan.params()['_people_transfer']['options']
    check_options(selected, list(plan.modules), selected['source_ref']['asset_sha256'])
    policies = options(selected['eye_bag'], selected)
    source = selected['source']['document']
    if (source['document_id'] != plan.source_id or source['revision'] != plan.source_revision
            or source['epoch'] != plan.workspace):
        raise ValueError('Eye-bag frozen source differs from its reviewed document fence')
    wanted = {item['document_id'] for item in policies['targets']}
    actual = [target.document_id for target in plan.targets]
    if (not 1 <= len(actual) <= MAX_TARGETS or len(set(actual)) != len(actual)
            or set(actual) != wanted or plan.rejected()):
        raise ValueError('Eye-bag review requires the complete exact requested target set')
    aliases = {}
    for mapping in selected['targets']:
        endpoint = mapping['target']; key = (endpoint['people_scope'], endpoint['source_proof']['asset_sha256'])
        policy = for_document(selected, endpoint['document']['document_id'])
        if key in aliases and aliases[key] != policy:
            raise ValueError('Frozen shared-source aliases disagree on explicit legacy replacement')
        aliases[key] = policy
    out = []
    for target in plan.targets:
        if target.blocked: continue
        payload = json.loads(target.people_json)
        policy = for_document(selected, target.document_id)
        mapping = next(item for item in selected['targets'] if item['target']['document']['document_id'] == target.document_id)
        if mapping['target']['document']['revision'] != target.revision:
            raise ValueError('Eye-bag frozen target revision differs from the exact reviewed owner')
        if (choice(payload.get('eye_bag')) != policy or payload.get('target_policy') != 'explicit_face_map'
                or payload.get('target_refs') != mapping['target_refs'] or payload.get('target_owner') != mapping['target']
                or payload.get('source_owner') != selected['source'] or payload.get('source_ref') != selected['source_ref']):
            raise ValueError('Eye-bag target changed its exact source, owner, faces or replacement choice')
        expected = sorted((op, path) for op, paths in selected['selection'].items() for path in paths)
        leaves = payload.get('parameters')
        if (type(leaves) is not list or any(type(item) is not dict or set(item) != {'operation_id', 'parameter_path', 'value'} for item in leaves)
                or sorted((item['operation_id'], item['parameter_path']) for item in leaves) != expected):
            raise ValueError('Eye-bag target must retain all selected mixed scalar leaves')
        for leaf in leaves: S.scalar(leaf['value'])
        coverage = coverage_checked(payload.get('eye_bag_coverage'), payload['target_refs'])
        scalar = EYE.neutral()
        for leaf in leaves:
            if leaf['operation_id'] == EYE.OP: scalar[leaf['parameter_path'][1:]] = leaf['value']
            if leaf['operation_id'] == 'lnx.enhance.v1' and leaf['parameter_path'] == '/eye_bags':
                EYE.check({'version': 2, 'amount': leaf['value'], 'preserve': 1})
        EYE.check(scalar)  # Typed finite unit scalars, even for dormant leaves.
        amounts = [leaf['value'] for leaf in leaves if leaf['operation_id'] == EYE.OP and leaf['parameter_path'] == '/amount']
        active = [item['scope'] == 'target-reviewed-ridge' for item in coverage['targets']]
        if amounts and any(value != (amounts[0] > 0) for value in active):
            raise ValueError('Eye-bag coverage contradicts the exact selected target amount')
        if any(active) and any(leaf['operation_id'] == 'lnx.enhance.v1' and leaf['parameter_path'] == '/eye_bags'
                               and leaf['value'] > 0 for leaf in leaves):
            raise ValueError('Frozen active v2 cannot discard selected nonzero legacy intent')
        record = checked(payload.get('eye_bag_visual'))
        proof = json.loads(target.before_json).get('source_proof')
        snapshots = json.loads(target.before_json).get('eye_bag_snapshots')
        if type(snapshots) is not dict or set(snapshots) != {'before', 'after'}:
            raise ValueError('Eye-bag review requires both complete repair/support snapshot proofs')
        for snapshot in snapshots.values():
            if type(snapshot) is not dict or set(snapshot) != {'render_sha256', 'context_sha256', 'graph_sha256'}:
                raise ValueError('Eye-bag snapshot must pin its render, context and graph')
            for digest in snapshot.values(): S.digest(digest)
        if (record['document_id'] != target.document_id or record['revision'] != str(target.revision)
                or record['source_proof'] != proof or proof != mapping['target']['source_proof']
                or record['coverage_sha256'] != VISUAL.coverage_digest(coverage)):
            raise ValueError('Eye-bag image evidence belongs to another target, source or support')
        if 'lnx.collarbone.v1' in plan.modules:
            other = VISUAL.checked(payload.get('collarbone_visual'))
            if any(record[key] != other[key] for key in VISUAL.FIELDS - {'coverage_sha256'}):
                raise ValueError('Mixed eye-bag and collarbone reviews must show the same complete target candidate')
        out.append({'visual': record, 'replace_legacy': policy['replace_legacy']})
    return out


def acknowledgments(raw, records):
    expected = []
    for item in records:
        record = checked(item['visual'])
        if type(item['replace_legacy']) is not bool: raise ValueError('Invalid eye-bag replacement receipt')
        expected.append({'document_id': record['document_id'], 'revision': record['revision'],
            'before_sha256': record['before']['sha256'], 'after_sha256': record['after']['sha256'],
            'coverage_sha256': record['coverage_sha256'], 'replace_legacy': item['replace_legacy']})
    if (type(raw) is not list or len(raw) != len(expected) or len(raw) > MAX_TARGETS
            or len({item['document_id'] for item in expected}) != len(expected)
            or any(type(a) is not dict or set(a) != set(b) or type(a.get('replace_legacy')) is not bool or a != b for a, b in zip(raw, expected))):
        raise ValueError('Acknowledge every exact eye-bag image pair, support and replacement choice')
    return deepcopy(expected)
