"""Resident levels stage: owns validated recipe and scalar parameters, no Engine state."""
import time
from .ops import levels as L

class LevelsStage:
    def __init__(self):
        self.spec=L.default_levels();self.params=(None,)*4;self.last_ms=0.

    @property
    def active(self):return any(p is not None for p in self.params)

    def state(self):return {'levels':L.check_levels(self.spec),'levels_set':self.active}

    def set(self,spec):
        checked=L.check_levels(spec);params=L.parameters(checked)
        self.spec,self.params=checked,params
        return self.state()

    def apply(self,tensor):
        self.last_ms=0.
        if not self.active:return tensor
        start=time.perf_counter();result=L.levels_t(tensor,self.params)
        if not L.torch.isfinite(result).all():raise ValueError('levels produced nonfinite pixels')
        if tensor.device.type!='cpu':L.torch.cuda.synchronize(tensor.device)
        self.last_ms=(time.perf_counter()-start)*1000.
        return result
