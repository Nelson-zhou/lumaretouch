"""AUTHORED / UNRUN: XMP review orchestration and evidence fixtures.

The renderer seam below is synthetic and cannot establish full-pipeline pixel
quality, source ownership, native availability, or photographic acceptance.
Real original RGB8/RGB16/RAW and creative-return cases remain integration QA.
No test in this file has been executed as part of authoring this source slice.
"""
import base64
from copy import deepcopy
from hashlib import sha256
import io
import json
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from lumaretouch_engine import full_candidate_render as FULL
from lumaretouch_engine import xmp_target_review as REVIEW


def digest(value):
    return sha256(json.dumps(value, sort_keys=True).encode('utf-8')).hexdigest()


@pytest.fixture
def target(monkeypatch):
    """Fake canonical-renderer outputs test this wrapper, not that renderer."""
    engine = SimpleNamespace(revision='7', document_id='target', people='owned-people')
    row = {'src_w': 16, 'src_h': 12, 'original': 'a' * 64, 'asset': 'a' * 64, 'creative': False}
    before = {'_crop_rect': (0., 0., 1., 1.), '_crop_rotation': 0., '_exposure': (0.,) * 7}
    candidate = {**before, '_exposure': (1., 0., 0., 0., 0., 0., 0.)}
    calls = []

    def identity(owner, current, state, document_id, revision):
        if owner.document_id != document_id or owner.revision != revision:
            raise ValueError('Synthetic target identity changed')
        creative = ({'sha256': current['asset'], 'width': current['src_w'], 'height': current['src_h']}
                    if current['creative'] else None)
        proof = {'asset_sha256': current['asset'], 'original_sha256': current['original'], 'creative_source': creative}
        return {'document_id': document_id, 'revision': revision, 'source_proof': proof,
                'candidate_sha256': digest(state), 'people_sha256': digest(owner.people)}, {}, {}

    def render(owner, current, state, document_id, revision):
        calls.append(state)
        proof, _, _ = identity(owner, current, state, document_id, revision)
        source, output = REVIEW._geometry(current, state, proof['source_proof'])
        pixels = np.full((output[1], output[0], 3), .2 + state['_exposure'][0] * .1, dtype=np.float32)
        return pixels, {**proof, 'source_size': source, 'output_size': output}

    monkeypatch.setattr(FULL, 'identity', identity)
    monkeypatch.setattr(FULL, 'render', render)
    return engine, row, before, candidate, calls


def prepared(target):
    engine, row, before, candidate, _ = target
    return REVIEW.prepare(engine, row, before, candidate, 'target', '7', 'f' * 64)


@pytest.mark.parametrize('derived', [False, True])
def test_two_independent_full_views_compact_private_and_valid_public_png(target, derived):
    engine, row, before, candidate, calls = target
    row['creative'] = derived
    if derived:
        row['asset'] = 'b' * 64
    original = deepcopy((row, before, candidate, vars(engine)))
    private, public = prepared(target)
    assert calls == [before, candidate]
    assert calls[0] is before and calls[1] is candidate
    assert (row, before, candidate, vars(engine)) == original
    assert set(private) == REVIEW.FIELDS == set(public)
    assert REVIEW.checked(private) == private
    assert private['before_sha256'] != private['candidate_sha256']
    assert private['before']['sha256'] != private['after']['sha256']
    assert private['source_proof']['asset_sha256'] == row['asset']
    for key in ('before', 'after'):
        assert set(private[key]) == REVIEW.IMAGE_FIELDS
        assert set(public[key]) == REVIEW.IMAGE_FIELDS | {'base64'}
        raw = base64.b64decode(public[key]['base64'], validate=True)
        assert len(raw) <= REVIEW.MAX_PNG_BYTES
        assert len(public[key]['base64']) <= REVIEW.MAX_BASE64
        assert sha256(raw).hexdigest() == private[key]['sha256']
        with Image.open(io.BytesIO(raw)) as image:
            assert image.format == 'PNG'
            assert list(image.size) == [private[key]['width'], private[key]['height']]


@pytest.mark.parametrize('changed', ['before', 'candidate', 'source', 'people', 'document', 'revision', 'xmp', 'extent'])
def test_reverification_rejects_changed_target_or_either_recipe(target, changed):
    engine, row, before, candidate, calls = target
    private, _ = prepared(target)
    xmp = 'f' * 64
    if changed == 'before':
        before['_unrelated_upstream_edit'] = .7
    elif changed == 'candidate':
        candidate['_unrelated_upstream_edit'] = .8
    elif changed == 'source':
        row['original'] = row['asset'] = 'c' * 64
    elif changed == 'people':
        engine.people = 'different-owned-people'
    elif changed == 'document':
        engine.document_id = 'other'
    elif changed == 'revision':
        engine.revision = '8'
    elif changed == 'xmp':
        xmp = 'e' * 64
    else:
        row['src_w'] += 1
    with pytest.raises(ValueError):
        REVIEW.verify(engine, row, before, candidate, 'target', '7', xmp, private)
    assert len(calls) == 2  # Verification never renders or applies again.


