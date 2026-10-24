# SPDX-License-Identifier: GPL-3.0-or-later
"""Preset-only paged image ownership. No batch token or effect data is accepted."""
import time
from types import SimpleNamespace
from . import collarbone_preset_review as REVIEW
from .collarbone_visual_store import _Images

FIELDS = {'cmd', 'action', 'request_id', 'id', 'document_id', 'revision', 'side', 'sha256', 'preflight_token'}


def image_read_only(request):
    """Exact read-only envelope; pending token/content ownership is checked later."""
    if (type(request) is not dict or set(request) != FIELDS or request.get('cmd') != 'preset'
            or request.get('action') != 'collarbone_visual'
            or request.get('side') not in ('before', 'after')):
        return False
    return all(type(request[key]) is str and 1 <= len(request[key]) <= 128
               for key in ('request_id', 'id', 'document_id', 'revision', 'sha256', 'preflight_token'))


def _record(reviews, token):
    record = reviews.pending.get(token)
    if record is None or record.get('collarbone') is None:
        raise ValueError('Preset image token is missing, consumed or belongs to another review')
    if time.monotonic() >= record['expires']:
        reviews.pending.pop(token, None); reviews.targets.pop(token, None); prune(reviews)
        raise ValueError('Preset image review expired')
    return record


def _plan(token, wrapper):
    wrapper = REVIEW.checked(wrapper); visual = wrapper['visual']
    return SimpleNamespace(token=token, records={visual['document_id']: visual})


def prune(reviews):
    now = time.monotonic()
    for token, record in list(reviews.pending.items()):
        if now >= record['expires']:
            reviews.pending.pop(token, None); reviews.targets.pop(token, None)
    cache = getattr(reviews, '_collarbone_images', None)
    if cache is not None: cache.prune(reviews.pending)


def attach(reviews, token, wrapper):
    prune(reviews)
    record = _record(reviews, token); wrapper = REVIEW.checked(wrapper)
    if record['collarbone'] != wrapper:
        raise ValueError('Preset image attachment does not match the actual frozen review')
    cache = getattr(reviews, '_collarbone_images', None)
    if cache is None:
        cache = _Images(records=lambda plan: plan.records)
        reviews._collarbone_images = cache
    images = REVIEW.take_images(wrapper)
    cache.attach(_plan(token, wrapper), {wrapper['visual']['document_id']: images})


def verify_available(reviews, token):
    record = _record(reviews, token); wrapper = REVIEW.checked(record['collarbone'])
    cache = getattr(reviews, '_collarbone_images', None)
    if cache is None: raise ValueError('Preset images are unavailable')
    plan = _plan(token, wrapper); visual = wrapper['visual']
    for side in ('before', 'after'):
        cache.read(plan, visual['document_id'], visual['revision'], side, visual[side]['sha256'])


def retrieve(controller, request):
    if not image_read_only(request):
        raise ValueError('Preset image read requires its exact scoped request')
    prune(controller.reviews)
    record = _record(controller.reviews, request['preflight_token'])
    wrapper = REVIEW.checked(record['collarbone']); visual = wrapper['visual']
    if (request['id'] != record['preset']['id'] or request['document_id'] != wrapper['load_id']
            or request['document_id'] != record['document_id'] or request['revision'] != record['revision']
            or request['revision'] != visual['revision'] or request['sha256'] != visual[request['side']]['sha256']
            or controller.ports.document_id() != wrapper['load_id']):
        raise ValueError('Preset image belongs to another preset, loaded document, revision or content')
    def require_current():
        row = controller.ports.target_row()
        if (type(row) is not dict or row.get('path') != record['path']
                or row.get('document_id') != record['row_document_id']
                or controller.ports.document_id() != wrapper['load_id']
                or str(controller.ports.revision()) != visual['revision']
                or controller.ports.target_row() is not controller.reviews.targets.get(request['preflight_token'])):
            raise ValueError('Preset image target or revision changed; prepare a fresh review')
    require_current()
    cache = getattr(controller.reviews, '_collarbone_images', None)
    if cache is None: raise ValueError('Preset image storage is unavailable')
    image = cache.read(_plan(request['preflight_token'], wrapper), visual['document_id'],
                       visual['revision'], request['side'], request['sha256'])
    require_current()
    return {'action': 'collarbone_visual',
            **{key: request[key] for key in ('request_id', 'id', 'document_id', 'revision', 'side', 'sha256', 'preflight_token')},
            'image': image}
