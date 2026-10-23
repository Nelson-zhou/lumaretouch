"""PC32473 portable two-control intent. Limits are LOCAL implementation policy.

Relinking never overwrites differing left/right values. It only changes the next
edit's propagation. Anatomical left/right, never screen/list-position identity.
"""
from copy import deepcopy
import math
VERSION=1
KEYS=('square','width')
SIDES=('left','right')
IDS={'square':'LNX-REF-PC-32473-C-1b5aae1f25','width':'LNX-REF-PC-32473-C-57c31b17e1'}
OPERATION_ID='lnx.shoulder_shape.v1'


def neutral():
    return {'version':VERSION, **{key:{'linked':True,'left':0.,'right':0.} for key in KEYS}}


def check(value):
    if type(value) is not dict or set(value)!={'version',*KEYS} or type(value['version']) is not int or value['version']!=VERSION: raise ValueError('Invalid shoulder recipe version/fields')
    for key in KEYS:
        item=value[key]
        if type(item) is not dict or set(item)!={'linked',*SIDES} or type(item['linked']) is not bool: raise ValueError('Shoulder bilateral state must be explicit')
        for side in SIDES:
            n=item[side]; low=0 if key=='square' else -1
            if type(n) not in (int,float) or not math.isfinite(n) or not low<=n<=1: raise ValueError('Shoulder amount is outside the local implementation range')
    return deepcopy(value)


def adjust(value,key,side,amount):
    out=check(value)
    if key not in KEYS or side not in SIDES: raise ValueError('Unknown shoulder control/side')
    for target in SIDES if out[key]['linked'] else (side,): out[key][target]=amount
    return check(out)


def link(value,key,linked):
    out=check(value)
    if key not in KEYS or type(linked) is not bool: raise ValueError('Invalid shoulder link intent')
    out[key]['linked']=linked
    return out


def active(value):
    value=check(value)
    return any(value[key][side]!=0 for key in KEYS for side in SIDES)


def vector(value):
    value=check(value)
    return [value[key][side] for key in KEYS for side in SIDES]


def portable(value):
    return check(value)  # No BodyRef, person, points, model, field or recovery travels.
