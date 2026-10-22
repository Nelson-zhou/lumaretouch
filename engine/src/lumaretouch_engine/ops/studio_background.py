"""Measured solid-backdrop cleanup using OpenCV and float32 source pixels.

Not proprietary AI parity. Robust low-order colour/luminance models classify
solid support; local outliers become actual inpainting holes, never blanket blur.
OpenCV accepts float single-channel inpainting: all RGB channels stay float, not
8-bit colour. The uint8 inpaint mask is topology, not the RGB/photo path.
"""
import numpy as np
from .. import studio_background_state as S
from ..studio_background_masks import raster


def rgb_float(source):
    source=np.asarray(source)
    if source.ndim!=3 or source.shape[2]!=3 or min(source.shape[:2])<2:
        raise ValueError('背景调整需要有效 RGB 原照片')
    if source.dtype==np.uint8: out=source.astype(np.float32)/255.
    elif source.dtype==np.uint16: out=source.astype(np.float32)/65535.
    elif np.issubdtype(source.dtype,np.floating): out=source.astype(np.float32,copy=False)
    else: raise ValueError('背景调整仅支持真实 float/8-bit/16-bit RGB')
    if not np.isfinite(out).all(): raise ValueError('背景调整源像素不是有限值')
    return out


def _basis(h,w,ys,xs):
    x=(xs+.5)/w*2-1;y=(ys+.5)/h*2-1
    return np.stack([np.ones_like(x),x,y,x*x,x*y,y*y],axis=-1)


def surface(rgb,support):
    """Huber IRLS quadratic: bounded samples, complete-grid field, no tile fits."""
    h,w=support.shape;step=max(1,int(np.ceil(np.sqrt(h*w/100000))))
    ys,xs=np.mgrid[0:h:step,0:w:step];valid=support[::step,::step]>.9
    if valid.sum()<64: raise ValueError('可信纯色范围太小，请扩大背景标记并避开主体')
    ys,xs=ys[valid].astype(np.float64),xs[valid].astype(np.float64)
    design=_basis(h,w,ys,xs);values=rgb[ys.astype(int),xs.astype(int)].astype(np.float64)
    weight=np.ones(len(ys));coef=None
    for _ in range(5):
        root=np.sqrt(weight)[:,None]
        coef=np.linalg.lstsq(design*root,values*root,rcond=1e-8)[0]
        error=np.linalg.norm(values-design@coef,axis=1)
        scale=max(.003,float(np.median(error))*1.4826)
        weight=np.minimum(1.,2.5*scale/np.maximum(error,1e-9))
    model=np.empty_like(rgb,dtype=np.float32)
    for y0 in range(0,h,256):
        yy,xx=np.mgrid[y0:min(h,y0+256),0:w]
        model[y0:y0+len(yy)]=(_basis(h,w,yy,xx)@coef).astype(np.float32)
    residual=np.linalg.norm(rgb-model,axis=2)
    # Large gradients are allowed; a strongly textured/multicolour region is not
    # advertised as a solid backdrop and the first four effects fail closed.
    median=float(np.median(residual[support>.9]))
    fraction=float(np.mean(residual[support>.9]<.08))
    solid=median<.045 and fraction>.80
    return model,residual,{'solid':solid,'residual_median':median,'inlier_fraction':fraction,
                           'method':'Huber quadratic RGB surface; deterministic, not a semantic AI model'}


def _components(score,support,*,large):
    import cv2
    selected=(score& (support>.9)).astype(np.uint8)
    count,labels,stats,_=cv2.connectedComponentsWithStats(selected,connectivity=8)
    out=np.zeros(support.shape,np.float32);pixels=int(np.count_nonzero(support>.9))
    # Separate measured scales, not an indiscriminate smooth-background toggle.
    boundary=max(24,round(pixels*.0004))
    for i in range(1,count):
        area=int(stats[i,cv2.CC_STAT_AREA])
        if (area>=boundary if large else 2<=area<boundary) and area<=pixels*.20:
            out[labels==i]=1
    return out


def _inpaint(rgb,weight,support):
    import cv2
    binary=weight>1e-5
    if not binary.any(): return np.zeros_like(rgb)
    known=(support>.8)&~binary
    if known.sum()<64: raise ValueError('修补缺少足够的可信背景边界，不能用模糊替代祛穿帮')
    ys,xs=np.nonzero(binary)
    pad=max(16,round(max(rgb.shape[:2])*.012));y0=max(0,int(ys.min())-pad);y1=min(len(rgb),int(ys.max())+pad+1)
    x0=max(0,int(xs.min())-pad);x1=min(rgb.shape[1],int(xs.max())+pad+1)
    src=rgb[y0:y1,x0:x1];hole=binary[y0:y1,x0:x1];valid=known[y0:y1,x0:x1]
    if valid.sum()<16: raise ValueError('修补范围附近没有干净背景，请减小或重新标记')
    # Exclude people/props from inpaint context. Nearest known background pixels
    # extend a context outside support; only the requested holes are composited.
    invalid=(~valid).astype(np.uint8)
    _,labels=cv2.distanceTransformWithLabels(invalid,cv2.DIST_L2,5,labelType=cv2.DIST_LABEL_PIXEL)
    colors=src[valid];lookup=np.zeros((len(colors)+1,3),np.float32);lookup[1:]=colors
    context=lookup[np.minimum(labels,len(colors))];context[valid]=src[valid]
    mask=(hole.astype(np.uint8)*255)
    radius=max(2.,min(8.,max(rgb.shape[:2])*.0015))
    # NS float32 avoids a float->uint8->float photograph round trip. Scale to
    # 0..255 units for OpenCV's numerical conditioning, not integer quantization.
    fixed=np.stack([cv2.inpaint(np.ascontiguousarray(context[...,c]*255.),mask,radius,cv2.INPAINT_NS)/255. for c in range(3)],axis=2)
    if not np.isfinite(fixed).all(): raise ValueError('背景修补产生非有限像素')
    delta=np.zeros_like(rgb);patch=(fixed-src)*weight[y0:y1,x0:x1,None]
    delta[y0:y1,x0:x1]=np.where(hole[...,None],patch,0)
    return delta


