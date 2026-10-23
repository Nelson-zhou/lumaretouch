"""Original-source editor render path, shared with source-grain delivery."""
from . import colour_editor_state as S

def active(engine):
    stage=getattr(getattr(engine,'_vram',None),'colour_editor',None)
    return bool(stage is not None and (stage.active or stage.show_range)) or S.active(getattr(engine,S.KEY,S.neutral()))

def render_preview(engine, *, pack=True, input_only=False):
    from .photo_grain_runtime import render_preview as render_source
    return render_source(engine,pack=pack,editor_mode='input' if input_only else 'view' if getattr(engine._vram.colour_editor,'show_range',False) else 'render')
