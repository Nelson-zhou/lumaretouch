"""Distinct, source-addressed BodyRef and all 33 measured pose outputs.

Coordinates are unaltered normalized canonical-source coordinates. Outside-frame
and occluded observations are retained as evidence, never clamped or repaired.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math
import re
import uuid

BACKEND = 'mediapipe-tasks-pose-landmarker'
ORIENTATION = 'exif_normalized_once'
POINT_NAMES = ('nose','left_eye_inner','left_eye','left_eye_outer','right_eye_inner','right_eye','right_eye_outer','left_ear','right_ear','mouth_left','mouth_right','left_shoulder','right_shoulder','left_elbow','right_elbow','left_wrist','right_wrist','left_pinky','right_pinky','left_index','right_index','left_thumb','right_thumb','left_hip','right_hip','left_knee','right_knee','left_ankle','right_ankle','left_heel','right_heel','left_foot_index','right_foot_index')
ANCHORS = (0,7,8,11,12,13,14,23,24)


def digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None: raise ValueError('Expected actual SHA-256')
    return value


def token(value):
    if type(value) is not str or re.fullmatch('[A-Za-z0-9_.:-]{1,128}',value) is None: raise ValueError('Invalid body identifier')
    return value


def revision(value):
    if type(value) is not int or not 0 <= value < 2**63: raise ValueError('Invalid body revision')
    return value


def content_digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',',':'),allow_nan=False).encode()).hexdigest()


def source(value):
    if type(value) is not dict or set(value) != {'sha256','width','height','orientation'}: raise ValueError('Body source frame is incomplete')
    digest(value['sha256'])
    for key in ('width','height'):
        if type(value[key]) is not int or not 2 <= value[key] <= 1000000: raise ValueError('Invalid body source dimensions')
    if value['orientation'] != ORIENTATION: raise ValueError('Body pose requires EXIF normalization exactly once')
    return deepcopy(value)


def ref(value):
    if type(value) is not dict or set(value) != {'asset_sha256','body_instance_id','analysis_revision'}: raise ValueError('A BodyRef is not a FaceRef')
    digest(value['asset_sha256']); token(value['body_instance_id']); revision(value['analysis_revision'])
    return deepcopy(value)


def points(value):
    if type(value) is not list or len(value) != 33: raise ValueError('Exactly 33 real body landmarks required')
    for i,row in enumerate(value):
        if type(row) is not dict or set(row) != {'index','x','y','z','visibility','presence'} or type(row['index']) is not int or row['index'] != i:
            raise ValueError('Body landmark index/schema mismatch')
        if any(type(row[k]) not in (int,float) or not math.isfinite(row[k]) for k in ('x','y','z','visibility','presence')): raise ValueError('Body output must contain actual finite values including visibility/presence')
        if any(not 0 <= row[k] <= 1 for k in ('visibility','presence')): raise ValueError('Visibility/presence must be backend probabilities')
    return deepcopy(value)


def check(record):
    if type(record) is not dict or set(record) != {'version','body_ref','source','backend','backend_version','backend_code_sha256','model_id','model_sha256','input_rgb_sha256','input_dimensions','points','points_sha256'} or type(record['version']) is not int or record['version'] != 1:
        raise ValueError('Invalid measured body record')
    r = ref(record['body_ref']); s = source(record['source'])
    if r['asset_sha256'] != s['sha256'] or record['backend'] != BACKEND: raise ValueError('Body source/backend mismatch')
    token(record['backend_version']); token(record['model_id'])
    for key in ('backend_code_sha256','model_sha256','input_rgb_sha256','points_sha256'): digest(record[key])
    dims=record['input_dimensions']
    if type(dims) is not list or len(dims)!=2 or any(type(n) is not int or n<2 or n>1000000 for n in dims): raise ValueError('Actual analysis input dimensions required')
    p = points(record['points'])
    if content_digest(p) != record['points_sha256']: raise ValueError('Retained pose points changed')
    return deepcopy(record)


def create(*, source_frame, values, backend_version, backend_code_sha256, model_id, model_sha256, input_rgb_sha256, input_dimensions):
    s = source(source_frame); p = points(values)
    return check({'version':1,'body_ref':{'asset_sha256':s['sha256'],'body_instance_id':'body:'+uuid.uuid4().hex,'analysis_revision':0},'source':s,'backend':BACKEND,'backend_version':backend_version,'backend_code_sha256':backend_code_sha256,'model_id':model_id,'model_sha256':model_sha256,'input_rgb_sha256':input_rgb_sha256,'input_dimensions':list(input_dimensions),'points':p,'points_sha256':content_digest(p)})


def explicit_reanalysis(previous, measured, *, expected_ref, user_confirmed):
    old=check(previous); new=check(measured)
    if user_confirmed is not True or ref(expected_ref)!=old['body_ref'] or old['source']!=new['source']:
        raise ValueError('Reanalysis needs explicit current BodyRef review on the same source')
    new['body_ref']={**old['body_ref'],'analysis_revision':old['body_ref']['analysis_revision']+1}
    return check(new)  # Any old visibility review/association is now stale.


def whole_source_shape(frame, shape):
    """Validate full canvas or the decoder's ALIGN=8 proxy rounding.

    Shape alone does not prove pixel provenance. Callers must supply their
    immutable canonical source, never a cropped/retouched/display buffer.
    A single common scale must be able to produce both downward-aligned sides.
    """
    source_frame=source(frame)
    if type(shape) not in (tuple,list) or len(shape)!=2 or any(type(n) is not int or n<2 for n in shape):raise ValueError('Invalid whole-source body frame')
    h,w=shape;sw,sh=source_frame['width'],source_frame['height']
    if (w,h)==(sw,sh):return
    if w>sw or h>sh:raise ValueError('Body proxy cannot enlarge the original frame')
    if w%8 or h%8:raise ValueError('Body proxy must use canonical decoder ALIGN=8 dimensions')
    # Integer cross-products avoid a floating-point edge relaxing the interval.
    if w*sh >= (h+8)*sw or h*sw >= (w+8)*sh:raise ValueError('Body proxy does not preserve the whole-source aspect within decoder alignment')
