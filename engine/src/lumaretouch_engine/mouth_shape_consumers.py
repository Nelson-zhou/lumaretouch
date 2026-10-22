"""Conservative source-domain cavity veto, then the ONE shared final-map sample.

Legacy enhancement's expanded outer-lip band is retained for neutral projects.
With new mouth geometry, teeth weights may only originate well inside the actual
observed inner contour. This prevents lowered gummy lip pixels inheriting a
bright lip highlight misclassified by the older teeth photometric gate.
"""
import numpy as np
from .lip_makeup_geometry import INNER
from .brow_shape_geometry import polygon_inside
from .nose_shape_field import edge_distance
from .brow_shape_field import smoothstep


def cavity_support(landmarks,shape,*,band_pixels=65536):
    h,w = shape
    polygon = np.asarray(landmarks)[list(INNER)]
    result = np.zeros(shape,np.float32)
    width = float(np.linalg.norm(landmarks[61]-landmarks[291]))
    clearance = max(1.5,width*.012)
    rows = max(1,int(band_pixels)//w)
    for y in range(0,h,rows):
        end = min(h,y+rows)
        yy,xx = np.mgrid[y:end,:w]
        X = np.stack((xx.ravel(),yy.ravel()),axis=1)
        inside = polygon_inside(X[:,0],X[:,1],polygon)
        # Zero beyond the inner contour plus an inward > bilinear-footprint rim.
        weight = inside*smoothstep((edge_distance(X,polygon)-clearance)/clearance)
        result[y:end] = weight.reshape(end-y,w)
    return result


def gate_teeth_source(pipe,weights):
    """Mutates a newly allocated source-weight tensor, never cached legacy mask."""
    field = getattr(pipe,'mouth_shape_field',None)
    if field is not None and field.state is not None:
        support = field.teeth_support
    elif getattr(pipe,'mouth_shape_combined',False):
        support = getattr(pipe,'mouth_shape_teeth_support',None)
        if support is None: raise ValueError('嘴形导出缺少原始内唇牙齿保护场')
    else:
        return weights
    if support.shape != (pipe.h,pipe.w): raise ValueError('嘴形牙齿保护场尺寸不一致')
    import torch
    weights[:,2] *= torch.as_tensor(support,dtype=weights.dtype,device=weights.device)
    return weights
