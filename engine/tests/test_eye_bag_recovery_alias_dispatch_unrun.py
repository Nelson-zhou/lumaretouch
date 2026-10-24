# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Prepared authority owns fences, never a wire flag.

No imports, test collection, execution or application validation was performed
during authoring. These fixtures are acceptance specifications only.
"""
from hashlib import sha256
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lumaretouch_engine import effect_recovery_dispatch as D
from lumaretouch_engine import eye_bag_recovery_alias_controller as A
from lumaretouch_engine.source_patch_controller import PROOF_KEYS


def request():
    return {'cmd': 'effect_recovery', 'action': 'apply', 'request_id': 'request',
            'preview_id': 'a' * 32, **{key: 'proof-' + key for key in PROOF_KEYS}}


def retained(command):
    pending = {'recovery_alias': object(), 'started': False,
               'digest': sha256(json.dumps(command, sort_keys=True, allow_nan=False).encode()).hexdigest(),
               'result': {'protocol': 2, **{key: command[key] for key in
                          ('request_id', 'preview_id', *PROOF_KEYS)}}}
    return SimpleNamespace(_effect_recovery_owner=SimpleNamespace(pending=pending)), pending


def test_wire_flag_without_internal_review_cannot_own_fence(monkeypatch):
    check = Mock(return_value=True); monkeypatch.setattr(A, 'prepared', check)
    command = {**request(), 'protocol': 2, 'recovery_alias': True}
    assert D.owns_fence(SimpleNamespace(), command) is False
    check.assert_not_called()


def test_complete_prepared_authority_is_rechecked_without_consumption(monkeypatch):
    command = request(); engine, pending = retained(command)
    check = Mock(return_value=True); monkeypatch.setattr(A, 'prepared', check)
    assert D.owns_fence(engine, command) is True
    check.assert_called_once_with(engine, pending)
    assert pending['started'] is False


@pytest.mark.parametrize('field', ['request_id', 'preview_id', *PROOF_KEYS])
def test_each_identity_change_refuses_dispatch_suppression(monkeypatch, field):
    command = request(); engine, _ = retained(command)
    monkeypatch.setattr(A, 'prepared', Mock(return_value=True))
    with pytest.raises(ValueError): D.owns_fence(engine, {**command, field: 'changed'})


def test_extra_client_field_cannot_match_prepared_digest(monkeypatch):
    command = request(); engine, _ = retained(command)
    monkeypatch.setattr(A, 'prepared', Mock(return_value=True))
    with pytest.raises(ValueError): D.owns_fence(engine, {**command, 'bypass': True})


@pytest.mark.parametrize('accepted', [False, None, 1])
def test_missing_complete_review_never_suppresses_dispatch(monkeypatch, accepted):
    command = request(); engine, _ = retained(command)
    monkeypatch.setattr(A, 'prepared', Mock(return_value=accepted))
    with pytest.raises(ValueError): D.owns_fence(engine, command)


def test_started_or_replayed_request_is_not_fresh_authority(monkeypatch):
    command = request(); engine, pending = retained(command)
    monkeypatch.setattr(A, 'prepared', Mock(return_value=True))
    pending['started'] = True
    with pytest.raises(ValueError): D.owns_fence(engine, command)
    pending['started'] = False; pending['result']['replayed'] = True
    with pytest.raises(ValueError): D.owns_fence(engine, command)
