# SPDX-License-Identifier: GPL-3.0-or-later
"""Authoritative host family routing, distinct from numeric chain ordering.

Keep presentation/publication and replay identity in one place. Unknown request
operations are never reinterpreted as shoulder edits.
"""
FAMILIES=('shoulder_shape','leg_shape','arm_shape','waist_shape','leg_length','neck_shape')


def request_family(request):
    family=request.get('family_id')
    if family is not None:
        if family!='lnx.arm_shape.v1':raise ValueError('Unknown body request family')
        return 'arm_shape'
    operation=request.get('operation_id')
    if operation is None:return 'shoulder_shape'  # observation/association owner
    for name in ('shoulder_shape','leg_shape','waist_shape','leg_length','neck_shape'):
        if operation=='lnx.'+name+'.v1':return name
    raise ValueError('Unknown body request operation')


def presenter(name):
    from . import shoulder_shape_host,leg_shape_host,arm_shape_host,waist_shape_host,leg_length_host,neck_shape_host
    return dict(zip(FAMILIES,(shoulder_shape_host,leg_shape_host,arm_shape_host,waist_shape_host,leg_length_host,neck_shape_host)))[name]


def report(engine):
    if not engine._image_loaded or engine._doc_index<0:return {}
    result={}
    for name in FAMILIES:
        try:result[name]=engine._body_view(name)
        except (ValueError,RuntimeError,OSError,KeyError) as error:
            result[name]=None;result[name+'_error']=str(error)
    return result
