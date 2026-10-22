"""Small portrait command adapters, extracted from the capped server host."""
def _emit(value):
    from .server import emit
    emit(value)

class PortraitGeometryMixin:
    def cmd_lip_makeup(self,p):
        from .lip_makeup_command import apply
        apply(self,p,_emit)

    def cmd_brow_shape(self,p):
        from .brow_shape_receipts import apply
        apply(self,p,_emit)

    def finish_brow_shape(self,p,error):
        from .brow_shape_receipts import finish
        finish(self,p,error,_emit)
