"""The sole processing -> final-canvas adapter, called exactly once at delivery.

Never call on source evidence, masks, landmarks, intermediate retouch or original
comparison. Neutral is object identity and never loads the native library. No
numeric conversion, interpolation, fallback or in-place writes are permitted.
"""
import ctypes as C
from functools import lru_cache
from pathlib import Path
from . import final_canvas_flip_state as S

@lru_cache(maxsize=1)
def native():
    path = Path(__file__).parent / 'bin/liblrt_final_canvas_flip.so'
    if not path.is_file():
        raise RuntimeError('Final canvas flip Rust core is not installed; explicit build/package required')
    lib = C.CDLL(str(path))
    lib.lrt_final_canvas_flip_abi.restype = C.c_uint32
    if lib.lrt_final_canvas_flip_abi() != 1:
        raise RuntimeError('Final canvas flip ABI mismatch')
    lib.lrt_final_canvas_flip.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t, C.c_size_t, C.c_size_t, C.c_uint8, C.c_uint8]
    lib.lrt_final_canvas_flip.restype = C.c_int
    return lib

def available():
    try:
        native()
        return True
    except (OSError, RuntimeError, AttributeError):
        return False

def admit(nbytes):
    from .cpu_memory_budget import available_estimate
    # CPU transfer, packed source, native destination and upload owner may overlap.
    required = int(nbytes) * 4 + 16 * 1024 * 1024
    budget = min(2_000_000_000, int(available_estimate()) // 2)
    if required > budget:
        raise MemoryError(f'Final canvas reflection requires {required} bytes, budget {budget}; no downsample or omitted flip')

def processing_to_final(pixels, recipe):
    recipe = S.neutral() if recipe is None else S.check(recipe)
    if not S.active(recipe):
        return pixels
    import numpy as np
    tensor = not isinstance(pixels, np.ndarray)
    if tensor:
        import torch
        if not isinstance(pixels, torch.Tensor) or pixels.ndim != 4 or tuple(pixels.shape[:2]) != (1, 3):
            raise ValueError('Final reflection requires packed RGB or a 1x3xHxW tensor')
        admit(pixels.numel() * pixels.element_size())
        src = pixels.detach().cpu()[0].permute(1, 2, 0).numpy()
    else:
        src = pixels
        admit(src.nbytes)
    if src.ndim != 3 or src.shape[2] != 3 or min(src.shape[:2]) < 1 or src.dtype not in (np.dtype('uint8'), np.dtype('uint16'), np.dtype('float32'), np.dtype('float64')):
        raise ValueError('Final reflection requires nonempty RGB u8/u16/f32/f64 without conversion')
    lib = native()  # Fail before output allocation; never compile or fall back.
    src = np.ascontiguousarray(src)
    out = np.empty_like(src)
    code = lib.lrt_final_canvas_flip(src.ctypes.data, out.ctypes.data, src.shape[1], src.shape[0], src.dtype.itemsize, int(recipe['horizontal']), int(recipe['vertical']))
    if code:
        raise RuntimeError(f'Final canvas reflection refused ({code}); no frame published')
    if tensor:
        return torch.from_numpy(out).permute(2, 0, 1)[None].to(pixels.device)
    return out
