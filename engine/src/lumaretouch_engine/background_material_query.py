# SPDX-License-Identifier: GPL-3.0-or-later
"""Small revision-pinned metadata pages, never complete image buffers."""
from copy import deepcopy
from . import background_material_state as S

PUBLIC = ('id', 'name', 'group_id', 'sha256', 'bytes', 'width', 'height', 'bits',
          'format', 'has_alpha', 'created_at', 'deleted_at')


def query(value):
    S.fields(value, ('group_id', 'text', 'trash', 'sort', 'offset', 'limit'))
    if value['group_id'] is not None and value['group_id'] != S.UNGROUPED:
        S.identifier(value['group_id'])
    text = value['text']
    if type(text) is not str or len(text) > 120 or any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in text):
        S.fail('背景搜索词无效')
    if type(value['trash']) is not bool or value['sort'] not in ('manual', 'name_asc', 'name_desc', 'newest', 'oldest'):
        S.fail('背景列表筛选或排序无效')
    S.integer(value['offset'], 0, S.MAX_RECORDS); S.integer(value['limit'], 1, 48)
    return deepcopy(value)


def page(catalog, request):
    value = query(request)
    if value['group_id'] is not None: S.group(catalog, value['group_id'])
    text = value['text'].strip().casefold()
    rows = [row for row in catalog['materials']
            if (row['deleted_at'] is not None) == value['trash']
            and (value['group_id'] is None or row['group_id'] == value['group_id'])
            and (not text or text in row['name'].casefold())]
    if value['sort'] in ('name_asc', 'name_desc'):
        rows.sort(key=lambda row: (row['name'].casefold(), row['id']), reverse=value['sort'] == 'name_desc')
    elif value['sort'] in ('newest', 'oldest'):
        rows.sort(key=lambda row: (row['created_at'], row['id']), reverse=value['sort'] == 'newest')
    start, limit = value['offset'], value['limit']
    return {'version': S.VERSION, 'library_id': catalog['library_id'], 'revision': catalog['revision'],
            'query': value, 'total': len(rows),
            'items': [{key: row[key] for key in PUBLIC} for row in rows[start:start + limit]],
            'next_offset': start + limit if start + limit < len(rows) else None}


def snapshot(catalog, store):
    return {'version': S.VERSION, 'library_id': catalog['library_id'], 'revision': catalog['revision'],
            'groups': deepcopy(catalog['groups']),
            'order_ids': [row['id'] for row in catalog['materials'] if row['deleted_at'] is None],
            'counts': S.counts(catalog), 'storage': {'bytes': store.usage(), 'budget_bytes': store.budget_bytes},
            'limits': {'max_active': S.MAX_ACTIVE, 'max_records': S.MAX_RECORDS,
                       'max_groups': S.MAX_GROUPS, 'max_import': S.MAX_IMPORT,
                       'max_object_bytes': S.MAX_OBJECT_BYTES, 'max_pixels': S.MAX_PIXELS},
            'warnings': ['本地自有背景库；不含官方素材或 AI 布景模型',
                         '回收站和未索引对象仍占空间；不会自动删除原件',
                         '移除背景素材不会删除已经写入工程的背景原件包']}


def receipt(before, candidate, outcomes=None):
    changed = before != candidate
    # Construct before publication: no allocation/validation should turn a known
    # durable commit into an apparent failed write.
    result = {'version': S.VERSION, 'library_id': candidate['library_id'],
              'revision': before['revision'] + int(changed), 'changed': changed,
              'counts': S.counts(candidate)}
    if outcomes is not None: result['outcomes'] = outcomes
    return result
