# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-bound unretouched eye-region review crop, never the rendered effect.

PNG8 is a bounded review display, not RGB16 render input or acceptance evidence.
The source-pixel-centre mapping records exact crop edges without adding detail.
"""
import io
import base64
import hashlib
import numpy as np
from PIL import Image


def acquire(engine,source,face_ref):
    from .body_pose_evidence import whole_source_shape
    from .people_render_runtime import verify_analysis
    from .creative_derived_source import analysis_rgb, record, verify_precompute
    from . import people_state as P
    from .eye_makeup_enhance_support import check_source
    source=check_source(source); ref=P.check_ref(face_ref)
    if engine._people_source()!=source or ref['asset_sha256']!=source['sha256']:
        raise ValueError('眼妆审核来源或人物已改变')
    if record(engine) is not None:
        pc=getattr(engine,'_precompute',None)
        if pc is None or pc.backend!='mediapipe': raise ValueError('合成源眼妆需要自身真实分析')
        verify_precompute(engine,pc)
    state=engine._people_owner().snapshot(); face=state['faces'].get(ref['face_instance_id'])
    if face is None or P.face_ref(face)!=ref or not face['enabled']:
        raise ValueError('眼妆审核人物已改变或停用')
    if (face['evidence']['source_width'],face['evidence']['source_height'])!=(source['width'],source['height']):
        raise ValueError('眼妆分析尺寸不属于当前有效来源')
    analysis=engine._people_analyses.get(source['sha256'],{}).get(ref['face_instance_id'])
    if analysis is None: raise ValueError('眼妆审核缺少此人物真实分析')
    rgb=np.asarray(analysis_rgb(engine))
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[-1]!=3:
        raise ValueError('眼妆未修饰源图参考不可用')
    h,w=rgb.shape[:2];whole_source_shape({**source,'orientation':'exif_normalized_once'},(h,w))
    lm=verify_analysis(face,analysis,(h,w)); xy=lm[:,:2]*[w-1,h-1]
    widths=[float(np.linalg.norm(xy[b]-xy[a])) for a,b in ((263,362),(33,133))]
    points=xy[[263,362,33,133]]; pad=max(widths)*.80
    x,y=np.maximum(np.floor(points.min(0)-pad),0).astype(int)
    x1,y1=np.minimum(np.ceil(points.max(0)+pad)+1,[w,h]).astype(int)
    if min(x1-x,y1-y)<2: raise ValueError('眼妆没有有效可见参考范围')
    scale=min(1.,1280/max(x1-x,y1-y))
    if min(widths)*scale<40: raise ValueError('眼妆参考分辨率不足，无法可靠描绘可见眼妆与干净参考')
    image=Image.fromarray(rgb[y:y1,x:x1],'RGB');image.thumbnail((1280,1280));buf=io.BytesIO();image.save(buf,format='PNG');data=buf.getvalue()
    if len(data)>5*1024**2 or engine._people_source()!=source: raise ValueError('眼妆参考超预算或来源改变')
    current=engine._people_owner().snapshot()['faces'].get(ref['face_instance_id'])
    if current is None or P.face_ref(current)!=ref or not current['enabled'] or current['evidence']!=face['evidence']:
        raise ValueError('眼妆参考读取期间分析改变')
    sx,sy=(source['width']-1)/(w-1),(source['height']-1)/(h-1)
    return {'mime':'image/png','base64':base64.b64encode(data).decode('ascii'),'sha256':hashlib.sha256(data).hexdigest(),
        'source':source,'width':image.width,'height':image.height,
        'view_box':[(float(x)-.5)*sx,(float(y)-.5)*sy,float(x1-x)*sx,float(y1-y)*sy],
        'mapping':'source_pixel_centre_periocular_crop','minimum_eye_width':min(widths)*scale}
