# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: preset image-store ownership and read fences.

These isolate the store with a fake image cache and wrapper validator. They do
not establish PNG, rendering, numerical, integration or photographic acceptance.
No product imports or tests were executed during authoring.
"""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from lumaretouch_engine import collarbone_preset_store as STORE


class Images:
    def __init__(self, records=None):
        self.records = records
        self.reads = []; self.attached = []; self.pruned = []
        self.on_read = None

    def prune(self, pending):
        self.pruned.append(set(pending))

    def attach(self, plan, images):
        self.attached.append((plan, images))

    def read(self, plan, document, revision, side, digest):
        self.reads.append((plan.token, document, revision, side, digest))
        if self.on_read is not None: self.on_read()
        return {'mime': 'image/png', 'sha256': digest, 'base64': 'fixture-only'}


@pytest.fixture
def context(monkeypatch):
    monkeypatch.setattr(STORE.time, 'monotonic', lambda: 10.0)
    # The real checker has separate source/FaceRef/coverage fixtures. This suite
    # tests only transport admission and never treats this minimal DTO as valid.
    monkeypatch.setattr(STORE.REVIEW, 'checked', deepcopy)
    monkeypatch.setattr(STORE, '_Images', Images)
    visual = {'document_id': 'logical', 'revision': '4',
              'before': {'sha256': 'a'*64}, 'after': {'sha256': 'b'*64}}
    wrapper = {'load_id': 'load-one', 'visual': visual}
    row = {'document_id': 'logical', 'path': 'source.png'}
    record = {'preset': {'id': 'preset-one'}, 'modules': {'lnx.collarbone.v1': {'amount': 0}},
              'document_id': 'load-one', 'revision': '4', 'path': 'source.png',
              'row_document_id': 'logical', 'expires': 100.0, 'collarbone': deepcopy(wrapper)}
    images = Images()
    reviews = SimpleNamespace(pending={'token': record}, targets={'token': row}, _collarbone_images=images)
    live = {'row': row, 'revision': '4', 'load': 'load-one'}
    controller = SimpleNamespace(reviews=reviews, ports=SimpleNamespace(
        document_id=lambda: live['load'], revision=lambda: live['revision'], target_row=lambda: live['row']))
    request = {'cmd': 'preset', 'action': 'collarbone_visual', 'request_id': 'read-one',
               'id': 'preset-one', 'document_id': 'load-one', 'revision': '4',
               'side': 'before', 'sha256': 'a'*64, 'preflight_token': 'token'}
    return controller, request, live, images, wrapper


def test_exact_pending_preset_record_serves_one_side(context):
    controller, request, _, images, _ = context
    result = STORE.retrieve(controller, request)
    for field in ('request_id', 'id', 'document_id', 'revision', 'side', 'sha256', 'preflight_token'):
        assert result[field] == request[field]
    assert 'success' not in result  # PresetController owns the envelope.
    assert images.reads == [('token', 'logical', '4', 'before', 'a'*64)]
    assert 'token' in controller.reviews.pending  # Reads cannot consume approval.


@pytest.mark.parametrize('field,value', [
    ('cmd', 'batch'), ('id', 'other-preset'), ('document_id', 'logical'),
    ('revision', '5'), ('side', 'mask'), ('sha256', 'b'*64), ('preflight_token', 'batch-token'),
])
def test_other_scope_or_content_never_reads_cache(context, field, value):
    controller, request, _, images, _ = context
    request[field] = value
    with pytest.raises(ValueError): STORE.retrieve(controller, request)
    assert images.reads == []


@pytest.mark.parametrize('extra', ['collarbone_review_ack', 'mask', 'path'])
def test_unexpected_payload_fields_are_rejected(context, extra):
    controller, request, _, images, _ = context
    request[extra] = 'untrusted'
    with pytest.raises(ValueError): STORE.retrieve(controller, request)
    assert images.reads == []


def test_consumed_token_cannot_read_cached_pixels(context):
    controller, request, _, images, _ = context
    del controller.reviews.pending['token']
    with pytest.raises(ValueError): STORE.retrieve(controller, request)
    assert images.reads == [] and images.pruned[-1] == set()


def test_expired_token_releases_row_and_image_reservation(context):
    controller, request, _, images, _ = context
    controller.reviews.pending['token']['expires'] = 10.0
    with pytest.raises(ValueError): STORE.retrieve(controller, request)
    assert controller.reviews.pending == {} and controller.reviews.targets == {}
    assert images.reads == [] and images.pruned[-1] == set()


def test_non_collarbone_pending_record_is_not_a_preset_image_token(context):
    controller, request, _, images, _ = context
    controller.reviews.pending['token']['collarbone'] = None
    with pytest.raises(ValueError): STORE.retrieve(controller, request)
    assert images.reads == []


@pytest.mark.parametrize('change', ['revision', 'load', 'row_object', 'logical', 'path'])
def test_current_target_drift_rejects_before_any_cached_read(context, change):
    controller, request, live, images, _ = context
    if change == 'row_object': live['row'] = dict(live['row'])
    elif change == 'logical': live['row']['document_id'] = 'other'
    elif change == 'path': live['row']['path'] = 'other.png'
    else: live[change] = 'new'
    with pytest.raises(ValueError): STORE.retrieve(controller, request)
    assert images.reads == []


def test_target_drift_during_cache_read_never_returns_stale_image(context):
    controller, request, live, images, _ = context
    images.on_read = lambda: live.update(revision='5')
    with pytest.raises(ValueError): STORE.retrieve(controller, request)
    assert len(images.reads) == 1


def test_verify_available_checks_both_frozen_sides(context):
    controller, _, _, images, _ = context
    STORE.verify_available(controller.reviews, 'token')
    assert images.reads == [('token', 'logical', '4', 'before', 'a'*64),
                            ('token', 'logical', '4', 'after', 'b'*64)]


def test_attach_requires_same_private_wrapper_before_taking_images(context, monkeypatch):
    controller, _, _, images, wrapper = context
    taken = []
    monkeypatch.setattr(STORE.REVIEW, 'take_images', lambda value: taken.append(value) or {'pixels': 'fixture'})
    other = deepcopy(wrapper); other['load_id'] = 'other'
    with pytest.raises(ValueError): STORE.attach(controller.reviews, 'token', other)
    assert taken == [] and images.attached == []
    STORE.attach(controller.reviews, 'token', wrapper)
    assert taken == [wrapper]
    plan, mapping = images.attached[0]
    assert plan.token == 'token' and set(plan.records) == {'logical'}
    assert mapping == {'logical': {'pixels': 'fixture'}}
