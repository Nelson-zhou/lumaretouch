# SPDX-License-Identifier: GPL-3.0-or-later
"""Scalar-only torso transfer into an independently reviewed target. AUTHORED / UNRUN.

Only version/amount travel. One enabled target body, current operation-specific
support and explicit own-face consent are mandatory, including for amount zero.
"""
import sys
from . import body_pose_project as D
from . import torso_length_project as P, torso_length_state as S
from .body_scalar_scope import BodyScalarScope

OP = S.OPERATION_ID
FIELDS = (D.KEY,)
_SCOPE = BodyScalarScope(project=P, state=S, api=sys.modules[__name__], label='上半身长短',
    support_requirement='完整头发、双臂双手和背景过渡范围', review_requirement='独立可见关节审核')

check_params = _SCOPE.check_params
target = _SCOPE.target
params_of = _SCOPE.params_of
install = _SCOPE.install
validate_target = _SCOPE.validate_target
bank_sha256 = _SCOPE.bank_sha256
undo_key = _SCOPE.undo_key
restore = _SCOPE.restore
