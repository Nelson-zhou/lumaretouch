"""Current-owner consensus, separate from internally valid historical generations.

This admission check reads retained identities only. It never blesses unavailable
source bytes, runs analysis, or revives a dormant member. Mutation still requires
the coordinator's fresh per-document source, face and review proofs.
"""
from . import people_state as S


def _graph(value):
    return S.check(value) if value is not None else S.empty()


def _recipe(row):
    versions = row.get('versions', [])
    matches = [item for item in versions if isinstance(item, dict)
               and item.get('id') == row.get('active_version')]
    if len(matches) != 1 or type(matches[0].get('recipe')) is not dict:
        return None
    return matches[0]['recipe']


def _original(project, row):
    source = project.get('source_assets', {}).get(row.get('source_asset_id'), {})
    fingerprint = source.get('fingerprint') or row.get('fingerprint') or {}
    if fingerprint.get('hash_level') != 'full':
        return None
    return S.digest(fingerprint.get('sha256'))


def _asset(row, original):
    recipe = _recipe(row)
    if recipe is None:
        return None
    base = recipe.get('_creative_base')
    if base is None:
        return original
    if type(base) is not dict or not isinstance(base.get('id'), str) or not base['id'].startswith('sha256:'):
        raise ValueError('Association member has an invalid retained creative source')
    return S.digest(base['id'][7:])


def validate_project(project):
    """Reject active split replicas; return explicitly suspended retained cohorts.

    Historical recipe/document/batch snapshots are deliberately not enumerated:
    protected undo restores an older content generation, not a monotonic counter.
    The ordinary recursive people validator still validates their local schema.
    """
    from .people_cross_owner import check_descriptor
    if type(project) is not dict or type(project.get('docs', [])) is not list:
        raise ValueError('Cross-owner associations require a document table')
    root = _graph(project.get('people_graph'))
    rows = {}; owners = {}; replicas = {}
    for row in project.get('docs', []):
        if type(row) is not dict:
            raise ValueError('Invalid association document row')
        identity = row.get('document_id')
        # Older projects have no cross-owner capsules and keep their migration.
        if identity is None:
            continue
        S.token(identity)
        if identity in rows:
            raise ValueError('Ambiguous cross-owner document identity')
        context = row.get('people_context')
        if context is not None:
            if type(context) is not dict:
                raise ValueError('Invalid private portrait owner')
            graph = _graph(context.get('people_graph')); scope = identity
        else:
            graph = root; scope = 'project'
        original = _original(project, row)
        rows[identity] = {'row': row, 'scope': scope, 'graph': graph,
                          'original': original, 'asset': _asset(row, original)}
        owners.setdefault(scope, graph)
    owners.setdefault('project', root)
    for scope, graph in owners.items():
        for person in graph['persons'].values():
            if 'cross_owner' not in person:
                continue
            capsule = check_descriptor(person['cross_owner'])
            identity = capsule['local_document_id']
            local = next(member for member in capsule['members'] if member['document_id'] == identity)
            if local['scope_id'] != scope or (scope != 'project' and identity != scope):
                raise ValueError('Saved association replica belongs to another portrait owner')
            endpoint = rows.get(identity)
            if endpoint is not None and endpoint['scope'] != scope:
                raise ValueError('Saved association document changed portrait owner')
            key = (capsule['association_id'], identity)
            if key in replicas:
                raise ValueError('Duplicate saved association replica')
            replicas[key] = capsule

    def current(member):
        endpoint = rows.get(member['document_id'])
        if endpoint is None or endpoint['row'].get('trashed'):
            return False
        if (endpoint['scope'] != member['scope_id'] or endpoint['original'] != member['original_sha256']
                or endpoint['asset'] != member['ref']['asset_sha256']):
            return False
        face = endpoint['graph']['faces'].get(member['ref']['face_instance_id'])
        return (face is not None and S.face_ref(face) == member['ref'] and face['enabled']
                and face['evidence']['status'] == 'verified')

    result = {}
    for capsule in replicas.values():
        association = capsule['association_id']; suspended = []
        local = next(member for member in capsule['members']
                     if member['document_id'] == capsule['local_document_id'])
        for member in capsule['members']:
            peer = replicas.get((association, member['document_id']))
            if not current(member):
                suspended.append(member['document_id']); continue
            # A missing available replica cannot be explained by dormant source
            # history. Atomic unlink removes every member, never just one side.
            if peer is None:
                raise ValueError('Current association member is missing its accepted replica')
            if current(local) and (peer['generation'] != capsule['generation']
                                  or peer['members'] != capsule['members']
                                  or peer['intent'] != capsule['intent']):
                raise ValueError('Current association members have divergent accepted generations')
        previous = result.setdefault(association, {'status': 'retained_consistent', 'suspended_documents': []})
        previous['suspended_documents'] = sorted(set(previous['suspended_documents']) | set(suspended))
        if previous['suspended_documents']:
            previous['status'] = 'suspended'
    return result
