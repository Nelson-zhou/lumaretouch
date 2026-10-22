"""PC-32464 eight-region intent, shared by preview, project, preset and export.

The link flag is metadata, never an effect strength. Existing enhance records
may omit new fields; an explicitly invalid field is not silently reset.
"""
import math

REGIONS = ('forehead', 'glabellar', 'eye_area', 'nose', 'nasolabial_left',
           'nasolabial_right', 'cheek', 'marionette', 'mouth_surround')
KEYS = tuple('wrinkle_' + key for key in REGIONS)
LINK_KEY = 'wrinkle_nasolabial_unlocked'
INTENT_KEYS = (*KEYS, LINK_KEY)
CONTROL_IDS = dict(zip(('family', 'forehead', 'glabellar', 'eye_area', 'nose',
                        'nasolabial', 'cheek', 'marionette', 'mouth_surround'),
                       ('d9e8e03577', '294d9a2188', '3e1a0bb386', '24f710ab2b',
                        'fcd0c13b5f', '942d0bfb79', 'f28262041d', '5aa8868572', '22b2d6e2a0')))


def check(amounts):
    if type(amounts) is not dict:
        raise ValueError('面部祛纹参数必须是对象')
    out = {}
    for key in INTENT_KEYS:
        value = amounts.get(key, 0)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f'{key} 必须是 [0,1] 有限数值')
        if key == LINK_KEY and value not in (0, 1):
            raise ValueError('法令纹解锁状态只能为 0 或 1，不是连续强度')
        out[key] = float(value)
    return out


def active(amounts):
    return any(check(amounts)[key] > 0 for key in KEYS)


def active_enhance(amounts):
    """Use instead of any(amounts.values()) in neutral/eligibility gates."""
    check(amounts)
    return any(value != 0 for key, value in amounts.items() if key != LINK_KEY)


def patch(amounts, updates):
    """Explicit linked moves carry both sides. Relinking itself changes no pixels."""
    if type(updates) is not dict or set(updates) - set(INTENT_KEYS):
        raise ValueError('面部祛纹修改包含未知字段')
    return check({**check(amounts), **updates})


def preset(amounts):
    # Numeric intent only. Never copy landmarks, semantic masks, recovery owner,
    # cached deltas or region eligibility to a different photograph/person.
    return check(amounts)
