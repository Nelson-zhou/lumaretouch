# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict portable scalar validation; source reviews remain in the support bank."""
from . import eye_makeup_enhance_state as S


def validate_leaf(path, value):
    if type(path) is not str:
        raise ValueError('眼妆参数路径无效')
    parts = path.split('/')
    if len(parts) != 3 or parts[0] or parts[1] not in S.CONTROL_KEYS or parts[2] not in ('linked', *S.SIDES):
        raise ValueError('未知眼妆参数；不能携带参考样本、蒙版、来源或人物')
    if parts[2] == 'linked':
        if type(value) is not bool:
            raise ValueError('眼妆联动必须为布尔值')
    else:
        S.amount(value)


def validate_graph(state):
    from . import people_state as P
    from .people_algorithms import defaults
    from .people_resolver import resolve, materialize
    out = P.check(state)
    for row in out['overrides']:
        if row['operation_id'] == S.OP:
            validate_leaf(row['parameter_path'], row['value'])
    for face in out['faces']:
        resolved = resolve(out, face, defaults())
        if not any(item['operation_id'] == S.OP for item in resolved['conflicts']):
            materialize({**resolved, 'conflicts': []}, S.OP, S.neutral(), S.check)
    return out


def validate_project(project):
    from .eye_makeup_enhance_support import validate_project as validate_supports
    validate_supports(project)


def require_unaliased(engine, row, assets):
    """This current-photo path does not authorize unseen same-source documents."""
    if not assets: return
    from . import virtual_copy_people as V, creative_derived_source as SOURCE
    rows=V.scope_rows(engine,row); current=V.current_row(engine); counts={asset:0 for asset in assets}
    for other in rows:
        source_row={**other,'state':{'_creative_base':getattr(engine,'_creative_base',None)}} if other is current else other
        asset=SOURCE.row_asset(source_row)
        if asset in counts: counts[asset]+=1
    if any(count>1 for count in counts.values()):
        raise ValueError('原有眼妆修改涉及多个共用源图文档；当前仅支持独立照片或独立虚拟副本，不会借用其他工具的批量审核')


def changed_assets(before, candidate):
    from . import people_algorithms as A, people_resolver as R, people_state as P
    from .eye_makeup_enhance_support import KIND
    def signature(graph,key):
        face=graph['faces'].get(key)
        if face is None: return None
        persons={link['person_id'] for link in graph['links'] if link['face_instance_id']==key and link['state']=='confirmed'}
        groups={name for name,group in graph['groups'].items() if key in group['face_ids']}
        rows=[row for row in graph['overrides'] if row['operation_id']==S.OP and (
            row['scope']=='face' and row['target_id']==key or row['scope']=='all_people' and row['target_id']==face['asset_sha256']
            or row['scope']=='person' and row['target_id'] in persons or row['scope']=='group' and row['target_id'] in groups)]
        rows=sorted(rows,key=lambda r:(r['scope'],r['target_id'],r['parameter_path']))
        support=face['local_assets'].get(KIND)
        if not rows and support is None: return None
        resolved=R.resolve(graph,key,{S.OP:A.leaves(S.neutral())})
        return rows,resolved['operations'].get(S.OP,{}),[c for c in resolved['conflicts'] if c['operation_id']==S.OP],face['enabled'],P.face_ref(face),support
    result=set()
    for key in set(before['faces'])|set(candidate['faces']):
        if signature(before,key)==signature(candidate,key): continue
        for graph in (before,candidate):
            if key in graph['faces']: result.add(graph['faces'][key]['asset_sha256'])
    def rows(graph):
        return {(r['target_id'],r['parameter_path']):r for r in graph['overrides'] if r['operation_id']==S.OP and r['scope']=='all_people'}
    a,b=rows(before),rows(candidate)
    result.update(k[0] for k in set(a)|set(b) if a.get(k)!=b.get(k))
    return result


def require_transition(engine, before, candidate, *, row=None):
    """This bounded slice cannot authorize cross-photo parameter propagation."""
    from . import virtual_copy_people as V, creative_derived_source as SOURCE
    current = V.current_row(engine); actual = current if row is None else row
    changed = changed_assets(before, candidate)
    if not changed:
        return
    if type(actual) is not dict:
        raise ValueError('原有眼妆修改缺少当前规范文档归属')
    source_row = ({**actual, 'state': {'_creative_base': getattr(engine, '_creative_base', None)}}
                  if actual is current else actual)
    asset = SOURCE.row_asset(source_row)
    if changed - {asset}:
        raise ValueError('原有眼妆目前仅支持当前有效来源；跨照片人物、分组、预设或批处理缺少逐目标审核通路，未应用')
    require_unaliased(engine, actual, changed)
