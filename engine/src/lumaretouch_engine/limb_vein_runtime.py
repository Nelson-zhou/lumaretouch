# SPDX-License-Identifier: GPL-3.0-or-later
"""Canonical full-source measurement and shared preview/export stage. UNRUN."""
from copy import deepcopy
import hashlib
import numpy as np
from . import limb_vein_state as S
from .optics_candidate_identity import fingerprint


def budget():
    from .cpu_memory_budget import available_estimate
    return min(4 * 1024**3, max(0, int(available_estimate() * .65)))


def capture(engine):
    from .limb_vein_host import Capture
    from . import creative_derived_source as D, creative_derived_repairs as R
    from . import portrait_fit_source as F
    from .neck_wrinkle_source_capture import capture as repaired
    row, token = F._active(engine)
    source = S.source(D.binding(engine))
    state = engine._capture_state()
    repair = R.stack_digest(state)
    version = engine._document_versions().version(row)
    fence = fingerprint({'load_id': engine._load_id, 'workspace': engine._document_versions().workspace,
        'document_id': version.document_id, 'revision': version.revision, 'state': state})
    result = repaired(lambda **kw: F.capture(engine, expected_source=source, **kw),
        tuple(state.get('_repair_ops', ())), source, byte_budget=budget(), cancelled=None)
    F._assert_active(engine, row, token)
    if R.stack_digest(engine) != repair or fingerprint(engine._capture_state()) != fingerprint(state):
        raise ValueError('肢体青筋来源或修复记录在测量时改变')
    pixels = np.frombuffer(result.content, np.float32).reshape(source['height'], source['width'], 3)
    return Capture(source, result.input_sha256, repair, fence, pixels, S.check(state.get('_limb_vein')))


def require_input(recipe, pixels, repair):
    recipe = S.check(recipe)
    if not S.active(recipe): return recipe
    if pixels.shape != (recipe['source']['height'], recipe['source']['width'], 3):
        raise ValueError('肢体青筋必须在完整原图坐标测量')
    digest = hashlib.sha256()
    for y in range(0, pixels.shape[0], 64):
        digest.update(np.ascontiguousarray(pixels[y:y+64], dtype='<f4').tobytes())
    if digest.hexdigest() != recipe['input_sha256'] or repair != recipe['repair_sha256']:
        raise ValueError('肢体青筋所依据的原图或修复已改变；请清除后重新审核')
    return recipe


class Stage:
    def __init__(self, device):
        self.device, self.field, self.amount, self.key = device, None, 0., None
    def clear(self):
        self.field, self.amount, self.key = None, 0., None
    def install(self, field, amount, key=None):
        self.field, self.amount, self.key = np.ascontiguousarray(field), S.amount(amount), key
    def apply(self, rgb):
        if self.field is None or self.amount == 0: return rgb
        from .limb_vein_measure import apply_field
        from .optional_dependencies import optional_module
        torch = optional_module('torch')
        current = rgb[0].permute(1,2,0).detach().cpu().numpy()
        changed = apply_field(np.ascontiguousarray(current, dtype=np.float32), self.field,
            amount=self.amount, byte_budget=budget())
        return torch.from_numpy(changed).permute(2,0,1).unsqueeze(0).to(rgb.device)


def sync(engine):
    pipe = engine._vram
    if pipe is None: return
    if not hasattr(pipe, 'limb_vein'): pipe.limb_vein = Stage(pipe.device)
    recipe = S.check(getattr(engine, '_limb_vein', None))
    if not S.active(recipe): pipe.limb_vein.clear(); return
    from .creative_derived_repairs import stack_digest
    from .creative_derived_source import binding
    if binding(engine) != recipe['source'] or stack_digest(engine) != recipe['repair_sha256']:
        raise ValueError('肢体青筋绑定已失效；清除后重新选择同件肢体参考')
    key = fingerprint({'recipe':recipe,'shape':[pipe.h,pipe.w]})
    if pipe.limb_vein.key == key: return
    captured = capture(engine)
    require_input(recipe, captured.encoded_rgb, captured.repair_sha256)
    from .limb_vein_measure import prepare
    prepared = prepare(captured.encoded_rgb, recipe, byte_budget=budget())
    field = prepared.field
    if field.shape[:2] != (pipe.h, pipe.w):
        # Display-only nearest source-grid projection. Confirmation/export use full field.
        ys = np.minimum(field.shape[0]-1, ((np.arange(pipe.h)+.5)*field.shape[0]/pipe.h).astype(int))
        xs = np.minimum(field.shape[1]-1, ((np.arange(pipe.w)+.5)*field.shape[1]/pipe.w).astype(int))
        field = field[ys[:,None],xs[None,:]]
    pipe.limb_vein.install(field, recipe['amount'], key)


def export_prepare(spec, src, base, divisor):
    recipe = S.check(getattr(spec, 'limb_vein', None))
    if not S.active(recipe): return None
    pixels = base if base is not None else np.asarray(src, dtype=np.float32) / np.float32(divisor)
    pixels = np.ascontiguousarray(pixels, dtype=np.float32)
    require_input(recipe, pixels, getattr(spec, 'limb_vein_repair_sha256', None))
    from .limb_vein_measure import prepare
    return prepare(pixels, recipe, byte_budget=budget())


def report(engine):
    from .limb_vein_native import capability
    row = S.check(getattr(engine, '_limb_vein', None))
    cap = capability()
    i = getattr(engine,'_doc_index',-1)
    docs = getattr(engine,'_docs',[])
    revision = str(engine._document_versions().version(docs[i]).revision) if 0 <= i < len(docs) else '0'
    return {'protocol':1,'revision':revision,'amount':0. if row is None else row['amount'],
        'recipe_sha256':fingerprint(row),'candidate_sha256':fingerprint(row),
        'available':cap['available'],'reason':cap.get('reason'),
        'source':None if row is None else deepcopy(row['source']), 'capability':cap,
        'manual_reference':True,'quality_accepted':False}


def validate_records(value, *, allowed=True):
    if type(value) is dict:
        if '_limb_vein' in value:
            if not allowed and value['_limb_vein'] is not None:
                raise ValueError('旧工程格式不可静默忽略肢体青筋配方')
            S.check(value['_limb_vein'])
        for child in value.values(): validate_records(child, allowed=allowed)
    elif type(value) in (list,tuple):
        for child in value: validate_records(child, allowed=allowed)
