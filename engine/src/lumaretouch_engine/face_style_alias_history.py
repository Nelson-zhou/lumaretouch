# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact-member protection inside the existing portrait batch history owner.

This marker does not create another ledger or authorize unreviewed FaceRefs.
Legacy entries without the marker keep their established restore behavior.
AUTHORED / UNRUN: no runtime, persistence or numerical acceptance is claimed.
"""
from copy import deepcopy

from . import people_state as S, creative_derived_source as SOURCE

KEY = 'face_style_alias_review'
FIELDS = {'version', 'review_sha256', 'people_scope', 'document_ids',
          'asset_sha256', 'face_ref'}
MAX_MEMBERS = 16


def _targets(value, marker):
    if type(value) is not dict or len(value) != len(marker['document_ids']):
        raise ValueError('Face-style alias history requires its exact reviewed members')
    seen = set()
    for target in value.values():
        if type(target) is not dict:
            raise ValueError('Invalid face-style alias history target')
        identity = S.token(target.get('document_id'))
        if identity in seen:
            raise ValueError('Face-style alias history repeats a document')
        seen.add(identity)
        if (target.get('people_scope') != marker['people_scope']
                or target.get('asset_sha256') != marker['asset_sha256']
                or target.get('reviewed_face_refs') != [marker['face_ref']]):
            raise ValueError('Face-style alias history changed its owner, source or exact face')
        proof = SOURCE.check_row_proof(target.get('source_proof'))
        if proof['asset_sha256'] != marker['asset_sha256']:
            raise ValueError('Face-style alias history source proof changed')
    if seen != set(marker['document_ids']):
        raise ValueError('Face-style alias history cannot add or omit reviewed documents')


def check(entry):
    """Validate only explicitly marked entries; an absent marker means legacy."""
    if KEY not in entry:
        return None
    if 'face_decoration_preset_alias_review' in entry:
        raise ValueError('Mixed decoration preset history cannot reuse another history authority')
    if 'face_decoration_support_alias_review' in entry:
        raise ValueError('Visible-support alias history cannot reuse another history authority')
    marker = entry[KEY]
    if (type(marker) is not dict or set(marker) != FIELDS
            or type(marker['version']) is not int or marker['version'] != 1):
        raise ValueError('Malformed face-style alias history marker')
    S.digest(marker['review_sha256']); S.digest(marker['asset_sha256'])
    ref = S.check_ref(marker['face_ref'])
    # Distinct private scopes cannot legitimately share one graph owner.
    if marker['people_scope'] != 'project' or ref['asset_sha256'] != marker['asset_sha256']:
        raise ValueError('Face-style aliases require the original shared portrait owner')
    ids = marker['document_ids']
    if type(ids) is not list or not 2 <= len(ids) <= MAX_MEMBERS:
        raise ValueError('Face-style alias history needs two to sixteen exact members')
    for identity in ids:
        S.token(identity)
    if ids != sorted(set(ids)):
        raise ValueError('Face-style alias history member identities are not canonical')
    if (entry.get('ops') != ['lnx.people_graph.v1'] or entry.get('people_changes') != []
            or entry.get('policy') != 'protected_scoped_graph'):
        raise ValueError('Face-style alias history must use the existing scoped graph ledger')
    scopes = entry.get('people_scoped_changes')
    if (type(scopes) is not list or len(scopes) != 1 or type(scopes[0]) is not dict
            or set(scopes[0]) != {'scope', 'document_id', 'changes'}
            or scopes[0]['scope'] != marker['people_scope']
            or scopes[0]['document_id'] not in ids):
        raise ValueError('Face-style alias history changed its canonical graph owner')
    from .face_style_recipes import catalogue
    owned = catalogue()['owned_parameters']
    changes = scopes[0]['changes']
    if type(changes) is not list or not 1 <= len(changes) <= sum(map(len, owned.values())):
        raise ValueError('Face-style alias history needs a nonempty bounded owned-leaf patch')
    seen = set()
    for change in changes:
        if (type(change) is not dict or set(change) != {'collection', 'key', 'before', 'after'}
                or change['collection'] != 'overrides'):
            raise ValueError('Face-style alias history cannot change observations or associations')
        key = change['key']
        if (type(key) is not list or len(key) != 4 or key[:2] != ['face', ref['face_instance_id']]
                or type(key[2]) is not str or key[2] not in owned or key[3] not in owned[key[2]]):
            raise ValueError('Face-style alias history contains an unreviewed parameter')
        pair = (key[2], key[3])
        if pair in seen:
            raise ValueError('Face-style alias history repeats an owned parameter')
        seen.add(pair)
        if change['after'] is None:
            raise ValueError('Face-style alias history cannot unset reviewed replacement leaves')
        for record in (change['before'], change['after']):
            if record is None:
                continue
            if (type(record) is not dict
                    or set(record) != {'scope', 'target_id', 'operation_id', 'parameter_path', 'value'}
                    or [record[field] for field in ('scope', 'target_id', 'operation_id', 'parameter_path')] != key):
                raise ValueError('Face-style alias history override identity changed')
            S.scalar(record['value'])
    _targets(entry.get('targets'), marker)
    return deepcopy(marker)


def prepare(review, plans, targets):
    """Validate the future marker before claiming or publishing the visual plan."""
    from .people_graph_patch import between
    members = review.get('members')
    if type(members) is not list or not 2 <= len(members) <= MAX_MEMBERS:
        raise ValueError('Face-style alias history requires its complete visual review')
    ids = []
    for member in members:
        if type(member) is not dict or set(member) != {'path', 'visual'} or type(member['visual']) is not dict:
            raise ValueError('Face-style alias history member lacks its exact visual identity')
        visual = member['visual']
        identity = S.token(visual.get('document_id'))
        matches = [target for target in targets.values() if target.get('document_id') == identity]
        if (len(matches) != 1 or member['path'] != matches[0]['path']
                or visual.get('revision') != str(matches[0]['revision'])
                or visual.get('source_proof') != matches[0]['source_proof']):
            raise ValueError('Face-style alias history differs from the reviewed member proof')
        ids.append(identity)
    scopes = [{'scope': identity, 'document_id': plan['row']['document_id'],
               'changes': between(plan['before'], plan['candidate'])}
              for identity, plan in plans.items()]
    marker = {'version': 1, 'review_sha256': review.get('review_sha256'),
              'people_scope': scopes[0]['scope'] if len(scopes) == 1 else None,
              'document_ids': sorted(ids), 'asset_sha256': review['face_ref']['asset_sha256'],
              'face_ref': deepcopy(review['face_ref'])}
    entry = {'ops': ['lnx.people_graph.v1'], 'targets': targets,
             'policy': 'protected_scoped_graph', 'people_changes': [],
             'people_scoped_changes': scopes, KEY: marker}
    return check(entry)


def verify_restore(engine, entry, plans, targets):
    """Refuse changed membership and dormant effects before restore publication."""
    marker = check(entry)
    if marker is None:
        return
    if set(plans) != {marker['people_scope']}:
        raise ValueError('Face-style alias restore changed its graph scope')
    _targets(targets, marker)
    plan = plans[marker['people_scope']]
    from .people_graph_owner import affected_assets
    assets = affected_assets(plan['before'], plan['candidate'])
    if assets != {marker['asset_sha256']}:
        raise ValueError('Face-style alias restore changed its affected source set')
    from .face_style_alias_review import verify_dormant
    verify_dormant(engine, plan['row'], assets)


def status_summary(entry):
    """Read-only classification; not permission for a new edit or history write."""
    marker=check(entry)
    return None if marker is None else {'version':1,'review_sha256':marker['review_sha256'],
                                       'member_count':len(marker['document_ids'])}
