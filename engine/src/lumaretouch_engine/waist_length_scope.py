# SPDX-License-Identifier: GPL-3.0-or-later
"""Scalar-only waist transfer into an independently reviewed target. AUTHORED / UNRUN.

Only version/amount travel. One enabled target body, current operation-specific
support and explicit own-face consent are mandatory, including for amount zero.
Waist support includes four independent manual source waist markers; neither
torso support nor shoulder/hip observations may manufacture those endpoints.
"""
import sys
from . import body_pose_project as D
from . import waist_length_project as P, waist_length_state as S
from .body_scalar_scope import BodyScalarScope

OP = S.OPERATION_ID
FIELDS = (D.KEY,)
_SCOPE = BodyScalarScope(project=P, state=S, api=sys.modules[__name__], label='腰部长度',
    support_requirement='四个人工腰部端点、完整上躯干、头发、双臂双手和背景过渡范围',
    review_requirement='独立可见关节及四个人工腰部端点审核')

check_params = _SCOPE.check_params
target = _SCOPE.target
params_of = _SCOPE.params_of
install = _SCOPE.install
validate_target = _SCOPE.validate_target
bank_sha256 = _SCOPE.bank_sha256
undo_key = _SCOPE.undo_key
restore = _SCOPE.restore
