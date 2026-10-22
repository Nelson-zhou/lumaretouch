# SPDX-License-Identifier: GPL-3.0-or-later
"""Local sample catalogue schema. Not an AI model, style engine or colour operator."""
from copy import deepcopy
import re
import uuid

VERSION = 1
MAX_IMPORT = 1000
MAX_ACTIVE = 2000
MAX_RECORDS = 20000  # Includes recoverable trash, never silently evicted.
MAX_GROUPS = 200
MAX_OBJECT_BYTES = 256 * 1024 * 1024
MAX_STORAGE_BYTES = 16 * 1024 * 1024 * 1024
MAX_CATALOG_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 32_000_000  # Same full-reference admission as reference_color_assets.
UNGROUPED = 'ungrouped'
FORMATS = {'JPEG': '.jpg', 'PNG': '.png', 'TIFF': '.tif', 'WEBP': '.webp'}


class LibraryError(ValueError):
    def __init__(self, message, *, code='invalid', outcome_unknown=False, committed=False):
        super().__init__(message)
        self.code = code
        self.outcome_unknown = outcome_unknown
        self.committed = committed


def fail(message, code='invalid'):
    raise LibraryError(message, code=code)


def identifier(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{32}', value):
        fail('样片或分组身份无效')
    return value


def new_id():
    return uuid.uuid4().hex


def digest(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        fail('样片资源摘要无效')
    return value


def name(value):
    if type(value) is not str or not value.strip() or len(value.strip()) > 120:
        fail('名称需为 1 至 120 个字符')
    value = value.strip()
    if any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        fail('名称不能包含控制字符')
    return value


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        fail('样片目录数值越界')
    return value


def empty():
    return {'version': VERSION, 'revision': 0,
            'groups': [{'id': UNGROUPED, 'name': '未分组'}], 'samples': []}


def check(value):
    if type(value) is not dict or set(value) != {'version', 'revision', 'groups', 'samples'}:
        fail('样片目录字段无效；未覆盖原文件', 'catalog_corrupt')
    if type(value['version']) is not int or value['version'] != VERSION:
        fail('不支持此样片目录版本；未覆盖原文件', 'catalog_version')
    integer(value['revision'], 0, 2**53 - 1)
    groups = value['groups']; samples = value['samples']
    if type(groups) is not list or not 1 <= len(groups) <= MAX_GROUPS:
        fail('样片分组列表无效')
    group_ids = set()
    for group in groups:
        if type(group) is not dict or set(group) != {'id', 'name'}:
            fail('样片分组字段无效')
        gid = group['id']
        if gid != UNGROUPED: identifier(gid)
        if gid in group_ids: fail('样片分组身份重复')
        group_ids.add(gid); name(group['name'])
    if UNGROUPED not in group_ids: fail('样片目录缺少未分组')
    if type(samples) is not list or len(samples) > MAX_RECORDS:
        fail('样片记录超出恢复目录预算')
    ids = set(); active = 0
    fields = {'id', 'name', 'group_id', 'kind', 'original_sha256', 'bytes',
              'width', 'height', 'format', 'precision', 'created_at', 'deleted_at',
              'reference', 'object_name', 'thumbnail_sha256', 'reference_supported',
              'reference_reason', 'notes'}
    for item in samples:
        if type(item) is not dict or set(item) != fields: fail('样片字段无效')
        identifier(item['id']); name(item['name']); digest(item['original_sha256'])
        digest(item['thumbnail_sha256'])
        if item['id'] in ids: fail('样片身份重复')
        ids.add(item['id'])
        if item['group_id'] not in group_ids: fail('样片所属分组不存在')
        if item['kind'] not in ('import', 'render'): fail('未知样片来源')
        integer(item['bytes'], 1, MAX_OBJECT_BYTES)
        integer(item['width'], 1, 100000); integer(item['height'], 1, 100000)
        if item['width'] * item['height'] > MAX_PIXELS: fail('样片像素预算越界')
        if type(item['precision']) is not str or len(item['precision']) > 80: fail('样片精度字段无效')
        integer(item['created_at'], 0, 2**53 - 1)
        if item['deleted_at'] is None: active += 1
        else: integer(item['deleted_at'], 0, 2**53 - 1)
        if type(item['reference_supported']) is not bool: fail('样片支持状态无效')
        if type(item['reference_reason']) is not str or len(item['reference_reason']) > 500: fail('样片支持说明无效')
        if type(item['notes']) is not list or len(item['notes']) > 12 or any(type(n) is not str or len(n) > 500 for n in item['notes']):
            fail('样片说明无效')
        if item['reference'] is not None:
            from . import reference_color_state as reference
            probe = reference.empty(); probe['reference'] = item['reference']; reference.check(probe)
            if item['reference']['source']['sha256'] != item['original_sha256']:
                fail('样片目录与参考资源源图摘要不一致')
            if item['kind'] == 'import' and (item['reference']['source']['width'], item['reference']['source']['height']) != (item['width'], item['height']):
                fail('导入样片目录与参考资源源图尺寸不一致')
        if item['kind'] == 'import':
            if item['format'] not in FORMATS or item['object_name'] != item['original_sha256'] + FORMATS[item['format']]:
                fail('原片资源路径无效')
        elif item['format'] != 'FLOAT32-NPZ' or item['object_name'] is not None or item['reference'] is None:
            fail('冻结渲染资源无效')
    if active > MAX_ACTIVE: fail('活动样片超过 2000 张', 'capacity')
    return deepcopy(value)


def selected(catalog, ids, *, archived=False):
    if (type(ids) is not list or not 1 <= len(ids) <= MAX_ACTIVE
            or any(type(sid) is not str for sid in ids) or len(set(ids)) != len(ids)):
        fail('请选择不重复的样片')
    for sid in ids: identifier(sid)
    found = {s['id']: s for s in catalog['samples'] if (s['deleted_at'] is not None) == archived}
    if any(sid not in found for sid in ids): fail('样片已移动至回收站或不存在，请刷新', 'stale')
    return [found[sid] for sid in ids]


def group(catalog, gid):
    if type(gid) is not str or gid not in {g['id'] for g in catalog['groups']}: fail('分组已不存在，请刷新', 'stale')
    return gid


def active_count(catalog):
    return sum(s['deleted_at'] is None for s in catalog['samples'])


def room(catalog, count=1):
    if active_count(catalog) + count > MAX_ACTIVE:
        fail('样片库最多 2000 张；可先移到回收站再导入', 'capacity')
    if len(catalog['samples']) + count > MAX_RECORDS:
        fail('恢复目录已达 20000 条记录；不会自动丢弃您的样片', 'archive_capacity')
