"""Bounded direct erase/restore intent on independently owned spill coverage.

This module accepts brush vectors, never client masks, source pixels or alpha.
The caller owns trusted effective-source and preview-token verification. The
existing Rust local-mask consumer replays the resulting recipe at source size.
Its existing composition is erase=max(current-dab, 0), restore=max(current,
dab), after feather and opacity. Partial restore never accumulates by addition.
"""
from . import local_mask_recipe as R, local_mask_state as M
from . import spill_removal_coverage as C

MAX_STROKES = 63
MIN_RADIUS = .0001
MAX_RADIUS = .5
FIELDS = frozenset(('id', 'mode', 'points', 'radius', 'opacity', 'feather'))


def _stroke(raw, source):
    if (type(raw) is not dict or set(raw) != FIELDS
            or type(raw['mode']) is not str or raw['mode'] not in ('erase', 'restore')):
        raise ValueError('祛染色涂抹仅接受完整的擦除或恢复画笔矢量')
    if raw['id'] == C.AUTOMATIC_BASE_ID:
        raise ValueError('祛染色涂抹不能使用受保护的自动覆盖度标识')
    points = raw['points']
    if (type(points) is not list or not 1 <= len(points) <= R.MAX_POINTS
            or any(type(point) is not list or len(point) != 2 for point in points)):
        raise ValueError('祛染色画笔需要 1–1024 个源图归一化坐标对')
    radius = R.number(raw['radius'], MIN_RADIUS, MAX_RADIUS)
    width, height = source['width'], source['height']
    # A circular true-source brush is generally an ellipse in normalized
    # coordinates. Never use the display PNG or cropped output dimensions.
    radius_pixels = radius * min(width, height)
    erase = raw['mode'] == 'erase'
    return R.check_object({
        'id': raw['id'], 'name': 'Erase spill coverage' if erase else 'Restore spill coverage',
        'enabled': True, 'operation': 'subtract' if erase else 'add', 'kind': 'brush',
        'opacity': raw['opacity'], 'feather': raw['feather'], 'points': points,
        'axes': [[radius_pixels / width, 0.], [0., radius_pixels / height]],
    })


def append(rawCoverage, source, strokes):
    """Return a new reviewed binding without changing any caller-owned state.

    None begins at automatic coverage=1. Otherwise the exact source-owned
    reviewed composition is retained, including order and disabled vectors.
    Erase subtracts coverage; restore uses the existing add/max union, not
    cumulative addition. Neither can manufacture estimator confidence, alter
    subject alpha or enable the spill effect. Repeated partial restores have
    the same endpoint as a single identical restore.
    """
    if type(strokes) is not list or not 1 <= len(strokes) <= MAX_STROKES:
        raise ValueError('一次祛染色涂抹需要 1–63 条画笔笔画')
    source = M.check({'source': source, 'semantic_owner': None,
                      'recipe': M.empty()['recipe']})['source']
    if source is None:
        raise ValueError('祛染色涂抹需要当前有效源图身份')
    R._shape((source['height'], source['width']))
    if rawCoverage is None:
        mask = M.check({'source': source, 'semantic_owner': None,
                        'recipe': {**M.empty()['recipe'], 'objects': [C.automatic_base()]}})
    else:
        mask = C.verify_source(rawCoverage, source)['mask']
    objects = mask['recipe']['objects']
    if len(objects) + len(strokes) > R.MAX_OBJECTS:
        raise ValueError('祛染色覆盖度超过 64 个保留矢量对象的上限')
    appended = []
    point_count = sum(len(obj.get('points', [])) for obj in objects)
    for stroke in strokes:
        obj = _stroke(stroke, source)
        point_count += len(obj['points'])
        if point_count > R.MAX_TOTAL_POINTS:
            raise ValueError('祛染色覆盖度超过 8192 个保留画笔坐标的上限')
        appended.append(obj)
    # check_stack rejects duplicate identities and the combined point budget;
    # check_binding also admits the complete true-source raster work budget.
    mask['recipe'] = R.check_stack({**mask['recipe'], 'objects': objects + appended})
    return C.check_binding({'version': C.PAINT_VERSION, 'reviewed': True, 'mask': mask,
                            'recipe_sha256': C.digest(mask)})
