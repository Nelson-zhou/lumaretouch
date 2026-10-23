"""Bounded source-band bridge; host owns upstream pixels/downstream geometry.

Source bands are original-resolution rows AFTER colour transforms. Sink writes
private render storage; finish performs canonical crop/rotation/resampling and
publishes via the host fence. Never publish partial bands or guess proxy scale.
"""
from dataclasses import dataclass
from typing import Protocol, Iterable
from .photo_grain_stage import PhotoGrainStage
from . import photo_grain_state as S


@dataclass(frozen=True)
class SourceBand:
    x: int
    y: int
    pixels: object


class RenderSink(Protocol):
    def write_source_band(self, band: SourceBand): ...
    def finish(self, *, cancelled): ...
    def discard(self): ...


def render_source_bands(recipe, bands: Iterable[SourceBand], sink: RenderSink, *,
                        source_size, encoding, cancelled=lambda: False):
    """One band in/out. Original uncropped width/height; at most 64 rows per band.

    Grain units are source_pixels, never output pixels or CSS/device pixel units.
    Sink must use globally aligned reconstruction filtering/halos, not resize
    independent bands. Its private target may be disk-backed for large originals.
    """
    if not isinstance(source_size, tuple) or len(source_size) != 2 or any(type(v) is not int or not 1 <= v <= 1000000 for v in source_size):
        raise ValueError('Photo grain requires verified original source dimensions')
    width, height = source_size
    if width * height > 100000000:
        raise ValueError('Photo grain source budget exceeded')
    stage = PhotoGrainStage(recipe)
    y = 0
    try:
        for band in bands:
            if cancelled():
                raise InterruptedError('Photo grain source render cancelled')
            shape = getattr(band.pixels, 'shape', ())
            if type(band.x) is not int or type(band.y) is not int or band.x != 0 or band.y != y or len(shape) != 3 or shape[1:] != (width, 3) or not 1 <= shape[0] <= 64 or y + shape[0] > height:
                raise ValueError('Photo grain source bands must cover original rows exactly once')
            pixels = stage.apply_np(band.pixels, source_pixels=True, source_origin=(0, y), encoding=encoding, cancelled=cancelled)
            sink.write_source_band(SourceBand(0, y, pixels))
            y += shape[0]
        if y != height:
            raise ValueError('Photo grain source render incomplete')
        if cancelled():
            raise InterruptedError('Photo grain source render cancelled')
        return sink.finish(cancelled=cancelled)
    except BaseException:
        sink.discard()
        raise


def engine_renderer(engine, *, bands, sink_factory, source_size, encoding):
    """Bind after upstream colour and canonical geometry ports are wired.

    bands() supplies fresh immutable post-colour original rows for current doc.
    sink_factory(reason) makes a private host target; source_size() reads decoder.
    """
    def render(*, reason, cancelled=lambda: False):
        recipe = getattr(engine, '_photo_grain_render_override', None)
        if recipe is None:
            recipe = S.check(getattr(engine, S.KEY, S.neutral()))
        return render_source_bands(recipe, bands(), sink_factory(reason),
                                   source_size=source_size(), encoding=encoding,
                                   cancelled=cancelled)
    return render
