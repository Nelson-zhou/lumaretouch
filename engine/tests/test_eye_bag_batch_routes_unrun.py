# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Exact cached reads and derived transport boundaries."""
from pathlib import Path
import pytest
from lumaretouch_engine.eye_bag_batch_store import image_read_only, read_only
from lumaretouch_engine.creative_transfer_host import require_route


def image_request():
    return {'cmd': 'batch', 'action': 'eye_bag_visual', 'request_id': 'eye-page',
        'preflight_token': 'a' * 32, 'document_id': 'b' * 32,
        'revision': '1', 'side': 'before', 'sha256': 'c' * 64}


def test_exact_cached_eye_page_is_read_only():
    request = image_request()
    assert image_read_only(request)
    assert read_only(request)
    require_route('batch', request)


@pytest.mark.parametrize('key', ['eye_bag_review_ack', 'people_transfer', 'force', 'module_scope'])
def test_cached_page_cannot_smuggle_write_fields(key):
    request = {**image_request(), key: True}
    assert not image_read_only(request)
    assert not read_only(request)
    with pytest.raises(ValueError):
        require_route('batch', request)


def test_commit_never_becomes_a_read_only_exemption():
    request = {'cmd': 'batch', 'action': 'commit', 'request_id': 'eye-commit',
        'preflight_token': 'a' * 32, 'eye_bag_review_ack': []}
    assert not read_only(request)
    # This narrow transport admission is not ACK validation or write authority.
    # The actual frozen controller must reject an empty ACK for eligible targets.
    require_route('batch', request)
    with pytest.raises(ValueError):
        require_route('batch', {**request, 'replace_legacy': True})


def test_target_review_return_keeps_earlier_guards_and_skips_capture_invalidation():
    root = Path(__file__).parents[1] / 'src' / 'lumaretouch_engine'
    server = (root / 'server.py').read_text()
    branch = server.index('if eye_bag_batch_read_only(msg):')
    assert server.index('CDH.guard_command(self, name, msg)') < branch
    assert server.index('if relocation is not None and relocation.blocks(name, msg):') < branch
    assert branch < server.index('invalidate_other(self,name,msg)')
    assert 'if eye_bag_batch_read_only(message):return' in (root / 'project_recovery_runtime.py').read_text()
