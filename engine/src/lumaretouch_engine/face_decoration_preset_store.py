# SPDX-License-Identifier: GPL-3.0-or-later
"""Preset-only paged image ownership. No batch token or effect data is accepted."""
import time
from types import SimpleNamespace
from . import face_decoration_preset_review as REVIEW
from .collarbone_visual_store import _Images

FIELDS = {'cmd', 'action', 'request_id', 'id', 'document_id', 'revision', 'side', 'sha256', 'preflight_token'}
MEMBER_FIELDS = {'member_document_id', 'member_revision'}


def image_read_only(request):
    """Exact read-only envelope; pending token/content ownership is checked later."""
    if (type(request) is not dict or set(request) not in (FIELDS, FIELDS | MEMBER_FIELDS) or request.get('cmd') != 'preset'
            or request.get('action') != 'face_decoration_visual'
            or request.get('side') not in ('before', 'after')):
        return False
    return all(type(request[key]) is str and 1 <= len(request[key]) <= 128
               for key in (set(request) - {'cmd', 'action', 'side'}))


def _record(reviews, token):
    record = reviews.pending.get(token)
    if record is None or record.get('face_decoration') is None:
        raise ValueError('Preset image token is missing, consumed or belongs to another review')
    if time.monotonic() >= record['expires']:
        reviews.pending.pop(token, None); reviews.targets.pop(token, None); prune(reviews)
        raise ValueError('Preset image review expired')
    return record


def _plan(token, wrapper):
    wrapper = REVIEW.checked(wrapper); visual = wrapper['visual']
    records = ({member['visual']['document_id']: member['visual'] for member in wrapper['members']}
               if wrapper['version'] == 2 else {visual['document_id']: visual})
    return SimpleNamespace(token=token, records=records)


def prune(reviews):
    now = time.monotonic()
    for token, record in list(reviews.pending.items()):
        if now >= record['expires']:
            reviews.pending.pop(token, None); reviews.targets.pop(token, None)
    cache = getattr(reviews, '_face_decoration_images', None)
    claimed = getattr(reviews, '_face_decoration_claimed', {})
    for token, record in list(claimed.items()):
        if now >= record['expires']: claimed.pop(token, None)
    if cache is not None: cache.prune(set(reviews.pending) | set(claimed))


def retain_claimed(reviews, token, record):
    """Keep immutable bytes for prewrite verification, never reusable approval."""
    if record.get('face_decoration', {}).get('version') != 2: return
    claimed = getattr(reviews, '_face_decoration_claimed', None)
    if claimed is None:
        claimed = {}; reviews._face_decoration_claimed = claimed
    if token in claimed: raise ValueError('Mixed preset approval was already claimed')
    claimed[token] = record


def verify_claimed(reviews, token, wrapper):
    prune(reviews)
    record = getattr(reviews, '_face_decoration_claimed', {}).get(token)
    if record is None or record['face_decoration'] != wrapper:
        raise ValueError('Claimed mixed preset images expired or changed')
    cache = getattr(reviews, '_face_decoration_images', None)
    if cache is None: raise ValueError('Claimed mixed preset image bytes are unavailable')
    plan = _plan(token, wrapper)
    for visual in plan.records.values():
        for side in ('before', 'after'):
            cache.read(plan, visual['document_id'], visual['revision'], side, visual[side]['sha256'])
    from .face_decoration_preset_alias_review import verify_served
    verify_served(wrapper)


def release_claimed(reviews, token):
    getattr(reviews, '_face_decoration_claimed', {}).pop(token, None)
    prune(reviews)


def attach(reviews, token, wrapper):
    prune(reviews)
    record = _record(reviews, token); wrapper = REVIEW.checked(wrapper)
    if record['face_decoration'] != wrapper:
        raise ValueError('Preset image attachment does not match the actual frozen review')
    cache = getattr(reviews, '_face_decoration_images', None)
    if cache is None:
        cache = _Images(records=lambda plan: plan.records)
        reviews._face_decoration_images = cache
    images = REVIEW.take_images(wrapper)
    cache.attach(_plan(token, wrapper), images if wrapper['version'] == 2 else {wrapper['visual']['document_id']: images})


