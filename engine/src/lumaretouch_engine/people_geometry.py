"""Actual all-face source-space geometry, reusing existing operation solvers.

Stable-instance priority partitions overlapping nonzero geometric supports. One
face owns each output sample; fields are not summed across people. Refuse folded
joint maps. Photographic quality and between-sample injectivity remain QA gates.
"""
from dataclasses import dataclass
import numpy as np
from .ops import deform as D
from .brow_shape_field import smoothstep


class AutomaticField:
    """Existing linear unit-field semantics, evaluated in bounded CPU bands."""
    def __init__(self, landmarks, amounts, shape):
        self.shape = tuple(shape); self.units = []; self.windows = []
        h, w = shape
        for kind, amount in D.check_amounts(amounts).items():
            if not amount: continue
            p, d, meta = D.controls(landmarks, kind, 1., h, w)
            cx, cy, radius, _, _ = meta['frame']
            r0, r1 = D.support_radii(radius)
            self.units.append((D.tps_solve(p, d, scale=float(max(shape))), amount, np.array([cx, cy]), r0, r1))
            self.windows.append((np.array([cx, cy]), r0, r1))

    def evaluate(self, points):
        total = np.zeros_like(points, dtype=np.float64)
        for state, amount, center, r0, radius in self.units:
            support = 1 - smoothstep((np.linalg.norm(points-center, axis=1)-r0)/max(radius-r0, 1e-9))
            active = support > 0
            if np.any(active): total[active] += D.tps_eval(state, points[active]) * (amount * support[active, None])
        if not np.isfinite(total).all(): raise ValueError('Automatic face geometry produced nonfinite values')
        return total

    def resident_bytes(self):
        return sum(v.nbytes for state, *_ in self.units for v in state.values() if isinstance(v, np.ndarray))


@dataclass(frozen=True)
class FaceGeometry:
    face_instance_id: str
    shape: tuple
    automatic: object
    fields: tuple

    def evaluate(self, points):
        total = self.automatic.evaluate(points)
        # Exact off-grid legacy M(E(N(B(A(x))))) then optional contour C.
        # Not a sum of independently sampled grids; one final image sampler.
        for field in self.fields:
            if field is not None and field.state is not None: total += field.evaluate(points-total)
        return total

    def resident_bytes(self):
        return self.automatic.resident_bytes() + sum(f.resident_bytes() for f in self.fields if f is not None)


@dataclass(frozen=True)
class CombinedGeometry:
    delta: object
    owner: object
    peak: float
    overlap_pixels: int
    face_ids: tuple

    def warp(self, source):
        """Same map for RGB, masks, recovery deltas and authentic-scene support."""
        a = np.asarray(source)
        h, w = self.delta.shape[1:3]
        if a.ndim not in (2, 3) or a.shape[:2] != (h, w) or a.dtype.kind not in 'uif':
            raise ValueError('Source-owned field must match the frozen source frame')
        if not np.isfinite(a).all(): raise ValueError('Cannot warp nonfinite source data')
        chw = a[None] if a.ndim == 2 else a.transpose(2, 0, 1)
        # Floating intermediate avoids quantizing RGB8/16 until the final output.
        warped = D.warp_np(chw.astype(np.float32), self.delta)
        return warped[0] if a.ndim == 2 else warped.transpose(1, 2, 0)

    def warp_original(self, source):
        if source.dtype not in (np.uint8, np.uint16): raise ValueError('Original export requires RGB8 or RGB16')
        out = self.warp(source)
        return np.rint(np.clip(out, 0, np.iinfo(source.dtype).max)).astype(source.dtype)


def combine(faces, shape, *, byte_budget, band_pixels=65536):
    h, w = shape
    if type(byte_budget) is not int or byte_budget < h*w*24:
        raise ValueError('Multi-person joint map exceeds admitted memory budget')
    if type(band_pixels) is not int or band_pixels < 1: raise ValueError('Invalid geometry band budget')
    ordered = sorted(faces, key=lambda f: f.face_instance_id)
    if len({f.face_instance_id for f in ordered}) != len(ordered): raise ValueError('Duplicate face geometry would repeat strength')
    if any(f.shape != tuple(shape) for f in ordered): raise ValueError('Face fields must share one source coordinate frame')
    if sum(f.resident_bytes() for f in ordered) + h*w*24 > byte_budget:
        raise ValueError('Face fields plus joint map exceed admitted memory budget')
    delta = np.zeros((1, h, w, 2), np.float32)
    owner = np.full((h, w), -1, np.int32); overlap = 0
    rows = max(1, band_pixels//w)
    for y in range(0, h, rows):
        end = min(h, y+rows); yy, xx = np.mgrid[y:end, :w]
        points = np.stack((xx.ravel(), yy.ravel()), axis=1).astype(np.float64)
        block = np.zeros_like(points); ownership = np.full(len(points), -1, np.int32)
        collided = np.zeros(len(points), bool)
        for i, face in enumerate(ordered):
            values = face.evaluate(points)
            if values.shape != points.shape or not np.isfinite(values).all(): raise ValueError('Invalid per-face joint field')
            active = np.any(values != 0, axis=1)
            collided |= active & (ownership >= 0)
            take = active & (ownership < 0)
            block[take] = values[take]; ownership[take] = i
        delta[0, y:end] = block.reshape(end-y, w, 2)
        owner[y:end] = ownership.reshape(end-y, w)
        overlap += int(np.count_nonzero(collided))
    # Check the final partition too, not only individual TPS fields. This catches
    # contradictory overlapping requests instead of exporting a torn boundary.
    if min(h, w) > 1:
        for y in range(0, h-1, rows):
            end = min(h-1, y+rows)
            base = delta[0, y:end, :-1]
            dx = delta[0, y:end, 1:] - base
            dy = delta[0, y+1:end+1, :-1] - base
            jacobian = (1-dx[..., 0])*(1-dy[..., 1])-dy[..., 0]*dx[..., 1]
            if not np.isfinite(jacobian).all() or np.any(jacobian < .15):
                raise ValueError('Overlapping people geometry risks a fold; reduce or separate the requested edits')
    peak = float(np.max(np.abs(delta))) if delta.size else 0.
    delta.setflags(write=False); owner.setflags(write=False)
    return CombinedGeometry(delta, owner, peak, overlap, tuple(f.face_instance_id for f in ordered))
