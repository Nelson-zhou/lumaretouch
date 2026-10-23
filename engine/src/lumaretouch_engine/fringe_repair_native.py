"""Original Rust dehalo bridge. No compiler, fallback or precision downgrade."""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import numpy as np
from . import fringe_repair_state as S

P=C.POINTER(C.c_float)
CANCEL=C.CFUNCTYPE(C.c_int,C.c_void_p)
RADIUS=2.0
THRESHOLD=.02


@lru_cache(maxsize=1)
def native():
    path=Path(__file__).parent/'bin/liblrt_fringe_repair.so'
    if not path.is_file():raise RuntimeError('Fringe repair Rust core is not installed; no substitute filter was applied')
    lib=C.CDLL(str(path));lib.lrt_fringe_repair_abi.restype=C.c_uint32
    if lib.lrt_fringe_repair_abi()!=1:raise RuntimeError('Fringe repair ABI mismatch')
    for name in ('lrt_fringe_validate_rgb','lrt_fringe_validate_coverage'):
        fn=getattr(lib,name);fn.argtypes=[P,C.c_size_t,C.c_size_t,C.c_size_t];fn.restype=C.c_int
    lib.lrt_fringe_required_halo.argtypes=[C.c_float,C.c_float];lib.lrt_fringe_required_halo.restype=C.c_size_t
    lib.lrt_fringe_repair_tile.argtypes=[P,C.c_size_t,P,C.c_size_t,C.c_size_t,C.c_size_t,P,C.c_size_t,
        C.c_size_t,C.c_size_t,C.c_size_t,C.c_size_t,C.c_float,C.c_float,C.c_float,C.c_float,P,C.c_size_t,CANCEL,C.c_void_p]
    lib.lrt_fringe_repair_tile.restype=C.c_int
    return lib


def available():
    try:native();return True
    except (OSError,RuntimeError,AttributeError):return False


def admit(pixels):
    from .cpu_memory_budget import available_estimate
    if type(pixels) is not int or not 0<pixels<=100_000_000:raise ValueError('Fringe repair requires a complete grid within 100 MP')
    required=pixels*40+32*1024**2
    if required>available_estimate():raise MemoryError('Insufficient memory for original-resolution fringe repair; no proxy fallback')
    return required


def render(edited,guide,recipe,coverage=None,*,cancelled=lambda:False):
    recipe=S.check(recipe)
    if not S.active(recipe):return edited
    if (type(edited) is not np.ndarray or edited.dtype!=np.float32 or edited.ndim!=3 or edited.shape[2]!=3
            or type(guide) is not np.ndarray or guide.dtype!=np.float32 or guide.shape!=edited.shape):
        raise ValueError('Fringe repair requires co-registered complete float32 RGB edited and pre-edit frames')
    h,w=edited.shape[:2];admit(h*w)
    if cancelled():raise InterruptedError('Fringe repair cancelled before allocation')
    lib=native();src=np.ascontiguousarray(edited);ref=np.ascontiguousarray(guide)
    for value in (src,ref):
        if lib.lrt_fringe_validate_rgb(value.ctypes.data_as(P),value.size,w,h):
            raise ValueError('Fringe repair source is nonfinite or outside its declared float bounds; no clipping')
    mask=None
    if coverage is not None:
        if type(coverage) is not np.ndarray or coverage.dtype!=np.float32 or coverage.shape!=(h,w):
            raise ValueError('Fringe repair coverage must share the actual complete canvas')
        mask=np.ascontiguousarray(coverage)
        if lib.lrt_fringe_validate_coverage(mask.ctypes.data_as(P),mask.size,w,h):raise ValueError('Invalid fringe repair coverage')
    result=np.empty_like(src);errors=[]
    def poll(_):
        try:return int(bool(cancelled()))
        except BaseException as error:errors.append(error);return 1
    callback=CANCEL(poll)
    # All reads address the complete immutable raster. Tile boundaries never
    # become artificial image boundaries and no partial output is published.
    for y in range(0,h,128):
        for x in range(0,w,256):
            if poll(None):
                if errors:raise errors[0]
                raise InterruptedError('Fringe repair cancelled; private output discarded')
            tw,th=min(256,w-x),min(128,h-y);tile=np.empty((th,tw,3),np.float32)
            code=lib.lrt_fringe_repair_tile(src.ctypes.data_as(P),src.size,ref.ctypes.data_as(P),ref.size,w,h,
                mask.ctypes.data_as(P) if mask is not None else None,0 if mask is None else mask.size,
                x,y,tw,th,recipe['strength']/100.,RADIUS,1.,THRESHOLD,tile.ctypes.data_as(P),tile.size,callback,None)
            if errors:raise errors[0]
            if cancelled():raise InterruptedError('Fringe repair cancelled; private output discarded')
            if code:raise RuntimeError(f'Fringe repair Rust refused tile ({code}); no output published')
            result[y:y+th,x:x+tw]=tile
    if not np.isfinite(result).all():raise RuntimeError('Fringe repair produced invalid float output')
    return result
