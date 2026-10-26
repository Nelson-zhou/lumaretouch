# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline optional hand-landmark proposals, never automatic shape authority.

No network, package installation, body-pose prerequisite or synthetic fallback.
The document host must bind these results to its current immutable source and
retain the actual producer receipt; JSON supplied by a client is not a receipt.
"""
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
import math
import os
from pathlib import Path
import stat
import uuid

import numpy as np
from . import hand_shape_manifest as M


def model_root(root=None):
    return Path(root) if root is not None else Path(os.environ.get(
        'XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'lumaretouch/optional-models' / M.MODEL_ID


def _read_regular(path, limit, *, exact_size=None):
    """One bounded open/read; final-component symlinks cannot race the check."""
    path = Path(path)
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('Hand proposal asset/code path contains a symlink')
    if not hasattr(os, 'O_NOFOLLOW'):
        raise RuntimeError('Hand proposal regular-file verification requires O_NOFOLLOW')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError('Hand proposal asset/code must be a bounded regular file')
        if exact_size is not None and before.st_size != exact_size:
            raise ValueError('Hand model byte size differs from reviewed official pin')
        data = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
        if len(data) > limit or len(data) != before.st_size or (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('Hand proposal file changed during bounded verification')
    return data


def verified_model_bytes(root=None):
    """Verify precisely the buffer later passed to MediaPipe, not a second open."""
    data = _read_regular(model_root(root) / M.MODEL_FILENAME, M.MODEL_SIZE_BYTES,
                         exact_size=M.MODEL_SIZE_BYTES)
    if sha256(data).hexdigest() != M.MODEL_SHA256:
        raise ValueError('Hand model bytes differ from reviewed official SHA-256')
    return data


def status(root=None):
    """Offline integrity/readiness receipt; never imports the optional backend."""
    from .hand_shape_setup import model_status
    result = model_status(root)
    result.update(available=result['ready'], reason=result.get('error'),
                  inference_verified=False, limitations=list(M.LIMITATIONS),
                  model_sha256=M.MODEL_SHA256, model_bytes=M.MODEL_SIZE_BYTES,
                  pin_status=M.PIN_STATUS)
    if not result['available']:
        result['reason'] = (result['reason'] or '请在手部面板明确安装模型或重新检查 CPU 准备状态。') + (
            ' 手动轮廓支持仍可独立使用；基础 MediaPipe '+M.RUNTIME_VERSION+
            ' 须由已审核应用运行环境提供，不会自动安装或修改全局包。')
    result['setup'] = {'mode':'explicit-curated-install','automatic_install':False,
        'extension_id':M.EXTENSION_ID,'model_path':str(model_root(root)/M.MODEL_FILENAME),
        'runtime_requirements':M.RUNTIME_REQUIREMENTS,'runtime_version':M.RUNTIME_VERSION}
    return result


def _source(value):
    from .body_pose_evidence import source, ORIENTATION
    if type(value) is not dict or set(value) != {'sha256', 'width', 'height'}:
        raise ValueError('Hand proposal requires exact source hash and dimensions')
    checked = source({**value, 'orientation': ORIENTATION})
    return {key: checked[key] for key in ('sha256', 'width', 'height')}


def _categories(values):
    if len(values) > 8:
        raise ValueError('Hand backend category count exceeds proposal budget')
    output = []
    for item in values:
        score = float(item.score)
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('Hand backend returned invalid handedness score')
        index = item.index
        if index is not None and type(index) is not int:
            raise ValueError('Hand backend returned invalid category index')
        for label in (item.category_name, item.display_name):
            if label is not None and (type(label) is not str or len(label) > 256):
                raise ValueError('Hand backend returned an invalid category label')
        output.append({'index': index, 'score': score, 'category_name': item.category_name,
                       'display_name': item.display_name})
    if len(output) > 8:
        raise ValueError('Hand backend category count exceeds proposal budget')
    return output


def analyse(rgb, source_frame, *, model_root=None, max_hands=4, byte_budget=256*1024*1024):
    """Actual CPU IMAGE inference, called only on explicit user proposal action.

    Shape checks do not prove provenance. The canonical document source owner
    must supply these immutable full-frame pixels and recheck its fence after
    this call; a display/cropped/already warped image is not an admissible input.
    """
    from .body_pose_evidence import whole_source_shape, ORIENTATION
    source = _source(source_frame)
    if (type(rgb) is not np.ndarray or rgb.dtype != np.uint8 or rgb.ndim != 3
            or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 2 or rgb.flags.writeable):
        raise ValueError('Hand proposals need immutable canonical RGB8 pixels')
    if type(max_hands) is not int or not 1 <= max_hands <= 8:
        raise ValueError('Hand proposal limit must be an integer from 1 to 8')
    # Conservative admission, not a measured promise of native allocator peak.
    if type(byte_budget) is not int or rgb.nbytes*4 + M.MODEL_SIZE_BYTES*2 + 128*1024*1024 > byte_budget:
        raise ValueError('Hand proposal exceeds admitted image/model working budget')
    h, w = rgb.shape[:2]
    whole_source_shape({**source, 'orientation': ORIENTATION}, (h, w))
    readiness = status(model_root)
    if not readiness["available"]:
        raise RuntimeError(readiness["reason"] or "Explicit hand CPU readiness check required")
    data = verified_model_bytes(model_root)
    if find_spec('mediapipe') is None:
        raise RuntimeError('Optional reviewed MediaPipe runtime is missing; no install or synthetic fallback')
    backend_version = version('mediapipe')
    if backend_version != M.RUNTIME_VERSION:
        raise RuntimeError('MediaPipe runtime differs from the reviewed repository packaging version')
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode
    from mediapipe.tasks.python.vision import hand_landmarker
    from .hand_shape_setup import verify_producer_origin
    verify_producer_origin(hand_landmarker.__file__)
    backend_sha = sha256(_read_regular(hand_landmarker.__file__, 2*1024*1024)).hexdigest()
    # Private copy binds the hash to exactly the image passed to the detector.
    image = np.array(rgb, dtype=np.uint8, order='C', copy=True)
    image.setflags(write=False)
    input_sha = sha256(memoryview(image)).hexdigest()
    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_buffer=data, delegate=BaseOptions.Delegate.CPU),
        running_mode=RunningMode.IMAGE, num_hands=max_hands,
        min_hand_detection_confidence=.65, min_hand_presence_confidence=.7)
    with HandLandmarker.create_from_options(options) as detector:
        result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=image))
    if len(result.hand_landmarks) > max_hands or len(result.handedness) != len(result.hand_landmarks):
        raise ValueError('Hand backend output counts do not match the admitted proposal')
    records = []
    for landmarks, categories in zip(result.hand_landmarks, result.handedness):
        if len(landmarks) != 21:
            raise ValueError('Hand backend did not return 21 actual proposal points')
        points = []
        for i, point in enumerate(landmarks):
            xyz = [float(point.x), float(point.y), float(point.z)]
            if not all(math.isfinite(n) for n in xyz):
                raise ValueError('Hand backend returned nonfinite proposal coordinates')
            # Retain out-of-frame coordinates. Never clamp/fill hidden anatomy,
            # invent visibility scores, or interpret handedness as ownership.
            points.append({'index': i, 'x': xyz[0], 'y': xyz[1], 'z': xyz[2]})
        records.append({'proposal_id': uuid.uuid4().hex, 'points': points,
                        'handedness': _categories(categories)})
    return {'version': 1, 'source': source, 'model_id': M.MODEL_ID,
            'model_sha256': sha256(data).hexdigest(), 'backend_version': backend_version,
            'backend_code_sha256': backend_sha, 'input_rgb_sha256': input_sha,
            'input_dimensions': [w, h], 'records': records,
            'limit_reached': len(records) == max_hands, 'census_complete': False,
            'visibility_verified': False}
