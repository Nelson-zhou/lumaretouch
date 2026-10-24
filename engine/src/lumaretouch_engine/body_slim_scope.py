# SPDX-License-Identifier: GPL-3.0-or-later
"""Scalar-only whole-person width transfer into an independently reviewed target. AUTHORED / UNRUN.

Only version/amount travel. One enabled target body, current operation-specific
support and explicit own-face consent are mandatory, including for amount zero.
"""
import sys
from . import body_pose_project as D
from . import body_slim_project as P, body_slim_state as S
from .body_scalar_scope import BodyScalarScope

OP = S.OPERATION_ID
FIELDS = (D.KEY,)
_SCOPE = BodyScalarScope(project=P, state=S, api=sys.modules[__name__], label='全身瘦身',
    support_requirement='完整人物手工实测轮廓、背景过渡和轮廓间隙', review_requirement='独立全身轮廓、单人归属和当前本人面部审核')

check_params = _SCOPE.check_params
target = _SCOPE.target
params_of = _SCOPE.params_of
install = _SCOPE.install
validate_target = _SCOPE.validate_target
bank_sha256 = _SCOPE.bank_sha256
undo_key = _SCOPE.undo_key
restore = _SCOPE.restore
