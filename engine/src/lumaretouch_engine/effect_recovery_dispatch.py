# SPDX-License-Identifier: GPL-3.0-or-later
"""Internal prepared authority for recovery-only shared-source publication.

Client flags never suppress the normal document fence/history owner. The alias
ledger owns its complete affected-set fences only after the retained candidate,
source proofs, immutable images and acknowledgments have been checked again.
AUTHORED / UNRUN.
"""
from hashlib import sha256
import json


def owns_fence(engine, command):
    if command.get('cmd') != 'effect_recovery':
        return False
    controller = engine.__dict__.get('_effect_recovery_owner')
    pending = getattr(controller, 'pending', None)
    if type(pending) is not dict or 'recovery_alias' not in pending:
        return False
    from .source_patch_controller import PROOF_KEYS
    result = pending.get('result')
    if (command.get('action') != 'apply' or type(result) is not dict
            or result.get('protocol') != 2 or pending.get('started') is not False
            or result.get('replayed') is True
            or any(result.get(key) != command.get(key) for key in
                   ('request_id', 'preview_id', *PROOF_KEYS))):
        raise ValueError('Prepared recovery alias request identity changed before dispatch')
    digest = sha256(json.dumps(command, sort_keys=True, allow_nan=False).encode()).hexdigest()
    if pending.get('digest') != digest:
        raise ValueError('Prepared recovery alias command changed before dispatch')
    from .eye_bag_recovery_alias_controller import prepared
    if prepared(engine, pending) is not True:
        raise ValueError('Recovery alias publication lacks complete prepared review authority')
    return True
