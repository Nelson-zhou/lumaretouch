"""Source-normalized, document-owned view metadata, never an image recipe.

Undo/redo belongs to this record alone. No render/export, history capture, source
fingerprint, or pixel-document revision is involved in a guide edit.
"""
from copy import deepcopy
import math

MAX_LINES = 128
MAX_HISTORY = 64
MAX_REVISION = 9007199254740991
KEY = '_canvas_guides'


def default_state():
    return {'visible': True, 'lines': []}


def identifier(value):
    if (type(value) is not str or not 1 <= len(value) <= 128
            or any(not (c.isascii() and (c.isalnum() or c in '-_.:')) for c in value)):
        raise ValueError('参考线身份须为 1–128 位字母、数字或 -_.:')
    return value


def state(value):
    if type(value) is not dict or set(value) != {'visible', 'lines'}:
        raise ValueError('参考线状态须包含 visible 和 lines')
    if type(value['visible']) is not bool:
        raise ValueError('参考线可见性必须是布尔值')
    lines = value['lines']
    if type(lines) is not list or len(lines) > MAX_LINES:
        raise ValueError(f'每张文档最多 {MAX_LINES} 条参考线')
    result, seen = [], set()
    for line in lines:
        if type(line) is not dict or set(line) != {'id', 'axis', 'position'}:
            raise ValueError('参考线须包含 id、axis、position')
        identity = identifier(line['id'])
        if identity in seen:
            raise ValueError('同一文档的参考线身份不能重复')
        seen.add(identity)
        if line['axis'] not in ('horizontal', 'vertical'):
            raise ValueError('参考线方向必须是 horizontal 或 vertical')
        position = line['position']
        if type(position) not in (int, float) or not 0 <= position <= 1 or not math.isfinite(position):
            raise ValueError('参考线位置必须是 [0,1] 内的有限原图归一化坐标')
        result.append({'id': identity, 'axis': line['axis'], 'position': float(position)})
    return {'visible': value['visible'], 'lines': result}


def record(value=None):
    if value is None:
        return {'version': 1, 'revision': 0, 'state': default_state(), 'undo': [], 'redo': []}
    if type(value) is not dict or set(value) != {'version', 'revision', 'state', 'undo', 'redo'}:
        raise ValueError('参考线视图记录格式无效')
    if type(value['version']) is not int or value['version'] != 1:
        raise ValueError('参考线视图记录版本不受支持')
    if type(value['revision']) is not int or not 0 <= value['revision'] <= MAX_REVISION:
        raise ValueError('参考线修订必须是非负安全整数')
    result = {'version': 1, 'revision': value['revision'], 'state': state(value['state'])}
    for key in ('undo', 'redo'):
        if type(value[key]) is not list or len(value[key]) > MAX_HISTORY:
            raise ValueError('参考线视图历史超过上限或格式无效')
        result[key] = [state(entry) for entry in value[key]]
    return result


def change(current, action, value=None):
    """Return an owned next record, or an equal record for a no-op."""
    result = record(current)
    before = result['state']
    if action == 'set':
        after = state(value)
        if after == before:
            return result
        result['undo'] = (result['undo'] + [before])[-MAX_HISTORY:]
        result['redo'] = []
        result['state'] = after
    elif action in ('undo', 'redo'):
        if not result[action]:
            return result
        opposite = 'redo' if action == 'undo' else 'undo'
        result[opposite] = (result[opposite] + [before])[-MAX_HISTORY:]
        result['state'] = result[action].pop()
    else:
        raise ValueError('未知参考线动作')
    if result['revision'] == MAX_REVISION:
        raise ValueError('参考线修订已到上限，修改未应用')
    result['revision'] += 1
    return result


def copy_record(value=None):
    """A virtual copy inherits current guides, but owns a fresh view history."""
    return {**record(), 'state': deepcopy(record(value)['state'])}


def validate_row(row):
    if 'canvas_guides' in row:
        if row['canvas_guides'] is None:
            raise ValueError('已保存的参考线记录不能是 null')
        record(row['canvas_guides'])


def save_row(runtime, stored):
    stored['canvas_guides'] = record(runtime.get(KEY))


def restore_row(stored, runtime):
    validate_row(stored)
    runtime[KEY] = record(stored.get('canvas_guides'))
