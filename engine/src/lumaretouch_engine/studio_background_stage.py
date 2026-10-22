"""Source-domain measured operators before automatic deformation and final warp.

Each recovery mask attenuates only its operator's contribution between the actual
operator input and output. Unrelated repair, lighting, skin/fabric, grades and
manual liquify remain intact; the original photograph is never pasted over them.
"""
import numpy as np
from . import studio_background_state as S
from .optional_dependencies import optional_module


def check_prepared(prepared,shape):
    if type(prepared) is not dict or not {'fields','recovery','masks','analysis','method'}<=set(prepared):
        raise ValueError('背景效果准备结果不完整')
    names={'intrusions':3,'blemishes':3,'uniformity':1,'banding':3,'enhancement':1}
    if set(prepared['fields'])!=set(names) or set(prepared['recovery'])!=set(S.RECOVERY):
        raise ValueError('背景效果或恢复目标缺失')
    for name,channels in names.items():
        a=prepared['fields'][name]
        if type(a) is not np.ndarray or a.dtype!=np.float32 or a.shape!=tuple(shape)+((3,) if channels==3 else ()) or not np.isfinite(a).all():
            raise ValueError('背景效果场类型或尺寸无效：'+name)
    for name,a in prepared['recovery'].items():
        if type(a) is not np.ndarray or a.dtype!=np.float32 or a.shape!=tuple(shape) or not np.isfinite(a).all() or np.any((a<0)|(a>1)):
            raise ValueError('背景效果恢复场无效：'+name)
    return prepared


class StudioBackgroundStage:
    def __init__(self,device,shape):
        self.device,self.shape=device,tuple(shape);self.fields={};self.recovery={};self.suspended=None;self.analysis=[];self.required=False

    def install(self,prepared):
        check_prepared(prepared,self.shape);torch=optional_module('torch')
        def own(a):
            data=a.transpose(2,0,1) if a.ndim==3 else a[None]
            return torch.tensor(np.ascontiguousarray(data),dtype=torch.float32,device=self.device)[None]
        fields={k:own(v) for k,v in prepared['fields'].items()}
        recovery={k:own(v) for k,v in prepared['recovery'].items()}
        self.fields,self.recovery,self.analysis=fields,recovery,prepared['analysis'];self.suspended=None;self.required=True

    def _recover(self,name,before,after):
        torch=optional_module('torch');weight=self.recovery[name]
        mixed=after+(before-after)*weight
        return torch.where(weight<=0,after,torch.where(weight>=1,before,mixed))

    def apply(self,rgb):
        if self.required and self.suspended: raise ValueError("背景效果已暂停："+self.suspended)
        if self.required and not self.fields: raise ValueError("启用的背景效果场缺失，拒绝省略用户编辑")
        if not self.fields: return rgb
        if tuple(rgb.shape)!=(1,3,*self.shape): raise ValueError('背景效果输入不在源图像素域')
        torch=optional_module('torch');out=rgb
        for name in ('intrusions','blemishes'):
            before=out;delta=self.fields[name]
            out=self._recover(name,before,torch.where(delta!=0,before+delta,before))
        before=out;gain=self.fields['uniformity']
        linear=torch.where(before<=.04045,before/12.92,((before+.055)/1.055).clamp_min(0).pow(2.4))
        lifted=linear*torch.exp2(gain)
        encoded=torch.where(lifted<=.0031308,lifted*12.92,1.055*lifted.clamp_min(0).pow(1/2.4)-.055)
        out=self._recover('uniformity',before,torch.where(gain!=0,encoded,before))
        before=out;delta=self.fields['banding']
        out=self._recover('banding',before,torch.where(delta!=0,before+delta,before))
        weight=self.fields['enhancement'];luma=out[:,0:1]*.2126+out[:,1:2]*.7152+out[:,2:3]*.0722
        rich=(luma+(out-luma)*1.20-.5)*1.15+.5
        out=torch.where(weight>0,out+(rich-out)*weight,out)
        if not torch.isfinite(out).all(): raise ValueError('背景处理输出包含非有限像素')
        return out

    def resident_bytes(self):
        return sum(int(v.numel()*v.element_size()) for v in (*self.fields.values(),*self.recovery.values()))
