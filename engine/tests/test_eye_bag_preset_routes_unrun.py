# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Read-route envelope and source integration contracts."""
from pathlib import Path
import pytest
from lumaretouch_engine.eye_bag_preset_store import read_only


def preflight():
    return {'cmd': 'preset', 'action': 'preflight', 'request_id': 'request-one',
        'id': 'preset-one', 'document_id': 'load-one',
        'module_scope': ['lnx.eye_bags.v2'], 'eye_bag_replace_legacy': False}


def test_exact_explicit_preflight_is_read_only():
    assert read_only(preflight())
    value = preflight(); value['eye_bag_replace_legacy'] = True
    assert read_only(value)


@pytest.mark.parametrize('field', ['force', 'eye_bag_preset_ack', 'preflight_token', 'modules'])
def test_write_or_unscoped_payload_never_gets_read_exemption(field):
    assert not read_only({**preflight(), field: True})


def test_apply_and_missing_policy_do_not_gain_read_exemption():
    assert not read_only({**preflight(), 'action': 'apply'})
    value = preflight(); value.pop('eye_bag_replace_legacy')
    assert not read_only(value)
    assert not read_only({**preflight(), 'module_scope': ['lnx.exposure.v1']})


def test_engine_read_return_precedes_capture_invalidation():
    root = Path(__file__).parents[1] / 'src' / 'lumaretouch_engine'
    server = (root / 'server.py').read_text()
    assert server.index('if eye_bag_preset_read_only(msg):') < server.index('invalidate_other(self,name,msg)')
    assert 'if eye_bag_preset_read_only(message):return' in (root / 'project_recovery_runtime.py').read_text()
    gate = (root / 'creative_transfer_host.py').read_text()
    assert "if name=='preset' and action=='eye_bag_visual':" in gate
    assert "from .eye_bag_preset_store import image_read_only" in gate
