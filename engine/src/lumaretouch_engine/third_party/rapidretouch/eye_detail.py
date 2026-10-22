# SPDX-License-Identifier: AGPL-3.0-only
# Copyright Chris Cork. Adapted for LumaRetouch, 2026-10-22. See UNDER_EYE_NOTICE.
"""Existing catchlight enhancement and scleral vein correction, not synthetic eyes.

Derived from pinned RapidRetouch eyes.py. No iris recolouring or lash makeup is
exposed: those do not match the frozen portrait-enhancement control contract.
"""
from __future__ import annotations
import numpy as np
from .under_eye import (cv2, EYES, MIN_EYE_PX, FORESHORTENED, _eye_geometry,
                        _poly_mask, _inner_feather, _smoothstep, _line_strength)
from .eye_filters import blur, masked_blur, max_filter

VEIN_SCALES = (0.006, 0.012)  # vein half-widths the detector looks for
# Calibrated on real veins (P1246006, P1256101): they score ~0.3-0.4 as lines
# and are ~1.5-2.5 Lab a redder than the white around them.
VEIN_LOW, VEIN_HIGH = 0.12, 0.5  # redness-line strength ramp (Lab a units)
VEIN_MIN_RED = (0.6, 2.2)  # how much redder than the white around it
VEIN_LID_MARGIN = 0.012  # eye widths inside the lids (the lid rim is red too)
VEIN_CARUNCLE_CLEAR = (0.05, 0.1)  # nearer the inner corner than the whites edit goes
VEIN_FULL = 2.5  # the vein map is scaled by this: half-detected veins are fully replaced
REDNESS_CLEAN_PCT = 20  # the white's cleanest colour: this percentile of its redness (Lab a)
REDNESS_SHARE = 0.85  # share of the white's pinkness above that taken out at full
VEIN_REFERENCE = 0.05  # neighbourhood the clean white is taken from
CATCH_SIGMA = 0.08  # surroundings a catchlight stands out from
CATCH_EXCESS = (6.0, 18.0)  # how much brighter than surroundings to count
CATCH_BOOST = 1.6
CATCH_MIN_L = (45.0, 70.0)  # Lab L: dimmer spots aren't catchlights


def _remove_veins(lab: np.ndarray, sclera: np.ndarray, eye_w: float, amount: float) -> None:
    """Blood vessels in the white of the eye: thin lines redder than the white
    around them. The line detector runs on redness (Lab a), so the iris edge,
    lash shadows and the white's own shading don't count; each vein pixel then
    takes the colour and brightness of the clean white beside it (measured
    with the veins left out), so it vanishes rather than becoming a pale line.
    Brightness is only ever raised, so no grey patches appear.

    (Repainting veins with LaMa was tried and removed: it filled them with the
    white around them, which near the corners is already pink, and left the
    eye as red as before, while taking 2-3 s.)"""
    a = np.ascontiguousarray(lab[..., 1])
    hard = (sclera > 0.05).astype(np.float32)
    # A red ridge in a is a dark valley in -a: reuse the wrinkle line detector.
    line = _smoothstep(_line_strength(-a, eye_w, VEIN_SCALES), VEIN_LOW, VEIN_HIGH)
    local_a = masked_blur(a, hard, max(0.7, VEIN_REFERENCE * eye_w))
    redder = _smoothstep(a - local_a, *VEIN_MIN_RED)
    vein = line * redder * hard
    k = 2 * round(max(1.0, VEIN_SCALES[-1] * eye_w)) + 1
    vein = max_filter(vein, k)
    vein = np.clip(blur(vein, max(0.5, VEIN_SCALES[0] * eye_w)), 0, 1)
    clean = masked_blur(lab, hard * (1 - vein) ** 2, max(0.7, VEIN_REFERENCE * eye_w))
    target = clean - lab
    target[..., 0] = np.clip(target[..., 0], 0, None)  # only ever brighten
    # A clearly detected vein is fully replaced at full strength: the vein
    # map ramps up gradually, and used as it is it only ever faded veins.
    weight = np.clip(VEIN_FULL * vein, 0, 1)
    lab += (amount * weight * sclera)[..., None] * target
    # Bloodshot whites are pink all over, not just along the veins: pull the
    # white's redness toward its own cleanest part (colour only; brightness
    # and the white's shading stay as they are).
    inside = sclera > 0.5
    if inside.sum() > 20:
        a = lab[..., 1]
        clean_a = float(np.percentile(a[inside], REDNESS_CLEAN_PCT))
        excess = blur(np.clip(a - clean_a, 0, None), max(0.5, VEIN_SCALES[-1] * eye_w))
        lab[..., 1] -= amount * REDNESS_SHARE * sclera * excess


