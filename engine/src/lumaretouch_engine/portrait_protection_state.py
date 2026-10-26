"""P0 single-face bounded correction recipe. Authored source contract, UNRUN.

Frozen analysis is actual retained evidence, not a new classifier. Dark marks
are conservatively vetoed; no scar/tattoo/identity-recognition claim is made.
"""
from copy import deepcopy
import base64
import hashlib
import math
import zlib

KEY = '_portrait_protection'
VERSION = 'bounded-small-outlier-v1'
CONTROL_KEYS = {'enabled', 'strength', 'protect_identity_marks', 'analysis_enabled',
                'overlay_visible', 'feather', 'protected_regions'}
MAX_MASK_SIDE = 256


def controls(value=None):
    default = dict(enabled=False, strength=0.0, protect_identity_marks=True,
                   analysis_enabled=False, overlay_visible=False, feather=0,
                   protected_regions=[])
    if value is None: return default
    if type(value) is not dict or set(value) != CONTROL_KEYS:
        raise ValueError('Portrait protection requires exact versioned controls')
    for key in ('enabled', 'protect_identity_marks', 'analysis_enabled', 'overlay_visible'):
        if type(value[key]) is not bool: raise ValueError(key + ' must be boolean')
    if type(value['strength']) not in (int, float) or not math.isfinite(value['strength']) or not 0 <= value['strength'] <= 1:
        raise ValueError('Blemish strength must be finite in [0,1]')
    if type(value['feather']) is not int or not 0 <= value['feather'] <= 256:
        raise ValueError('Protection feather must be integer source pixels in [0,256]')
    regions = value['protected_regions']
    if type(regions) is not list or len(regions) > 64: raise ValueError('At most 64 explicit protected regions')
    for box in regions:
        if (type(box) is not list or len(box) != 4 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0 <= v <= 1 for v in box)
                or not box[0] < box[2] or not box[1] < box[3]):
            raise ValueError('Protected regions need normalized source [left,top,right,bottom]')
    return deepcopy({**value, 'strength': float(value['strength'])})


def neutral():
    return {'version': VERSION, 'controls': controls(), 'source': None, 'evidence': None}


def _digest(value):
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Portrait evidence needs an exact SHA256')
    return value


def decode_mask(evidence):
    import numpy as np
    width, height = evidence['mask_size']
    encoded = evidence['mask']
    if type(encoded) is not str or len(encoded) > 400000: raise ValueError('Portrait semantic evidence exceeds bound')
    packed = base64.b64decode(encoded, validate=True)
    decoder = zlib.decompressobj()
    raw = decoder.decompress(packed, width*height*4+1)
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or len(raw) != width*height*4:
        raise ValueError('Malformed or excessive portrait semantic evidence')
    if hashlib.sha256(raw).hexdigest() != evidence['mask_sha256']: raise ValueError('Portrait semantic digest mismatch')
    mask = np.frombuffer(raw, dtype='<f4').reshape(height,width)
    if not np.isfinite(mask).all() or np.any((mask<0)|(mask>1)): raise ValueError('Invalid portrait semantic confidence')
    return mask


def check(value=None):
    if value is None: return neutral()
    if type(value) is not dict or set(value) != {'version','controls','source','evidence'} or value['version'] != VERSION:
        raise ValueError('Unsupported portrait protection recipe/version')
    result = deepcopy(value); result['controls'] = controls(value['controls'])
    source, evidence = value['source'], value['evidence']
    if (source is None) != (evidence is None): raise ValueError('Portrait source/evidence must be bound together')
    if source is None:
        if needs_analysis(result): raise ValueError('Active portrait controls require frozen source analysis')
        return result
    if type(source) is not dict or set(source) != {'sha256','width','height'}: raise ValueError('Invalid portrait source binding')
    _digest(source['sha256'])
    if any(type(source[k]) is not int or not 1 <= source[k] <= 65536 for k in ('width','height')): raise ValueError('Invalid portrait source extent')
    keys = {'face_instance_id','backend','num_faces','landmarks','landmark_sha256','semantic_model_sha256','detector_model_sha256','mask_size','mask','mask_sha256'}
    if type(evidence) is not dict or set(evidence) != keys or evidence['backend'] != 'mediapipe' or type(evidence['num_faces']) is not int or evidence['num_faces'] != 1:
        raise ValueError('P0 requires exactly one actually measured face')
    if evidence['face_instance_id'] is not None:
        from .people_state import token
        token(evidence['face_instance_id'])
    for key in ('landmark_sha256','semantic_model_sha256','detector_model_sha256','mask_sha256'): _digest(evidence[key])
    size=evidence['mask_size']
    if type(size) is not list or len(size)!=2 or any(type(n) is not int or not 1<=n<=MAX_MASK_SIDE for n in size): raise ValueError('Invalid bounded semantic grid')
    import numpy as np
    lm=evidence['landmarks']
    if type(lm) is not list or len(lm)!=478 or any(type(row) is not list or len(row)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>2 for v in row) for row in lm): raise ValueError('Invalid measured face landmarks')
    arr=np.asarray(lm,dtype='<f4')
    if hashlib.sha256(arr.tobytes()).hexdigest()!=evidence['landmark_sha256']: raise ValueError('Portrait landmark digest mismatch')
    decode_mask(evidence)
    return result


