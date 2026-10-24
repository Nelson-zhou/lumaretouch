# SPDX-License-Identifier: GPL-3.0-or-later
"""Narrow affected-source checks, without relaxing existing alias/cohort owners."""
from . import face_decoration_state as D, people_state as P, people_algorithms as A, people_resolver as R
from .face_decoration_support import KIND


def changed_assets(before, candidate):
    def signature(graph, key):
        face = graph['faces'].get(key)
        if face is None: return None
        persons = {link['person_id'] for link in graph['links']
                   if link['face_instance_id']==key and link['state']=='confirmed'}
        groups = {name for name,group in graph['groups'].items() if key in group['face_ids']}
        rows = [entry for entry in graph['overrides'] if entry['operation_id']==D.OP and (
            (entry['scope']=='face' and entry['target_id']==key)
            or (entry['scope']=='all_people' and entry['target_id']==face['asset_sha256'])
            or (entry['scope']=='person' and entry['target_id'] in persons)
            or (entry['scope']=='group' and entry['target_id'] in groups))]
        rows = sorted(rows,key=lambda item:(item['scope'],item['target_id'],item['parameter_path']))
        support = face['local_assets'].get(KIND); recovery = face['local_assets'].get('face_decoration')
        if not rows and support is None and recovery is None: return None
        # Compare operation-local intent, including shadowed/explicit neutral
        # overrides. Never materialize unrelated family conflicts or recipes.
        resolved = R.resolve(graph,key,{D.OP:A.leaves(D.neutral())})
        leaves = resolved['operations'].get(D.OP,{})
        conflicts = [item for item in resolved['conflicts'] if item['operation_id']==D.OP]
        return rows,leaves,conflicts,face['enabled'],P.face_ref(face),support,recovery
    result = set()
    for key in set(before['faces']) | set(candidate['faces']):
        if signature(before,key) == signature(candidate,key): continue
        for graph in (before,candidate):
            if key in graph['faces']: result.add(graph['faces'][key]['asset_sha256'])
    # Photograph-wide dormant intent also exists before any face is retained.
    def photograph_rows(graph):
        return {(row['target_id'],row['parameter_path']):row for row in graph['overrides']
                if row['operation_id']==D.OP and row['scope']=='all_people'}
    left,right=photograph_rows(before),photograph_rows(candidate)
    result.update(key[0] for key in set(left)|set(right) if left.get(key)!=right.get(key))
    return result


def require_unaliased(engine, row, assets):
    """Single-photo review cannot grant consent for unseen source-identical rows.

    General scalar transfer still uses its existing complete frozen target map.
    New decoration does not pretend the separate eye-specific alias review has
    authorized these pixels. Independent virtual-copy owners remain independent.
    """
    if not assets: return
    from . import virtual_copy_people as V, creative_derived_source as SOURCE
    rows = V.scope_rows(engine,row); current = V.current_row(engine)
    counts = {asset:0 for asset in assets}
    for other in rows:
        source_row = {**other,'state':{'_creative_base':getattr(engine,'_creative_base',None)}} if other is current else other
        asset = SOURCE.row_asset(source_row)
        if asset in counts: counts[asset] += 1
    if any(count > 1 for count in counts.values()):
        raise ValueError('面部装饰会影响多个共用源图的文档；此通路没有完整逐文档审核，请使用独立虚拟副本，不会静默修改其他副本')


def require_transition(engine, before, candidate, *, row=None, authority=None):
    from .virtual_copy_people import current_row
    actual=current_row(engine) if row is None else row
    if authority is not None:
        from .face_decoration_alias_authority import AliasAuthority
        from .face_decoration_support_alias_authority import SupportAliasAuthority
        if type(authority) not in (AliasAuthority,SupportAliasAuthority):raise ValueError("Private exact decoration alias authority required")
        authority.verify(engine,actual,before,candidate)
        return
    require_unaliased(engine,actual,changed_assets(before,candidate))


def photograph_dormant(state, asset):
    D.validate_graph(state)
    leaves = {row['parameter_path']:{'value':row['value']} for row in state['overrides']
              if row['scope']=='all_people' and row['target_id']==asset and row['operation_id']==D.OP}
    recipe = R.materialize({'conflicts':[],'operations':{D.OP:leaves}},D.OP,D.neutral(),D.check)
    return not D.active(recipe)
