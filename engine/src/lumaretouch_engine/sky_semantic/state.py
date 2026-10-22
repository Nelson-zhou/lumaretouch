"""Retained proposal intent. Brush corrections remain ordinary source-domain LMR2."""
from copy import deepcopy
import math
import re
from . import manifest as M

REGIONS = ('sky', 'person', 'water')


def sha(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('自动选区缺少 SHA256 身份')
    return value


def source(value):
    if type(value) is not dict or set(value) != {'sha256', 'width', 'height'}:
        raise ValueError('自动选区源照片身份无效')
    sha(value['sha256'])
    if any(type(value[k]) is not int or not 1 <= value[k] <= 65536 for k in ('width', 'height')):
        raise ValueError('自动选区源照片尺寸无效')
    if value['width'] * value['height'] > 64_000_000:
        raise ValueError('自动选区源照片超过 64 MP')
    return deepcopy(value)


def check(value):
    if value is None:
        return None
    keys = {'version', 'domain', 'source', 'model', 'host', 'device', 'input_sha256',
            'input_size', 'fields_sha256', 'regions'}
    if type(value) is not dict or set(value) != keys or value['version'] != 1 or type(value['version']) is not int:
        raise ValueError('不支持的天空自动选区配方')
    if value['domain'] != 'source-normalized':
        raise ValueError('自动选区坐标域无效')
    model = value['model']
    if (type(model) is not dict or set(model) != set(M.identity())
            or any(type(v) is not str or not 1 <= len(v) <= 200 for v in model.values())):
        raise ValueError('自动选区模型来源字段无效')
    for key in ('weights_sha256', 'adapter_sha256', 'inventory_sha256'):
        sha(model[key])
    if not re.fullmatch('[0-9a-f]{40}', model['revision']):
        raise ValueError('自动选区模型缺少固定版本身份')
    # Retain unavailable older intent so the user can remove/review it. Runtime
    # resolution, not project parsing, rejects a different implementation.
    source(value['source']); sha(value['input_sha256'])
    if value['device'] not in ('cpu', 'cuda'):
        raise ValueError('自动选区设备必须明确指定')
    if (type(value['host']) is not dict or set(value['host']) != {'python', 'torch', 'torchvision', 'numpy', 'Pillow'}
            or any(type(v) is not str or not 1 <= len(v) <= 128 for v in value['host'].values())):
        raise ValueError('自动选区宿主运行库身份无效')
    size = value['input_size']
    if (type(size) is not list or len(size) != 2 or any(type(n) is not int or not 1 <= n <= 1024 for n in size)
            or size[0] * size[1] > M.MAX_MASK_PIXELS):
        raise ValueError('自动选区推理尺寸超出固定预算')
    if type(value['fields_sha256']) is not dict or set(value['fields_sha256']) != set(REGIONS):
        raise ValueError('自动选区结果身份无效')
    for digest in value['fields_sha256'].values():
        sha(digest)
    if type(value['regions']) is not dict or not value['regions'] or not set(value['regions']).issubset(REGIONS):
        raise ValueError('必须明确接受至少一个自动选区')
    for threshold in value['regions'].values():
        if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError('自动选区支持度阈值无效')
    return deepcopy(value)


def accept(result, binding, regions):
    return check({'version': 1, 'domain': 'source-normalized', 'source': source(binding),
                  **{key: result[key] for key in ('model', 'host', 'device', 'input_sha256', 'input_size', 'fields_sha256')},
                  'regions': regions})
