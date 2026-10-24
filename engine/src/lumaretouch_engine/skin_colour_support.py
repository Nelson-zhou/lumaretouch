"""Transport actual face-skin class support, never merged skin or an instance mask.

MediaPipe's existing producer validates all six confidence channels and converts
the face-skin probability to an editing weight. These helpers only validate/copy
that named output; they do not run a model or discover a person's identity.
The recorded producer grid is the inference input/output grid after the existing
producer's interpolation, NOT the network's native confidence resolution.
Export may resample this semantic observation, but must rebuild anatomical scope
and the colour effect from its full-resolution source rather than enlarge either.
"""
from copy import deepcopy
import re
import numpy as np

FIELDS = frozenset(('face_skin', 'face_skin_observation'))
CONTRACT = 'mediapipe-face-skin-edit-weight-v1'


def face_skin_support(pc):
    """Return an owned readonly face-skin weight, or genuinely missing support.

    A merged ``skin`` plane is never a fallback. This remains a whole-photo
    semantic class until the consumer intersects exact retained face geometry.
    """
    if (pc is None or getattr(pc, 'backend', None) != 'mediapipe'
            or not re.fullmatch('[0-9a-f]{64}', str(getattr(pc, 'semantic_model_sha256', None)))
            or not re.fullmatch('[0-9a-f]{64}', str(getattr(pc, 'detector_model_sha256', None)))):
        return None
    raw = (getattr(pc, 'masks', None) or {}).get('face_skin')
    if raw is None:
        return None
    value = np.asarray(raw, dtype=np.float32)
    if value.ndim != 2 or not value.size or not np.isfinite(value).all() or np.any((value < 0) | (value > 1)):
        raise ValueError('Face-skin semantic editing weight is invalid')
    value = np.array(value, dtype=np.float32, order='C', copy=True)
    value.setflags(write=False)
    return value


def analysis_fields(pc, asset_sha256, source_dimensions):
    """Called only by the existing source-bound original/derived analysis owner."""
    from . import people_state as S
    S.digest(asset_sha256)
    width, height = source_dimensions
    if any(type(n) is not int or not 1 <= n <= 1000000 for n in (width, height)):
        raise ValueError('Face-skin support needs canonical source dimensions')
    value = face_skin_support(pc)
    if value is None:
        return {'face_skin': None, 'face_skin_observation': None}
    h, w = value.shape
    proof = getattr(pc, 'input_source_binding', None)
    if proof is not None:
        # The live derived-source owner already verifies the exact proxy bytes.
        # Retain its source/grid fence here too; never rebind to original pixels.
        if (type(proof) is not dict or
                {key: proof.get(key) for key in ('sha256', 'width', 'height')} !=
                {'sha256': asset_sha256, 'width': width, 'height': height} or
                (proof.get('proxy_height'), proof.get('proxy_width')) != (h, w)):
            raise ValueError('Face-skin support belongs to another derived source or observation grid')
    return {'face_skin': value, 'face_skin_observation': {
        'contract': CONTRACT, 'source_sha256': asset_sha256,
        'semantic_model_sha256': pc.semantic_model_sha256,
        'producer_width': w, 'producer_height': h}}


def check_analysis_fields(analysis, shape=None):
    """Legacy rows may omit both fields; active consumers must require support.

    Producer dimensions deliberately remain unchanged after semantic resampling.
    The current array shape is a render grid, not a fresh inference claim.
    """
    if not FIELDS.intersection(analysis):
        return None
    if not FIELDS.issubset(analysis):
        raise ValueError('Face-skin observation and support must travel together')
    value, observation = analysis['face_skin'], analysis['face_skin_observation']
    if value is None:
        if observation is not None:
            raise ValueError('Missing face-skin support cannot claim an observation')
        return None
    if (type(value) is not np.ndarray or value.dtype != np.float32 or value.ndim != 2
            or not value.size or not np.isfinite(value).all() or np.any((value < 0) | (value > 1))):
        raise ValueError('Frozen face-skin support is not a finite float32 editing weight')
    if shape is not None and value.shape != tuple(shape):
        raise ValueError('Face-skin support differs from the current source render grid')
    keys = {'contract', 'source_sha256', 'semantic_model_sha256', 'producer_width', 'producer_height'}
    if type(observation) is not dict or set(observation) != keys or observation['contract'] != CONTRACT:
        raise ValueError('Face-skin support lacks its producer observation contract')
    from . import people_state as S
    ref = S.check_ref(analysis['face_ref'])
    evidence = S.check_evidence(analysis['evidence'])
    if (evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe'
            or observation['source_sha256'] != ref['asset_sha256']
            or observation['semantic_model_sha256'] != evidence['semantic_model_sha256']):
        raise ValueError('Face-skin observation source/model differs from retained face evidence')
    S.digest(observation['semantic_model_sha256'])
    if any(type(observation[k]) is not int or not 1 <= observation[k] <= 1000000
           for k in ('producer_width', 'producer_height')):
        raise ValueError('Face-skin producer observation extent is invalid')
    return deepcopy(observation)
