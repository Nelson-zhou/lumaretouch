"""Source-stage only: proxy/crop transform must follow this stage, not precede it."""
from . import photo_grain_state as S
from .photo_grain_native import apply


class PhotoGrainStage:
    def __init__(self, recipe):
        self.recipe = S.check(recipe)
        self.active = S.active(recipe)
        self.cancelled = lambda: False

    def apply_np(self, pixels, *, encoding='extended-srgb-d65', source_origin=None,
                 source_pixels=False, cancelled=None):
        if not self.active:
            return pixels  # Exact legacy neutral bypass without native loading.
        if not source_pixels or source_origin is None:
            raise ValueError('Active grain needs original-resolution source bands and source coordinates; proxy grain is not equivalent')
        return apply(pixels, self.recipe, encoding=encoding, source_origin=source_origin,
                     cancelled=cancelled or self.cancelled)

    def apply_t(self, pixels, **kwargs):
        if not self.active:
            return pixels
        raise ValueError('Photo grain must run on source RGB before host proxy/tensor resampling')
