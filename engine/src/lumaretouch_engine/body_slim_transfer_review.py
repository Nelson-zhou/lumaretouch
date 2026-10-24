# SPDX-License-Identifier: GPL-3.0-or-later
"""Target-owned full body-slim review ports. AUTHORED / UNRUN.

Only policy and identity selection differ; complete-source rendering, compact
proofs, exact acknowledgments and replay fences share one implementation.
"""
import sys
from . import body_slim_scope as SCOPE, body_slim_state as STATE
from .body_scalar_transfer_review import (BodyScalarReview, MAX_TARGETS, PREVIEW_EDGE,
    MAX_PNG_BYTES, MAX_BASE64, FIELDS, IDENTITY_FIELDS)


def _runtime():
    from . import body_slim_runtime
    return body_slim_runtime


_REVIEW = BodyScalarReview(scope=SCOPE, state=STATE, runtime=_runtime,
    api=sys.modules[__name__], name='body-slim', label='全身瘦身')

_hash = _REVIEW._hash
_size = _REVIEW._size
_context = _REVIEW._context
_image = _REVIEW._image
checked = _REVIEW.checked
rollback_record = _REVIEW.rollback_record
acknowledgments = _REVIEW.acknowledgments
_require_retained_people_candidate = _REVIEW._require_retained_people_candidate
_require_stable_live_people = _REVIEW._require_stable_live_people
_target_proof = _REVIEW._target_proof
_target_identity = _REVIEW._target_identity
history_identity = _REVIEW.history_identity
_identities = _REVIEW._identities
_geometry = _REVIEW._geometry
verify = _REVIEW.verify
_view = _REVIEW._view
prepare = _REVIEW.prepare