def needs_analysis(value):
    c=value['controls']
    return c['analysis_enabled'] or (c['enabled'] and c['strength'] != 0)


def active(value=None):
    c=check(value)['controls']
    return c['enabled'] and c['strength'] != 0


def capture(pc, source, desired, *, face_instance_id=None):
    """Freeze one real observation; no synthetic, largest-face or merged-skin fallback."""
    import cv2
    import numpy as np
    c=controls(desired)
    if (pc is None or pc.backend != 'mediapipe' or pc.num_faces != 1 or pc.detection_limit_reached
            or len(pc.all_landmarks or [pc.landmarks]) != 1):
        raise ValueError('P0 portrait protection requires current exact-one-face MediaPipe analysis')
    # face_skin is the explicit six-class observation, never merged body skin.
    mask=pc.masks.get('face_skin')
    if mask is None: raise ValueError('Actual face_skin semantic evidence unavailable; no whole-skin substitute')
    mask=np.asarray(mask,dtype=np.float32)
    if mask.ndim!=2 or not np.isfinite(mask).all() or np.any((mask<0)|(mask>1)): raise ValueError('Invalid actual face-skin confidence')
    h,w=mask.shape; scale=min(1.,MAX_MASK_SIDE/max(h,w)); size=(max(1,round(w*scale)),max(1,round(h*scale)))
    mask=np.ascontiguousarray(cv2.resize(mask,size,interpolation=cv2.INTER_AREA),dtype='<f4')
    raw=mask.tobytes(); lm=np.ascontiguousarray(pc.landmarks,dtype='<f4')
    return check({'version':VERSION,'controls':c,'source':deepcopy(source),'evidence':{
        'face_instance_id':face_instance_id,'backend':'mediapipe','num_faces':1,'landmarks':lm.tolist(),
        'landmark_sha256':hashlib.sha256(lm.tobytes()).hexdigest(),
        'semantic_model_sha256':pc.semantic_model_sha256,'detector_model_sha256':pc.detector_model_sha256,
        'mask_size':list(size),'mask':base64.b64encode(zlib.compress(raw)).decode('ascii'),
        'mask_sha256':hashlib.sha256(raw).hexdigest()}})


def validate_records(value):
    if type(value) is dict:
        if KEY in value: check(value[KEY])
        for child in value.values(): validate_records(child)
    elif type(value) is list:
        for child in value: validate_records(child)


def check_owner(recipe, ledger, graph=None, *, source_sha256=None):
    """Canonical persisted owner admission; no spatial-overlap guess.

    Legacy disabled/added ledger ambiguity refuses the whole new P0 operation.
    Canonical graph ownership uses a stable instance plus exact measured digest.
    """
    if type(ledger) is not dict or set(ledger)!={'disabled','added'}:
        raise ValueError('Portrait protection requires the persisted manual-face ledger')
    if any(type(ledger[k]) is not list for k in ('disabled','added')):
        raise ValueError('Malformed portrait manual-face ledger')
    if ledger['disabled'] or ledger['added']:
        raise ValueError('P0 portrait protection suspended: manual disabled/added face ledger requires explicit review')
    source=source_sha256 if recipe is None else recipe['source']['sha256']
    evidence=None if recipe is None else recipe['evidence']
    rows=[]
    if graph is not None:
        from .people_state import check as check_graph
        graph=check_graph(graph)
        rows=[face for face in graph['faces'].values() if face['asset_sha256']==source]
        if any(row['asset_sha256']==source for row in graph['unresolved_legacy']):
            raise ValueError('Unresolved canonical portrait owner; no P0 fallback')
    if not rows:
        if evidence is not None and evidence['face_instance_id'] is not None:
            raise ValueError('Frozen portrait instance is missing from the current document graph')
        return None
    if len(rows)!=1 or not rows[0]['enabled'] or rows[0]['manual']:
        raise ValueError('P0 requires one enabled automatic canonical face, never a disabled/manual/ambiguous owner')
    face=rows[0]
    if evidence is not None:
        if evidence['face_instance_id'] is not None and face['face_instance_id']!=evidence['face_instance_id']:
            raise ValueError('Frozen portrait instance was replaced')
        if face['evidence']['landmark_digest']!=evidence['landmark_sha256']:
            raise ValueError('Canonical face analysis differs from the frozen portrait owner')
    return face['face_instance_id']
