"""Original neutral hair recipe; names describe colour intent, not commercial RGB."""
from copy import deepcopy
import math

VERSION = 1
OPERATION = 'lnx.hair_colour.v1'
STAGE = 'hair_colour'
CONTROL_IDS = {
    'colour': 'LNX-REF-PC-32472-C-281e093d26',
    'gloss': 'LNX-REF-PC-32472-C-29852ec2fd',
}
# Order is the Rust ABI's style index. Values/formula/ranges are our originals.
STYLES = (
    ('honey_tea_brown', '蜜茶棕'), ('chestnut_brown', '栗棕'),
    ('sunset_orange', '落日橘'), ('cool_tea_brown', '冷茶棕'),
    ('bitter_flax', '苦亚麻'), ('natural_black', '自然黑'),
    ('rose_purple', '玫瑰紫'), ('blue_black', '蓝黑'),
    ('iris_blue_purple', '鸢尾蓝紫'), ('raspberry_pink_brown', '树莓粉棕'),
    ('maple_red', '枫叶红'), ('moss_green', '苔绿'), ('pale_wisteria_pink', '薄藤粉'),
)
STYLE_IDS = tuple(row[0] for row in STYLES)


def neutral():
    return {'version': VERSION, 'style': 'honey_tea_brown', 'strength': 0., 'gloss': 0.}


def check(value):
    if value is None: return neutral()
    if type(value) is not dict or set(value) != set(neutral()) or type(value['version']) is not int or value['version'] != VERSION:
        raise ValueError('Unsupported hair colour recipe')
    if value['style'] not in STYLE_IDS: raise ValueError('Unknown original hair colour intent')
    out = deepcopy(value)
    for key in ('strength', 'gloss'):
        if type(value[key]) not in (int, float) or not math.isfinite(value[key]) or not 0 <= value[key] <= 1:
            raise ValueError('Hair amounts use the original finite 0–1 scale')
        out[key] = float(value[key])
    return out


def active(value):
    r = check(value)
    return r['strength'] > 0 or r['gloss'] > 0


def transferable(value):
    """Only scalar recipe intent can inherit; never instance-support/recovery assets."""
    return check(value)
