# SPDX-License-Identifier: GPL-3.0-or-later
"""Compact target-control TPS pullback; composed before ONE final RGB sampler.

Reuse the existing normalized TPS implementation, not an unrelated facial
operator's protection policy. TPS reference: F. L. Bookstein, Principal Warps,
IEEE TPAMI 11(6), 1989, https://doi.org/10.1109/34.24792 . No external code copied.
Numerical Jacobian probes are conservative refusal, not an injectivity proof or
photographic acceptance. Moving the silhouette transports nearby background in
the bounded halo; this does not claim perfect foreground/background isolation.
"""
from __future__ import annotations

from copy import deepcopy
import numpy as np

from .ops.deform import tps_solve, tps_eval
from .face_contour_geometry import IDENTITY_POLYGONS, polygon_inside


def smoothstep(t):
    t = np.clip(t, 0., 1.)
    return t * t * (3. - 2. * t)


def segment_distance(points, a, b):
    d = b - a
    den = float(d @ d)
    if den < 1e-12:
        return np.linalg.norm(points - a, axis=1)
    t = np.clip((points - a) @ d / den, 0., 1.)
    return np.linalg.norm(points - a - t[:, None] * d, axis=1)


class FaceContourField:
    def __init__(self, P, D, meta, shape):
        self.shape = tuple(shape)
        self.facts = deepcopy(meta['controls'])
        self.merged = meta['merged']
        self.width = float(meta['width'])
        self.landmarks = np.array(meta['landmarks'], dtype=np.float64, copy=True)
        self.windows = tuple((np.array(c, dtype=np.float64, copy=True), float(r0), float(r1))
                             for c, r0, r1 in meta['windows'])
        self.pinned_segments = np.array(meta['pinned_segments'], dtype=np.float64, copy=True)
        self.source_contour = np.array(meta['source_contour'], dtype=np.float64, copy=True)
        self.target_contour = np.array(meta['target_contour'], dtype=np.float64, copy=True)
        self.batch = max(1, 2_000_000 // max(1, len(P)))
        # Distinct checked controls, an affine tail and exact interpolation; do
        # not smooth away a requested movement with regularization or a fallback.
        self.state = tps_solve(P, D, lam=0., scale=float(max(shape))) if self.windows else None
        if self.state is not None:
            requested_P = np.asarray(meta['requested_P'], np.float64)
            requested_D = np.asarray(meta['requested_D'], np.float64)
            actual = self.evaluate(requested_P)
            difference = actual - requested_D
            error = np.hypot(difference[:, 0], difference[:, 1])
            motion = np.hypot(requested_D[:, 0], requested_D[:, 1])
            # Moving controls get a RELATIVE tolerance, so a tiny nonzero edit
            # cannot disappear inside a fixed absolute-error allowance.
            tolerance = np.where(motion > 0, motion * 1e-4, 1e-6)
            if np.any(error > tolerance):
                raise ValueError('Face contour protection or TPS would attenuate a requested control; no silent reduction')
            self.control_error_px = float(np.max(error))
            self.minimum_jacobian = self._check_fold(requested_P)
        else:
            self.control_error_px = 0.
            self.minimum_jacobian = 1.
        for fact in self.facts.values():
            fact['control_error_px'] = self.control_error_px
            fact['sampled_minimum_jacobian'] = self.minimum_jacobian
            fact['fold_check'] = 'numerical_probes_not_between_sample_injectivity_proof'
        for value in (self.landmarks, self.pinned_segments, self.source_contour, self.target_contour,
                      *(c for c, _, _ in self.windows)):
            value.setflags(write=False)
        for value in (self.state or {}).values():
            if isinstance(value, np.ndarray):
                value.setflags(write=False)

    def _protection(self, points):
        factor = np.ones(len(points), np.float64)
        clearance = max(.6, self.width * .025)
        for ids in IDENTITY_POLYGONS:
            poly = self.landmarks[list(ids)]
            distance = np.full(len(points), np.inf)
            for a, b in zip(poly, np.roll(poly, -1, axis=0)):
                distance = np.minimum(distance, segment_distance(points, a, b))
            factor *= np.where(polygon_inside(points, poly), 0., smoothstep(distance / clearance))
        # Entire inactive contour segments, not only isolated pins, remain
        # identity. If that protection conflicts with motion, __init__ refuses.
        for a, b in self.pinned_segments:
            factor *= smoothstep(segment_distance(points, a, b) / clearance)
        return factor

    def evaluate(self, points):
        X = np.asarray(points, dtype=np.float64)
        if X.ndim != 2 or X.shape[1] != 2 or not np.isfinite(X).all():
            raise ValueError('Face contour evaluation needs finite Nx2 pixel coordinates')
        out = np.zeros_like(X)
        if self.state is None:
            return out
        for start in range(0, len(X), self.batch):
            q = X[start:start + self.batch]
            outside = np.ones(len(q), np.float64)
            for center, flat, radius in self.windows:
                weight = 1. - smoothstep((np.linalg.norm(q - center, axis=1) - flat) / (radius - flat))
                # Smooth union, unlike max(window_i), whose intersections have
                # derivative kinks. Flat cores retain exact unit weight.
                outside *= 1. - weight
            window = (1. - outside) * self._protection(q)
            active = window > 0
            if np.any(active):
                out[start:start + len(q)][active] = tps_eval(self.state, q[active]) * window[active, None]
        if not np.isfinite(out).all():
            raise ValueError('Face contour TPS produced nonfinite displacement')
        return out

    def _check_fold(self, controls):
        eps = max(.03, self.width * 1e-4)
        minimum = 1.
        probes = [controls, self.source_contour, self.target_contour]
        angle = np.arange(96, dtype=np.float64) * (2 * np.pi / 96)
        circle = np.stack((np.cos(angle), np.sin(angle)), axis=1)
        for center, flat, radius in self.windows:
            yy, xx = np.mgrid[-1:1:49j, -1:1:49j]
            probes.append(np.stack((xx.ravel(), yy.ravel()), axis=1) * radius + center)
            for r in (flat, (flat + radius) * .5, radius):
                probes.append(circle * r + center)
        for X in probes:
            dx = (self.evaluate(X + [eps, 0]) - self.evaluate(X - [eps, 0])) / (2 * eps)
            dy = (self.evaluate(X + [0, eps]) - self.evaluate(X - [0, eps])) / (2 * eps)
            determinant = (1 - dx[:, 0]) * (1 - dy[:, 1]) - dy[:, 0] * dx[:, 1]
            if not np.isfinite(determinant).all() or np.any(determinant < .20):
                raise ValueError('Face contour pullback risks a fold; reduce or separate requested controls')
            if np.any(np.linalg.norm(self.evaluate(X), axis=1) > self.width * .08 + 1e-8):
                raise ValueError('Face contour TPS overshoots the aggregate displacement bound')
            minimum = min(minimum, float(np.min(determinant)))
        return minimum

    def resident_bytes(self):
        return (self.landmarks.nbytes + self.pinned_segments.nbytes + self.source_contour.nbytes
                + self.target_contour.nbytes + sum(c.nbytes for c, _, _ in self.windows)
                + sum(v.nbytes for v in (self.state or {}).values() if isinstance(v, np.ndarray)))
