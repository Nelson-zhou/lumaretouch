"""Bounded library view preferences, independent of recipes and project history.

The published guide specifies axes, not their complete enums. These enums are
this application's explicit policy; they are not claims about another product.
"""
from copy import deepcopy
import re

FLAGS = ('accepted', 'rejected', 'unflagged')
LABELS = ('', '红', '黄', '绿', '蓝', '紫')
ORIENTATIONS = ('landscape', 'portrait', 'square', 'unknown')
SORTS = ('capture_time', 'edit_time', 'rating', 'type', 'size', 'name', 'import')
RAW_FORMATS = frozenset(('dng', 'arw', 'cr2', 'cr3', 'nef', 'raf', 'orf', 'rw2',
                         'pef', 'srw', '3fr', 'x3f', 'rwl', 'iiq', 'raw'))


class QueryError(ValueError):
    pass


def default_query():
    return {'rating': None, 'flags': [], 'labels': [], 'edited': [],
            'exported': [], 'formats': [], 'orientations': [],
            'trash': 'active', 'search': '', 'sort': 'import', 'direction': 'asc'}


def canonical_format(value):
    if type(value) is not str:
        return None
    value = value.lower().strip().lstrip('.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,23}', value):
        return None
    return {'jpg': 'jpeg', 'jpe': 'jpeg', 'tif': 'tiff'}.get(value, value)


def _multi(value, key, choices=None):
    if type(value) is not list or len(value) > 32:
        raise QueryError(key + ' must be a bounded list')
    result = []
    for item in value:
        if type(item) is not str or len(item) > 64:
            raise QueryError(key + ' contains an invalid choice')
        if choices is not None and item not in choices:
            raise QueryError(key + ' contains an unsupported choice: ' + item)
        if key == 'formats':
            item = canonical_format(item)
            if item is None:
                raise QueryError('formats contains an invalid identifier')
        if item not in result:
            result.append(item)
    return result


def validate_query(value):
    """Validate the whole candidate before replacing any existing preference."""
    base = default_query()
    if type(value) is not dict or set(value) - set(base):
        raise QueryError('Unsupported library query fields')
    result = {**base, **deepcopy(value)}
    rating = result['rating']
    if rating is not None:
        if (type(rating) is not dict or set(rating) != {'op', 'value'}
                or rating['op'] not in ('gte', 'lte', 'eq')
                or type(rating['value']) is not int or not 0 <= rating['value'] <= 5):
            raise QueryError('rating requires gte/lte/eq and an integer from 0 to 5')
    for key, choices in (('flags', FLAGS), ('labels', LABELS),
                         ('edited', ('yes', 'no')), ('exported', ('yes', 'no')),
                         ('formats', None), ('orientations', ORIENTATIONS)):
        result[key] = _multi(result[key], key, choices)
    if result['trash'] not in ('active', 'trash', 'all'):
        raise QueryError('Unsupported trash view')
    if type(result['search']) is not str or len(result['search']) > 512:
        raise QueryError('Library search must be at most 512 characters')
    if result['sort'] not in SORTS or result['direction'] not in ('asc', 'desc'):
        raise QueryError('Unsupported library sort')
    return result
