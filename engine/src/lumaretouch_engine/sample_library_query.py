# SPDX-License-Identifier: GPL-3.0-or-later
"""Revision-pinned catalogue metadata pages; no silent truncation or offset drift."""
from copy import deepcopy
from hashlib import sha256
import base64
import json
from . import sample_library_state as S

MAX_PAGE = 100


def counts(catalog):
    groups = {group['id']: {'active': 0, 'trash': 0} for group in catalog['groups']}
    active = 0
    for sample in catalog['samples']:
        live = sample['deleted_at'] is None
        groups[sample['group_id']]['active' if live else 'trash'] += 1
        active += int(live)
    return {'active': active, 'trash': len(catalog['samples']) - active, 'total': len(catalog['samples'])}, groups


def capacity(catalog):
    return {'active': S.active_count(catalog), 'limit': S.MAX_ACTIVE, 'per_import': S.MAX_IMPORT}


def receipt(catalog, original):
    """Small terminal metadata, no thumbnail or whole-catalogue echo on writes."""
    old = {item['id']: item for item in original['samples']}
    affected = [item['id'] for item in catalog['samples'] if old.get(item['id']) != item]
    # Ordering changes do not change rows, but still identify reordered active IDs.
    if [s['id'] for s in catalog['samples']] != [s['id'] for s in original['samples']] and not affected:
        affected = [s['id'] for s in catalog['samples'] if s['deleted_at'] is None]
    totals, group_totals = counts(catalog)
    return {'revision': catalog['revision'] + int(catalog != original),
            'affected_ids': affected, 'capacity': capacity(catalog),
            'counts': totals, 'group_counts': group_totals}


def _query(catalog, query):
    if type(query) is not dict or set(query) != {'view', 'search', 'limit', 'cursor'}:
        S.fail('分页查询字段无效')
    view = query['view']; search = query['search']; limit = query['limit']
    if type(view) is dict:
        if set(view) != {'group'}: S.fail('分页分组条件无效')
        S.group(catalog, view['group'])
    elif type(view) is not str or view not in ('all', 'ungrouped', 'trash'):
        S.fail('分页视图无效')
    if type(search) is not str or len(search) > 240 or any(0xD800 <= ord(c) <= 0xDFFF for c in search):
        S.fail('搜索条件过长或无效')
    S.integer(limit, 1, MAX_PAGE)
    normalized = {'view': view, 'search': search.strip().casefold(), 'limit': limit}
    digest = sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
    offset = 0; cursor = query['cursor']
    if cursor is not None:
        if type(cursor) is not str or not 1 <= len(cursor) <= 320: S.fail('分页游标无效', 'stale_page')
        try:
            raw = base64.b64decode(cursor.encode('ascii'), altchars=b'-_', validate=True)
            value = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise S.LibraryError('分页游标损坏，请刷新目录', code='stale_page') from error
        if (type(value) is not dict or set(value) != {'v', 'r', 'q', 'o'} or type(value['v']) is not int or value['v'] != 1
                or type(value['r']) is not int or value['r'] != catalog['revision'] or value['q'] != digest):
            S.fail('分页条件或目录版本已变化，请刷新后重新浏览', 'stale_page')
        offset = S.integer(value['o'], 0, S.MAX_RECORDS)
    return normalized, digest, offset


def page(catalog, query):
    normalized, digest, offset = _query(catalog, query)
    view, search, limit = normalized['view'], normalized['search'], normalized['limit']
    names = {group['id']: group['name'] for group in catalog['groups']}
    matches = []
    for sample in catalog['samples']:
        if (sample['deleted_at'] is not None) != (view == 'trash'): continue
        if view == 'ungrouped' and sample['group_id'] != S.UNGROUPED: continue
        if type(view) is dict and sample['group_id'] != view['group']: continue
        if search:
            text = ' '.join((sample['name'], names[sample['group_id']], sample['format'], sample['precision'],
                             '当前成片' if sample['kind'] == 'render' else '导入图片',
                             str(sample['width']) + '×' + str(sample['height'])))
            if search not in text.casefold(): continue
        matches.append(sample)
    if offset > len(matches): S.fail('分页位置已失效，请刷新目录', 'stale_page')
    items = [{key: deepcopy(value) for key, value in sample.items()
              if key not in ('object_name', 'thumbnail_sha256')} for sample in matches[offset:offset + limit]]
    next_cursor = None
    if offset + len(items) < len(matches):
        token = {'v': 1, 'r': catalog['revision'], 'q': digest, 'o': offset + len(items)}
        next_cursor = base64.urlsafe_b64encode(json.dumps(token, separators=(',', ':')).encode()).decode('ascii')
    return {'revision': catalog['revision'], 'samples': items, 'total': len(matches),
            'offset': offset, 'limit': limit, 'next_cursor': next_cursor}
