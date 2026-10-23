# SPDX-License-Identifier: GPL-3.0-or-later
"""Unretouched decoded eye-region crop, never enlarging thumbnail to invent detail."""
import io
import base64
import numpy as np
from PIL import Image

def acquire(engine,source,face_ref):
    from .body_pose_evidence import whole_source_shape
    from .people_render_runtime import verify_analysis
    state=engine._people_owner().snapshot();face=state['faces'][face_ref['face_instance_id']]
    analysis=engine._people_analyses.get(source['sha256'],{}).get(face_ref['face_instance_id'])
    if analysis is None:raise ValueError('缺少当前人物的真实虹膜分析')
    lm=verify_analysis(face,analysis,analysis['excluded'].shape if analysis['excluded'] is not None else (0,0))
    rgb=np.asarray(engine._src_rgb)
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('美瞳未修饰参考图不可用')
    h,w=rgb.shape[:2];whole_source_shape({**source,'orientation':'exif_normalized_once'},(h,w));xy=lm[:,:2]*[w-1,h-1]
    ids=[33,133,263,362,468,469,470,471,472,473,474,475,476,477];points=xy[ids]
    radii=[float(np.linalg.norm(xy[list(ids)]-xy[c],axis=1).min()) for c,ids in ((468,(469,470,471,472)),(473,(474,475,476,477)))]
    pad=max(radii)*1.8
    x,y=np.maximum(np.floor(points.min(0)-pad),0).astype(int);x1,y1=np.minimum(np.ceil(points.max(0)+pad)+1,[w,h]).astype(int)
    scale=min(1.,1280/max(x1-x,y1-y))
    if min(radii)*scale<8:raise ValueError('参考图虹膜像素不足，不能可靠描绘实测瞳孔')
    image=Image.fromarray(rgb[y:y1,x:x1],'RGB');image.thumbnail((1280,1280));buf=io.BytesIO();image.save(buf,format='PNG');data=buf.getvalue()
    if len(data)>6*1024*1024 or engine._people_source()!=source:raise ValueError('美瞳参考图过大或源图已改变')
    # SVG uses original source-pixel-centre coordinates; edges account for
    # canonical ALIGN8 decoded canvas without stretching a cropped thumbnail.
    sx,sy=(source['width']-1)/(w-1),(source['height']-1)/(h-1)
    return {'mime':'image/png','base64':base64.b64encode(data).decode('ascii'),'source':source,
            'width':image.width,'height':image.height,'view_box':[(float(x)-.5)*sx,(float(y)-.5)*sy,float(x1-x)*sx,float(y1-y)*sy],
            'mapping':'source_pixel_centre_eye_crop','minimum_iris_radius':min(radii)*scale}
