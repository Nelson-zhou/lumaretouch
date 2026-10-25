# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: genuine glow-to-canonical-copy integration fixtures.

These tests have not been imported or executed. When separately authorized,
they require the already installed CPU runtime and native glow/creative cores.
They use a tiny synthetic local PNG, not downloaded photography or AI inference.
No source, renderer, asset store, history controller, commit_return, or readback
is replaced with a successful dummy. The final case wraps the real commit only
to simulate losing its return acknowledgement after actual publication.

This is not Tauri/UI, photographic-quality, memory/RSS or performance acceptance.
"""
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def live_glow(tmp_path, monkeypatch):
    # Missing packages/binaries are an explicit unavailable test environment,
    # never grounds for installing, compiling, downloading or substituting math.
    np = pytest.importorskip('numpy')
    Image = pytest.importorskip('PIL.Image')
    pytest.importorskip('torch')
    from lumaretouch_engine import light_glow_native as native
    directory = Path(native.__file__).parent / 'bin'
    for name in ('liblrt_light_glow.so', 'liblrt_creative_layers.so'):
        if not (directory / name).is_file():
            pytest.skip('Packaged ' + name + ' is absent; real publication acceptance remains UNRUN')
    # An installed but incompatible native ABI is a failure, not a skipped pass.
    capability = native.capability()
    assert capability['status'] == 'available', capability
    from lumaretouch_engine import server, face
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'data'))

    def no_inference(*_args, **_kwargs):
        raise AssertionError('This synthetic colour-only fixture must never create an inference backend')

    monkeypatch.setattr(face, 'build', no_inference)
    events = []
    monkeypatch.setattr(server, 'emit', events.append)
    pixels = np.full((48, 64, 3), 35, dtype=np.uint8)
    pixels[14:34, 22:42] = (210, 175, 125)
    path = tmp_path / 'synthetic-glow-source.png'
    Image.fromarray(pixels).save(path)
    original = path.read_bytes()
    engine = server.Engine('glow-publication-' + uuid4().hex)
    table = engine._dispatch_table()

    def dispatch(request, *, expect_error=False):
        start = len(events)
        engine._process_line(json.dumps(request), table)
        batch = events[start:]
        errors = [event for event in batch if event.get('event') == 'error']
        if not expect_error:
            assert not errors, errors
        if request['cmd'] == 'light_glow':
            replies = [event for event in batch if event.get('event') == 'light_glow_result'
                       and event.get('request_id') == request['request_id']]
            assert len(replies) == 1, batch
            return replies[0]
        return batch

    try:
        dispatch({'cmd': 'load_image', 'path': str(path), 'device': 'cpu', 'strength': 0})
        assert engine._image_loaded and len(engine._docs) == 1
        # Two distinct real edit groups, followed by an actual undo, leave both
        # original stacks nonempty. Publication must preserve both independently.
        dispatch({'cmd': 'exposure', 'action': 'set', 'ev': .25})
        dispatch({'cmd': 'exposure', 'action': 'set', 'contrast': .1})
        dispatch({'cmd': 'history', 'action': 'undo'})
        engine._remember_current()
        assert len(engine._undo) == len(engine._redo) == 1
        yield engine, dispatch, path, original, events
    finally:
        # No Engine.run reader/worker loop was started by this fixture.
        engine.cmd_shutdown({})
        engine._thumb_stop.set()
        engine._pick_stop.set()
        for name in ('_thumbs', '_picks'):
            worker = getattr(engine, name, None)
            if worker is not None:
                worker.join(timeout=5)
                assert not worker.is_alive(), name
        if engine.shm is not None:
            engine.shm.close()
            engine.shm.unlink()


def _prepare(live_glow, *, strength=.45):
    engine, dispatch, path, original, _events = live_glow
    from lumaretouch_engine import light_glow_host as host
    row = engine._docs[0]
    before = dict(state=deepcopy(row['state']), undo=deepcopy(row['undo']),
                  redo=deepcopy(row['redo']), version=engine._document_versions().version(row),
                  people=engine._people_owner().snapshot(), load_id=engine._load_id)
    current = dispatch({'cmd': 'light_glow', 'action': 'current', 'request_id': 'current-one'})
    assert current['status'] == 'ready', current
    context = current['context']
    assert context['owner']['document_id'] == row['document_id']
    assert context['source_evidence']['load_id'] == str(engine._load_id)
    assert context['source_evidence']['capture_version'] == 3
    recipe = {'version': 1, 'operation_id': 'lnx.light_glow.v1', 'math_identity': 65537,
              'mode': 'glow', 'strength': strength, 'radius_px': 4, 'threshold': .15,
              'exposure_ev': 0, 'scattering': 0,
              'tint': {'hue_deg': 0, 'saturation': 0, 'lightness': 0}}
    preview = {'version': 1, 'operation_id': 'lnx.light_glow.v1', 'action': 'preview',
               'request_id': 'preview-one', 'session_id': context['session_id'],
               'owner': context['owner'], 'recipe': recipe}
    result = dispatch({'cmd': 'light_glow', 'action': 'preview',
                       'request_id': preview['request_id'], 'command': preview})
    assert result['status'] == 'ready', result
    review = result['review']
    service = host.service(engine, _events.append)
    expected_asset = service.candidate.output_asset
    assert review['before'] == context['before']
    assert review['source_evidence'] == context['source_evidence']
    assert review['result_source_sha256'] == expected_asset['id'][7:]
    assert review['no_change'] is (strength == 0)
    assert len(expected_asset['content']) == 64 * 48 * 16
    if strength:
        assert service.source.pixels.content != expected_asset['content']
        assert review['before']['sha256'] != review['after']['sha256']
    command = {'version': 1, 'operation_id': 'lnx.light_glow.v1', 'action': 'apply',
               'request_id': 'apply-one', 'session_id': review['session_id'],
               'owner': review['owner'], 'token': review['token'],
               **{key: review[key] for key in
                  ('recipe_sha256', 'result_source_sha256', 'coverage_sha256')},
               'before_sha256': review['before']['sha256'],
               'after_sha256': review['after']['sha256'],
               'coverage_image_sha256': review['coverage']['sha256'],
               'reviewed': True, 'return_mode': 'new_image'}
    _assert_original(engine, row, before, path, original)
    return row, before, expected_asset, command


def _assert_tree(actual, expected):
    """Exact state/history comparison, including any retained NumPy planes."""
    import numpy as np
    if isinstance(expected, np.ndarray):
        assert isinstance(actual, np.ndarray) and actual.dtype == expected.dtype
        np.testing.assert_array_equal(actual, expected)
    elif isinstance(expected, dict):
        assert isinstance(actual, dict) and actual.keys() == expected.keys()
        for key in expected:
            _assert_tree(actual[key], expected[key])
    elif isinstance(expected, (list, tuple)):
        assert type(actual) is type(expected) and len(actual) == len(expected)
        for a, b in zip(actual, expected):
            _assert_tree(a, b)
    else:
        assert actual == expected


def _assert_original(engine, row, before, path, original):
    assert engine._docs[0] is row
    assert engine._document_versions().version(row) == before['version']
    _assert_tree(row['state'], before['state'])
    _assert_tree(row['undo'], before['undo'])
    _assert_tree(row['redo'], before['redo'])
    from lumaretouch_engine.virtual_copy_people import row_snapshot
    assert row_snapshot(engine, row) == before['people']
    assert path.read_bytes() == original


def _assert_copy(live_glow, row, before, asset, receipt):
    engine, _dispatch, path, original, _events = live_glow
    assert receipt['phase'] == 'done' and receipt['outcome'] == 'applied'
    assert receipt['outcome_unknown'] is False
    assert len(engine._docs) == 2 and engine._doc_index == 1
    copy = engine._docs[1]
    assert copy['document_id'] == receipt['result_document_id'] != row['document_id']
    assert receipt['copied_original_document_id'] == row['document_id']
    assert receipt['result_revision'] == str(engine._document_versions().version(copy).revision)
    assert copy['path'] == row['path'] and copy['source_asset_id'] == row['source_asset_id']
    assert copy['root_document_id'] == row['root_document_id'] and copy['copy_number'] == 1
    assert copy['state']['_creative_base'] == asset
    assert copy['state']['_creative_base']['id'][7:] == receipt['result_source_sha256']
    document = copy['state']['_creative_document']
    assert document['source_uid'] == copy['document_id'] and document['revision'] == 0
    assert document['source_asset'] == asset['id']
    from lumaretouch_engine.creative_document_assets import AssetStore, validate_asset
    from lumaretouch_engine.creative_document_state import validate
    validate_asset(asset)
    assets = AssetStore()
    for record in copy['state']['_creative_asset_records'].values():
        assets.intern(record)
    validate(document, assets)
    assert copy['undo'] == copy['redo'] == engine._undo == engine._redo == []
    assert engine._load_id != before['load_id']
    _assert_original(engine, row, before, path, original)


@pytest.mark.parametrize('strength', [0., .45])
def test_real_glow_publication_creates_one_canonical_copy_and_preserves_original(live_glow, strength):
    engine, dispatch, _path, _original, _events = live_glow
    row, before, asset, command = _prepare(live_glow, strength=strength)
    request = {'cmd': 'light_glow', 'action': 'submit',
               'request_id': command['request_id'], 'command': command}
    result = dispatch(request)
    receipt = result['receipt']
    _assert_copy(live_glow, row, before, asset, receipt)
    assert receipt['no_change'] is (strength == 0)
    assert dispatch(request)['receipt'] == receipt
    assert dispatch({'cmd': 'light_glow', 'action': 'receipt',
                     'request_id': 'query-one', 'command': command})['receipt'] == receipt
    assert len(engine._docs) == 2  # Neither exact replay nor receipt creates another copy.


def test_lost_return_ack_reconciles_real_copy_without_second_commit(live_glow, monkeypatch):
    engine, dispatch, _path, _original, _events = live_glow
    row, before, asset, command = _prepare(live_glow)
    from lumaretouch_engine.creative_document_host import CreativeHost
    from lumaretouch_engine import light_glow_host as host
    original_commit = CreativeHost.commit_return
    calls = []

    def lose_return_after_real_commit(owner, plan):
        result = original_commit(owner, plan)
        calls.append(deepcopy(result))
        assert result['status'] == 'applied'
        raise RuntimeError('Fixture lost the return acknowledgement after actual canonical publication')

    monkeypatch.setattr(CreativeHost, 'commit_return', lose_return_after_real_commit)
    request = {'cmd': 'light_glow', 'action': 'submit',
               'request_id': command['request_id'], 'command': command}
    first = dispatch(request)['receipt']
    assert first['phase'] == 'unknown' and first['outcome_unknown'] is True
    assert len(calls) == 1 and len(engine._docs) == 2
    assert dispatch(request)['receipt'] == first and len(calls) == 1
    with pytest.raises(ValueError):
        host.guard_other(engine, 'exposure', {'action': 'set', 'ev': 1})
    receipt = dispatch({'cmd': 'light_glow', 'action': 'receipt',
                        'request_id': 'query-after-loss', 'command': command})['receipt']
    _assert_copy(live_glow, row, before, asset, receipt)
    assert len(calls) == 1 and host.service(engine, _events.append).uncertain is None