def verify_available(reviews, token):
    record = _record(reviews, token); wrapper = REVIEW.checked(record['face_decoration'])
    cache = getattr(reviews, '_face_decoration_images', None)
    if cache is None: raise ValueError('Preset images are unavailable')
    plan = _plan(token, wrapper)
    for visual in plan.records.values():
        for side in ('before', 'after'):
            cache.read(plan, visual['document_id'], visual['revision'], side, visual[side]['sha256'])
    if wrapper['version'] == 2:
        from .face_decoration_preset_alias_review import verify_served
        verify_served(wrapper)


def retrieve(controller, request):
    if not image_read_only(request):
        raise ValueError('Preset image read requires its exact scoped request')
    prune(controller.reviews)
    record = _record(controller.reviews, request['preflight_token'])
    wrapper = REVIEW.checked(record['face_decoration']); visual = wrapper['visual']
    aliases = wrapper['version'] == 2
    if (set(request) != (FIELDS | MEMBER_FIELDS if aliases else FIELDS)):
        raise ValueError('Preset image member identity must match the exact review version')
    if (request['id'] != record['preset']['id'] or request['document_id'] != wrapper['load_id']
            or request['document_id'] != record['document_id'] or request['revision'] != record['revision']
            or request['revision'] != visual['revision']
            or controller.ports.document_id() != wrapper['load_id']):
        raise ValueError('Preset image belongs to another preset, loaded document, revision or content')
    if aliases:
        visual = _plan(request['preflight_token'], wrapper).records.get(request['member_document_id'])
        if visual is None or visual['revision'] != request['member_revision']:
            raise ValueError('Preset image belongs to another reviewed member or revision')
    if request['sha256'] != visual[request['side']]['sha256']:
        raise ValueError('Preset image content differs from its exact reviewed member')
    def require_current():
        row = controller.ports.target_row()
        if (type(row) is not dict or row.get('path') != record['path']
                or row.get('document_id') != record['row_document_id']
                or controller.ports.document_id() != wrapper['load_id']
                or str(controller.ports.revision()) != wrapper['visual']['revision']
                or controller.ports.target_row() is not controller.reviews.targets.get(request['preflight_token'])):
            raise ValueError('Preset image target or revision changed; prepare a fresh review')
        if aliases:
            verify = getattr(controller.ports, 'verify_face_decoration_alias', None)
            if verify is None: raise ValueError('Complete alias image ownership verifier is unavailable')
            verify(wrapper)
    require_current()
    cache = getattr(controller.reviews, '_face_decoration_images', None)
    if cache is None: raise ValueError('Preset image storage is unavailable')
    image = cache.read(_plan(request['preflight_token'], wrapper), visual['document_id'],
                       visual['revision'], request['side'], request['sha256'])
    require_current()
    if aliases:
        from .face_decoration_preset_alias_review import served
        served(wrapper, visual['document_id'], request['side'])
    return {'action': 'face_decoration_visual',
            **{key: request[key] for key in ('request_id', 'id', 'document_id', 'revision', 'side', 'sha256', 'preflight_token')},
            **({key: request[key] for key in MEMBER_FIELDS} if aliases else {}),
            'image': image}


def read_only(request):
    """Only exact preflight/image reads; server still checks the stored modules."""
    if image_read_only(request): return True
    required={'cmd','action','request_id','id','document_id'}
    if (type(request) is not dict or not required <= set(request)
            or set(request)-(required|{'module_scope','local_mask_transfer'})
            or request.get('cmd')!='preset' or request.get('action')!='preflight'):
        return False
    scope=request.get('module_scope')
    if scope is not None and (type(scope) is not list or not scope or len(scope)>128
            or any(type(op) is not str or not 1<=len(op)<=128 for op in scope)
            or len(scope)!=len(set(scope))):return False
    return all(type(request[key]) is str and 1<=len(request[key])<=128
               for key in ('request_id','id','document_id'))
