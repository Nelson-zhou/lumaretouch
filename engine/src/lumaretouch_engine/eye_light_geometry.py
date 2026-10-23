"""Observed MediaPipe iris/rim geometry and explicit reviewed visibility only."""
import hashlib
import re
import numpy as np
EYES={
    'right': ((33,246,161,160,159,158,157,173,133,155,154,153,145,144,163,7),468,(469,470,471,472),(33,133)),
    'left': ((362,398,384,385,386,387,388,466,263,249,390,373,374,380,381,382),473,(474,475,476,477),(362,263)),
}
def signature(landmarks):
    a=np.asarray(landmarks,dtype=np.float32)
    if a.shape!=(478,3) or not np.isfinite(a).all(): raise ValueError('需要真实 478 点含虹膜的人脸检测')
    return hashlib.sha256(a.astype('<f4').tobytes()).hexdigest()
def source_key(source):
    if source.dtype!=np.float32 or source.ndim!=3 or source.shape[2]!=3 or not np.isfinite(source).all(): raise ValueError('需要有限 float32 RGB 原图')
    return hashlib.sha256(str(source.shape).encode()+source.astype('<f4').tobytes()).hexdigest()
def validate_binding(source,landmarks,binding):
    if not isinstance(binding,dict) or binding.get('backend')!='mediapipe' or binding.get('working_space')!='linear-rgb': raise ValueError('眼神光需要明确线性 RGB 和真实检测来源')
    for field in ('source_sha256','face_sha256','model_sha256'):
        if not re.fullmatch('[0-9a-f]{64}',str(binding.get(field,''))): raise ValueError('来源绑定无效')
    if binding['source_sha256']!=source_key(source) or binding['face_sha256']!=signature(landmarks): raise ValueError('眼神光人物或源图已改变，请重新审核')
    if not isinstance(binding.get('person_id'),str) or not binding['person_id'] or type(binding.get('source_revision')) is not int: raise ValueError('缺少人物身份和源图修订号')

def prepare(source,landmarks,binding,side,support):
    validate_binding(source,landmarks,binding)
    if not isinstance(support,dict) or support.get('reviewed') is not True or support.get('occluded') is not False:
        raise ValueError(f'{side}: 眼部尚未审核或存在遮挡')
    for key in ('source_sha256','face_sha256','person_id','source_revision'):
        if support.get(key)!=binding[key]: raise ValueError('可见眼球支持已过期')
    if support.get('side')!=side or not isinstance(support.get('review_id'),str) or not support['review_id']: raise ValueError('缺少此眼审核记录')
    mask=support.get('mask')
    if not isinstance(mask,np.ndarray) or mask.dtype!=np.float32 or mask.shape!=source.shape[:2] or not np.isfinite(mask).all() or np.any((mask<0)|(mask>1)): raise ValueError('需要与原图对齐的可见眼球掩膜')
    h,w=source.shape[:2]; lm=np.asarray(landmarks,np.float32)[:,:2]*[w-1,h-1]
    ring,center,iris,corners=EYES[side]; polygon=lm[list(ring)]; c=lm[center]; ir=lm[list(iris)]
    if np.any(polygon<0) or np.any(polygon>=[w,h]) or np.any(ir<0) or np.any(ir>=[w,h]): raise ValueError('眼部边界截断，不能放置')
    axis=lm[corners[1]]-lm[corners[0]]
    # Keep positive horizontal image-right for both anatomical eyes.
    if axis[0]<0: axis=-axis
    width=float(np.linalg.norm(axis)); axis=axis/max(width,1e-8)
    normal=np.array([-axis[1],axis[0]])
    aperture=float(np.ptp(polygon@normal)); distances=np.linalg.norm(ir-c,axis=1)
    radius=float(distances.min())
    if width<14 or aperture<4 or aperture/width<0.12 or radius<2: raise ValueError('闭眼、过小或不可靠眼部，未应用')
    if distances.max()>radius*1.8 or radius>width*0.4: raise ValueError('虹膜观测异常，未生成隐藏眼球')
    x,y=np.floor(polygon.min(0)).astype(int); x1,y1=np.ceil(polygon.max(0)).astype(int)+1
    x1=min(x1,w); y1=min(y1,h)
    visible=np.ascontiguousarray(mask[y:y1,x:x1])
    if int(np.count_nonzero(visible>0.5))<16: raise ValueError('可见眼球支持不足')
    return (y,x,y1-y,x1-x),np.ascontiguousarray(polygon-[x,y],dtype=np.float32),np.asarray([*(c-[x,y]),*axis,radius],np.float32),visible
