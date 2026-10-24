# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN derived alias admission specifications; no tests executed."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lumaretouch_engine import eye_bag_recovery_alias_derived as D
from lumaretouch_engine import eye_bag_recovery_alias_controller as C
from lumaretouch_engine import eye_bag_recovery_alias_review as R
from lumaretouch_engine import creative_derived_recovery as G
from lumaretouch_engine.source_patch_controller import PROOF_KEYS


def test_old_envelope_does_not_acquire_alias_authority():
    assert D.check_request('effect_recovery', {'cmd': 'effect_recovery'}) is False


@pytest.mark.parametrize('name', ['source_patch_capture', 'people', 'preset'])
def test_protocol_cannot_admit_unrelated_command(name):
    with pytest.raises(ValueError): D.check_request(name, {'protocol': 2})


def test_versioned_envelopes_use_exact_family_validators(monkeypatch):
    preview = Mock(return_value=True); apply = Mock(return_value=True)
    monkeypatch.setattr(C, 'check_preview_request', preview)
    monkeypatch.setattr(C, 'check_apply_request', apply)
    p = {'protocol': 2}
    assert D.check_request('effect_recovery_preview', p) is True
    assert D.check_request('effect_recovery', p) is True
    preview.assert_called_once_with(p); apply.assert_called_once_with(p)


@pytest.mark.parametrize('record', [None, {}, {'target': 'skin_smoothing', 'eye_bag_alias_entry': {}},
                                  {'target': 'eye_bag_preserve'}])
def test_versioned_wire_needs_retained_eye_bag_review(record):
    with pytest.raises(ValueError): D.require_record(SimpleNamespace(), record, {'protocol': 2})


def test_retained_record_is_reverified_against_actual_engine(monkeypatch):
    engine = SimpleNamespace(); entry = object(); verify = Mock()
    monkeypatch.setattr(R, 'verify', verify)
    D.require_record(engine, {'target': 'eye_bag_preserve', 'eye_bag_alias_entry': entry}, {'protocol': 2})
    verify.assert_called_once_with(engine, entry)


def test_derived_image_admission_still_checks_capture_pixels_and_context(monkeypatch):
    engine = SimpleNamespace()
    command = {'cmd': 'effect_recovery_preview', 'action': 'image', 'protocol': 2,
               'preview_id': 'a' * 32, **{key: 'proof-' + key for key in PROOF_KEYS}}
    record = {'id': command['preview_id'], 'target': 'eye_bag_preserve',
              'proof': {key: command[key] for key in PROOF_KEYS}, 'eye_bag_alias_entry': object()}
    engine._effect_recovery_preview_owner = SimpleNamespace(record=record)
    checked = []
    monkeypatch.setattr(D, 'check_request', lambda *args: True)
    monkeypatch.setattr(G, '_global_value', lambda *args: checked.append('global'))
    monkeypatch.setattr(G, '_capture', lambda *args: checked.append('capture') or {'eligible': True})
    monkeypatch.setattr(G, '_pixels', lambda *args: checked.append('pixels'))
    monkeypatch.setattr(G, 'assert_review', lambda *args: checked.append('context'))
    monkeypatch.setattr(D, 'require_record', lambda *args: checked.append('retained'))
    G.require_command(engine, command['cmd'], command)
    assert checked == ['global', 'capture', 'pixels', 'context', 'retained']
