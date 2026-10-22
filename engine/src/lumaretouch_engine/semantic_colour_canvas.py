# SPDX-License-Identifier: GPL-3.0-or-later
"""Immutable rendered-canvas admission, shared by target AND reference inference.

Never reopen original files. FLOAT32-NPZ samples are real rendered canvases, not
source-domain images. Geometry identity is supplied by the actual renderer owner.
"""
from dataclasses import dataclass
from copy import deepcopy
import numpy as np
from . import semantic_colour_state as S
from .reference_color_review import pixel_digest

@dataclass(frozen=True)
class FrozenCanvas:
    rgb: np.ndarray
    binding: dict

def freeze(rgb, *, source, geometry_sha256, state_key, document_id, revision, owned=False):
    if type(rgb) is not np.ndarray or rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype not in (np.float32,np.float64,np.uint8,np.uint16):
        raise ValueError('AI 追色只接受引擎实际完整 RGB8/16/浮点画布')
    h,w = rgb.shape[:2]
    if h*w > S.MAX_PIXELS or min(h,w)<16: raise ValueError('AI 追色画布尺寸不在完整参考预算内')
    if not np.isfinite(rgb).all(): raise ValueError('AI 追色冻结画布含非有限值')
    # Preserve source values for fitting; only the neural analysis branch later
    # gets a bounded RGB8 view. Current renderer uses float32 by contract.
    scale = np.iinfo(rgb.dtype).max if rgb.dtype.kind == 'u' else 1.
    owned = np.array(rgb, dtype=np.float32, copy=not (owned and rgb.dtype == np.float32 and rgb.flags.c_contiguous), order='C')
    if scale != 1.: owned /= scale
    owned.setflags(write=False)
    identity = S.binding({'source': deepcopy(source), 'render_sha256': pixel_digest(owned),
        'geometry_sha256': S.digest(geometry_sha256), 'state_key': S.digest(state_key),
        'document_id': document_id, 'revision': str(revision), 'width': w, 'height': h, 'stage': S.STAGE})
    return FrozenCanvas(owned, identity)

def validate(frame):
    if type(frame) is not FrozenCanvas: raise ValueError('AI 追色必须使用冻结画布，不接受路径或可变代理')
    S.binding(frame.binding)
    if type(frame.rgb) is not np.ndarray or frame.rgb.dtype != np.float32 or frame.rgb.flags.writeable or frame.rgb.shape != (frame.binding['height'],frame.binding['width'],3):
        raise ValueError('AI 追色冻结所有权/形状无效')
    if pixel_digest(frame.rgb) != frame.binding['render_sha256']: raise ValueError('冻结像素发生变化')
    return frame

def reference_admission(reference,*,include_bundle=False):
    """Admit the stored rendered canvas, not unrelated original-source dimensions."""
    import zipfile
    from . import reference_color_assets as A
    from .reference_color_scope import check_params
    from .cpu_memory_budget import available_estimate
    check_params({'version':1,'strength':1.,'reference':reference})
    root=A.cache_root();path=root/(reference['asset_id']+'.npz')
    if path.is_symlink() or not path.is_file() or path.stat().st_size>A.MAX_BYTES:
        raise ValueError('完整样片资源缺失或超过保存预算')
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist();size=sum(e.file_size for e in entries)
        if len(entries)!=3 or {e.filename for e in entries}!={'rgb.npy','authentic.npy','metadata.npy'} or size>A.MAX_RAW_BYTES:
            raise ValueError('完整样片展开目录或内存预算无效')
    # Full NPY header, model-independent pixel and content validation is still
    # performed by A.load before returning anything. This pre-admission includes
    # validation temporaries and, for commit, the retained compressed byte bundle.
    required=2*size+128*1024*1024+(path.stat().st_size if include_bundle else 0)
    if available_estimate()<required:raise ValueError('完整样片展开内存不足；不会降采样')
    return root


def from_reference(reference):
    """Load exact full working-float asset. No authentic-scene matching gate."""
    from . import reference_color_assets as A
    f=A.load(reference_admission(reference),reference)
    # A stored reference is immutable. Its full state_key is a conservative
    # geometry fingerprint; no edited source mask is borrowed or reinterpreted.
    return freeze(f.rgb, source=f.source, geometry_sha256=f.state_key,
                  state_key=f.state_key, document_id=f.document_id, revision=f.revision, owned=True)
