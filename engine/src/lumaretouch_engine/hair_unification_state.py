# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent signed root/tip colour unification intent. AUTHORED / UNRUN."""
import math

VERSION = 1
OPERATION = OP = 'lnx.hair_unification.v1'
STAGE = KIND = 'hair_unification'
CONTROL_ID = 'LNX-REF-PC-32472-C-fb2fe59a22'
CONTROL_IDS = {'amount': CONTROL_ID}
KEYS = ('amount',)


def neutral():
    return {'version': VERSION, 'amount': 0.0}


def check(value):
    if value is None:
        return neutral()
    if (type(value) is not dict or set(value) != {'version', 'amount'}
            or type(value['version']) is not int or value['version'] != VERSION):
        raise ValueError('Unsupported hair unification recipe')
    amount = value['amount']
    if type(amount) not in (int, float):
        raise ValueError('Hair unification requires a finite amount in [-1,1]')
    try:
        amount = float(amount)
    except (OverflowError, ValueError) as error:
        raise ValueError('Hair unification amount is outside [-1,1]') from error
    if not math.isfinite(amount) or not -1 <= amount <= 1:
        raise ValueError('Hair unification amount is outside [-1,1]')
    return {'version': VERSION, 'amount': amount}


def active(value):
    return check(value)['amount'] != 0.0


def reference_side(value):
    amount = check(value)['amount']
    return 'tips' if amount < 0 else 'roots' if amount > 0 else None


def transferable(value):
    """Portable scalar intent only; target-owned samples never travel with it."""
    return check(value)
