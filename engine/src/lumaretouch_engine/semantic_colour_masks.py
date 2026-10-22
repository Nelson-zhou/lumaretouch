# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit rendered-canvas masks with retained probabilities and editable marks.

The generic LMR2 normalized primitive rasterizer is reused only after an explicit
coordinate-contract adapter. Source semantic/range/prompted bindings are forbidden.
A rendered mask is NEVER warped through the people/source geometry pipeline.
"""
from copy import deepcopy
from hashlib import sha256
import base64
import zlib
import numpy as np
from . import semantic_colour_state as S
MAX_MASK_PIXELS = 262144
MAX_DATA = 2 * 1024 * 1024


def pack(plane):
    a = np.ascontiguousarray(plane, dtype='<f4')
    if a.ndim != 2 or not a.size or a.size > MAX_MASK_PIXELS or not np.isfinite(a).all() or np.any(a < 0) or np.any(a > 1):
        raise ValueError('AI 追色蒙版概率无效或超限')
    raw = a.tobytes()
    return {'width': a.shape[1], 'height': a.shape[0], 'sha256': sha256(raw).hexdigest(),
            'encoding': 'zlib-float32-le-v1', 'data': base64.b64encode(zlib.compress(raw, 6)).decode('ascii')}

def unpack(value):
    if isinstance(value,dict) and value.get('encoding')=='asset-float32-le-v1':
        from .semantic_colour_assets import read
        return read(value)
    if type(value) is not dict or set(value) != {'width','height','sha256','encoding','data'} or value['encoding'] != 'zlib-float32-le-v1':
        raise ValueError('AI 追色蒙版保留格式无效')
    w,h = value['width'],value['height']
    if any(type(n) is not int or n < 1 for n in (w,h)) or w*h > MAX_MASK_PIXELS or type(value['data']) is not str or len(value['data']) > MAX_DATA:
        raise ValueError('AI 追色蒙版数据超限')
    S.digest(value['sha256'])
    compressed = base64.b64decode(value['data'], validate=True)
    decoder = zlib.decompressobj(); raw = decoder.decompress(compressed, w*h*4+1)
    if len(raw) != w*h*4 or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or sha256(raw).hexdigest() != value['sha256']:
        raise ValueError('AI 追色保留蒙版长度或摘要不符')
    a = np.frombuffer(raw, dtype='<f4').reshape(h,w)
    if not np.isfinite(a).all() or np.any(a < 0) or np.any(a > 1): raise ValueError('保留蒙版不是真实有限概率')
    return a

def check(value):
    if type(value) is not dict or set(value) != {'id','name','domain','binding','base','objects'} or value['domain'] != S.DOMAIN:
        raise ValueError('AI 追色必须使用显式渲染画布蒙版，不能重解释源图蒙版')
    S.identifier(value['id']); S.binding(value['binding'])
    if type(value['name']) is not str or not 1 <= len(value['name']) <= 80: raise ValueError('AI 追色蒙版名称无效')
    if value['base'] is not None:
        if isinstance(value['base'],dict) and value['base'].get('encoding')=='asset-float32-le-v1':
            from .semantic_colour_assets import reference
            reference(value['base'])
        else:unpack(value['base'])
    from . import local_mask_recipe as L
    if type(value['objects']) is not list or len(value['objects']) > 32: raise ValueError('AI 追色蒙版编辑对象超限')
    seen = set(); points = 0
    for obj in value['objects']:
        checked = L.check_object(obj)
        if checked['kind'] not in ('brush','linear','radial') or checked['id'] == 'rendered_base':
            raise ValueError('画布编辑只支持明确的画笔/线性/径向对象，源图语义与提示绑定不能混入')
        if checked['id'] in seen: raise ValueError('画布蒙版标记身份重复')
        seen.add(checked['id']); points += len(checked.get('points', []))
    if points > 4096: raise ValueError('画布蒙版总画笔点超限')
    return deepcopy(value)

def create(ident, name, binding, plane=None):
    return check({'id':ident, 'name':name, 'domain':S.DOMAIN, 'binding':deepcopy(binding),
                  'base':None if plane is None else pack(plane), 'objects':[]})

def assert_geometry(mask, binding):
    a,b = check(mask)['binding'],S.binding(binding)
    if (a['source'],a['geometry_sha256'],a['width'],a['height']) != (b['source'],b['geometry_sha256'],b['width'],b['height']):
        raise ValueError('AI 追色蒙版因源图/素材归属/几何变化暂停；保留原参数与蒙版，请重新分析后审核')

def raster(mask, shape):
    """The exact production interpolation/rasterizer, bounded to analysis grids."""
    h,w=shape
    if any(type(n) is not int or n<1 for n in (h,w)) or h*w>MAX_MASK_PIXELS:
        raise ValueError('AI 追色分析蒙版网格超限')
    compiled=TileMask(mask,shape);success=False
    try:
        result=compiled.tile(0,0,w,h);success=True;return result
    finally:compiled.close(success)

class TileMask:
    """Compile once, keep analysis-grid support; reconstruct only a render tile.

    LMR2 receives the original full canvas dimensions and global tile origin, so
    stroke shape and feather radius do not change between preview and export.
    """
    def __init__(self,mask,shape):
        from . import local_mask_recipe as L
        self.mask=check(mask);self.shape=shape;self.worker=None
        self.base=None if self.mask['base'] is None else unpack(self.mask['base'])
        self.objects=[];self.radius=0;self.body=None
        if self.mask['objects']:
            self.objects=[{'id':'rendered_base','name':'保留画布选区','enabled':True,'operation':'add','kind':'semantic','opacity':1.,'feather':0.,'channel':'rendered_base'}]+self.mask['objects']
            stack={'version':1,'domain':L.DOMAIN,'objects':self.objects}
            self.radius=L.validate_budget(stack,shape)['radius']
            self.body=L._objects_packet([o for o in self.objects if o['enabled']],shape,['rendered_base'])
            self.worker=L._Worker()

    def _base(self,x,y,w,h):
        import cv2
        if self.base is None:return np.zeros((h,w),np.float32)
        ah,aw=self.base.shape;fh,fw=self.shape
        # OpenCV half-pixel linear reconstruction with replicated borders,
        # identical global coordinates regardless of tile boundaries.
        xx=((np.arange(x,x+w,dtype=np.float32)+.5)*aw/fw-.5)[None,:]
        yy=((np.arange(y,y+h,dtype=np.float32)+.5)*ah/fh-.5)[:,None]
        mx=np.broadcast_to(xx,(h,w));my=np.broadcast_to(yy,(h,w))
        return cv2.remap(self.base,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)

    def tile(self,x,y,w,h):
        if self.worker is None:return self._base(x,y,w,h)
        import struct
        from . import local_mask_recipe as L
        fh,fw=self.shape;r=self.radius
        sx,sy=max(0,x-r),max(0,y-r);ex,ey=min(fw,x+w+r),min(fh,y+h+r)
        tw,th=ex-sx,ey-sy
        packet=bytearray(b'LMR2')
        packet+=struct.pack('<13I',fw,fh,sx,sy,tw,th,x-sx,y-sy,w,h,sum(o['enabled'] for o in self.objects),0,1)
        packet+=self.body;packet+=np.asarray(self._base(sx,sy,tw,th),dtype='<f4').tobytes()
        if len(packet)>L.MAX_PACKET_BYTES:raise ValueError('AI 追色蒙版瓦片超出协议预算')
        return np.frombuffer(self.worker.transact(packet,w*h),np.uint8).reshape(h,w).astype(np.float32)/255.

    def close(self,success):
        if self.worker is not None:self.worker.close(success)