def test_verify_is_read_only_and_public_bytes_cannot_become_private_evidence(target):
    engine, row, before, candidate, calls = target
    private, public = prepared(target)
    assert REVIEW.verify(engine, row, before, candidate, 'target', '7', 'f' * 64, private) == private
    assert len(calls) == 2
    with pytest.raises(ValueError):
        REVIEW.checked(public)
    changed = deepcopy(private)
    changed['before']['width'] = REVIEW.PREVIEW_EDGE + 1
    with pytest.raises(ValueError):
        REVIEW.checked(changed)


def test_intentional_commit_fence_change_requires_actual_installed_candidate(target):
    engine, row, before, candidate, calls = target
    private, _ = prepared(target)
    engine.revision = '8'
    committed = {**private, 'revision': '8'}
    installed = deepcopy(candidate)
    assert REVIEW.verify(engine, row, before, installed, 'target', '8', 'f' * 64, committed) == committed
    installed['_exposure'] = (2., 0., 0., 0., 0., 0., 0.)
    with pytest.raises(ValueError, match='proposed edits'):
        REVIEW.verify(engine, row, before, installed, 'target', '8', 'f' * 64, committed)
    assert len(calls) == 2


def test_prior_recipe_change_while_second_view_renders_invalidates_both(target, monkeypatch):
    _, _, before, candidate, _ = target
    render = FULL.render

    def changed(*args):
        result = render(*args)
        if args[2] is candidate:
            before['_edit_during_other_view'] = True
        return result

    monkeypatch.setattr(FULL, 'render', changed)
    with pytest.raises(ValueError, match='prior edits'):
        prepared(target)


def test_renderer_failure_propagates_without_proxy_or_apply_undo_fallback(target, monkeypatch):
    def failed(*args):
        raise ValueError('Original target exceeds complete preparation budget')

    monkeypatch.setattr(FULL, 'render', failed)
    with pytest.raises(ValueError, match='complete preparation budget'):
        prepared(target)
    assert target[-1] == []


@pytest.mark.parametrize('changed', ['candidate_sha256', 'source_size', 'output_size'])
def test_wrong_full_render_proof_is_not_presented_as_review(target, monkeypatch, changed):
    render = FULL.render

    def wrong(*args):
        pixels, proof = render(*args)
        proof[changed] = 'e' * 64 if changed == 'candidate_sha256' else [4, 4]
        return pixels, proof

    monkeypatch.setattr(FULL, 'render', wrong)
    with pytest.raises(ValueError):
        prepared(target)


@pytest.mark.parametrize('bad', [np.full((2, 2, 3), np.nan), np.zeros((2, 2, 3), dtype=np.uint8), np.zeros((2, 2, 4))])
def test_display_rejects_nonfinite_quantized_or_non_rgb_canonical_result(bad):
    with pytest.raises(ValueError):
        REVIEW._display(bad, [2, 2])


def test_large_noisy_display_obeys_edge_and_png_budget_without_changing_float_pixels():
    # This exercises display encoding only, not the photographic render pipeline.
    rgb = np.random.default_rng(98231).random((900, 1200, 3), dtype=np.float32)
    prior = rgb.copy()
    compact, public = REVIEW._display(rgb, [1200, 900])
    assert np.array_equal(rgb, prior)
    assert max(compact['width'], compact['height']) <= REVIEW.PREVIEW_EDGE
    raw = base64.b64decode(public['base64'], validate=True)
    assert len(raw) <= REVIEW.MAX_PNG_BYTES
    assert sha256(raw).hexdigest() == compact['sha256']


def test_png_budget_reduction_changes_only_display_extent(monkeypatch):
    rgb = np.random.default_rng(471).random((640, 640, 3), dtype=np.float32)
    prior = rgb.copy()
    monkeypatch.setattr(REVIEW, 'MAX_PNG_BYTES', 64 * 1024)
    compact, public = REVIEW._display(rgb, [640, 640])
    assert len(base64.b64decode(public['base64'], validate=True)) <= 64 * 1024
    assert max(compact['width'], compact['height']) < REVIEW.PREVIEW_EDGE
    assert np.array_equal(rgb, prior)


def test_private_copies_do_not_share_image_or_source_metadata(target):
    private, public = prepared(target)
    public['before']['width'] = 1
    public['source_proof']['asset_sha256'] = '0' * 64
    assert private['before']['width'] == 16
    assert private['source_proof']['asset_sha256'] == 'a' * 64
