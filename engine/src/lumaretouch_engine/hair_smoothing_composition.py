# SPDX-License-Identifier: GPL-3.0-or-later
"""Same frozen hair smoothing field on actual current pixels, never a source RGB delta.

apply_np/apply_t accept CURRENT LINEAR RGB; apply_records_np/apply_records_t are
encoded-working-sRGB pipeline adapters using existing transfer helpers. All gain
and headroom algebra is the independent native kernel, with no Python numerical
fallback. Signed source proposals are composed independently of current chroma.
Only genuinely changed pixels enter an encoded colour-space roundtrip.
Full-resolution tiles slice the solved field by true expanded (y,x) origin.
AUTHORED / UNRUN.
"""
import numpy as np

from . import hair_smoothing_state as S
from . import people_state as P

STAGE = 'hair_smoothing'
MAX_CHUNK_PIXELS = 65536
_FIXED_BYTES = 32 * 1024**2


def _poll(cancelled):
    if cancelled is not None and cancelled():
        raise InterruptedError('Hair smoothing composition cancelled; no partial output published')


def _strips(y0, x0, y1, x1):
    rows = max(1, MAX_CHUNK_PIXELS // (x1-x0))
    for y in range(y0, y1, rows):
        yield y, x0, min(y+rows, y1), x1


def _extent(shape, source_shape, origin):
    if (type(source_shape) not in (tuple, list) or len(source_shape) != 2
            or any(type(n) is not int or not 1 <= n <= 65536 for n in source_shape)
            or type(origin) not in (tuple, list) or len(origin) != 2
            or any(type(n) is not int or n < 0 for n in origin)):
        raise ValueError('Hair smoothing composition needs exact source extent and expanded-tile origin')
    y, x = origin; h, w = shape
    if min(h, w) < 1 or y+h > source_shape[0] or x+w > source_shape[1]:
        raise ValueError('Hair smoothing current pixels lie outside the frozen source grid')
    return tuple(source_shape), tuple(origin)


def _selected(records):
    result = []
    for record in records:
        if record.stage != STAGE:
            continue
        if type(record.amounts) is not dict or set(record.amounts) != {'amount'}:
            raise ValueError('Hair smoothing field lost its independently checked amount')
        amount = S.check({'version': 1, 'amount': record.amounts['amount']})['amount']
        if amount:
            result.append((record, amount))
    return result


def _retained_bytes(selected):
    total = 0
    for record, _ in selected:
        if type(record.log_gain) is not np.ndarray:
            raise ValueError('Hair smoothing composition requires an existing immutable scalar field')
        if type(record.eligibility) is not np.ndarray:
            raise ValueError('Hair smoothing composition requires frozen exact eligibility')
        total += record.log_gain.nbytes + record.eligibility.nbytes
    return total


def _check_application_grid(facts, application_shape, ref):
    canonical = facts.get('source_shape_hw')
    if (type(canonical) is not list or len(canonical) != 2
            or any(type(n) is not int or not 2 <= n <= 65536 for n in canonical)):
        raise ValueError('Hair smoothing field lost its actual canonical measurement dimensions')
    if facts.get('application_shape_hw', canonical) != list(application_shape):
        raise ValueError('Hair smoothing field application extent differs from the current grid; never enlarge a preview field')
    projection = facts.get('display_projection')
    if canonical == list(application_shape):
        if projection is not None or facts.get('review_authority', True) is not True:
            raise ValueError('Projected hair smoothing preview cannot masquerade as canonical export/review evidence')
        return
    expected = {'version': 1, 'kind': 'canonical-field-preview-only',
        'mapping': 'source-pixel-edge-centres-cv2-linear',
        'canonical_shape_hw': canonical, 'application_shape_hw': list(application_shape),
        'authorizes_review': False, 'authorizes_export': False}
    if projection != expected or facts.get('review_authority') is not False:
        raise ValueError('Reduced hair smoothing application requires explicitly labelled display-only projection')
    from .body_pose_evidence import whole_source_shape, ORIENTATION
    whole_source_shape({'sha256': ref['asset_sha256'], 'width': canonical[1],
                        'height': canonical[0], 'orientation': ORIENTATION}, application_shape)


def _checked(selected, recovery, source_shape, cancelled):
    from .hair_smoothing_measure import MAX_LOG_GAIN
    if recovery is not None and type(recovery) is not dict:
        raise ValueError('Hair smoothing recovery must remain the canonical map or absent')
    if any(type(key) is tuple and len(key) == 2 and key[1] == STAGE for key in (recovery or {})):
        raise ValueError('Hair smoothing FaceRef/visible-support recovery is not implemented; generic face recovery is fenced')
    seen = set(); common_source = None; common_proof = None
    for record, _ in selected:
        _poll(cancelled)
        ref = P.check_ref(record.face_ref)
        if ref['face_instance_id'] in seen:
            raise ValueError('Each owned hair smoothing may be composed only once')
        seen.add(ref['face_instance_id'])
        window = record.window
        if type(window) not in (tuple, list) or len(window) != 4 or any(type(n) is not int for n in window):
            raise ValueError('Hair smoothing field lost its integer full-source ROI')
        y, x, h, w = window
        if min(y, x) < 0 or min(h, w) < 1 or y+h > source_shape[0] or x+w > source_shape[1]:
            raise ValueError('Hair smoothing field exceeds the original canonical source domain')
        field = record.log_gain
        if (type(field) is not np.ndarray or field.dtype != np.float32
                or field.shape != (h, w, 1) or field.flags.writeable or not field.flags.c_contiguous
                or record.delta is not None or record.chroma_shift is not None or record.weights is not None):
            raise ValueError('Hair smoothing requires a readonly scalar source-owned log-gain, not RGB/chroma replacement')
        eligible = record.eligibility
        if (type(eligible) is not np.ndarray or eligible.dtype != np.bool_
                or eligible.shape != (h, w) or eligible.flags.writeable or not eligible.flags.c_contiguous):
            raise ValueError('Hair smoothing requires immutable exact complete-context eligibility beside its field')
        facts = record.facts
        if (type(facts) is not dict or facts.get('operation_id') != S.OP
                or facts.get('face_ref') != ref or facts.get('runtime_quality_accepted') is not False
                or type(facts.get('source_proof')) is not dict or not facts['source_proof']):
            raise ValueError('Hair smoothing field source/owner evidence changed')
        _check_application_grid(facts, source_shape, ref)
        P.digest(facts.get('measurement_key'))
        if common_source is None:
            common_source = ref['asset_sha256']; common_proof = facts.get('source_proof')
        if ref['asset_sha256'] != common_source or facts.get('source_proof') != common_proof:
            raise ValueError('Hair smoothing fields cannot mix different effective sources or repair stages')
        for top, left, bottom, right in _strips(0, 0, h, w):
            _poll(cancelled); part = field[top:bottom, left:right]
            if not np.isfinite(part).all() or np.any(np.abs(part.astype(np.float64)) > MAX_LOG_GAIN):
                raise ValueError('Hair smoothing field is nonfinite or over the symmetric signed luminance-gain cap')
            admitted = eligible[top:bottom, left:right]
            if np.any((part[..., 0] != 0) & ~admitted):
                raise ValueError('Hair smoothing field changed a center outside its frozen exact eligibility')
    # Full-domain pairwise preflight happens even for an unrelated output tile.
    # No sort order or partially rendered first person can hide a later overlap.
    for index, (one, _) in enumerate(selected):
        ay, ax, ah, aw = one.window
        for two, _ in selected[index+1:]:
            by, bx, bh, bw = two.window
            y0, x0, y1, x1 = max(ay, by), max(ax, bx), min(ay+ah, by+bh), min(ax+aw, bx+bw)
            if y1 <= y0 or x1 <= x0:
                continue
            for top, left, bottom, right in _strips(y0, x0, y1, x1):
                _poll(cancelled)
                a = one.eligibility[top-ay:bottom-ay, left-ax:right-ax]
                b = two.eligibility[top-by:bottom-by, left-bx:right-bx]
                if np.any(a & b):
                    raise ValueError('Hair smoothing fields overlap another owner; no sorted-person priority winner')


def _admit(current_bytes, output_bytes, retained_bytes, tile_pixels, byte_budget):
    if byte_budget is not None and (type(byte_budget) is not int or byte_budget < 0):
        raise ValueError('Hair smoothing composition byte budget must be a nonnegative integer')
    from .cpu_memory_budget import available_estimate
    available = available_estimate()
    if type(available) is not int or available < 0:
        raise MemoryError('Hair smoothing available-memory estimate is unavailable')
    allowed = available if byte_budget is None else min(available, byte_budget)
    # Gather/transfer/validation and native input/output private snapshots are
    # charged together; this is conservative admission, not measured RSS/VRAM.
    required = current_bytes + output_bytes + retained_bytes + min(tile_pixels, MAX_CHUNK_PIXELS)*128 + _FIXED_BYTES
    if required > allowed:
        raise MemoryError('Hair smoothing current-stage composition exceeds aggregate memory admission')


def _validate_pixels(current, cancelled):
    h, w = current.shape[:2]
    for y, x, end_y, end_x in _strips(0, 0, h, w):
        _poll(cancelled); part = current[y:end_y, x:end_x]
        if not np.isfinite(part).all() or np.any((part < 0) | (part > 1)):
            raise ValueError('Hair smoothing composition refuses nonfinite or HDR current pixels rather than clipping')


def _native(current, field, amount, *, encoded, cancelled):
    """Gather only active current pixels; the kernel alone chooses common gain."""
    take = (field != 0) & ((field < 0) | (np.max(current, axis=2) < 1)) & np.any(current != 0, axis=2)
    if not np.any(take):
        return current
    selected = np.ascontiguousarray(current[take][:, None, :], dtype=np.float32)
    gain = np.ascontiguousarray(field[take][:, None], dtype=np.float32)
    linear = selected
    if encoded:
        from .third_party.rapidretouch.eye_colour import srgb_to_linear
        linear = np.ascontiguousarray(srgb_to_linear(selected), dtype=np.float32)
    from .hair_smoothing_measure import apply
    updated = apply(linear, gain, amount=amount, cancelled=cancelled)
    if (type(updated) is not np.ndarray or updated.dtype != np.float32
            or updated.shape != linear.shape or not np.isfinite(updated).all()
            or np.any((updated < 0) | (updated > 1))):
        raise ValueError('Hair smoothing native composition returned invalid current-stage linear RGB')
    changed = np.any(updated.view(np.uint32) != linear.view(np.uint32), axis=2)[:, 0]
    if not np.any(changed):
        return current
    if encoded:
        from .third_party.rapidretouch.eye_colour import linear_to_srgb
        converted = np.ascontiguousarray(linear_to_srgb(updated[changed]), dtype=np.float32)
        if not np.isfinite(converted).all() or np.any((converted < 0) | (converted > 1)):
            raise ValueError('Hair smoothing linear-to-sRGB transport exceeded SDR; no independent channel clipping')
        corrected = selected.copy()
        corrected[changed] = converted
    else:
        corrected = updated
    # Preserve every zero-field/zero-headroom/zero-native-change pixel bitwise.
    output = current.copy()
    merged = selected.copy(); merged[changed] = corrected[changed]
    output[take] = merged[:, 0, :]
    return output


def _apply_np(current, records, recovery, *, source_shape, origin, byte_budget, cancelled, encoded):
    selected = _selected(records)
    if not selected:
        return current, {'stage': STAGE, 'overlap_pixels': 0, 'changed_pixels': 0}
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    _poll(cancelled)
    if (type(current) is not np.ndarray or current.dtype != np.float32
            or current.ndim != 3 or current.shape[2] != 3):
        raise ValueError('Hair smoothing composition requires current float32 HWC RGB without alpha')
    h, w = current.shape[:2]
    source_shape, origin = _extent((h, w), (h, w) if source_shape is None else source_shape, origin)
    _admit(current.nbytes, current.nbytes, _retained_bytes(selected), h*w, byte_budget)
    _checked(selected, recovery, source_shape, cancelled)
    _validate_pixels(current, cancelled)
    output = current; changed = 0; oy, ox = origin
    for record, amount in selected:
        y, x, rh, rw = record.window
        y0, x0, y1, x1 = max(y, oy), max(x, ox), min(y+rh, oy+h), min(x+rw, ox+w)
        if y1 <= y0 or x1 <= x0:
            continue
        for top, left, bottom, right in _strips(y0, x0, y1, x1):
            _poll(cancelled)
            field = record.log_gain[top-y:bottom-y, left-x:right-x, 0]
            if not np.any(field != 0):
                continue
            before = current[top-oy:bottom-oy, left-ox:right-ox]
            after = _native(before, field, amount, encoded=encoded, cancelled=cancelled)
            count = int(np.count_nonzero(np.any(after.view(np.uint32) != before.view(np.uint32), axis=2)))
            if count:
                if output is current:
                    output = current.copy()
                output[top-oy:bottom-oy, left-ox:right-ox] = after
                changed += count
    _poll(cancelled)
    return output, {'stage': STAGE, 'overlap_pixels': 0, 'changed_pixels': changed,
                    'application': 'native-common-linear-RGB-gain-on-current-stage',
                    'input_encoding': 'working-sRGB' if encoded else 'linear-sRGB',
                    'display_only_approximation': any(r.facts.get('display_projection') is not None for r, _ in selected),
                    'runtime_quality_accepted': False}


def apply_np(current, records, recovery=None, *, source_shape=None, origin=(0, 0), byte_budget=None, cancelled=None):
    """CURRENT LINEAR float32 RGB application using the frozen full-source field."""
    return _apply_np(current, records, recovery, source_shape=source_shape, origin=origin,
                     byte_budget=byte_budget, cancelled=cancelled, encoded=False)


def apply_records_np(current, records, recovery=None, *, source_shape=None, origin=(0, 0), byte_budget=None, cancelled=None):
    """Existing encoded-working-sRGB people-pipeline adapter."""
    return _apply_np(current, records, recovery, source_shape=source_shape, origin=origin,
                     byte_budget=byte_budget, cancelled=cancelled, encoded=True)


def _apply_t(pixels, records, recovery, *, source_shape, origin, byte_budget, cancelled, encoded):
    selected = _selected(records)
    if not selected:
        return pixels
    import torch
    if (not isinstance(pixels, torch.Tensor) or pixels.dtype != torch.float32
            or pixels.ndim != 4 or pixels.shape[0] != 1 or pixels.shape[1] != 3):
        raise ValueError('Hair smoothing tensor composition requires float32 NCHW RGB')
    h, w = pixels.shape[2:]
    source_shape, origin = _extent((h, w), source_shape, origin)
    _admit(int(pixels.numel())*4, int(pixels.numel())*4,
           _retained_bytes(selected), h*w, byte_budget)
    _checked(selected, recovery, source_shape, cancelled)
    for y, x, end_y, end_x in _strips(0, 0, h, w):
        _poll(cancelled); part = pixels[:, :, y:end_y, x:end_x]
        if not bool(torch.isfinite(part).all()) or bool(torch.any((part < 0) | (part > 1))):
            raise ValueError('Hair smoothing composition refuses HDR or nonfinite current pixels')
    output = pixels; oy, ox = origin
    for record, amount in selected:
        y, x, rh, rw = record.window
        y0, x0, y1, x1 = max(y, oy), max(x, ox), min(y+rh, oy+h), min(x+rw, ox+w)
        if y1 <= y0 or x1 <= x0:
            continue
        for top, left, bottom, right in _strips(y0, x0, y1, x1):
            _poll(cancelled)
            field = record.log_gain[top-y:bottom-y, left-x:right-x, 0]
            if not np.any(field != 0):
                continue
            before = pixels[0, :, top-oy:bottom-oy, left-ox:right-ox]
            current = before.detach().permute(1, 2, 0).contiguous().to('cpu').numpy()
            after = _native(current, field, amount, encoded=encoded, cancelled=cancelled)
            if after is current:
                continue
            if np.array_equal(after.view(np.uint32), current.view(np.uint32)):
                continue
            if output is pixels:
                output = pixels.clone()
            updated = torch.from_numpy(after).permute(2, 0, 1).to(device=pixels.device, dtype=pixels.dtype)
            output[0, :, top-oy:bottom-oy, left-ox:right-ox] = updated
    _poll(cancelled)
    return output


def apply_t(pixels, records, recovery=None, *, source_shape, origin=(0, 0), byte_budget=None, cancelled=None):
    """CURRENT LINEAR tensor application, bounded strips through the same kernel."""
    return _apply_t(pixels, records, recovery, source_shape=source_shape, origin=origin,
                    byte_budget=byte_budget, cancelled=cancelled, encoded=False)


def apply_records_t(pixels, records, recovery=None, *, source_shape, origin=(0, 0), byte_budget=None, cancelled=None):
    """Encoded-sRGB tensor adapter; origin names the true expanded export tile."""
    return _apply_t(pixels, records, recovery, source_shape=source_shape, origin=origin,
                    byte_budget=byte_budget, cancelled=cancelled, encoded=True)
