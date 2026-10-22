"""Global stitched float optics; only active optics changes the legacy export path."""
import numpy as np
from . import optics_state as S


def check_spec(spec):
    spec.optics=S.check(spec.optics)
    if S.source_bound(spec.optics):
        if not spec.optics_path or type(spec.optics_stamp) is not list or len(spec.optics_stamp)!=5: raise ValueError('镜头/透视导出缺少已验证源图')


def admit(shape,scale,value):
    from .cpu_memory_budget import available_estimate
    h,w=shape
    if h*w>64_000_000 or max(h,w)>65536: raise ValueError('镜头/透视导出图幅超过预算')
    # Existing decoded RGB/masks already count against available. Admit future
    # stitched float, original-size f64/gain/output, scaled output and band scratch.
    reserve=h*w*(84+12*scale*scale)+(768 if value['lens']['enabled'] else 128)*1024*1024
    if reserve>available_estimate(): raise ValueError('完整镜头/透视出片内存不足，不会降位深或放大代理图')
    return reserve


def upscale(pixels,plan,*,cancelled=lambda:False):
    """Global Lanczos weights, bounded source windows, no full-raster f64 copy per band."""
    if plan.s==1:return pixels
    output=np.empty((plan.out_h,plan.out_w,3),np.float32)
    rows=max(1,min(64,1_048_576//plan.out_w))
    for y in range(0,plan.out_h,rows):
        if cancelled():raise InterruptedError('镜头/透视放大已取消')
        end=min(plan.out_h,y+rows)
        lo=int(plan._ih[y:end].min());hi=int(plan._ih[y:end].max())+1
        output[y:end]=plan.region_float(pixels[lo:hi],y,end,0,plan.out_w,lo,0)
    return output
