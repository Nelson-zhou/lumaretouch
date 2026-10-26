"""Bounded immutable custom ICC bytes for an Original export plan.

The existing ICC conversion/writer still validates and uses this profile. This
module only freezes the requested asset; workers never reopen a mutable path.
"""
import base64
from hashlib import sha256
import os
import stat

MAX_BYTES = 1024 * 1024


def freeze(name):
    if name in ('srgb', 'source', 'none'):
        return None
    with open(name, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
            raise ValueError('Original 自定义 ICC 必须是最多 1 MiB 的普通文件')
        data = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
        stamp = lambda value: (value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
        if (len(data) != before.st_size or stamp(before) != stamp(after)
                or stamp(after) != stamp(os.stat(name))):
            raise ValueError('Original 自定义 ICC 在冻结期间变化')
    return {'schema':'lrt.export-icc-asset.v1', 'path':name, 'sha256':sha256(data).hexdigest(),
            'bytes':len(data), 'data_base64':base64.b64encode(data).decode('ascii')}


def validate(asset):
    if asset is None:
        return None
    if (type(asset) is not dict or set(asset) != {'schema','path','sha256','bytes','data_base64'}
            or asset['schema'] != 'lrt.export-icc-asset.v1' or type(asset['path']) is not str
            or not os.path.isabs(asset['path']) or type(asset['bytes']) is not int
            or not 0 < asset['bytes'] <= MAX_BYTES or type(asset['data_base64']) is not str
            or len(asset['data_base64']) > 4 * ((MAX_BYTES + 2) // 3)):
        raise ValueError('original_invalid_profile_asset')
    try:
        data = base64.b64decode(asset['data_base64'],validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError('original_invalid_profile_bytes') from error
    if len(data) != asset['bytes'] or sha256(data).hexdigest() != asset['sha256']:
        raise ValueError('original_profile_asset_integrity')
    return data