def _correct(rgb, geo, veins, catchlight):
    eye_w = geo["eye_w"]
    h, w = rgb.shape[:2]
    # Complete eye context, independent of preview/export tiles.
    points = geo["contour"]
    margin = eye_w * 0.8
    x0, y0 = np.maximum(np.floor(points.min(0) - margin), 0).astype(int)
    x1, y1 = np.minimum(np.ceil(points.max(0) + margin), [w, h]).astype(int)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return
    off = np.array([x0, y0], np.float32)
    crop = rgb[y0:y1, x0:x1]
    lab = cv2.cvtColor(np.clip(crop, 0, 1), cv2.COLOR_RGB2Lab)
    original = lab.copy()
    L = lab[..., 0].copy()
    shape = L.shape
    opening = _poly_mask(shape, points - off)
    yy, xx = np.mgrid[:shape[0], :shape[1]].astype(np.float32)
    cx, cy = geo["iris_centre"] - off
    r = geo["iris_radius"]
    d = np.hypot(xx - cx, yy - cy)
    around = blur(L, max(0.7, CATCH_SIGMA * eye_w))
    excess = L - around
    catch = (_smoothstep(excess, *CATCH_EXCESS) * _smoothstep(L, *CATCH_MIN_L)
             * cv2.dilate(opening, np.ones((3, 3), np.uint8)))
    catch = np.clip(blur(catch, max(0.5, 0.01 * eye_w)) * 1.5, 0, 1)
    # Unlike a global Lab round trip, pixels outside the eye stay bit-identical.
    catch *= opening
    support = np.zeros(shape, np.float32)
    if veins > 0:
        ic = geo["inner_corner"] - off
        from_inner = np.hypot(xx - ic[0], yy - ic[1]) / eye_w
        sclera_ring = np.clip((d - 1.08 * r) / max(0.5, 0.1 * r) + 0.5, 0, 1)
        zone = (_inner_feather(opening, VEIN_LID_MARGIN * eye_w) * sclera_ring
                * _smoothstep(from_inner, *VEIN_CARUNCLE_CLEAR) * (1 - catch))
        _remove_veins(lab, zone, eye_w, veins)
        support = np.maximum(support, zone)
    if catchlight > 0:
        s = catchlight * catch
        lab[..., 0] += s * np.minimum(CATCH_BOOST * np.clip(excess, 0, None), 100 - lab[..., 0])
        lab[..., 1:] *= (1 - 0.5 * s)[..., None]
        support = np.maximum(support, catch)
    lab[..., 0] = np.clip(lab[..., 0], 0, 100)
    corrected = np.clip(cv2.cvtColor(lab, cv2.COLOR_Lab2RGB), 0, 1)
    changed = (support > 0) & np.any(lab != original, axis=2)
    crop[:] = np.where(changed[..., None], corrected, crop)


def apply(rgb, faces, amounts):
    out = rgb.copy()
    veins = amounts.get("veins", 0)
    if not veins and not any(amounts.get("catchlight_" + side, 0) for side in EYES):
        return out
    h, w = rgb.shape[:2]
    for face in faces:
        lm = face * np.array([w, h], np.float32)
        geos = {side: _eye_geometry(lm, spec) for side, spec in EYES.items()}
        widest = max(g["eye_w"] for g in geos.values())
        for side, geo in geos.items():
            catchlight = amounts.get("catchlight_" + side, 0)
            if not veins and not catchlight:
                continue
            if geo["eye_w"] < MIN_EYE_PX or geo["eye_w"] < FORESHORTENED * widest:
                continue
            _correct(out, geo, veins, catchlight)
    return out
