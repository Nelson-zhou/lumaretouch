"""Engine lifecycle port for the all-face bank. Shared host wiring is separate.

The host owns state/history/receipts. This adapter owns derived preview resources,
not association persistence. A failed requested graph cannot fall back to a stale
single-selected-face image and claim it rendered the people bank.
"""
import numpy as np
from .people_render_runtime import prepare
from . import people_pipeline as PIPE


def prepare_preview(pipe,state,asset_sha256,analyses,*,byte_budget,recovery_assets=None):
    import torch
    source=pipe.src_f32
    if source is None:raise ValueError('All-face rendering needs the current immutable source')
    rgb=np.array(source[0].permute(1,2,0).to('cpu',torch.float32).numpy(),dtype=np.float32,copy=True)
    rgb.setflags(write=False)
    repaired=None
    if pipe.repair_base is not None:
        repaired=np.array(pipe.repair_base[0].permute(1,2,0).to('cpu',torch.float32).numpy(),dtype=np.float32,copy=True)
        repaired.setflags(write=False)
    prepared=prepare(state,asset_sha256,rgb,analyses,byte_budget=byte_budget,recovery_assets=recovery_assets,repaired=repaired)
    return prepared


def synchronize(pipe,state,asset_sha256,analyses,*,byte_budget,recovery_assets=None):
    prepared=prepare_preview(pipe,state,asset_sha256,analyses,byte_budget=byte_budget,recovery_assets=recovery_assets)
    PIPE.install(pipe,prepared);pipe.people_suspended=None
    return prepared


def suspend(pipe,reason):
    if type(reason) is not str or not reason:raise ValueError('People suspension needs a visible reason')
    PIPE.clear(pipe);pipe.people_suspended=reason


def require_ready(pipe):
    reason=getattr(pipe,'people_suspended',None)
    if reason:raise ValueError('Retained people edits are unresolved: '+reason)


def prepare_export(snapshot,source,repaired,*,byte_budget,recovery_assets=None):
    """Original RGB8/16 enters once; all face solvers run before tile slicing."""
    from .people_snapshot import at_dimensions
    if source.dtype not in (np.uint8,np.uint16):raise ValueError('People export needs original RGB8/16')
    divisor=255 if source.dtype==np.uint8 else 65535
    state,asset,analyses=at_dimensions(snapshot,tuple(source.shape[:2]))
    rgb=np.array(source.astype(np.float32)/divisor,dtype=np.float32,copy=True)
    rgb.setflags(write=False)
    return prepare(state,asset,rgb,analyses,byte_budget=byte_budget,recovery_assets=recovery_assets,repaired=repaired)
