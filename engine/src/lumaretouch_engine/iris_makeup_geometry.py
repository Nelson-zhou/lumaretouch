# SPDX-License-Identifier: GPL-3.0-or-later
"""Observed iris perimeter bounds texture coordinates, NEVER pupil segmentation."""
import numpy as np
from .face_scope import _polygon_field
from .lip_makeup_geometry import _crossed
# Anatomical sides in MediaPipe's actual 478-landmark topology.
EYES={'right':((33,160,158,133,153,144),468,(469,470,471,472)),
      'left':((362,385,387,263,373,380),473,(474,475,476,477))}

def fields(source,landmarks,eyes,excluded,*,backend):
    h,w=source.shape[:2];lm=np.asarray(landmarks,np.float32)
    if backend!='mediapipe' or lm.shape!=(478,3) or not np.isfinite(lm).all():raise ValueError('美瞳需要真实 478 点，不接受模板关键点')
    if excluded is None or excluded.shape!=(h,w) or not np.isfinite(excluded).all() or np.any((excluded<0)|(excluded>1)):raise ValueError('美瞳缺少源图遮挡证据')
    lm=lm[:,:2]*[w-1,h-1]
    yy,xx=np.mgrid[:h,:w].astype(np.float32);xx+=.5;yy+=.5
    uv=np.zeros((h,w,2),np.float32);support=np.zeros((h,w),np.float32);counts={};protected=np.zeros((h,w),bool)
    def shape(points):
        p=np.asarray(points,np.float32)*[w-1,h-1]
        if _crossed(p) or np.any(p<1) or np.any(p>[w-2,h-2]):raise ValueError('审核轮廓交叉或裁切')
        inside,edge=_polygon_field(xx,yy,p)
        if np.count_nonzero(inside)<4:raise ValueError('审核轮廓面积不足')
        return inside,edge,p
    for side,(lid_ids,center_id,iris_ids) in EYES.items():
        lid=lm[list(lid_ids)];c=lm[center_id];perimeter=lm[list(iris_ids)]
        axis=lid[3]-lid[0];width=float(np.linalg.norm(axis));axis/=max(width,1e-8);normal=np.array([-axis[1],axis[0]])
        aperture=float(np.ptp(lid@normal));radii=np.linalg.norm(perimeter-c,axis=1);radius=float(radii.min())
        if width<24 or radius<5 or aperture<6 or aperture/width<.16 or radii.max()>radius*1.5 or radius>width*.4:raise ValueError('虹膜过小、闭眼或严重侧脸，未应用美瞳')
        if _crossed(lid) or np.any(lid<1) or np.any(lid>[w-2,h-2]):raise ValueError('眼部边界不完整')
        lid_inside,lid_edge=_polygon_field(xx,yy,lid)
        iris,iris_edge,ip=shape(eyes[side]['iris']);pupil,pupil_edge,pp=shape(eyes[side]['pupil'])
        # Measured pupil polygon must lie entirely within independently reviewed
        # visible iris. No circle guess, dilation from center or hidden fill.
        if np.any(pupil&~iris) or np.count_nonzero(pupil)<9:raise ValueError('瞳孔排除轮廓必须完整位于可见虹膜范围内')
        observed=((xx-c[0])**2+(yy-c[1])**2)<(float(radii.max())*1.12)**2
        if np.count_nonzero(iris&~(lid_inside&observed))>max(2,.03*np.count_nonzero(iris)):raise ValueError('审核范围超出实测可见虹膜')
        if np.count_nonzero(pupil)>.72*np.count_nonzero(iris):raise ValueError('虹膜环过窄，不能可靠应用')
        highlight=source.max(axis=2)>.80
        for poly in eyes[side]['highlights']:
            hi,edge,_=shape(poly);highlight|=hi|(edge<1.5)
        if np.count_nonzero(highlight&iris)>.22*np.count_nonzero(iris):raise ValueError('虹膜强反光，未应用美瞳')
        if np.any((excluded>.1)&iris):raise ValueError('虹膜有已知遮挡，未应用美瞳')
        # Hard zero inside measured pupil and its boundary clearance, highlights,
        # lids and outside reviewed source ring; feather only inward.
        safe=iris&lid_inside&observed&~pupil&~highlight&(pupil_edge>1.5)&(lid_edge>1)&(iris_edge>.75)
        n=int(np.count_nonzero(safe))
        if n<24:raise ValueError('审核后的可见虹膜支持不足')
        if np.any(safe&(support>0)):raise ValueError('两侧虹膜审核重叠')
        radial=np.sqrt((xx-c[0])**2+(yy-c[1])**2)/radius
        theta=np.arctan2((xx-c[0])*normal[0]+(yy-c[1])*normal[1],(xx-c[0])*axis[0]+(yy-c[1])*axis[1])
        uv[safe]=np.stack((radial,theta),axis=-1)[safe]
        support[safe]=np.minimum.reduce((np.clip(iris_edge[safe]-.75,0,1),np.clip(pupil_edge[safe]-1.5,0,1),np.clip(lid_edge[safe]-1,0,1)))
        protected|=pupil|highlight;counts[side]=n
    return np.ascontiguousarray(uv),np.ascontiguousarray(support),protected,counts
