"""Full-source fringe finishing; no proxy detector, source-mask promotion or cache.

The guide starts at the export tile's actual repaired effective-source pixels.
It follows precisely the image's face/body warp, manual liquify, optical geometry
and final crop, but none of its smoothing, studio/background or colour changes.
This is evidence of an edit-introduced halo, not an unretouched-photo replacement.
"""
import numpy as np
from . import fringe_repair_state as S


def recipe(engine):
    override = getattr(engine, '_fringe_repair_render_override', None)
    return S.check(override) if override is not None else S.from_state(engine.__dict__)


def active(engine):
    return S.active(recipe(engine))


def check_export_decode(snapshot, path, before, shape):
    """Freeze actual decode provenance without promoting a displayed mask."""
    from .local_mask_state import file_stamp
    value = S.check(snapshot['fringe_repair']) if 'fringe_repair' in snapshot else S.neutral()
    if value['source'] is None:
        return
    if file_stamp(path) != tuple(before):
        raise ValueError('Fringe source changed during full-resolution decode')
    from .creative_derived_source import record
    source = record(snapshot)
    actual_size = (source['width'], source['height']) if source is not None else tuple(reversed(shape))
    S.verify_source(value, snapshot, path, actual_size)
    if file_stamp(path) != tuple(before):
        raise ValueError('Fringe source changed during source verification')
    snapshot['fringe_repair_path'] = path
    snapshot['fringe_repair_stamp'] = list(before)


def configure_export(spec, snapshot, shape, *, for_document):
    value = S.check(snapshot['fringe_repair']) if 'fringe_repair' in snapshot else S.neutral()
    spec.fringe_repair = value
    spec.fringe_repair_path = snapshot.get('fringe_repair_path')
    spec.fringe_repair_stamp = snapshot.get('fringe_repair_stamp')
    if value['source'] is not None and not for_document:
        raise ValueError('Fringe coverage belongs to its document; transfer parameters only')
    verify_export(spec, shape)


def verify_export(spec, shape):
    from .local_mask_state import file_stamp
    value = S.neutral() if spec.fringe_repair is None else S.check(spec.fringe_repair)
    if value['source'] is None:
        return
    path = spec.fringe_repair_path
    stamp = spec.fringe_repair_stamp
    if not path or type(stamp) is not list or len(stamp) != 5:
        raise ValueError('Fringe coverage lacks verified original-file provenance')
    if list(file_stamp(path)) != stamp:
        raise ValueError('Fringe source changed after snapshot capture')
    actual = S.verify_source(value, {'creative_base': spec.creative_base}, path, tuple(reversed(shape)))
    if tuple(shape) != (actual['height'], actual['width']):
        raise ValueError('Fringe coverage extent differs from the effective full-source canvas')
    if list(file_stamp(path)) != stamp:
        raise ValueError('Fringe source changed during render verification')


def admit(width, height, geometry=None):
    from .cpu_memory_budget import available_estimate
    if (type(width) is not int or type(height) is not int or min(width, height) < 1
            or max(width, height) > 65536 or width * height > 100_000_000):
        raise ValueError('Fringe repair exceeds the bounded full-source extent')
    from .ops.geometry import out_size
    canvas = out_size(width, height, *(geometry or ((0., 0., 1., 1.), 0.)))
    if canvas[0] * canvas[1] > 100_000_000:
        raise ValueError('Fringe repair rotated canvas exceeds the full-resolution 100 MP budget')
    # Complete edit/guide/crop/native output, mask, and bounded native scratch.
    reserve = max(width * height, canvas[0] * canvas[1]) * 224 + 256 * 1024 * 1024
    if reserve > available_estimate():
        raise MemoryError('Insufficient memory for full-source fringe repair; no proxy fallback')
    return reserve


def guide_tile(pipe):
    """Reuse actual installed image geometry and restore render timing counters."""
    deform_ms = pipe.last_deform_ms
    manual_ms = pipe.manual_liquify.last_ms
    try:
        guide = pipe.manual_liquify.apply(pipe.apply_deform(pipe.src_f32))
        return np.ascontiguousarray(guide[0].permute(1, 2, 0).detach().cpu().numpy(), dtype=np.float32)
    finally:
        pipe.last_deform_ms = deform_ms
        pipe.manual_liquify.last_ms = manual_ms


def optical_guide(guide, spec, *, cancelled=lambda: False):
    """Actual optical coordinates and interpolation space, without lens gains.

    OpticsStage switches to linear-light interpolation whenever its gain branch
    is active, including pixels where the local gain happens to be one. The
    guide must use that same branch or interpolation itself becomes a false
    halo signal. Only multiplication by the photometric gains is omitted.
    """
    from . import optics_state as O
    if not O.active(spec.optics):
        return guide
    from .optics_stage import OpticsStage, linear, encoded
    from .optics_native import sample
    stage = OpticsStage(spec.optics, guide.shape[:2])
    result = np.empty_like(guide)
    # optics_native.sample accepts a complete f64 source. Normalize once, not
    # another full-frame copy for every band and colour channel.
    source = np.ascontiguousarray(guide, dtype=np.float64)
    interpolate_linear = ((stage.profile.gains() if stage.profile else None) is not None
                          or bool(stage.value['lens']['vignette']))
    if interpolate_linear:
        for y in range(0, len(guide), 64):
            if cancelled():
                raise InterruptedError('Fringe optical guide cancelled')
            source[y:y + 64] = linear(source[y:y + 64])
    rows = max(1, min(64, 1_048_576 // guide.shape[1]))
    for y in range(0, len(guide), rows):
        if cancelled():
            raise InterruptedError('Fringe optical guide cancelled')
        count = min(rows, len(guide) - y)
        coordinates = stage.coordinates(y0=y, rows=count)
        band = np.empty((count, guide.shape[1], 3), np.float64)
        for channel in range(3):
            band[..., channel] = sample(source, coordinates[..., channel, :])[..., channel]
        if interpolate_linear:
            band = encoded(band)
        if not np.isfinite(band).all():
            raise ValueError('Fringe optical guide contains nonfinite pixels')
        result[y:y + count] = band
    return result


def apply_export(edited, guide, spec, *, source_size, geometry, cancelled=lambda: False):
    value = S.neutral() if spec.fringe_repair is None else S.check(spec.fringe_repair)
    capture = bool(getattr(spec, '_fringe_repair_capture_coverage', False))
    if not S.active(value) and not capture:
        return edited
    if int(spec.scale) != 1:
        raise ValueError('Fringe repair must precede delivery resizing')
    if S.active(value) and (not isinstance(guide, np.ndarray) or guide.dtype != np.float32
            or guide.shape != edited.shape or not np.isfinite(guide).all()):
        raise ValueError('Fringe repair requires the exact co-registered full-resolution guide')
    from .fringe_repair_geometry import coverage
    mask = coverage(value, source_size, geometry, (edited.shape[1], edited.shape[0]), cancelled=cancelled)
    output = edited
    if S.active(value):
        from .fringe_repair_native import render
        output = render(edited, guide, value, mask, cancelled=cancelled)
    if capture:
        # This is processing eligibility, NOT detected candidates or successes.
        spec._fringe_repair_coverage = mask
    return output
