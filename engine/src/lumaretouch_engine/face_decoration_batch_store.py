# SPDX-License-Identifier: GPL-3.0-or-later
"""Paged session-only decoration image blobs on the existing frozen store. UNRUN."""
import re
from .collarbone_visual_store import _Images, REQUEST_FIELDS
from . import face_decoration_batch_review as REVIEW


def read_only(request):
    if image_read_only(request):return True
    try:
        if (type(request) is not dict or request.get('cmd')!='batch' or request.get('action')!='preflight'
                or set(request)-{'cmd','action','request_id','docs','module_scope','conflict_policy','people_transfer'}
                or type(request.get('request_id')) is not str or not 1<=len(request['request_id'])<=128):return False
        selected=request.get('people_transfer')
        if type(selected) is not dict or selected.get('target_policy')!='explicit_face_map':return False
        from .people_batch_transfer import options
        options(selected,request.get('module_scope'),selected['source_ref']['asset_sha256'])
        docs=request.get('docs')
        return (type(docs) is list and len(docs)==len(set(docs))
                and set(docs)=={item['target']['document']['document_id'] for item in selected['targets']})
    except (ValueError,TypeError,KeyError):return False


def image_read_only(request):
    return (type(request) is dict and set(request) == REQUEST_FIELDS and request.get('cmd') == 'batch'
        and request.get('action') == 'face_decoration_visual' and request.get('side') in ('before', 'after')
        and all(type(request.get(key)) is str and 1 <= len(request[key]) <= 128 for key in ('request_id', 'document_id'))
        and type(request.get('preflight_token')) is str and re.fullmatch('[0-9a-f]{32}', request['preflight_token']) is not None
        and type(request.get('revision')) is str and re.fullmatch('(0|[1-9][0-9]{0,19})', request['revision']) is not None
        and int(request['revision']) <= 2**64-1 and type(request.get('sha256')) is str
        and re.fullmatch('[0-9a-f]{64}', request['sha256']) is not None)


def _records(plan):
    records = REVIEW.records(plan)
    if records is None: raise ValueError('Decoration images require their actual frozen ordinary target review')
    return {item['document_id']: item for item in records}


def prune(store):
    cache = getattr(store, '_face_decoration_batch_images', None)
    if cache is not None: cache.prune(store.pending)


def attach(store, plan, displays):
    store._prune(store.clock()); prune(store)
    if store.pending.get(plan.token) is not plan: raise ValueError('Actual live decoration plan required')
    cache = getattr(store, '_face_decoration_batch_images', None)
    if cache is None:
        cache = _Images(records=_records); store._face_decoration_batch_images = cache
    cache.attach(plan, displays)


def verify_available(store, plan):
    store._prune(store.clock()); prune(store)
    if store.pending.get(plan.token) is not plan: raise ValueError('Decoration plan expired or consumed')
    cache = getattr(store, '_face_decoration_batch_images', None)
    if cache is None: raise ValueError('Decoration images unavailable')
    for document, record in _records(plan).items():
        for side in ('before', 'after'): cache.read(plan, document, record['revision'], side, record[side]['sha256'])


def retrieve(controller, request):
    if not image_read_only(request): raise ValueError('Exact decoration image coordinates required')
    try: plan = controller.store.get(request['preflight_token'], controller.versions.workspace)
    finally: prune(controller.store)
    cache = getattr(controller.store, '_face_decoration_batch_images', None)
    if cache is None: raise ValueError('Decoration images are no longer retained')
    pixels = cache.read(plan, request['document_id'], request['revision'], request['side'], request['sha256'])
    return {'event': 'batch_result', 'action': 'face_decoration_visual', 'success': True,
        **{key: request[key] for key in ('request_id', 'preflight_token', 'document_id', 'revision', 'side', 'sha256')},
        'compact': {key: value for key, value in pixels.items() if key != 'base64'}, 'image': pixels}


def failure_context(request):
    """Echo bounded exact correlation data, never convert it into authority."""
    from copy import deepcopy
    from .batch_preflight import canonical
    extra = {}
    if request.get('action') == 'preflight' and type(request.get('people_transfer')) is dict and request['people_transfer'].get('target_policy')=='explicit_face_map':
        extra = {'module_scope': request.get('module_scope'), 'policy': request.get('conflict_policy', 'skip_and_report'),
                 'applies': request['people_transfer']}
    elif request.get('action') == 'commit' and 'face_decoration_review_ack' in request:
        extra = {key: request[key] for key in ('preflight_token', 'face_decoration_review_ack', 'collarbone_review_ack','eye_bag_review_ack') if key in request}
        extra['face_decoration_visual_required']=True
    elif request.get('action') == 'face_decoration_visual':
        extra = {key: request[key] for key in ('preflight_token', 'document_id', 'revision', 'side', 'sha256') if key in request}
    elif request.get('action') in ('undo', 'redo') and type(request.get('batch_id')) is str and 1 <= len(request['batch_id']) <= 128:
        extra = {'batch_id': request['batch_id']}
    try: canonical(extra, 2*1024*1024)
    except (TypeError, ValueError): return {}
    return deepcopy(extra)
