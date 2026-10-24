# SPDX-License-Identifier: GPL-3.0-or-later
"""Scalar-only complete-head transfer into an independently reviewed target. AUTHORED / UNRUN.

Only version/amount travel. One enabled target body, current operation-specific
support and explicit own-face consent are mandatory, including for amount zero.
Head support retains the target's own complete head/hair box, transition and
pivot. Neither pose points nor a face box may manufacture complete-head bounds.
"""
import sys
from . import body_pose_project as D
from . import head_size_project as P, head_size_state as S
from .body_scalar_scope import BodyScalarScope

OP = S.OPERATION_ID
FIELDS = (D.KEY,)
_SCOPE = BodyScalarScope(project=P, state=S, api=sys.modules[__name__], label='头部大小',
    support_requirement='独立手工完整头发范围、过渡和中心',
    review_requirement='独立完整头发范围、过渡、中心及当前本人面部审核')

check_params = _SCOPE.check_params
target = _SCOPE.target
params_of = _SCOPE.params_of
install = _SCOPE.install
validate_target = _SCOPE.validate_target
bank_sha256 = _SCOPE.bank_sha256
undo_key = _SCOPE.undo_key
restore = _SCOPE.restore
