"""Original source-domain colour/gloss bank for the ONE canonical people map.

Produces LocalEffect deltas before common geometry. Does not warp RGB, detect
people, infer long-hair ownership from face boxes or write its own edit history.
"""
import numpy as np
from . import hair_colour_state as S, hair_colour_assets as A, hair_colour_analysis as E
from . import people_state as P, people_resolver as R, local_mask_recipe as M
from .people_effects import LocalEffect
from .hair_colour_native import solve
from .hair_colour_evidence import identity as evidence_identity


class HairColourRefused(ValueError):
    def __init__(self, reason, *, face_ref=None, facts=None):
        self.reason, self.face_ref, self.facts = reason, face_ref, facts or {}
        super().__init__('头发调整未应用：' + reason)


def fields(record, shape, hair, *, source_path=None, force_prompted=False):
    """Re-raster normalized retained vectors at requested size, never proxy masks."""
    record = A.check(record)
    shape = tuple(shape)
    if hair.shape != shape: raise ValueError('Hair class coverage differs from source dimensions')
    support = record['support']; recovery = record['recovery']
    semantic = None
    if any(o['kind'] == 'prompted' and o['enabled'] for o in support['objects']):
        if not source_path: raise HairColourRefused('保留的提示选区缺少其原始照片路径，不能用其他照片或全图替代')
        from .prompted_mask_resolver import fields as prompted_fields
        semantic = prompted_fields(support, record['source'], source_path, shape, force=force_prompted)
    weight = np.ascontiguousarray(M.raster(support, shape, semantic=semantic), dtype=np.float32)/255.
    # Genuine confidence-gated class field remains indispensable even for a
    # manually reviewed mask. A user's broad region is NOT a hair detector.
    weight *= hair
    restored = np.ascontiguousarray(M.raster(recovery, shape), dtype=np.float32)/255.
    return np.ascontiguousarray(weight), restored


def crop_bounds(weight):
    ys, xs = np.nonzero(weight > 0)
    if not len(ys): return None
    y, x = int(ys.min()), int(xs.min())
    return y, x, int(ys.max())-y+1, int(xs.max())-x+1


