# SPDX-License-Identifier: GPL-3.0-or-later
"""Measure one immutable full-source reference; never remeasure export tiles."""
from dataclasses import dataclass
import numpy as np
from . import hair_unification_state as S, hair_unification_assets as A
from . import hair_colour_assets as HAIR, hair_colour_analysis as ANALYSIS, hair_colour_evidence as EVIDENCE
from . import people_state as P, people_resolver as R, local_mask_recipe as M
from .hair_colour_runtime import fields as hair_fields, crop_bounds
from .people_effects import LocalEffect
from . import hair_unification_native as N


class HairUnificationRefused(ValueError):
    def __init__(self, reason, *, face_ref=None, facts=None):
        self.reason, self.face_ref, self.facts = reason, face_ref, facts or {}
        super().__init__('头发统一未应用：' + reason)


@dataclass(frozen=True)
class Parameters:
    amount: float
    reference: N.MeasuredReference

    @property
    def recipe(self):
        return S.check({'version': 1, 'amount': self.amount})


def fields(record, hair_record, shape, hair, *, source_path=None, force_prompted=False):
    record = A.check(record); shape = tuple(shape)
    if A.digest(hair_record) != record['hair_colour_asset_sha256']:
        raise ValueError('Hair-unification fields use a different retained support')
    support, _ = hair_fields(hair_record, shape, hair, source_path=source_path, force_prompted=force_prompted)
    roots = np.ascontiguousarray(M.raster(record['root_sample'], shape), dtype=np.float32) / 255.
    tips = np.ascontiguousarray(M.raster(record['tip_sample'], shape), dtype=np.float32) / 255.
    if np.any((roots > 0) & (tips > 0)):
        raise HairUnificationRefused('发根与发梢取样区域重叠，请分开手工标记', face_ref=record['face_ref'])
    return support, np.ascontiguousarray(roots * support), np.ascontiguousarray(tips * support)


def target_coverage(hair, roots, tips, recipe):
    selected = tips if S.reference_side(recipe) == 'tips' else roots
    target = hair.copy()
    # Exact protection includes feathered nonzero sample edges. These masks are
    # roles, NOT inferred anatomy or an image-half target selection.
    target[selected > 0] = 0
    return target


