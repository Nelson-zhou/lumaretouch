# SPDX-License-Identifier: GPL-3.0-or-later
"""Effective-source eye crop; never relabel original pixels or invent detail."""
import io
import base64
import numpy as np
from PIL import Image

def acquire(engine,source,face_ref):
    from .body_pose_evidence import whole_source_shape
    from .people_render_runtime import verify_analysis
    from .creative_derived_source import analysis_rgb, record, verify_precompute
    from . import people_state as P
    face_ref=P.check_ref(face_ref)
    if engine._people_source()!=source or face_ref['asset_sha256']!=source['sha256']:
        raise ValueError('美瞳参考图源或人物已改变')
    if record(engine) is not None:
        pc=getattr(engine,'_precompute',None)
        if pc is None or pc.backend!='mediapipe':raise ValueError('需要当前合成图的真实人物分析')
        verify_precompute(engine,pc)
    state=engine._people_owner().snapshot();face=state['faces'].get(face_ref['face_instance_id'])
    if face is None or P.face_ref(face)!=face_ref or not face['enabled']:
        raise ValueError('美瞳参考图人物已改变或停用')
    if (face['evidence']['source_width'],face['evidence']['source_height'])!=(source['width'],source['height']):
        raise ValueError('美瞳人物分析源尺寸不匹配')
    analysis=engine._people_analyses.get(source['sha256'],{}).get(face_ref['face_instance_id'])
    if analysis is None:raise ValueError('缺少当前人物的真实虹膜分析')
    rgb=np.asarray(analysis_rgb(engine))
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('美瞳未修饰参考图不可用')
    h,w=rgb.shape[:2];whole_source_shape({**source,'orientation':'exif_normalized_once'},(h,w))
    lm=verify_analysis(face,analysis,(h,w));xy=lm[:,:2]*[w-1,h-1]
    ids=[33,133,263,362,468,469,470,471,472,473,474,475,476,477];points=xy[ids]
    radii=[float(np.linalg.norm(xy[list(ids)]-xy[c],axis=1).min()) for c,ids in ((468,(469,470,471,472)),(473,(474,475,476,477)))]
    pad=max(radii)*1.8
    x,y=np.maximum(np.floor(points.min(0)-pad),0).astype(int);x1,y1=np.minimum(np.ceil(points.max(0)+pad)+1,[w,h]).astype(int)
    if x1<=x or y1<=y:raise ValueError('美瞳参考图没有有效源像素范围')
    scale=min(1.,1280/max(x1-x,y1-y))
    if min(radii)*scale<8:raise ValueError('参考图虹膜像素不足，不能可靠描绘实测瞳孔')
    image=Image.fromarray(rgb[y:y1,x:x1],'RGB');image.thumbnail((1280,1280));buf=io.BytesIO();image.save(buf,format='PNG');data=buf.getvalue()
    if len(data)>6*1024*1024 or engine._people_source()!=source:raise ValueError('美瞳参考图过大或源图已改变')
    current=engine._people_owner().snapshot()['faces'].get(face_ref['face_instance_id'])
    if current is None or P.face_ref(current)!=face_ref or not current['enabled'] or current['evidence']!=face['evidence']:
        raise ValueError('美瞳参考图准备期间人物分析改变')
    # SVG uses effective source-pixel-centre coordinates; edges account for
    # canonical ALIGN8 decoded canvas without stretching a cropped thumbnail.
    sx,sy=(source['width']-1)/(w-1),(source['height']-1)/(h-1)
    return {'mime':'image/png','base64':base64.b64encode(data).decode('ascii'),'source':source,
            'width':image.width,'height':image.height,'view_box':[(float(x)-.5)*sx,(float(y)-.5)*sy,float(x1-x)*sx,float(y1-y)*sy],
            'mapping':'source_pixel_centre_eye_crop','minimum_iris_radius':min(radii)*scale}
