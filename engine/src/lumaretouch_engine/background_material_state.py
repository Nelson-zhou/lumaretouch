# SPDX-License-Identifier: GPL-3.0-or-later
"""Strict independent background catalogue. No image or colour-sample ownership."""
from copy import deepcopy
import re
import uuid

VERSION = 1
UNGROUPED = 'ungrouped'
MAX_IMPORT = 1000
MAX_ACTIVE = 2000
MAX_RECORDS = 20000
MAX_GROUPS = 200
MAX_OBJECT_BYTES = 10_000_000
MAX_PIXELS = 32_000_000
MAX_CATALOG_BYTES = 32 * 1024 * 1024
MAX_STORAGE_BYTES = 16 * 1024**3
MAX_THUMB_BYTES = 256 * 1024
FORMATS = {'JPEG': '.jpg', 'PNG': '.png', 'TIFF': '.tif', 'BMP': '.bmp'}
MAX_REVISION = 2**53 - 1


class MaterialError(ValueError):
    def __init__(self, message, *, code='invalid', outcome_unknown=False, committed=False):
        super().__init__(message)
        self.code = code
        self.outcome_unknown = outcome_unknown
        self.committed = committed


def fail(message, code='invalid', **kwargs):
    raise MaterialError(message, code=code, **kwargs)


def integer(value, low=0, high=MAX_REVISION):
    if type(value) is not int or not low <= value <= high:
        fail('背景素材目录数值无效')
    return value


def identifier(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{32}', value) is None:
        fail('背景素材或分类身份无效')
    return value


def digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        fail('背景素材摘要无效')
    return value


def name(value):
    if type(value) is not str or not value.strip() or len(value.strip()) > 120:
        fail('名称需为 1 至 120 个字符')
    value = value.strip()
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        fail('名称不能包含控制字符')
    return value


def fields(value, wanted):
    if type(value) is not dict or set(value) != set(wanted):
        fail('背景素材字段不完整或包含未知字段')


def new_id():
    return uuid.uuid4().hex


def empty():
    return {'version': VERSION, 'library_id': new_id(), 'revision': 0,
            'groups': [{'id': UNGROUPED, 'name': '未分类'}], 'materials': []}


def counts(catalog):
    active = sum(row['deleted_at'] is None for row in catalog['materials'])
    return {'active': active, 'trash': len(catalog['materials']) - active,
            'total': len(catalog['materials'])}


def check(value):
    fields(value, ('version', 'library_id', 'revision', 'groups', 'materials'))
    if type(value['version']) is not int or value['version'] != VERSION:
        fail('不支持此背景素材目录版本；未重建或覆盖原目录', 'catalog_version')
    identifier(value['library_id']); integer(value['revision'])
    groups, materials = value['groups'], value['materials']
    if type(groups) is not list or not 1 <= len(groups) <= MAX_GROUPS:
        fail('背景分类列表无效', 'catalog_corrupt')
    group_ids = set()
    for group in groups:
        fields(group, ('id', 'name'))
        gid = group['id']
        if gid != UNGROUPED: identifier(gid)
        if gid in group_ids: fail('背景分类身份重复', 'catalog_corrupt')
        group_ids.add(gid)
        if name(group['name']) != group['name']: fail('背景分类名称未规范化')
    if UNGROUPED not in group_ids: fail('背景目录缺少固定未分类项', 'catalog_corrupt')
    if type(materials) is not list or len(materials) > MAX_RECORDS:
        fail('背景素材记录超过目录预算', 'capacity')
    identifiers, hashes = set(), set()
    wanted = {'id', 'name', 'group_id', 'sha256', 'bytes', 'width', 'height',
              'bits', 'format', 'has_alpha', 'created_at', 'deleted_at',
              'object_name', 'thumbnail_name', 'thumbnail_sha256', 'binding'}
    from .id_background_state import asset as check_asset
    for row in materials:
        fields(row, wanted); identifier(row['id']); digest(row['sha256'])
        digest(row['thumbnail_sha256'])
        if row['id'] in identifiers or row['sha256'] in hashes:
            fail('背景素材身份或原件摘要重复', 'catalog_corrupt')
        identifiers.add(row['id']); hashes.add(row['sha256'])
        if name(row['name']) != row['name']: fail('背景素材名称未规范化')
        if row['group_id'] not in group_ids: fail('背景素材分类不存在', 'catalog_corrupt')
        integer(row['bytes'], 1, MAX_OBJECT_BYTES)
        integer(row['width'], 1, 32766); integer(row['height'], 1, 32766)
        if row['width'] * row['height'] > MAX_PIXELS: fail('背景素材像素预算超限')
        if type(row['bits']) is not int or row['bits'] not in (8, 16): fail('背景位深无效')
        if row['format'] not in FORMATS or row['object_name'] != row['sha256'] + FORMATS[row['format']]:
            fail('背景原件对象名称无效', 'catalog_corrupt')
        if row['thumbnail_name'] != row['thumbnail_sha256'] + '.png':
            fail('背景缩略图对象名称无效', 'catalog_corrupt')
        if type(row['has_alpha']) is not bool: fail('背景透明通道状态无效')
        integer(row['created_at'])
        if row['deleted_at'] is not None: integer(row['deleted_at'])
        binding = check_asset(row['binding'])
        if (binding is None or binding['sha256'] != row['sha256']
                or (binding['width'], binding['height'], binding['bits']) !=
                   (row['width'], row['height'], row['bits'])
                or (binding['alpha_sha256'] is not None) != row['has_alpha']):
            fail('背景目录与真实解码绑定不一致', 'catalog_corrupt')
    if counts(value)['active'] > MAX_ACTIVE: fail('活动背景素材超过 2000 张', 'capacity')
    return deepcopy(value)


def group(catalog, gid):
    if type(gid) is not str or gid not in {g['id'] for g in catalog['groups']}:
        fail('背景分类已变化，请刷新', 'stale')
    return gid


def selected(catalog, ids, *, archived=False):
    if (type(ids) is not list or not 1 <= len(ids) <= MAX_ACTIVE
            or any(type(v) is not str for v in ids) or len(set(ids)) != len(ids)):
        fail('请选择不重复的背景素材')
    for value in ids: identifier(value)
    rows = {r['id']: r for r in catalog['materials'] if (r['deleted_at'] is not None) == archived}
    if any(value not in rows for value in ids):
        fail('背景素材不存在或已移入回收站，请刷新', 'stale')
    return [rows[value] for value in ids]


def selection(value):
    fields(value, ('version', 'library_id', 'material_id', 'catalog_revision', 'sha256'))
    if type(value['version']) is not int or value['version'] != VERSION:
        fail('不支持此背景素材选择版本')
    identifier(value['library_id']); identifier(value['material_id'])
    integer(value['catalog_revision']); digest(value['sha256'])
    return deepcopy(value)


def match_selection(catalog, value):
    value = selection(value)
    if catalog['library_id'] != value['library_id'] or catalog['revision'] != value['catalog_revision']:
        fail('背景素材库或目录版本已变化，请重新选择', 'stale')
    row = selected(catalog, [value['material_id']])[0]
    if row['sha256'] != value['sha256']:
        fail('背景素材选择与原件不一致', 'stale')
    return row


def cancelled(check):
    if check(): fail('背景素材操作已取消', 'cancelled')