def prepare_bank(state, asset_sha256, source, plan, *, evidence=None, assets=None,
                 hair_assets=None, byte_budget, source_path=None, force_prompted=False,
                 cancelled=lambda: False):
    requests = []
    for entry in plan['entries']:
        recipe = R.materialize(entry['resolved'], S.OP, S.neutral(), S.check)
        if not S.active(recipe): continue
        ref = P.check_ref(entry['face_ref'])
        if ref['asset_sha256'] != asset_sha256 or entry['status'] != 'ready':
            raise HairUnificationRefused('当前来源人物计划未准备好', face_ref=ref)
        requests.append((ref, recipe))
    if not requests: return (), {}  # No evidence, masks, native or allocations.
    state = P.check(state); P.digest(asset_sha256)
    hair_assets = HAIR.check_store({} if hair_assets is None else hair_assets)
    assets = A.verify_graph(state, {} if assets is None else assets, hair_assets)
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3
            or source.shape[2] != 3 or not np.isfinite(source).all() or np.any((source < 0) | (source > 1))):
        raise ValueError('Hair-unification measurement needs actual immutable working-sRGB source')
    h, w = source.shape[:2]; pixels = h*w
    owned = ownership_faces(state, asset_sha256)
    required = pixels*(64 + 8*len(owned) + 4*len(requests)) + 128*1024*1024
    if type(byte_budget) is not int or byte_budget < required or pixels > M.MAX_PIXELS:
        raise HairUnificationRefused('完整源图头发统一超过内存预算，不以缩略图代替导出')
    selected = {}
    for ref, recipe in requests:
        record = A.resolve(state, assets, ref, hair_assets)
        if record is None:
            raise HairUnificationRefused('先审核本人物头发范围，再手工标记发根或发梢取样', face_ref=ref)
        hair_record = A.current_support(state, record, hair_assets)
        selected[ref['face_instance_id']] = (record, hair_record)
    binding = next(iter(selected.values()))[0]['source']
    hair = ANALYSIS.at_dimensions(evidence, binding, (h, w)); evidence_sha = EVIDENCE.identity(evidence)
    if any(record['semantic_evidence_sha256'] != evidence_sha or record['source'] != binding
           for record, _ in selected.values()):
        raise HairUnificationRefused('头发统一取样与保留类别证据或来源不一致')
    # The union of independently reviewed person claims must be unambiguous.
    occupied = np.zeros((h, w), dtype=bool); work = 0
    for face in owned:
        record = HAIR.resolve(state, hair_assets, P.face_ref(face))
        if record['source'] != binding or record['semantic_evidence_sha256'] != evidence_sha:
            raise HairUnificationRefused('同一来源人物的头发归属证据不一致')
        work += sum(M.validate_budget(record[key], (h, w))['work'] for key in ('support', 'recovery'))
        if work > M.MAX_WORK: raise HairUnificationRefused('头发归属栅格超过合计工作预算')
        support, _ = hair_fields(record, (h, w), hair, source_path=source_path, force_prompted=force_prompted)
        visible = support > 0
        if np.any(visible & occupied):
            raise HairUnificationRefused('不同人物已审核的头发区域重叠；不会自动分配归属', face_ref=P.face_ref(face))
        occupied |= visible
    effects = []; facts = {}
    for ref, recipe in requests:
        if cancelled(): raise InterruptedError('Hair-unification preparation cancelled')
        record, hair_record = selected[ref['face_instance_id']]
        work += sum(M.validate_budget(record[key], (h, w))['work'] for key in ('root_sample', 'tip_sample'))
        if work > M.MAX_WORK: raise HairUnificationRefused('头发样本超过合计栅格工作预算', face_ref=ref)
        support, roots, tips = fields(record, hair_record, (h, w), hair,
            source_path=source_path, force_prompted=force_prompted)
        reference = N.measure(np.ascontiguousarray(source), support, roots, tips, recipe,
                              byte_budget=byte_budget, cancelled=cancelled)
        coverage = target_coverage(support, roots, tips, recipe); window = crop_bounds(coverage)
        if window is None:
            raise HairUnificationRefused('除受保护取样区外没有可处理的本人头发', face_ref=ref)
        y, x, rh, rw = window
        local = np.array(coverage[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
        local.setflags(write=False)
        fact = {'requested': True, 'applied': None, 'stage': S.STAGE, 'recipe': recipe,
            'face_ref': ref, 'source_sha256': asset_sha256, 'asset_sha256': A.digest(record),
            'support_sha256': record['support_sha256'], 'semantic_evidence_sha256': evidence_sha,
            'reference_side': S.reference_side(recipe), 'selected_pixels': reference.selected_pixels,
            'reliable_pixels': reference.reliable_pixels, 'effective_samples': reference.effective_samples,
            'target_pixels': int(np.count_nonzero(coverage)), 'target_extent': 'reviewed-own-person-hair-minus-selected-sample-nonzero-footprint',
            'composition': 'current-linear-luminance-preserving-chroma',
            'limitation': '不均衡纯亮度差、不恢复裁黑过曝细节、不推断发根发梢位置；柔边取样的整个非零范围受保护。'}
        effects.append(LocalEffect(ref, S.STAGE, window, weights=local,
            amounts=Parameters(recipe['amount'], reference), facts=fact))
        facts[ref['face_instance_id']] = fact
    return tuple(effects), facts


def ownership_faces(state, asset_sha256):
    """Disabled suppresses effects, never erases another person's retained claim."""
    return [face for face in state['faces'].values() if face['asset_sha256'] == asset_sha256
            and HAIR.KIND in face['local_assets']]