def prepare_bank(state, asset_sha256, source, plan, *, evidence=None, assets=None,
                 byte_budget, source_path=None, force_prompted=False):
    """Every requested face is prepared atomically; ambiguous support refuses.

    Call once from people_render_runtime.prepare, append returned LocalEffects to
    PreparedPeople.effects, and merge the per-face facts. Install no second warp.
    Full-source RGB8/16 is converted by the existing people export owner; source
    here stays unquantized working-sRGB float32, including repaired source RGB.
    """
    state = P.check(state); P.digest(asset_sha256)
    store = A.verify_graph(state, {} if assets is None else assets)
    requests = []
    for entry in plan['entries']:
        ref = P.check_ref(entry['face_ref'])
        recipe = R.materialize(entry['resolved'], S.OPERATION, S.neutral(), S.check)
        if ref['asset_sha256'] != asset_sha256: raise ValueError('Hair plan includes another photograph')
        if S.active(recipe):
            if entry['status'] != 'ready': raise HairColourRefused('当前人物计划尚未准备好', face_ref=ref)
            requests.append((ref, recipe))
    if not requests: return (), {}  # No native load, inference, raster or beautification.
    if (type(source) is not np.ndarray or source.dtype != np.float32 or source.ndim != 3 or source.shape[2] != 3
            or not np.isfinite(source).all() or np.any((source < 0) | (source > 1))):
        raise ValueError('Hair rendering needs frozen source-frame working-sRGB float32')
    h, w = source.shape[:2]; pixels = h*w
    if type(byte_budget) is not int or pixels > M.MAX_PIXELS or byte_budget < pixels*112+128*1024*1024:
        raise HairColourRefused('完整源图头发处理超过内存预算；不会降采样替代导出')
    # Validate ownership for all retained source supports, including neutral ones,
    # so a current edit cannot silently occupy another explicitly claimed head.
    owned = []
    for face in state['faces'].values():
        if face['asset_sha256'] != asset_sha256 or not face['enabled'] or A.KIND not in face['local_assets']: continue
        record = A.resolve(state, store, P.face_ref(face))
        owned.append((face, record))
    by_id = {face['face_instance_id']: record for face, record in owned}
    for ref, recipe in requests:
        if ref['face_instance_id'] not in by_id:
            raise HairColourRefused('请先在源图上审核此人物的头发范围；人脸选择或只检测到一张脸均不能证明头发归属', face_ref=ref)
    if byte_budget < pixels*(112+8*len(owned)+24*len(requests))+128*1024*1024:
        raise HairColourRefused('多人源图差分与选区超出合计内存预算；未分配大尺寸栅格')
    binding = by_id[requests[0][0]['face_instance_id']]['source']
    hair = E.at_dimensions(evidence, binding, (h, w))
    evidence_sha = evidence_identity(evidence)
    if any(record['semantic_evidence_sha256'] != evidence_sha for _, record in owned):
        raise HairColourRefused('保留的头发类别证据与已审核范围不一致；不会用新推理悄悄替换')
    total_work = sum(M.validate_budget(record[key], (h, w))['work'] for _, record in owned for key in ('support', 'recovery'))
    if total_work > M.MAX_WORK or len(owned)*pixels > 128_000_000:
        raise HairColourRefused('多人头发选区超出合计栅格预算，请简化笔迹')
    occupied = np.zeros((h, w), bool); retained = {}; requested = {ref['face_instance_id'] for ref, _ in requests}
    # Overlap is an ambiguity, not a first-face-wins compositing policy.
    for face, record in sorted(owned, key=lambda row: row[0]['face_instance_id']):
        if record['source'] != binding: raise ValueError('Same-photo hair assets disagree about source dimensions')
        weight, recovery = fields(record, (h, w), hair, source_path=source_path, force_prompted=force_prompted)
        visible = weight > 0
        if np.any(visible & occupied):
            raise HairColourRefused('不同人物的已审核头发范围有重叠，请先擦除歧义部分；不会自动指定给某个人', face_ref=P.face_ref(face),
                facts={'overlap_pixels': int(np.count_nonzero(visible & occupied))})
        occupied |= visible
        if face['face_instance_id'] in requested:
            retained[face['face_instance_id']] = (weight, recovery)
    effects = []; facts = {}; resident = sum(weight.nbytes+recovery.nbytes for weight, recovery in retained.values())
    for ref, recipe in requests:
        key = ref['face_instance_id']; record = by_id[key]; weight, recovery = retained.pop(key)
        window = crop_bounds(weight)
        if window is None or np.count_nonzero(weight > .05) < 16:
            raise HairColourRefused('人工选区与可信头发证据相交后不足，需纠正选区或更清晰的原片', face_ref=ref)
        if resident+pixels*112+128*1024*1024 > byte_budget:
            raise HairColourRefused('多人头发差分超出内存预算；未发布部分结果', face_ref=ref)
        delta, highlights = solve(np.ascontiguousarray(source), weight, recipe)
        if recipe['gloss'] and not np.any(highlights > 1e-6):
            raise HairColourRefused('此头发范围没有可信的已有高光结构；不通过整体提亮冒充光泽', face_ref=ref,
                facts={'colour_requested': recipe['strength'] > 0, 'gloss_requested': True, 'gloss_applied': False})
        # Recovery attenuates THIS operator only, before the single people warp.
        # It never paints original RGB over wrinkle/colour/other-face changes.
        delta *= (1-recovery[..., None])
        y, x, rh, rw = window
        local = np.array(delta[y:y+rh, x:x+rw], dtype=np.float32, order='C', copy=True)
        masks = np.stack((weight[y:y+rh, x:x+rw], highlights[y:y+rh, x:x+rw], recovery[y:y+rh, x:x+rw]), axis=0)
        changed = int(np.count_nonzero(np.any(local != 0, axis=2)))
        fully_recovered = bool(np.all(recovery[weight > 0] == 1))
        fact = {'requested': True, 'applied': changed > 0, 'reason': 'fully_recovered' if fully_recovered else (None if changed else 'no_measurable_change'),
            'face_ref': ref, 'source_sha256': asset_sha256, 'semantic_model_sha256': record['semantic_model_sha256'],
            'asset_sha256': A.digest(record), 'semantic_evidence_sha256': evidence_sha, 'recipe': recipe, 'palette': 'Lumaretouch original v1',
            'ownership': 'explicit_source_review_intersect_real_hair', 'support_pixels': int(np.count_nonzero(weight)),
            'highlight_pixels': int(np.count_nonzero(highlights > 1e-6)), 'changed_pixels': changed,
            'recovered_pixels': int(np.count_nonzero((recovery > 0) & (weight > 0))),
            'limitation': '不重建裁黑/过曝细节、发丝或光源；六类分割不是逐像素真值，也不是人物实例分割。'}
        for array in (local, masks): array.setflags(write=False)
        effects.append(LocalEffect(ref, S.STAGE, window, delta=local, weights=masks, facts=fact))
        facts[key] = fact
        resident += local.nbytes + masks.nbytes - weight.nbytes - recovery.nbytes
    return tuple(effects), facts


def apply_source(pipe, pixels):
    """Shared pipeline adapter: apply precomputed deltas BEFORE its one warp."""
    from .people_pipeline import _merge_delta, active
    if not active(pipe): raise ValueError('Hair effects require the canonical people preparation')
    import torch
    delta = _merge_delta(pipe, S.STAGE, align=False)
    return torch.where(delta != 0, (pixels+delta).clamp(0, 1), pixels)


def aligned_fields(pipe, face_ref):
    """Diagnostic coverage/highlight/recovery use exactly the existing people map.

    Return three channels; do not feed these already aligned fields back into
    source preparation. Colour delta and recovery attenuation already enter RGB
    before that same map, including full-resolution export tile halos.
    """
    from .people_pipeline import _local, warp, active
    if not active(pipe): raise ValueError('Canonical people map is unavailable')
    records = [r for r in pipe.people_prepared.effects if r.stage == S.STAGE and r.face_ref == face_ref]
    if len(records) != 1: raise ValueError('Hair source mask owner is missing or ambiguous')
    record = records[0]
    return warp(pipe, _local(pipe, record, record.weights.transpose(1, 2, 0), 3))
