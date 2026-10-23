# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual face landmarks + measured skin, never a rectangular cheek overlay.

Only moderately frontal visible faces are admitted. Six-class semantics cannot
identify all skin-coloured hands/glasses; exclusions are conservative, not a
complete occlusion claim. Source-owned recovery removes false-positive support.
"""
import numpy as np
from .face_scope import _polygon_field
from .lip_makeup_geometry import OUTER as LIPS, _crossed
OVAL=(10,338,297,332,284,251,389,356,454,323,361,288,397,365,379,378,400,377,152,148,176,149,150,136,172,58,132,93,234,127,162,21,54,103,67,109)
EYES=((33,160,158,133,153,144),(362,385,387,263,373,380))

def fields(lm,shape,skin,excluded,*,backend):
    h,w=shape;lm=np.asarray(lm,np.float32)
    if backend!='mediapipe' or lm.shape!=(478,2) or not np.isfinite(lm).all():
        raise ValueError('腮红需要真实 478 点人物分析')
    for mask in (skin,excluded):
        if mask is None or mask.shape!=shape or not np.isfinite(mask).all() or np.any((mask<0)|(mask>1)):
            raise ValueError('腮红缺少当前源图的皮肤或遮挡证据')
    eye_widths=[np.linalg.norm(lm[a]-lm[b]) for a,b in ((33,133),(263,362))]
    cheeks=[np.linalg.norm(lm[a]-lm[1]) for a in (234,454)]
    if min(eye_widths)<10 or min(cheeks)<24:raise ValueError('腮红人物分辨率不足')
    if min(eye_widths)<.55*max(eye_widths) or min(cheeks)<.50*max(cheeks):
        raise ValueError('侧脸过强，腮红暂不应用')
    oval=lm[list(OVAL)]
    if _crossed(oval) or np.any(oval<1) or np.any(oval[:,0]>w-2) or np.any(oval[:,1]>h-2):
        raise ValueError('脸部边界不完整，腮红暂不应用')
    ys,xs=np.mgrid[:h,:w].astype(np.float32);xs+=.5;ys+=.5
    inside,edge=_polygon_field(xs,ys,oval)
    clearance=max(1.5,min(eye_widths)*.08)
    allowed=inside&(edge>clearance)&(skin>=.7)&(excluded<.1)
    for ids in (*EYES,LIPS):
        polygon=lm[list(ids)]
        if _crossed(polygon):raise ValueError('眼唇边界异常，腮红未应用')
        occupied,distance=_polygon_field(xs,ys,polygon)
        allowed&=~occupied&(distance>clearance)
    # Exclude the nose bridge/tip and mouth corridor even for long patterns.
    nose_width=max(2.,float(np.linalg.norm(lm[98]-lm[327]))*.7)
    across=(lm[454]-lm[234])
    if np.linalg.norm(across)<24:raise ValueError('脸部横轴退化，腮红未应用')
    across/=np.linalg.norm(across)
    nose_distance=np.abs((xs-lm[1,0])*across[0]+(ys-lm[1,1])*across[1])
    allowed&=nose_distance>nose_width
    down=lm[152]-(lm[33]+lm[263])*.5
    if np.linalg.norm(down)<10:raise ValueError('脸部纵轴退化，腮红未应用')
    down/=np.linalg.norm(down)
    uv=np.zeros((h,w,2),np.float32);support=np.zeros(shape,np.float32);owner=np.zeros(shape,np.uint8);facts=[]
    # Each half belongs to one measured cheek, never overlapping masks. Cheek
    # axes are measured, not template meshes; no synthetic fallback landmarks.
    side_axis=(xs-lm[1,0])*across[0]+(ys-lm[1,1])*across[1]
    for side,(center_id,outer_id,eye_width) in enumerate(((50,234,eye_widths[0]),(280,454,eye_widths[1]))):
        center=lm[center_id];outward=lm[outer_id]-lm[1];outward/=np.linalg.norm(outward)
        vertical=down-outward*np.dot(down,outward)
        if np.linalg.norm(vertical)<.3:raise ValueError('面颊局部坐标退化，腮红未应用')
        vertical/=np.linalg.norm(vertical)
        scale=max(float(eye_width)*1.35,1.)
        u=((xs-center[0])*outward[0]+(ys-center[1])*outward[1])/scale
        v=((xs-center[0])*vertical[0]+(ys-center[1])*vertical[1])/scale
        region=(side_axis<0 if side==0 else side_axis>=0)&(np.abs(u)<1.5)&(np.abs(v)<1.3)
        safe=region&allowed
        owner[region]=side+1
        if np.count_nonzero(safe)<30:raise ValueError('一侧面颊遮挡或有效皮肤不足；未部分应用腮红')
        uv[region]=np.stack((u,v),axis=-1)[region]
        support[safe]=skin[safe]*(1-excluded[safe])*np.clip((edge[safe]-clearance)/clearance,0,1)
        facts.append(int(np.count_nonzero(support[safe])))
    return np.ascontiguousarray(uv),np.ascontiguousarray(support),owner,{'cheek_support_pixels':facts,'limitation':'known_occluders_only_not_full_segmentation'}
