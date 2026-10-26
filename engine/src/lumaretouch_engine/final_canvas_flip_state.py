"""Independent strict two-boolean recipe. Missing legacy state is neutral."""
KEY = '_final_canvas_flip'
OP = 'lnx.final_canvas_flip.v1'
REASON = '翻转后的坐标捕获尚未接通；请先关闭水平/垂直翻转再使用此工具。已有编辑会保留并正常渲染。'

def neutral():
    return {'horizontal': False, 'vertical': False}

def check(value):
    if type(value) is not dict or set(value) != {'horizontal', 'vertical'} or any(type(v) is not bool for v in value.values()):
        raise ValueError('Final canvas flip requires exactly horizontal/vertical JSON booleans')
    return dict(value)

def from_state(state):
    return check(state[KEY]) if KEY in state else neutral()

def active(value):
    value = neutral() if value is None else check(value)
    return value['horizontal'] or value['vertical']

def require_processing_capture(engine):
    if active(getattr(engine, KEY, None)):
        raise ValueError(REASON)

def require_capture_state(state):
    if active(from_state(state)):
        raise ValueError('创意素材捕获暂不支持非中性最终画布翻转；请先关闭翻转，未烘焙或丢弃任何编辑')
