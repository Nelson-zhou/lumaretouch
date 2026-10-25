"""Strict, bounded ingress envelopes. No device, filesystem or project mutations."""
from copy import deepcopy
import json
import os
import re
import uuid

PROTOCOL = 1
MAX_OPERATIONS = 64
MAX_RECEIPTS = 256
RECOVERY_RESERVE = 16
MAX_FILES = 512
MAX_FILE_BYTES = 2 * 1024 ** 3
MAX_BYTES = 16 * 1024 ** 3
MAX_COMMAND_BYTES = 4 * 1024 ** 2
FIELDS = {
    'state': set(),
    'arm': {'owner', 'expected', 'max_operations'},
    'import': {'session_id', 'paths', 'root', 'root_identity', 'completed_sources'},
    'query': {'session_id', 'operation_id'},
    'cancel': {'session_id', 'operation_id'},
    'release': {'session_id'},
}


def identity(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('需要规范 UUID 请求或会话身份')
    return value


def token(value):
    if (not isinstance(value, str) or not value or len(value.encode('utf-8')) > 128
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError('缺少有界来源或工程身份')
    return value


def digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('缺少完整 SHA-256 内容证据')
    return value


def path(value):
    if (not isinstance(value, str) or not value.startswith('/') or '\x00' in value
            or len(value) > 4096 or (value != '/' and any(part in ('', '.', '..')
            for part in value.split('/')[1:]))):
        raise ValueError('需要规范绝对本地路径')
    return value


def binding(value):
    if type(value) is not dict or set(value) != {'project_id', 'path', 'workspace', 'disk_sha256'}:
        raise ValueError('工程身份必须包含工程、路径、工作区与已保存磁盘指纹')
    token(value['project_id']); token(value['workspace'])
    path(value['path']); digest(value['disk_sha256'])
    return deepcopy(value)


def sources(value, paths):
    if (type(paths) is not list or not 1 <= len(paths) <= MAX_FILES
            or any(not isinstance(item, str) for item in paths) or len(set(paths)) != len(paths)
            or type(value) is not list or len(value) != len(paths)):
        raise ValueError('需要 1–512 个独立文件及逐文件完整证据；不接受目录扫描')
    total, occurrences = 0, set()
    for expected_path, item in zip(paths, value):
        if type(item) is not dict or set(item) != {'path', 'sha256', 'size', 'stat', 'occurrence_id', 'completion'}:
            raise ValueError('完整来源证据字段不匹配')
        if path(item['path']) != path(expected_path):
            raise ValueError('来源证据与所选文件顺序不一致')
        digest(item['sha256']); token(item['occurrence_id'])
        if item['occurrence_id'] in occurrences:
            raise ValueError('同次导入不能重复来源事件身份')
        occurrences.add(item['occurrence_id'])
        if type(item['size']) is not int or not 0 < item['size'] <= MAX_FILE_BYTES:
            raise ValueError('来源文件必须非空且不超过 2 GiB')
        stamp = item['stat']
        if (type(stamp) is not list or len(stamp) != 5 or any(not isinstance(part, str)
                or not re.fullmatch('0|[1-9][0-9]{0,19}', part) for part in stamp)
                or int(stamp[2]) != item['size']):
            raise ValueError('来源 stat 必须为五个精确十进制字符串，大小须一致')
        if item['completion'] not in ('stable_read', 'completed_transfer'):
            raise ValueError('来源必须说明稳定读取或已完成传输，不能推断相机完成')
        total += item['size']
    if total > MAX_BYTES:
        raise ValueError('一次来源总量不能超过 16 GiB')
    return deepcopy(value)


def command(value):
    if type(value) is not dict or value.get('cmd') != 'ingest_session':
        raise ValueError('无效有界接入命令')
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > MAX_COMMAND_BYTES:
        raise ValueError('有界接入请求超过 4 MiB')
    action = value.get('action')
    if not isinstance(action, str) or action not in FIELDS:
        raise ValueError('未知有界接入动作')
    if set(value) != {'cmd', 'action', 'request_id'} | FIELDS[action]:
        raise ValueError('有界接入请求包含缺失或未知字段')
    identity(value['request_id'])
    if action == 'arm':
        if value['owner'] not in ('workflow', 'tether'):
            raise ValueError('接入来源只支持本地工作流或有线传输')
        binding(value['expected'])
        if type(value['max_operations']) is not int or not 1 <= value['max_operations'] <= MAX_OPERATIONS:
            raise ValueError('每次会话须明确限制为 1–64 次导入')
    if action in ('import', 'query', 'cancel', 'release'):
        identity(value['session_id'])
    if action in ('query', 'cancel'):
        identity(value['operation_id'])
    if action == 'import':
        path(value['root']); sources(value['completed_sources'], value['paths'])
        root_identity(value['root_identity'])
    return deepcopy(value)


def operation_id(session_id, request_id):
    """Stable recovery address, not permission to retry the operation."""
    return str(uuid.uuid5(uuid.UUID(identity(session_id)), identity(request_id)))


def prepared_matches(prepared, expected, root, operation):
    if type(prepared) is not list or len(prepared) != len(expected):
        raise ValueError('实际完整复制数量与来源证据不符')
    by_path = {row['path']: row for row in expected}
    seen = set()
    for item in prepared:
        source = item.get('source')
        proof = by_path.get(source)
        target = os.path.join(root, str(uuid.uuid5(uuid.UUID(operation), source))
                              + os.path.splitext(source)[1].lower()) if proof else None
        if (proof is None or source in seen or item.get('size') != proof['size']
                or item.get('sha256') != proof['sha256']
                or item.get('signature') != [int(part) for part in proof['stat']]
                or item.get('path') != target):
            raise ValueError('实际完整复制内容、来源 stat 或目标与已冻结证据不符')
        fingerprint = item.get('fingerprint') or {}
        if (fingerprint.get('hash_level') != 'full' or fingerprint.get('sha256') != proof['sha256']
                or fingerprint.get('bytes') != proof['size'] or fingerprint.get('path') != target):
            raise ValueError('托管复制缺少完整内容指纹')
        seen.add(source)
    if seen != set(by_path):
        raise ValueError('实际完整复制缺少指定来源')


def root_identity(value):
    if (type(value) is not list or len(value) != 2 or any(
            not isinstance(part, str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}', part)
            or int(part) > 2**64 - 1 for part in value)):
        raise ValueError('托管目标目录需要原始设备号与 inode 证据')
    return tuple(int(part) for part in value)
