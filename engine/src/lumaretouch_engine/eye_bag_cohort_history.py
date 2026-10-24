# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact-member eye-bag association history in the existing scoped ledger.

No new history owner. Canonical project dependencies survive save/reopen while
complete mixed graph hashes refuse replay after unrelated portrait edits.
AUTHORED / UNRUN; no numerical or runtime acceptance is claimed.
"""
from copy import deepcopy
from . import people_state as S, creative_derived_source as SOURCE
from .people_cross_owner import check_descriptor
from .collarbone_transfer_review import coverage_digest
from .eye_bag_batch_history import _dependencies

KEY = 'eye_bag_cohort_review'


def graph_digest(graph):
    value = S.check(graph)
    value['revision'] = 0; value['association_revision'] = 0
    from .people_graph_patch import LIST_KEYS
    for collection, keys in LIST_KEYS.items():
        value[collection] = sorted(value[collection], key=lambda row: tuple(row[key] for key in keys))
    return coverage_digest(value)


def _person(capsule):
    return None if capsule is None else {'anonymous': True, 'cross_owner': capsule}


def check(entry):
    if KEY not in entry: return None
    if 'face_decoration_support_alias_review' in entry:
        raise ValueError('Visible-support alias history cannot reuse another history authority')
    marker = entry[KEY]
    if (type(marker) is not dict or set(marker) != {'version', 'review_sha256', 'association_id', 'members', 'targets'}
            or type(marker['version']) is not int or marker['version'] != 1
            or type(marker['targets']) is not list or not 2 <= len(marker['targets']) <= 16
            or entry.get('ops') != ['lnx.people_graph.v1'] or entry.get('people_changes') != []
            or entry.get('policy') != 'protected_scoped_graph' or 'eye_bag_batch_review' in entry):
        raise ValueError('Malformed exact eye-bag cohort protected history')
    S.digest(marker['review_sha256']); S.token(marker['association_id'])
    targets = entry.get('targets'); scopes = entry.get('people_scoped_changes')
    if (type(targets) is not dict or len(targets) != len(marker['targets'])
            or type(scopes) is not list or len(scopes) != len(marker['targets'])):
        raise ValueError('Eye-bag cohort history requires every independent owner and document')
    by_scope = {}; by_document = {}; capsules = {'before': [], 'after': []}
    for item in marker['targets']:
        fields = {'document_id', 'people_scope', 'source_proof', 'face', 'person_id', 'before_capsule', 'after_capsule',
                  'before_graph_sha256', 'after_graph_sha256', 'context_sha256', 'state_sha256'}
        if type(item) is not dict or set(item) != fields: raise ValueError('Incomplete eye-bag cohort member history')
        doc = S.token(item['document_id']); scope = S.token(item['people_scope']); person = S.token(item['person_id'])
        if scope not in ('project', doc) or scope in by_scope or doc in by_document: raise ValueError('Eye-bag cohort history repeats or changes an owner')
        proof = SOURCE.check_row_proof(item['source_proof']); ref = S.check_ref(S.face_ref(item['face']))
        if ref['asset_sha256'] != proof['asset_sha256']: raise ValueError('Eye-bag cohort history borrows another source face')
        graph = S.empty(); graph['faces'][ref['face_instance_id']] = item['face']; S.check(graph)
        if not item['face']['enabled'] or item['face']['evidence']['status'] != 'verified': raise ValueError('Dormant cohort face cannot authorize history')
        for name in ('before_graph_sha256', 'after_graph_sha256', 'context_sha256', 'state_sha256'): S.digest(item[name])
        if item['before_graph_sha256'] == item['after_graph_sha256']: raise ValueError('Eye-bag cohort history cannot manufacture a graph no-op')
        matches = [target for target in targets.values() if target.get('document_id') == doc]
        if (len(matches) != 1 or matches[0].get('people_scope') != scope or matches[0].get('source_proof') != proof
                or matches[0].get('asset_sha256') != proof['asset_sha256'] or matches[0].get('reviewed_face_refs') != [ref]):
            raise ValueError('Eye-bag cohort history changed exact membership, source or selected face')
        if item['before_capsule'] is None and item['after_capsule'] is None: raise ValueError('Eye-bag cohort history lacks its association transition')
        for side in ('before', 'after'):
            raw = item[side + '_capsule']
            if raw is None: continue
            capsule = check_descriptor(raw)
            local = next(member for member in capsule['members'] if member['document_id'] == doc)
            if (capsule['association_id'] != marker['association_id'] or capsule['local_document_id'] != doc
                    or capsule['members'] != marker['members'] or local != {'document_id': doc, 'scope_id': scope,
                        'original_sha256': proof['original_sha256'], 'ref': ref}):
                raise ValueError('Eye-bag cohort history capsule changed owner, membership or source')
            capsules[side].append(capsule)
        by_scope[scope] = item; by_document[doc] = item
    for side, values in capsules.items():
        if values and (len(values) != len(by_document) or any(value['members'] != values[0]['members']
                or value['generation'] != values[0]['generation'] or value['intent'] != values[0]['intent'] for value in values)):
            raise ValueError('Eye-bag cohort history cannot restore partial or divergent capsule generations')
    if {member['document_id'] for member in marker['members']} != set(by_document): raise ValueError('Eye-bag cohort history member closure differs')
    seen = set()
    for scoped in scopes:
        if (type(scoped) is not dict or set(scoped) != {'scope', 'document_id', 'changes'} or scoped['scope'] in seen
                or scoped['scope'] not in by_scope or scoped['document_id'] != by_scope[scoped['scope']]['document_id']
                or type(scoped['changes']) is not list or not scoped['changes']):
            raise ValueError('Eye-bag cohort history changed its atomic graph scopes')
        seen.add(scoped['scope']); item = by_scope[scoped['scope']]; changed = set(); person_changed = False
        for change in scoped['changes']:
            if type(change) is not dict or set(change) != {'collection', 'key', 'before', 'after'}: raise ValueError('Invalid eye-bag cohort graph patch')
            collection = change['collection']; key = change['key']; identity = (collection, tuple(key) if type(key) is list else key)
            if identity in changed or change['before'] == change['after']: raise ValueError('Repeated or no-op eye-bag cohort history patch')
            changed.add(identity)
            if collection == 'persons':
                if key != item['person_id'] or any(change[side] != _person(item[side + '_capsule']) for side in ('before', 'after')):
                    raise ValueError('Eye-bag cohort may change only its exact local association replica')
                person_changed = True
            elif collection == 'links':
                if key != [item['face']['face_instance_id'], item['person_id']]: raise ValueError('Eye-bag history cannot relink another face')
                for side in ('before', 'after'):
                    link = change[side]; capsule = item[side + '_capsule']
                    if capsule is None:
                        if link is not None: raise ValueError('Removed cohort replica cannot retain an association link')
                    elif (type(link) is not dict or set(link) != {'face_instance_id', 'person_id', 'state', 'confirmation_revision'}
                            or link['face_instance_id'] != key[0] or link['person_id'] != key[1] or link['state'] != 'confirmed'):
                        raise ValueError('Eye-bag history requires its original confirmed member link')
                    else: S.revision(link['confirmation_revision'])
            elif collection == 'overrides':
                if type(key) is not list or len(key) != 4: raise ValueError('Malformed cohort scalar key')
                scope, target, operation, path = key; S.token(operation); S.parameter_path(path)
                if scope == 'person' and target == item['person_id']:
                    for side in ('before', 'after'):
                        capsule = item[side + '_capsule']
                        leaves = [] if capsule is None else [leaf for leaf in capsule['intent'] if (leaf['op'], leaf['path']) == (operation, path)]
                        expected = None if not leaves else {'scope': scope, 'target_id': target, 'operation_id': operation, 'parameter_path': path, 'value': leaves[0]['value']}
                        if change[side] != expected: raise ValueError('Cohort scalar patch differs from canonical capsule intent')
                elif key == ['face', item['face']['face_instance_id'], 'lnx.enhance.v1', '/eye_bags']:
                    after = change['after']
                    if type(after) is not dict or after.get('value') != 0.0: raise ValueError('Cohort face change is limited to reviewed legacy replacement zero')
                    for scalar in (change['before'], after):
                        if scalar is None: continue
                        if (type(scalar) is not dict or set(scalar) != {'scope', 'target_id', 'operation_id', 'parameter_path', 'value'}
                                or [scalar[name] for name in ('scope', 'target_id', 'operation_id', 'parameter_path')] != key):
                            raise ValueError('Eye-bag cohort changed legacy replacement identity')
                        from .eye_bag_preserve_state import check as check_eye
                        check_eye({'version': 2, 'amount': scalar['value'], 'preserve': 1})
                else: raise ValueError('Eye-bag cohort cannot mutate unrelated explicit face intent')
            else: raise ValueError('Eye-bag cohort cannot transfer masks, analysis, recovery, groups or support assets')
        if not person_changed: raise ValueError('Eye-bag cohort history omitted its local capsule transition')
    if seen != set(by_scope): raise ValueError('Eye-bag cohort history omitted an independent owner')
    return deepcopy(marker)


def prepare(engine, plans, targets, review, ack):
    from .people_graph_patch import between
    marker = {'version': 1, 'review_sha256': coverage_digest(ack), 'association_id': review['association_id'],
              'members': deepcopy(review['members']), 'targets': []}
    for target in targets.values():
        found = engine._document_versions().find(engine._docs, target['document_id'])
        if found is None: raise ValueError('Eye-bag cohort history member disappeared')
        row = found[1]; plan = plans[target['people_scope']]; ref = target['reviewed_face_refs'][0]
        face = deepcopy(plan['before']['faces'][ref['face_instance_id']])
        if plan['candidate']['faces'].get(ref['face_instance_id']) != face: raise ValueError('Cohort history cannot change member support/analysis')
        replicas = {}
        for side, graph in (('before', plan['before']), ('after', plan['candidate'])):
            matches = [(key, person['cross_owner']) for key, person in graph['persons'].items()
                       if person.get('cross_owner', {}).get('association_id') == review['association_id']]
            if len(matches) > 1: raise ValueError('Duplicate cohort replica during protected history preparation')
            replicas[side] = matches[0] if matches else None
        ids = {value[0] for value in replicas.values() if value is not None}
        if len(ids) != 1: raise ValueError('Cohort changed its local anonymous person identity')
        marker['targets'].append({'document_id': target['document_id'], 'people_scope': target['people_scope'],
            'source_proof': deepcopy(target['source_proof']), 'face': face, 'person_id': next(iter(ids)),
            'before_capsule': None if replicas['before'] is None else deepcopy(replicas['before'][1]),
            'after_capsule': None if replicas['after'] is None else deepcopy(replicas['after'][1]),
            'before_graph_sha256': graph_digest(plan['before']), 'after_graph_sha256': graph_digest(plan['candidate']),
            **_dependencies(engine, row)})
    entry = {'ops': ['lnx.people_graph.v1'], 'people_changes': [], 'policy': 'protected_scoped_graph', 'targets': targets,
        'people_scoped_changes': [{'scope': scope, 'document_id': plan['row']['document_id'],
            'changes': between(plan['before'], plan['candidate'])} for scope, plan in plans.items()], KEY: marker}
    return check(entry)


def verify_restore(engine, entry, plans, targets, *, redo):
    marker = check(entry)
    if marker is None: return
    expected = {item['document_id']: item for item in marker['targets']}
    if len(targets) != len(expected) or {item['document_id'] for item in targets.values()} != set(expected):
        raise ValueError('Eye-bag cohort history cannot add, omit or revive an unreviewed alias')
    for target in targets.values():
        item = expected[target['document_id']]; ref = S.face_ref(item['face'])
        if (target['people_scope'] != item['people_scope'] or target['source_proof'] != item['source_proof']
                or target.get('reviewed_face_refs') != [ref]): raise ValueError('Eye-bag cohort history changed exact source, face or owner')
        found = engine._document_versions().find(engine._docs, target['document_id'])
        if found is None or found[1].get('trashed'): raise ValueError('Eye-bag cohort history member is missing or dormant')
        plan = plans[item['people_scope']]
        if (graph_digest(plan['before']) != item['before_graph_sha256' if redo else 'after_graph_sha256']
                or graph_digest(plan['candidate']) != item['after_graph_sha256' if redo else 'before_graph_sha256']
                or _dependencies(engine, found[1]) != {key: item[key] for key in ('context_sha256', 'state_sha256')}):
            raise ValueError('Eye-bag cohort full mixed graph, source-owned analysis, support, recovery or repair changed; protected replay refused')
    from .eye_bag_batch_plan import closure
    closure(engine, engine._docs, plans, set(expected))
    from .people_cross_owner_ledger import validate_plans
    validate_plans(plans, targets)


def status_summary(entry):
    marker = check(entry)
    return None if marker is None else {'version': 1, 'review_sha256': marker['review_sha256'], 'member_count': len(marker['targets'])}
