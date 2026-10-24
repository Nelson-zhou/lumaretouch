# SPDX-License-Identifier: GPL-3.0-or-later
"""Family-qualified reads over shared immutable full-cohort images. UNRUN."""
import re
from copy import deepcopy
from .collarbone_visual_store import REQUEST_FIELDS
from . import eye_bag_cohort_review as REVIEW


def image_read_only(request):
    return (type(request) is dict and set(request) == REQUEST_FIELDS and request.get('cmd') == 'batch'
        and request.get('action') == 'eye_bag_cohort_visual' and request.get('side') in ('before', 'after')
        and all(type(request.get(key)) is str and 1 <= len(request[key]) <= 128 for key in ('request_id', 'document_id'))
        and type(request.get('preflight_token')) is str and re.fullmatch('[0-9a-f]{32}', request['preflight_token']) is not None
        and type(request.get('revision')) is str and re.fullmatch('(0|[1-9][0-9]{0,19})', request['revision']) is not None
        and int(request['revision']) <= 2**64-1 and type(request.get('sha256')) is str
        and re.fullmatch('[0-9a-f]{64}', request['sha256']) is not None)


def read_only(request):
    if image_read_only(request): return True
    try:
        if (type(request) is not dict or request.get('cmd') != 'batch' or request.get('action') != 'preflight'
                or set(request) - {'cmd', 'action', 'request_id', 'docs', 'module_scope', 'conflict_policy', 'people_transfer'}
                or type(request.get('request_id')) is not str or not 1 <= len(request['request_id']) <= 128
                or request.get('conflict_policy', 'recheck') != 'recheck'): return False
        selected = request.get('people_transfer')
        if type(selected) is not dict or 'eye_bag_cohort' not in selected: return False
        from .people_cross_owner_workflow import options
        options(selected, request.get('module_scope'))
        docs = request.get('docs')
        return (type(docs) is list and len(docs) == len(set(docs))
                and set(docs) == {item['target']['document']['document_id'] for item in selected['targets']})
    except (ValueError, TypeError, KeyError, StopIteration): return False


def _records(plan):
    rows = REVIEW.records(plan)
    if rows is None: raise ValueError('Image token is not an actual complete eye-bag cohort review')
    return {item['visual']['document_id']: item['visual'] for item in rows}


def prune(store):
    cache = getattr(store, '_eye_bag_cohort_images', None)
    if cache is not None: cache.prune(store.pending)


def attach(store, plan, displays):
    from .cohort_image_cache import cache as shared_cache
    store._prune(store.clock()); prune(store)
    if store.pending.get(plan.token) is not plan: raise ValueError('Actual live eye-bag cohort plan required')
    records = _records(plan); cache = shared_cache(store)
    if plan.token not in cache.plans:
        cache.attach(plan, displays); return
    if type(displays) is not dict or set(displays) != set(records): raise ValueError('Complete source-first eye-bag cohort display set required')
    for doc, record in records.items():
        display = displays[doc]
        if type(display) is not dict or set(display) != {'revision', 'before', 'after'} or display['revision'] != record['revision']:
            raise ValueError('Eye-bag cohort display identity changed')
        for side in ('before', 'after'):
            if cache.read(plan, doc, record['revision'], side, record[side]['sha256']) != display[side]:
                raise ValueError('Shared cohort image bytes differ; no implicit family replacement')


def verify_available(store, plan):
    store._prune(store.clock()); prune(store)
    if store.pending.get(plan.token) is not plan: raise ValueError('Eye-bag cohort expired or consumed')
    cache = getattr(store, '_eye_bag_cohort_images', None)
    if cache is None: raise ValueError('Eye-bag cohort images unavailable')
    for doc, record in _records(plan).items():
        for side in ('before', 'after'): cache.read(plan, doc, record['revision'], side, record[side]['sha256'])


def retrieve(controller, request):
    if not image_read_only(request): raise ValueError('Exact eye-bag cohort image coordinates required')
    try: plan = controller.store.get(request['preflight_token'], controller.versions.workspace)
    finally: prune(controller.store)
    records = _records(plan)
    if request['document_id'] not in records: raise ValueError('Image is not a reviewed eye-bag cohort member')
    cache = getattr(controller.store, '_eye_bag_cohort_images', None)
    if cache is None: raise ValueError('Eye-bag cohort images are no longer retained')
    pixels = cache.read(plan, request['document_id'], request['revision'], request['side'], request['sha256'])
    return {'event': 'batch_result', 'action': 'eye_bag_cohort_visual', 'success': True, 'outcome_unknown': False,
        **{key: request[key] for key in ('request_id', 'preflight_token', 'document_id', 'revision', 'side', 'sha256')},
        'compact': {key: value for key, value in pixels.items() if key != 'base64'}, 'image': pixels}


def failure_context(request):
    """Bounded request correlation only; never proof or execution outcome."""
    from .batch_preflight import canonical
    extra = {}
    if request.get('action') == 'preflight' and type(request.get('people_transfer')) is dict and 'eye_bag_cohort' in request['people_transfer']:
        extra = {'module_scope': request.get('module_scope'), 'policy': request.get('conflict_policy', 'recheck'), 'applies': request['people_transfer']}
    elif request.get('action') == 'commit' and 'eye_bag_cohort_ack' in request:
        extra = {key: request[key] for key in ('preflight_token', 'module_scope', 'eye_bag_cohort_ack', 'portrait_cohort_ack', 'collarbone_review_ack') if key in request}
        extra['eye_bag_cohort'] = True
        if 'portrait_cohort_ack' in extra: extra['portrait_cohort'] = True
        if 'collarbone_review_ack' in extra: extra['collarbone_cohort'] = True
    elif request.get('action') == 'eye_bag_cohort_visual':
        extra = {key: request[key] for key in ('preflight_token', 'document_id', 'revision', 'side', 'sha256') if key in request}
    elif request.get('action') in ('undo', 'redo') and type(request.get('batch_id')) is str and 1 <= len(request['batch_id']) <= 128:
        extra = {'batch_id': request['batch_id']}
    try: canonical(extra, 2*1024*1024)
    except (TypeError, ValueError): return {}
    return deepcopy(extra)
