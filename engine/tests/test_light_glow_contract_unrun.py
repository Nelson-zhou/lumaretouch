# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Source/ownership contracts, not photographic acceptance."""
import ast
from pathlib import Path
import pytest
from lumaretouch_engine import light_glow_stage as S
from lumaretouch_engine import light_glow_jobs as J

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT/'engine/src/lumaretouch_engine'


def owner():
    return {'document_id': 'document', 'document_epoch': 'epoch', 'document_revision': '4',
            'source': {'sha256': 'a'*64, 'width': 4, 'height': 3, 'orientation': 'exif_normalized_once'}}


def command():
    return {'version': 1, 'operation_id': S.OPERATION, 'action': 'apply', 'request_id': 'write',
            'session_id': 'session', 'owner': owner(), 'token': 'candidate',
            'recipe_sha256': 'b'*64, 'result_source_sha256': 'c'*64, 'coverage_sha256': 'd'*64,
            'before_sha256': 'e'*64, 'after_sha256': 'f'*64, 'coverage_image_sha256': '0'*64,
            'reviewed': True, 'return_mode': 'new_image'}


def candidate():
    c = command()
    r = {k: c[k] for k in ('session_id', 'owner', 'token', 'recipe_sha256', 'result_source_sha256', 'coverage_sha256')}
    r.update(before={'sha256': c['before_sha256']}, after={'sha256': c['after_sha256']},
             coverage={'sha256': c['coverage_image_sha256']})
    # Correlation-only fixture, not a fabricated image sent to a live renderer.
    return S.Candidate(S.shared._json(r), b'{}', b'', b'', b'', b'', False, S._SEAL)


def test_apply_requires_every_review_image_and_full_resolution_mask_hash():
    value = candidate()
    assert value.validate_apply(command())
    for key in ('recipe_sha256', 'result_source_sha256', 'coverage_sha256',
                'before_sha256', 'after_sha256', 'coverage_image_sha256'):
        changed = command()
        changed[key] = '1'*64
        with pytest.raises(ValueError):
            value.validate_apply(changed)


@pytest.mark.parametrize('change', [{'return_mode': 'update_original'}, {'reviewed': False},
    {'version': True}, {'operation_id': 'lnx.lens_blur.v1'}, {'extra': 0}])
def test_apply_rejects_unreviewed_or_other_operation_intent(change):
    with pytest.raises(ValueError):
        S.write_command({**command(), **change})


def test_read_cancellation_must_unwind_before_success():
    jobs = J.Jobs()
    request = {'cmd': 'light_glow', 'action': 'current', 'request_id': 'read'}
    sha = J.command_hash(request)
    jobs.register('read', sha)
    jobs.request_cancel('read', sha)
    with pytest.raises(InterruptedError):
        jobs.run('read', sha, lambda stop: 'not published')
    with pytest.raises(ValueError):
        jobs.run('read', sha, lambda stop: 'not replayed')


def test_reader_only_cancels_exact_source_job_and_never_apply():
    jobs = J.Jobs()
    request = {'cmd': 'light_glow', 'action': 'current', 'request_id': 'read'}
    jobs.ingress(J.canonical({**request, '_host_request_id': 7}).decode())
    assert jobs.identities['read'] == J.command_hash(request)
    assert jobs.ingress(J.canonical({'cmd': 'light_glow_cancel_read', 'request_id': 'read', 'request': request}).decode())
    assert jobs.active['read']['event'].is_set()
    apply = {'cmd': 'light_glow', 'action': 'submit', 'request_id': 'write', 'command': command()}
    jobs.ingress(J.canonical(apply).decode())
    assert 'write' not in jobs.active


def test_source_uses_complete_current_capture_and_real_ordered_repairs():
    source = (ENGINE/'light_glow_source.py').read_text()
    assert 'capture_current_asset(engine, base.row, state, assets' in source
    assert 'edited_capture_version=3' in source and 'neutral_import_version=1' in source
    assert 'allow_legacy_import_budget_fallback=False' in source
    assert 'stack_digest(state) != fence.repair_stack_sha256' in source
    assert 'require_photo_return(asset)' in source
    assert 'shared.capture_source(asset, owner' in source
    assert 'engine._vram.base()' not in source and 'load_rgb(' not in source


def test_only_existing_atomic_new_image_return_is_used():
    host = (ENGINE/'light_glow_host.py').read_text()
    assert host.count('host.commit_return(') == 1
    assert "host.commit_return({'mode': 'new_image'" in host
    before = host.index('self.uncertain = pending')
    commit = host.index('host.commit_return(')
    assert before < commit
    assert 'receipt = self._readback(' in host and 'base.versions.version(base.row) != base.version' in host
    assert 'export_float(' not in host and 'open(' not in host


def test_source_files_are_parseable_without_product_import():
    for path in ENGINE.glob('light_glow_*.py'):
        ast.parse(path.read_text(), filename=str(path))


def test_coverage_png_is_green_with_actual_coverage_alpha_and_same_full_frame_grid():
    import base64
    import struct
    import zlib
    import numpy as np
    value = np.array([[0., .25, .5, 1.], [.1, .2, .3, .4], [1., 0., .75, .5]], dtype='<f4')
    image = S._coverage_png(value.tobytes(), 4, 3, lambda: False)
    raw = base64.b64decode(image['base64'], validate=True)
    assert (image['width'], image['height']) == (4, 3)
    assert S.shared._hash(raw) == image['sha256']
    at, payload = 8, b''
    while at < len(raw):
        n = struct.unpack('>I', raw[at:at+4])[0]
        if raw[at+4:at+8] == b'IDAT':
            payload += raw[at+8:at+8+n]
        at += n+12
    scanlines = zlib.decompress(payload)
    rows = np.frombuffer(scanlines, dtype=np.uint8).reshape(3, 17)
    assert np.all(rows[:, 0] == 0)
    rgba = rows[:, 1:].reshape(3, 4, 4)
    assert np.all(rgba[:, :, 0] == 0) and np.all(rgba[:, :, 1] == 255) and np.all(rgba[:, :, 2] == 0)
    np.testing.assert_array_equal(rgba[:, :, 3], np.floor(value*255+.5).astype(np.uint8))


def test_coverage_png_cancel_cannot_return_an_image():
    import numpy as np
    def stop():
        raise InterruptedError('fixture cancelled')
    with pytest.raises(InterruptedError):
        S._coverage_png(np.zeros((3, 4), dtype='<f4').tobytes(), 4, 3, stop)
