"""Opt-in adapter ports. Not registered in the product pipeline in this slice.

Host must call solve on immutable linear float32 source, then composite delta
at a stable scene-linear stage before display conversion. Never feed preview
uint8 pixels, nor an already eye-light-composited source, back to solve.
"""
from dataclasses import dataclass
import copy
import numpy as np
from . import eye_light_state as S
from . import eye_light_geometry as G
from .eye_light_native import delta
@dataclass(frozen=True)
class EyeLightLayer:
    recipe: dict
    binding: dict
    tiles: tuple
    facts: tuple

def solve(source,landmarks,binding,supports,recipe,recovery=None):
    r=S.check(recipe); G.validate_binding(source,landmarks,binding)
    if recovery is None: recovery=np.zeros(source.shape[:2],np.float32)
    if recovery.dtype!=np.float32 or recovery.shape!=source.shape[:2] or not np.isfinite(recovery).all() or np.any((recovery<0)|(recovery>1)): raise ValueError('眼神光恢复场无效')
    if not S.active(r): return EyeLightLayer(r,copy.deepcopy(binding),(),('disabled',))
    if not isinstance(supports,dict): raise ValueError('缺少逐眼审核支持')
    tiles=[]; facts=[]
    # Transactional: any requested unsupported eye rejects the entire proposal.
    for side in ('left','right'):
        eye=r[side]
        if eye['strength']==0:continue
        window,poly,geom,visible=G.prepare(source,landmarks,binding,side,supports.get(side))
        y,x,h,w=window
        cfg=np.ascontiguousarray([*geom,eye['strength'],eye['horizontal'],eye['vertical'],eye['rotation'],int(eye['flip'])],dtype=np.float32)
        d=delta(visible,np.ascontiguousarray(recovery[y:y+h,x:x+w]),poly,cfg,S.ASSETS.index(eye['asset']))
        d.setflags(write=False); tiles.append((window,d)); facts.append({'side':side,'changed_pixels':int(np.count_nonzero(np.any(d!=0,axis=2))),'review_id':supports[side]['review_id']})
    return EyeLightLayer(r,copy.deepcopy(binding),tuple(tiles),tuple(facts))

def composite(source,layer,*,person_id,source_revision):
    if source_revision!=layer.binding['source_revision'] or person_id!=layer.binding['person_id'] or G.source_key(source)!=layer.binding['source_sha256']: raise ValueError('眼神光图层与当前人物或源图不匹配')
    result=source.copy()
    for (y,x,h,w),d in layer.tiles: result[y:y+h,x:x+w]+=d
    if not np.isfinite(result).all(): raise ValueError('眼神光合成超出 float32 范围')
    # Preserve negative / >1 scene values. Export conversion is host-owned.
    return result

def export_rgb16_to_linear(rgb16,decode):
    """Explicit decoder port: caller supplies profile-aware RGB16 -> linear RGB."""
    if rgb16.dtype!=np.uint16 or rgb16.ndim!=3 or rgb16.shape[2]!=3: raise ValueError('需要源 RGB16')
    linear=decode(rgb16.astype(np.float32)/np.float32(65535))
    G.source_key(linear)
    if linear.shape!=rgb16.shape: raise ValueError('解码不得改变原图尺寸')
    return linear
