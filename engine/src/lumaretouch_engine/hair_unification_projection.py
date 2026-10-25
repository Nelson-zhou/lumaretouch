# SPDX-License-Identifier: GPL-3.0-or-later
"""Declared display-grid coverage; full-source reference statistics never change."""
import numpy as np
from . import hair_unification_assets as A, hair_colour_analysis as ANALYSIS, hair_colour_assets as HAIR
from . import people_state as P
from .people_effects import LocalEffect
from .hair_unification_runtime import Parameters, fields, target_coverage, HairUnificationRefused, ownership_faces
from .hair_colour_runtime import crop_bounds, fields as hair_fields


def project(effects, facts, state, assets, hair_assets, evidence, shape, *,
            source_path=None, force_prompted=False, cancelled=lambda: False):
    h, w = shape
    if min(h, w) < 1: raise ValueError('Empty hair application grid')
    occupied = np.zeros(shape, dtype=bool); result = []; output_facts = dict(facts)
    # Resampling may merge formerly disjoint claims. Disabled owners still
    # reserve their reviewed region, just as they do in full-source fitting.
    claimed = np.zeros(shape, dtype=bool)
    if effects:
        source = evidence['source']; hair = ANALYSIS.at_dimensions(evidence, source, shape)
        for face in ownership_faces(state, source['sha256']):
            if cancelled(): raise InterruptedError('Hair ownership projection cancelled')
            retained = HAIR.resolve(state, hair_assets, P.face_ref(face))
            support, _ = hair_fields(retained, shape, hair,
                source_path=source_path, force_prompted=force_prompted)
            positive = support > 0
            if np.any(positive & claimed):
                raise HairUnificationRefused('显示网格合并了不同人物的头发归属，不自动改派范围')
            claimed |= positive
    for effect in effects:
        if cancelled(): raise InterruptedError('Hair reference grid preparation cancelled')
        reference = effect.amounts.reference
        sh, sw = reference.source_height, reference.source_width
        if h > sh or w > sw or ((h, w) != (sh, sw) and
                (w % 8 or h % 8 or w*sh >= (h+8)*sw or h*sw >= (w+8)*sh)):
            raise ValueError('Hair application grid is not a bounded whole-source display projection')
        record = A.resolve(state, assets, effect.face_ref, hair_assets)
        retained = A.current_support(state, record, hair_assets)
        support, roots, tips = fields(record, retained, shape, hair,
            source_path=source_path, force_prompted=force_prompted)
        selected = tips if effect.amounts.reference.direction < 0 else roots
        if not np.any(selected > 0):
            raise HairUnificationRefused('当前显示网格无法表达受保护的参考样本；请提高显示源图尺寸后重开，不取消样本保护')
        coverage = target_coverage(support, roots, tips, effect.amounts.recipe)
        positive = coverage > 0
        if np.any(positive & occupied):
            raise HairUnificationRefused('显示网格上的人物头发归属重叠，不自动分配')
        occupied |= positive
        window = crop_bounds(coverage)
        if window is None:
            raise HairUnificationRefused('当前显示网格不能表达已审核头发范围，不假装已显示效果')
        y, x, rh, rw = window
        local = np.array(coverage[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
        local.setflags(write=False)
        fact = {**effect.facts, 'measurement_dimensions': [sw, sh],
                'application_dimensions': [w, h], 'reference_fit': 'immutable-native-full-source-v1',
                'application_projection': 'whole-source-display-grid-v1'}
        result.append(LocalEffect(effect.face_ref, effect.stage, window, weights=local,
            amounts=Parameters(effect.amounts.amount, reference, shape), facts=fact))
        output_facts[effect.face_ref['face_instance_id']] = fact
    return tuple(result), output_facts
