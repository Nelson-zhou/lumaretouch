"""Real MediaPipe Tasks IMAGE producer. No face-box skeleton or inferred anatomy.

The host supplies canonical RGB8 analysis pixels from the effective immutable source, not an
already retouched preview. The full RGB8/16 or derived float render buffer is never replaced by model input.
"""
from hashlib import sha256
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path
import numpy as np
from . import body_pose_evidence as E, body_pose_manifest as M
from .body_pose_acquisition import verified_model_bytes


def analyse(rgb, source_frame, *, model_root=None, max_poses=4, byte_budget=256*1024*1024):
    source=E.source(source_frame)
    if type(rgb) is not np.ndarray or rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3 or min(rgb.shape[:2])<2:
        raise ValueError('Pose analysis requires canonical RGB8 pixels, not landmarks inferred from a face box')
    if type(max_poses) is not int or not 1<=max_poses<=8: raise ValueError('Body detection budget is 1 to 8, not a census promise')
    if type(byte_budget) is not int or rgb.nbytes*4+96*1024*1024>byte_budget: raise ValueError('Body analysis exceeds admitted memory budget')
    h,w=rgb.shape[:2]
    E.whole_source_shape(source,(h,w))
    data=verified_model_bytes(model_root)  # Exact consumed bytes are hashed below.
    if find_spec('mediapipe') is None:raise RuntimeError('Reviewed optional MediaPipe runtime is missing; use the existing requirements-mediapipe packaging flow, not an automatic pip install')
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode
    from mediapipe.tasks.python.vision import pose_landmarker
    image=np.ascontiguousarray(rgb)
    backend_sha=sha256(Path(pose_landmarker.__file__).read_bytes()).hexdigest()
    options=PoseLandmarkerOptions(base_options=BaseOptions(model_asset_buffer=data),running_mode=RunningMode.IMAGE,num_poses=max_poses,min_pose_detection_confidence=.65,min_pose_presence_confidence=.7,output_segmentation_masks=False)
    with PoseLandmarker.create_from_options(options) as detector:
        result=detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB,data=image))
    records=[]
    for landmarks in result.pose_landmarks:
        if len(landmarks)!=33: raise ValueError('Backend did not return all 33 pose points')
        values=[]
        for i,p in enumerate(landmarks):
            if p.visibility is None or p.presence is None: raise ValueError('Backend omitted visibility/presence; do not invent confidence')
            values.append({'index':i,'x':float(p.x),'y':float(p.y),'z':float(p.z),'visibility':float(p.visibility),'presence':float(p.presence)})
        records.append(E.create(source_frame=source,values=values,backend_version=version('mediapipe'),backend_code_sha256=backend_sha,model_id=M.MODEL_ID,model_sha256=sha256(data).hexdigest(),input_rgb_sha256=sha256(image.tobytes()).hexdigest(),input_dimensions=(w,h)))
    return {'version':1,'source':source,'records':records,'detector_limit':max_poses,'limit_reached':len(records)==max_poses,'census_complete':False,'ownership':'unreviewed','limitations':list(M.LIMITATIONS)}
