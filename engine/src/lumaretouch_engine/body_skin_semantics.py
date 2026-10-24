"""Transport the measured whole-photo body-skin class, never body ownership.

The existing six-class producer supplies an editing weight in ``body_skin``.
This module only validates and copies that actual named plane. Merged ``skin``,
face skin, pose bounds and person-instance masks are not substitutes. A consumer
still needs an explicitly reviewed BodyRef/person association and manual scope;
carrying this observation beside a face does not establish any such association.

Producer dimensions name the existing producer's interpolated input/output
grid, not the model's native confidence grid. Resampling for export preserves
that observation and does not claim newly inferred full-resolution edges.
"""
from copy import deepcopy
import re
import numpy as np

FIELDS = frozenset(('body_skin', 'body_skin_observation'))
CONTRACT = 'mediapipe-body-skin-edit-weight-v1'


def body_skin_support(pc):
    """Own a readonly copy of actual body-skin support, or report it missing."""
    if (pc is None or getattr(pc, 'backend', None) != 'mediapipe'
            or not re.fullmatch('[0-9a-f]{64}', str(getattr(pc, 'semantic_model_sha256', None)))
            or not re.fullmatch('[0-9a-f]{64}', str(getattr(pc, 'detector_model_sha256', None)))):
        return None
    raw = (getattr(pc, 'masks', None) or {}).get('body_skin')
    if raw is None:
        return None
    value = np.asarray(raw, dtype=np.float32)
    if (value.ndim != 2 or not value.size or not np.isfinite(value).all()
            or np.any((value < 0) | (value > 1))):
        raise ValueError('Body-skin semantic editing weight is invalid')
    value = np.array(value, dtype=np.float32, order='C', copy=True)
    value.setflags(write=False)
    return value


def analysis_fields(pc, asset_sha256, source_dimensions):
    """Called by the existing source-bound original/derived analysis owner."""
    from . import people_state as S
    S.digest(asset_sha256)
    width, height = source_dimensions
    if any(type(n) is not int or not 1 <= n <= 1000000 for n in (width, height)):
        raise ValueError('Body-skin support needs canonical source dimensions')
    value = body_skin_support(pc)
    if value is None:
        return {'body_skin': None, 'body_skin_observation': None}
    h, w = value.shape
    if any(not 1 <= n <= 1000000 for n in (w, h)):
        raise ValueError('Body-skin producer observation extent is invalid')
    proof = getattr(pc, 'input_source_binding', None)
    if proof is not None:
        # The derived-source owner verifies the exact inference input bytes.
        # Keep its source/grid fence here; never relabel original-file masks.
        if (type(proof) is not dict or
                {key: proof.get(key) for key in ('sha256', 'width', 'height')} !=
                {'sha256': asset_sha256, 'width': width, 'height': height} or
                (proof.get('proxy_height'), proof.get('proxy_width')) != (h, w)):
            raise ValueError('Body-skin support belongs to another derived source or observation grid')
    return {'body_skin': value, 'body_skin_observation': {
        'contract': CONTRACT, 'source_sha256': asset_sha256,
        'semantic_model_sha256': pc.semantic_model_sha256,
        'detector_model_sha256': pc.detector_model_sha256,
        'producer_width': w, 'producer_height': h}}


def check_analysis_fields(analysis, shape=None):
    """Legacy rows may omit the pair; consumers must require nonmissing support.

    This checks transport evidence only, never a person/body association. The
    optional render shape may differ from the retained producer grid after
    semantic resampling, without rewriting the original observation.
    """
    if not FIELDS.intersection(analysis):
        return None
    if not FIELDS.issubset(analysis):
        raise ValueError('Body-skin observation and support must travel together')
    value, observation = analysis['body_skin'], analysis['body_skin_observation']
    if value is None:
        if observation is not None:
            raise ValueError('Missing body-skin support cannot claim an observation')
        return None
    if (type(value) is not np.ndarray or value.dtype != np.float32 or value.ndim != 2
            or not value.size or not np.isfinite(value).all() or np.any((value < 0) | (value > 1))):
        raise ValueError('Frozen body-skin support is not a finite float32 editing weight')
    if shape is not None and value.shape != tuple(shape):
        raise ValueError('Body-skin support differs from the current source render grid')
    return check_observation(observation, analysis['face_ref'], analysis['evidence'])


def check_observation(observation, face_ref, evidence):
    """Check immutable observation JSON without inventing a semantic array.

    Historical review assets use this structural contract. Current rendering
    additionally calls check_analysis_fields with the actual source-bound plane.
    Neither function establishes body/person ownership.
    """
    keys = {'contract', 'source_sha256', 'semantic_model_sha256',
            'detector_model_sha256', 'producer_width', 'producer_height'}
    if type(observation) is not dict or set(observation) != keys or observation['contract'] != CONTRACT:
        raise ValueError('Body-skin support lacks its producer observation contract')
    from . import people_state as S
    ref = S.check_ref(face_ref)
    evidence = S.check_evidence(evidence)
    if (evidence['status'] != 'verified' or evidence['backend'] != 'mediapipe'
            or observation['source_sha256'] != ref['asset_sha256']
            or observation['semantic_model_sha256'] != evidence['semantic_model_sha256']
            or observation['detector_model_sha256'] != evidence['detector_model_sha256']):
        raise ValueError('Body-skin observation source/models differ from retained analysis evidence')
    S.digest(observation['semantic_model_sha256'])
    S.digest(observation['detector_model_sha256'])
    if any(type(observation[k]) is not int or not 1 <= observation[k] <= 1000000
           for k in ('producer_width', 'producer_height')):
        raise ValueError('Body-skin producer observation extent is invalid')
    return deepcopy(observation)
