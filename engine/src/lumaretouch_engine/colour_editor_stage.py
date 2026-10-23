"""Single full-domain stage shared by source/preview/export/inspection paths."""
import numpy as np
from . import colour_editor_state as S
from .colour_editor_native import FullDomain
class ColourEditorStage:
    def __init__(self, recipe):
        self.recipe = S.check(recipe); self.active = S.active(recipe)
        self.domain = FullDomain(); self.cancelled = lambda: False
        self.show_range = False; self.external_mask = None
        self.canonical = None; self.domain_identity = None
    def prepare_source(self, pixels, identity, *, mask=None, cancelled=None):
        if not isinstance(identity, tuple) or len(identity) != 4 or any(not isinstance(v, str) or not v for v in identity):
            raise ValueError('Source identity needs document, upstream revision, geometry and external-mask revision')
        self.canonical = self.domain.apply(pixels, self.recipe, mask=mask, cancelled=cancelled or self.cancelled, prepare_only=True)
        self.domain_identity = identity
    def require_identity(self, identity):
        if self.domain_identity != identity: raise ValueError('Full-domain colour target stale; prepare source again')
    def apply_np(self, pixels, *, encoding='extended-srgb-d65', cancelled=None, purpose='render', full_domain=True):
        if purpose not in ('render', 'export', 'inspection', 'selection-view'): raise ValueError('Unknown colour editor stage purpose')
        view = purpose == 'selection-view'
        if not self.active and not view: return pixels
        if not full_domain: raise ValueError('Colour editor needs full operator domain before ROI/tile slicing; tile-local uniformity forbidden')
        if encoding != S.SPACE: raise ValueError('Colour editor requires extended encoded sRGB; decode/encode outside stage')
        if any(self.recipe['uniformity']) and self.canonical is None:
            raise ValueError('Uniformity requires canonical full-source statistics before preview/export/inspection')
        return self.domain.apply(pixels, self.recipe, mask=self.external_mask, view=view, cancelled=cancelled or self.cancelled, canonical=self.canonical)
    def apply_t(self, pixels, *, cancelled=None, purpose='render', full_domain=True):
        if not self.active and purpose != 'selection-view': return pixels
        import torch
        if pixels.ndim != 4 or pixels.shape[0] != 1 or pixels.shape[1] != 3 or not pixels.is_floating_point(): raise ValueError('Colour editor requires one full NCHW float image')
        if pixels.numel() > 300_000_000: raise ValueError('Colour editor tensor exceeds domain budget')
        from .cpu_memory_budget import available_estimate
        if pixels.numel()*8 + 256*1024**2 > available_estimate(): raise MemoryError('Colour editor CPU bridge exceeds memory budget')
        stop = cancelled or self.cancelled
        if stop(): raise InterruptedError('Colour editor cancelled')
        # CPU bridge is deliberate, not a claimed GPU kernel or performance pass.
        source = pixels.detach().to(device='cpu', dtype=torch.float32)[0].permute(1,2,0).contiguous().numpy()
        result = self.apply_np(source, cancelled=stop, purpose=purpose, full_domain=full_domain)
        if stop(): raise InterruptedError('Colour editor cancelled before device publication')
        return torch.from_numpy(result).permute(2,0,1).unsqueeze(0).to(device=pixels.device, dtype=torch.float32)
