"""Actual frozen pre-optics input preparation for frozen batch/preset ports.

The engine adapter supplies a freshly built, source-verified ExportSpec for the
TARGET's immutable snapshot, including every upstream effect. No Engine mutation,
source locator reuse, proxy stretch, model download or fake analysis is permitted.
The frozen batch and preset controllers call the same candidate-state adapter.
"""
from dataclasses import dataclass
import numpy as np
from . import optics_state as S, local_mask_state as M

@dataclass(frozen=True)
class TargetInput:
    document_id:str
    revision:str
    path:str
    stamp:tuple
    source:dict
    metadata:dict
    pixels:np.ndarray
    candidate_key:str
    domain:str=S.DOMAIN


def render_target(decoded,spec,*,path,document_id,revision,source,decoded_stamp,candidate_state,max_source_pixels=64_000_000,cancelled=lambda:False):
    """Consume a fresh spec already verified against this full decode.

    Full-size rendering keeps retained masks/deformation/manual vectors correct.
    The analysis raster is not a final output file and is never retained in project.
    Eight-bit analysis of an RGB8 source does not alter the final RGB16 export path.
    """
    from .optics_candidate_identity import fingerprint
    candidate_key=fingerprint(candidate_state)
    from .export import export_image,render_edited_rgb16
    from .optics_lensfun import metadata
    from .cpu_memory_budget import available_estimate
    if not document_id or not str(revision):raise ValueError('自动透视目标缺少冻结文档版本')
    source=S.binding(source)
    if source is None:raise ValueError('自动透视目标缺少源图身份')
    if tuple(decoded_stamp)!=M.file_stamp(path):raise ValueError('目标在解码后变化')
    M.verify_source({'source':source},path,(decoded.h,decoded.w))
    if (decoded.h,decoded.w)!=(decoded.src_h,decoded.src_w) or decoded.draft_used or (decoded.raw or {}).get('used_preview') or (decoded.raw or {}).get('half_size'):
        raise ValueError('自动批量分析需要完整目标源图，不接受代理或相机预览')
    if type(max_source_pixels) is not int or not 1<=max_source_pixels<=64_000_000 or decoded.h*decoded.w>max_source_pixels:raise ValueError('自动批量目标超过图幅预算')
    if decoded.h*decoded.w*128+768*1024*1024>available_estimate():raise ValueError('目标完整编辑分析内存不足，不会改用未经编辑的源图')
    # Optical effects and final crop/upscale/sharpen must NOT enter the evidence
    # that will be used to solve a new optical stage. All other stages remain.
    spec.optics=S.empty();spec.optics_path=None;spec.optics_stamp=None
    spec.scale=1;spec.sharpen_amount=0.;spec.upscale_backend='lanczos3'
    def progress(*_):
        if cancelled():raise InterruptedError('自动镜头/透视预检已取消')
    progress()
    if decoded.rgb.dtype==np.uint16:
        rendered,_,_=render_edited_rgb16(decoded,spec,device='cpu',crop_rect=(0.,0.,1.,1.),rotation_degrees=0.,output_profile='srgb',progress=progress)
        divisor=65535.
    elif decoded.rgb.dtype==np.uint8 and not (decoded.raw or {}) and int(decoded.src_bits)<=8:
        rendered,_=export_image(decoded.rgb,spec,device='cpu',progress=progress);divisor=255.
    else:raise ValueError('高位深目标必须提供真实 RGB16 解码')
    if rendered.shape!=(decoded.h,decoded.w,3):raise ValueError('自动分析输入不是完整未裁剪的编辑画布')
    progress()
    if tuple(decoded_stamp)!=M.file_stamp(path):raise ValueError('目标在编辑分析期间变化')
    if fingerprint(candidate_state)!=candidate_key:raise ValueError('目标候选状态在分析渲染期间变化')
    pixels=np.ascontiguousarray(rendered,dtype=np.float32)/divisor
    return TargetInput(document_id,str(revision),path,tuple(decoded_stamp),source,metadata(decoded,path),pixels,candidate_key)