def prepare(source,value,*,semantic_background=None,cancelled=lambda:False):
    import cv2
    value=S.check(value);rgb=rgb_float(source);shape=rgb.shape[:2];S.validate_budget(value,shape)
    from ..cpu_memory_budget import available_estimate
    if S.validate_budget(value,shape)['bytes']>available_estimate():
        raise ValueError('完整背景处理内存不足；不会缩小后冒充全尺寸导出')
    p=value['parameters']
    def mask(target,base=None):
        if cancelled(): raise InterruptedError('背景调整计算已取消')
        return raster(value,target,shape,base,cancelled=cancelled)
    floor=mask('floor');protect=mask('protect')
    if value['region_mode']=='semantic_background':
        if semantic_background is None: raise ValueError('人像分析背景来源缺失；不会推断地面或退回全图')
        background=mask('background',semantic_background)
    else: background=mask('background')
    # Explicit floor always wins over background; protect shrinks every consumer.
    floor*=1-protect;background*=1-np.maximum(protect,floor)
    support=np.maximum(background,floor)
    if S.active(value) and np.count_nonzero(support>.9)<64:
        raise ValueError('请先标记背景范围；地面必须单独手动标记，主体应排除在外')
    regions=[];models=[];details=[]
    for name,region in (('background',background),('floor',floor)):
        if np.count_nonzero(region>.9)<64:
            if name=='floor' and p['blemish_floor']>0: raise ValueError('地面祛瑕开启前必须提供足够的显式地面标记')
            continue
        model,residual,status=surface(rgb,region)
        details.append({'region':name,**status})
        needs_solid=any(p[k]>0 for k in ('intrusions','uniformity','banding')) or p['blemish_'+name]>0
        if needs_solid and not status['solid']:
            raise ValueError(('背景' if name=='background' else '地面')+'不是可信纯色区域；前四项仅处理纯色，已暂停而非破坏纹理')
        regions.append((name,region));models.append((model,residual))
    zeros=lambda:np.zeros(shape,np.float32)
    auto_large=zeros();auto_small=zeros();gain=zeros();band_delta=np.zeros_like(rgb)
    for (name,region),(model,residual) in zip(regions,models):
        baseline=float(np.median(residual[region>.9]));sigma=max(.004,1.4826*float(np.median(np.abs(residual[region>.9]-baseline))))
        outlier=residual>max(.035,baseline+5*sigma)
        if p['intrusions']>0: auto_large=np.maximum(auto_large,_components(outlier,region,large=True))
        blemish=p['blemish_'+name]
        if blemish>0: auto_small=np.maximum(auto_small,_components(outlier,region,large=False)*blemish)
        if p['uniformity']>0:
            linear_model=np.where(model<=.04045,model/12.92,np.maximum((model+.055)/1.055,0)**2.4)
            luminance=np.maximum(linear_model@np.array([.2126,.7152,.0722],np.float32),1e-4)
            target=float(np.median(luminance[region>.9]));log_gain=np.clip(np.log2(target/luminance),-1.5,1.5)
            # brightness -100..100 maps to -1..+1 stop and is gated by uniformity.
            gain+=(log_gain+p['brightness']/100.)*region*p['uniformity']
        if p['banding']>0:
            # Work on residual, not colour/model gradients. Re-add high-frequency
            # detail; protect strong edges so cloth/props do not get flattened.
            residual_rgb=rgb-model
            smooth=cv2.bilateralFilter(residual_rgb,9,.025,3.)
            detail=rgb-cv2.GaussianBlur(rgb,(0,0),.65)
            proposal=smooth+model+detail
            gray=rgb@np.array([.2126,.7152,.0722],np.float32)
            gx=cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3)/8;gy=cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3)/8
            safe=np.clip(1-np.sqrt(gx*gx+gy*gy)/.04,0,1)*region
            band_delta+=(proposal-rgb)*safe[...,None]*p['banding']
    intrusion=mask('intrusion',auto_large)*support*p['intrusions']
    # Brush add/subtract refines the detected blemish mask, including removing
    # false positives. It is not an extra global smoothing strength.
    blemish=mask('blemish',auto_small)*support
    if p['blemish_background']==0 and p['blemish_floor']==0: blemish.fill(0)
    else:
        enabled=np.clip(background*(p['blemish_background']>0)+floor*(p['blemish_floor']>0),0,1)
        blemish*=enabled
    fields={'intrusions':_inpaint(rgb,intrusion,support),
            'blemishes':_inpaint(rgb,blemish*(1-intrusion),support),
            'uniformity':gain,'banding':band_delta,'enhancement':support*p['enhancement']}
    recovery={name:mask('recover_'+name) for name in S.RECOVERY}
    if any(not np.isfinite(v).all() for v in fields.values()): raise ValueError('背景效果场不完整')
    return {'fields':fields,'recovery':recovery,'masks':{'background':background,'floor':floor,'protect':protect,
             'intrusion':intrusion,'blemish':blemish},'analysis':details,
            'method':'Explicit/verified background support; robust surface, OpenCV float NS inpainting, edge-aware band correction'}
