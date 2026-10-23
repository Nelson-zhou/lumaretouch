"""Read-only AND-of-axes / OR-within-axis library query and stable sorting.

No filesystem, render, history, selection, decoding, or project mutation here.
Unknown sort values stay last in BOTH directions. Path tie-breaking is always
ascending, even for a descending primary sort, to avoid direction-dependent ties.
"""
from datetime import datetime, timezone
from .library_query_schema import RAW_FORMATS, validate_query


def _chosen(choices, value):
    return not choices or value in choices


def _boolean(value):
    return 'yes' if value is True else 'no' if value is False else None


def _matches(row, query):
    facts = row['library']
    trash = bool(row.get('trashed'))
    if query['trash'] != 'all' and trash != (query['trash'] == 'trash'):
        return False
    search = query['search'].strip().casefold()
    if search and search not in str(row.get('name', '')).casefold():
        return False
    rating = query['rating']
    if rating is not None:
        actual, wanted = facts.get('rating'), rating['value']
        if actual is None:
            return False
        if not {'gte': actual >= wanted, 'lte': actual <= wanted,
                'eq': actual == wanted}[rating['op']]:
            return False
    for key, actual in (('flags', facts.get('flag')), ('labels', facts.get('label')),
                        ('edited', _boolean(facts.get('edited'))),
                        ('exported', _boolean(facts.get('exported'))),
                        ('orientations', facts.get('orientation', 'unknown'))):
        if not _chosen(query[key], actual):
            return False
    fmt = facts.get('format') or 'unknown'
    if query['formats'] and fmt not in query['formats']:
        if not ('raw' in query['formats'] and fmt in RAW_FORMATS):
            return False
    return True


def _time_key(value):
    if type(value) is not str:
        return None
    try:
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None
    # Zoned EXIF dates compare in UTC; absent offsets remain camera wall time.
    # The response describes that policy instead of fabricating a source offset.
    return (value.year, value.month, value.day, value.hour, value.minute,
            value.second, value.microsecond)


def _sort_value(row, field):
    facts = row['library']
    if field == 'import':
        return row['index']
    if field == 'name':
        return str(row.get('name', '')).casefold()
    if field in ('capture_time', 'edit_time'):
        return _time_key(facts.get(field))
    if field == 'type':
        return facts.get('format')
    if field == 'size':
        return facts.get('size')
    return facts.get('rating')


def evaluate(rows, query):
    """Return references to rows in view order; never reorder the input list."""
    query = validate_query(query)
    matches = [row for row in rows if _matches(row, query)]
    stable = sorted(matches, key=lambda row: (row['path'].casefold(), row['path'], row['index']))
    known, unknown = [], []
    for row in stable:
        value = _sort_value(row, query['sort'])
        (unknown if value is None else known).append((value, row))
    known.sort(key=lambda pair: pair[0], reverse=query['direction'] == 'desc')
    return [row for _, row in known] + [row for _, row in unknown]
