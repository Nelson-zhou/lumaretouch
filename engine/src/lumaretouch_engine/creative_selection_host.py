# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned manual creative selections, exact review and one history commit.

AUTHORED / UNRUN. Vector drafts belong to the UI. Context/preview never publish
assets or alter the canonical graph. Apply reuses the existing CreativeController
ports and CreativeHost.commit_document, including its history/project codec.
"""
from __future__ import annotations
from collections import OrderedDict
from copy import deepcopy
import uuid
from . import creative_document_state as S
from . import creative_selection_recipe as R
from . import creative_selection_stage as ST
from .creative_selection_jobs import controller as jobs

COMMAND = 'creative_selection'
EVENT = 'creative_selection_result'
MAX_WRITES = 128
MAX_READS = 64
ENVELOPE = ('request_id', 'document_id', 'source_uid', 'expected_revision', 'ownership_token')
BASE = {'cmd', 'action', 'request_id', 'source_uid'}
FIELDS = {
    'context': BASE | {'document_id', 'expected_revision', 'ownership_token', 'layer_id'},
    'preview': BASE | {'proof', 'recipe', 'mask_policy'},
    'apply': BASE | {'proof', 'preview_token', 'ack', 'reviewed'},
    'cancel': BASE | {'target_request_id'},
    'status': BASE | {'target_request_id'},
}


def capability():
    from .creative_selection_native import capability as query
    return query()


def _validate(request):
    if type(request) is not dict or request.get('cmd') != COMMAND or request.get('action') not in FIELDS:
        raise ValueError('Unknown creative selection command')
    expected = FIELDS[request['action']]
    actual = set(request)
    if request['action'] == 'cancel':
        actual -= {'preview_token'}
    if actual != expected or not all(R.valid_id(request.get(k)) for k in ('request_id', 'source_uid')):
        raise ValueError('Malformed creative selection command')
    if request['action'] in ('cancel', 'status') and not R.valid_id(request.get('target_request_id')):
        raise ValueError('Selection request query requires its exact original request ID')
    if request.get('preview_token') is not None and not R.valid_id(request['preview_token']):
        raise ValueError('Invalid selection review token')
    if len(R.canonical(request)) > 8_000_000:
        raise ValueError('Selection vector command exceeds its transport budget')
    return request


def _event(request, status, **extra):
    return {'event': EVENT, 'action': request.get('action'), 'request_id': request.get('request_id'),
            'source_uid': request.get('source_uid'), 'status': status,
            'success': status in ('ready', 'applied', 'no_change'),
            'outcome_unknown': status == 'unknown', **extra}


def _layer(document, identity):
    if identity != document['selected_id']:
        raise ValueError('Select the exact image layer before starting a manual selection')
    by_id = {item['id']: item for item in document['layers']}
    layer = by_id.get(identity)
    if layer is None or layer['kind'] != 'image':
        raise ValueError('Manual selections require a selected leaf image, not a group or canvas')
    current = layer
    while current is not None:
        if current['locked']:
            raise ValueError('The selected image or one of its ancestors is locked')
        current = by_id.get(current['parent_id'])
    return layer


class Service:
    def __init__(self, engine, emit):
        self.engine, self.emit = engine, emit
        self.context = None
        self.candidate = None
        self.receipts = OrderedDict()
        self.uncertain = None

    def _workspace(self):
        return self.engine._document_versions().workspace

    def _maintain(self):
        if self.uncertain is not None and self.uncertain['workspace'] != self._workspace():
            self.uncertain = None
            self.context = None
            self.candidate = None

    def _host(self):
        from .creative_document_host import CreativeHost, source_uid
        document = getattr(self.engine, '_creative_document', None)
        if document is None or document['source_uid'] != source_uid(self.engine):
            raise ValueError('Open the current creative document first; selection reads never open or rebind it')
        host = self.engine.__dict__.get('_creative_host')
        if host is None:
            host = CreativeHost(self.engine, self.emit)
            self.engine._creative_host = host
        host.sync()  # Source owner was checked above: no read-only graph rebinding.
        return host

    def _guard(self):
        self._maintain()
        if self.uncertain is not None:
            raise ValueError('Selection apply outcome is unresolved; inspect its original receipt or reopen the authoritative project')
        host = self._host()
        reason = host.guard('selection')
        if reason:
            raise ValueError(reason)
        if host.controller.pending is not None:
            raise ValueError('Finish the pending creative return before editing a selection')
        cap = capability()
        if not cap['available']:
            raise ValueError(cap['reason'])
        return host

    def _budget(self):
        from .creative_document_host import memory_budget
        return min(2_000_000_000, memory_budget())

    def _proof(self, host, document, layer, *, cancelled=lambda: False):
        from .creative_document_host import token
        source = host.assets.get(layer['asset_id'], 'rgba')
        if any(value > 131_072 for value in (source['width'], source['height'],
                                           document['canvas']['width'], document['canvas']['height'])):
            raise ValueError('Manual selection full-resolution edge budget is 131072 pixels')
        old = host.assets.get(layer['mask_id'], 'mask') if layer['mask_id'] is not None else None
        return {'document_id': document['document_id'], 'source_uid': document['source_uid'],
                'ownership_token': token(self.engine), 'expected_revision': document['revision'],
                'layer_id': layer['id'], 'asset_id': layer['asset_id'],
                'source_sha256': ST.content_hash(source['content'], cancelled),
                'document_sha256': R.sha(document), 'transform_sha256': R.sha(layer['transform']),
                'existing_mask_id': layer['mask_id'],
                'existing_mask_sha256': ST.content_hash(old['content'], cancelled) if old else None,
                'canvas': {k: document['canvas'][k] for k in ('width', 'height')},
                'source': {k: source[k] for k in ('width', 'height')}}

    def _hot(self, document, proof, event=lambda: False):
        from .creative_document_host import token, source_uid
        return (event() or source_uid(self.engine) != proof['source_uid']
                or token(self.engine) != proof['ownership_token']
                or self.engine._creative_document != document)

    def _require(self, request, host):
        proof = request.get('proof')
        context = self.context
        if context is None or R.canonical(proof) != R.canonical(context['proof']):
            raise ValueError('Selection requires its exact engine-issued current context proof')
        envelope = {k: request['request_id'] if k == 'request_id' else proof[k] for k in ENVELOPE}
        if request['source_uid'] != proof['source_uid']:
            raise ValueError('Selection source owner mismatch')
        document = host.controller._check(envelope, 'selection')
        if document != context['document'] or self._hot(document, proof):
            raise ValueError('Selection document, layer, transform or mask changed; refresh before editing')
        layer = _layer(document, proof['layer_id'])
        if self._proof(host, document, layer) != proof:
            raise ValueError('Selection immutable source or mask proof changed')
        return envelope, deepcopy(document), deepcopy(layer)

    def acquire(self, request):
        host = self._guard()
        envelope = {k: request.get(k) for k in ENVELOPE}
        document = deepcopy(host.controller._check(envelope, 'selection_context'))
        layer = deepcopy(_layer(document, request['layer_id']))
        self.context = None
        self.candidate = None
        def work(event):
            proof = self._proof(host, document, layer, cancelled=event)
            stopped = lambda: self._hot(document, proof, event)
            ST.poll(stopped)
            source = host.assets.get(layer['asset_id'], 'rgba')
            old = host.assets.get(layer['mask_id'], 'mask') if layer['mask_id'] is not None else None
            image = ST.composite_image(document, host.assets, max_bytes=self._budget() - ST.DISPLAY_RESERVE,
                                       cancelled=stopped)
            mask = ST.mask_image(old, source['width'], source['height'], cancelled=stopped) if old else None
            ST.poll(stopped)
            return proof, image, mask
        proof, image, mask = jobs(self.engine).run(request, work)
        self.context = {'proof': proof, 'document': document, 'request_id': request['request_id']}
        return _event(request, 'ready', context={'proof': deepcopy(proof), 'canvas_image': image,
                                               'existing_mask_image': mask}, capability=capability())

    def preview(self, request):
        host = self._guard()
        _, document, layer = self._require(request, host)
        recipe = R.validate(request['recipe'], document['canvas'])
        policy = R.mask_policy(request['mask_policy'], layer['mask_id'])
        proof = deepcopy(request['proof'])
        self.candidate = None
        def work(event):
            stopped = lambda: self._hot(document, proof, event)
            return ST.prepare(document, layer, host.assets, recipe, policy,
                              max_bytes=self._budget(), cancelled=stopped)
        record, after, images = jobs(self.engine).run(request, work)
        ST.poll(lambda: self._hot(document, proof))
        review = {'proof': proof, 'preview_token': uuid.uuid4().hex, 'recipe': recipe,
                  'recipe_sha256': R.sha(recipe), 'mask_policy': policy,
                  'output_mask_id': record['id'], 'output_mask_sha256': ST.content_hash(record['content']),
                  **images}
        ack_fields = {k: review[k] for k in ('proof', 'preview_token', 'recipe_sha256', 'mask_policy',
                                           'output_mask_id', 'output_mask_sha256')}
        ack_fields['images'] = {k: images[k]['sha256'] for k in images}
        review['ack'] = 'creative-selection-review-v1:' + R.sha(ack_fields)
        self.candidate = {'request_id': request['request_id'], 'before': document, 'after': after,
                          'record': record, 'review': deepcopy(review)}
        return _event(request, 'ready', review=review)

    def apply(self, request):
        host = self._guard()
        envelope, before, layer = self._require(request, host)
        candidate = self.candidate
        if candidate is None or candidate['before'] != before:
            raise ValueError('No exact current full-resolution selection review is retained')
        review = candidate['review']
        if (request['reviewed'] is not True or request['preview_token'] != review['preview_token']
                or request['ack'] != review['ack'] or R.canonical(request['proof']) != R.canonical(review['proof'])):
            raise ValueError('Compare both complete composite images and both coverage images, then acknowledge that exact review')
        if sum(item['request']['action'] == 'apply' for item in self.receipts.values()) >= MAX_WRITES:
            raise ValueError('Selection mutation receipt budget exhausted; reopen the project before starting more edits')
        record, after = candidate['record'], candidate['after']
        if ST.content_hash(record['content']) != review['output_mask_sha256']:
            raise ValueError('Reviewed immutable mask changed')
        R.mask_policy(review['mask_policy'], layer['mask_id'])
        overlay = ST.OverlayAssets(host.assets, record)
        S.validate(after, overlay)
        if after['source_asset'] != before['source_asset']:
            raise ValueError('Selection may not replace original source pixels')
        details = {'proof': deepcopy(review['proof']), 'preview_token': review['preview_token'],
                   'mask_id': record['id'], 'mask_sha256': review['output_mask_sha256'],
                   'revision': after['revision']}
        if after == before:
            self.candidate = None
            return _event(request, 'no_change', **details)
        # Publish only through the established creative transaction. Interning is
        # private immutable caching; graph references/history are not yet changed.
        host.assets.intern(record)
        ST.poll(lambda: self._hot(before, request['proof']))
        if not host.controller.ports.history_recoverable():
            raise ValueError('Recoverable unified history is required for selection mask edits')
        self.uncertain = {'workspace': self._workspace(), 'request_id': request['request_id'],
                          'proof': deepcopy(request['proof'])}
        try:
            host.controller.ports.commit_document(deepcopy(after), deepcopy(before), 'creative:selection_mask')
            if host.controller.ports.read_document() != after:
                raise RuntimeError('Creative selection commit outcome requires authoritative reconciliation')
        except Exception as error:
            # Never infer rollback from a raised adapter error or repeat the write.
            raise RuntimeError('Creative selection commit outcome is unknown; inspect the original request and reopen the authoritative project') from error
        self.uncertain = None
        self.candidate = None
        self.context = None
        result = _event(request, 'applied', **details)
        # Publication/preview failure cannot relabel a confirmed canonical edit.
        try:
            host.render_preview()
            result['creative_state'] = host.report()
            result['doc_state'] = self.engine.doc_state()
        except Exception as error:
            result['preview_error'] = str(error)[:512]
        return result

    def lookup(self, request):
        key = (request['source_uid'], request['target_request_id'])
        known = self.receipts.get(key)
        if known is None:
            return _event(request, 'pending', target_request_id=request['target_request_id'],
                          message='No terminal original receipt is available; this does not authorize resubmission')
        return _event(request, known['event']['status'], target_request_id=request['target_request_id'],
                      original_result=deepcopy(known['event']))

    def cancel(self, request):
        target = request['target_request_id']
        key = (request['source_uid'], target)
        known = self.receipts.get(key)
        if known is not None and known['request']['action'] == 'apply':
            return self.lookup(request)  # A committed/unknown write is never called cancelled.
        signalled = jobs(self.engine).request_cancel(request['source_uid'], target)
        released = False
        if (self.candidate is not None and target == self.candidate['request_id']
                and request['source_uid'] == self.candidate['review']['proof']['source_uid']):
            if request.get('preview_token') not in (None, self.candidate['review']['preview_token']):
                raise ValueError('Selection cancellation token belongs to another review')
            self.candidate = None
            released = True
        if (self.context is not None and target == self.context['request_id']
                and request['source_uid'] == self.context['proof']['source_uid']):
            self.context = None
            self.candidate = None
            released = True
        if released or (known is not None and known['event']['status'] == 'cancelled'):
            return _event(request, 'cancelled', target_request_id=target, no_write=True)
        if signalled:
            return _event(request, 'pending', target_request_id=target,
                          message='Cancellation requested; wait for the original operation to unwind')
        return _event(request, 'rejected', target_request_id=target, no_write=True,
                      message='The read already completed and no matching uncommitted review remains to cancel')

    def settle_cancels(self, original, outcome):
        """Settle queued early-cancel receipts only after original actual outcome."""
        if outcome['status'] == 'pending' or original['action'] in ('cancel', 'status'):
            return []
        results = []
        for row in list(self.receipts.values()):
            cancel = row['request']
            if (cancel['action'] != 'cancel' or row['event']['status'] != 'pending'
                    or cancel['source_uid'] != original['source_uid']
                    or cancel['target_request_id'] != original['request_id']):
                continue
            if original['action'] == 'apply':
                result = _event(cancel, outcome['status'], target_request_id=original['request_id'],
                                original_result=deepcopy(outcome))
            elif outcome['status'] == 'cancelled':
                result = _event(cancel, 'cancelled', target_request_id=original['request_id'], no_write=True)
            elif outcome['status'] == 'ready':
                # Work won the last cancellation race; release any private review
                # rather than claim the already completed calculation unwound.
                result = self.cancel(cancel)
            else:
                result = _event(cancel, 'rejected', target_request_id=original['request_id'], no_write=True,
                                message='The original read ended without a retained candidate', original_result=deepcopy(outcome))
            row['event'] = deepcopy(result)
            results.append(result)
        return results

    def remember(self, request, event):
        key = (request['source_uid'], request['request_id'])
        retained = deepcopy(event)
        if request['action'] == 'apply' and 'creative_state' in retained:
            # A receipt proves the commit, not a second display-image history.
            retained['creative_state']['preview'] = None
        self.receipts[key] = {'request': deepcopy(request), 'event': retained}
        # Keep mutation outcomes without eviction. Old large read images are
        # released rather than retaining an RGBA/mask history per preview.
        reads = [key for key, row in self.receipts.items() if row['request']['action'] != 'apply']
        for old_key in reads[:-2]:
            row = self.receipts[old_key]
            if 'review' in row['event'] or 'context' in row['event'] or 'original_result' in row['event']:
                row['event'] = _event(row['request'], 'rejected', no_write=True,
                                      message='Completed read imagery was released; start a new explicit read, never retry a write')
        while len(reads) > MAX_READS:
            victim = next((key for key in reads if self.receipts[key]['event']['status'] != 'pending'), None)
            if victim is None:
                break
            reads.remove(victim)
            self.receipts.pop(victim, None)
        return event

    def handle(self, request):
        result = None
        should_remember = True
        cancellations = []
        try:
            _validate(request)
            key = (request['source_uid'], request['request_id'])
            old = self.receipts.get(key)
            if old is not None:
                if R.canonical(old['request']) != R.canonical(request):
                    result = _event(request, 'rejected', no_write=True,
                                    message='Selection request ID reused with different content; original receipt retained')
                else:
                    result = deepcopy(old['event'])
                should_remember = False
            else:
                from .creative_document_host import source_uid
                if request['action'] not in ('status', 'cancel') and request['source_uid'] != source_uid(self.engine):
                    raise ValueError('Selection photograph owner changed')
                self._maintain()
                if request['action'] == 'cancel' and sum(row['request']['action'] == 'cancel'
                        and row['event']['status'] == 'pending' for row in self.receipts.values()) >= 32:
                    raise ValueError('Selection pending cancellation receipt budget exhausted')
                result = {'context': self.acquire, 'preview': self.preview, 'apply': self.apply,
                          'status': self.lookup, 'cancel': self.cancel}[request['action']](request)
        except Exception as error:
            unknown = self.uncertain is not None and self.uncertain['request_id'] == request.get('request_id')
            status = 'unknown' if unknown else 'cancelled' if isinstance(error, InterruptedError) else 'rejected'
            extras = {'message': str(error)[:512]}
            if not unknown:
                extras['no_write'] = True
            if request.get('action') == 'apply':
                extras.update(proof=deepcopy(request.get('proof')), preview_token=request.get('preview_token'))
            result = _event(request, status, **extras)
        if should_remember and type(request) is dict and R.valid_id(request.get('request_id')) and R.valid_id(request.get('source_uid')):
            jobs(self.engine).retire(request)
            self.remember(request, result)
            cancellations = self.settle_cancels(request, result)
        # Cache first: a failed transport can be queried by original request ID.
        self.emit(result)
        for cancellation in cancellations:
            self.emit(cancellation)


def service(engine, emit):
    owner = engine.__dict__.get('_creative_selection_service')
    if owner is None:
        owner = Service(engine, emit)
        engine._creative_selection_service = owner
    return owner


def handle(engine, request, emit):
    service(engine, emit).handle(request)


def read_only(request):
    return request.get('cmd') == COMMAND and request.get('action') in ('context', 'preview', 'cancel', 'status')


def guard_other(engine, name, request):
    owner = engine.__dict__.get('_creative_selection_service')
    if owner is None:
        return
    owner._maintain()
    if owner.uncertain is None:
        return
    if name in ('hello', 'shutdown') or (name == COMMAND and request.get('action') in ('status', 'cancel')):
        return
    if name == 'session' and request.get('action') == 'query':
        return
    if name == 'project' and request.get('action') in ('open', 'create', 'new'):
        return
    if name == 'project_recovery' and request.get('action') in ('list', 'inspect', 'status', 'restore'):
        return
    raise ValueError('Selection mask commit is unresolved; query the original request or reopen the authoritative project before editing')


def invalidate_after_reload(engine):
    """Call only after a confirmed authoritative project/workspace reload."""
    owner = engine.__dict__.get('_creative_selection_service')
    if owner is not None:
        owner.uncertain = None
        owner.context = None
        owner.candidate = None


def dispatch_rejected(engine, request, message, started, emit):
    if type(request) is not dict or not R.valid_id(request.get('request_id')) or not R.valid_id(request.get('source_uid')):
        return
    owner = service(engine, emit)
    old = owner.receipts.get((request['source_uid'], request['request_id']))
    if old is not None:
        if R.canonical(old['request']) == R.canonical(request):
            emit(deepcopy(old['event']))
        else:
            emit(_event(request, 'rejected', no_write=True, message='Selection request identity conflict; original receipt retained'))
        return
    unknown = bool(started and request.get('action') == 'apply')
    result = _event(request, 'unknown' if unknown else 'rejected', message=str(message)[:512],
                    proof=deepcopy(request.get('proof')), preview_token=request.get('preview_token'))
    if unknown:
        owner.uncertain = {'workspace': owner._workspace(), 'request_id': request['request_id'],
                           'proof': deepcopy(request.get('proof'))}
    else:
        result['no_write'] = True
    jobs(engine).retire(request)
    owner.remember(request, result)
    cancellations = owner.settle_cancels(request, result)
    emit(result)
    for cancellation in cancellations:
        emit(cancellation)
