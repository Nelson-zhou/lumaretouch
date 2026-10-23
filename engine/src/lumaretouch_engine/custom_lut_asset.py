"""Immutable portable custom LUT occupying the existing LUT recipe/stage slot."""
from dataclasses import dataclass, field
import base64
import hashlib
from .custom_lut_native import ParsedCube, MAX_BYTES
from .custom_lut_library import digest_id, display_name

@dataclass(frozen=True, eq=False)
class CustomCube:
    content: bytes
    asset_id: str
    title: str
    metadata: tuple = field(init=False, repr=False)
    def __post_init__(self):
        digest_id(self.asset_id); display_name(self.title)
        if not isinstance(self.content, bytes) or not 0 < len(self.content) <= MAX_BYTES or hashlib.sha256(self.content).hexdigest() != self.asset_id:
            raise ValueError('自定义 LUT 内容或 SHA256 不匹配')
        with ParsedCube(self.content) as parsed: object.__setattr__(self, 'metadata', parsed.metadata())
    def __deepcopy__(self, memo): return self
    @property
    def kind(self): return '1d' if self.metadata[0] == 1 else '3d'
    @property
    def size(self): return int(self.metadata[1])
    @property
    def domain_min(self): return self.metadata[2:5]
    @property
    def domain_max(self): return self.metadata[5:8]
    @property
    def source(self): return 'custom-sha256:' + self.asset_id
    neutral = False
    clipped = 0
    notes = ('自定义 LUT 使用 CPU 插值；输入坐标夹到 DOMAIN 边界，输出浮点值不截断；仅 sRGB 编码',)
    def nbytes(self): return len(self.content)
    def portable(self): return {'schema':1,'sha256':self.asset_id,'name':self.title,'cube_base64':base64.b64encode(self.content).decode('ascii')}
    @staticmethod
    def restore(payload):
        if not isinstance(payload,dict) or set(payload)!={'schema','sha256','name','cube_base64'} or type(payload['schema']) is not int or payload['schema']!=1: raise ValueError('自定义 LUT 资源版本无效')
        text=payload['cube_base64']
        if not isinstance(text,str) or len(text)>((MAX_BYTES+2)//3)*4:raise ValueError('自定义 LUT 资源超过预算')
        return CustomCube(base64.b64decode(text,validate=True),payload['sha256'],payload['name'])
    def apply_tensor(self, image, amount, cancelled=lambda:False):
        import torch
        if image.ndim!=4 or image.shape[0]!=1 or image.shape[1]!=3 or image.dtype not in (torch.float32,torch.float64):raise ValueError('LUT 需要 1×3×H×W 浮点输入')
        if amount==0:return image
        # Output remains same dtype/device; only <=262144 pixels cross CPU per chunk.
        out=torch.empty_like(image)
        h,w=image.shape[2:]
        with ParsedCube(self.content) as parsed:
            for y in range(h):
                for x in range(0,w,262144):
                    if cancelled():raise InterruptedError('LUT 已取消')
                    tile=image[0,:,y:y+1,x:x+262144].permute(1,2,0).detach().cpu().contiguous().numpy()
                    mapped=parsed.apply(tile,amount,cancelled)
                    out[0,:,y:y+1,x:x+262144]=torch.from_numpy(mapped).permute(2,0,1).to(device=image.device,dtype=image.dtype)
        if cancelled():raise InterruptedError('LUT 已取消')
        return out
