# SPDX-License-Identifier: GPL-3.0-or-later
"""Canonical source/document lifecycle for standalone hand geometry. UNRUN."""
from copy import deepcopy
from . import hand_shape_state as S
from .optics_candidate_identity import fingerprint


def budget():
    from .cpu_memory_budget import available_estimate
    return min(4*1024**3,max(0,int(available_estimate()*.65)))


def checked_live(engine):
    value=S.check(getattr(engine,'_hand_shape',None))
    if not S.active(value):return value
    from .creative_derived_source import binding,record
    from .creative_derived_repairs import stack_digest
    if record(engine) is not None:raise ValueError('手部美型当前只支持原始来源；创意合成来源须清除后重新支持')
    from .local_mask_state import file_stamp
    row=engine._docs[engine._doc_index]
    if row.get('_local_source_stamp')!=file_stamp(engine._doc_path):raise ValueError('Hand original source changed since decode')
    if binding(engine)!=value['source'] or stack_digest(engine)!=value['repair_sha256']:raise ValueError('手部几何来源或修复记录已改变；请清除后重新审核')
    return value


def report(engine):
    from .virtual_copy_people import current_row
    row=current_row(engine);value=S.check(getattr(engine,'_hand_shape',None))
    revision='0' if row is None else str(engine._document_versions().version(row).revision)
    return {'protocol':1,'revision':revision,'active':S.active(value),'recipe_sha256':fingerprint(value)}


def validate_records(value,*,allowed=True):
    if isinstance(value,dict):
        if '_hand_shape' in value:
            recipe=S.check(value['_hand_shape'])
            if recipe is not None and not allowed:raise ValueError('This legacy schema cannot retain standalone hand geometry')
        for child in value.values():validate_records(child,allowed=allowed)
    elif isinstance(value,(list,tuple)):
        for child in value:validate_records(child,allowed=allowed)


def capture_export(engine,snap,state,path):
    value=S.check(state.get('_hand_shape'));snap['hand_shape']=deepcopy(value)
    snap['hand_shape_path']=None;snap['hand_shape_stamp']=None
    if value is None:return snap
    from .creative_derived_source import record
    from .creative_derived_repairs import stack_digest
    from .local_mask_state import file_stamp,source_digest
    if record(state) is not None:raise ValueError('Hand geometry cannot reuse original support on a creative-derived source')
    before=file_stamp(path)
    if source_digest(path)!=value['source']['sha256'] or stack_digest(state)!=value['repair_sha256'] or file_stamp(path)!=before:raise ValueError('Hand export source/repair changed since visible support review')
    if snap.get('people') is None and S.active(value):
        from .people_snapshot import capture
        # Empty observed graph is valid: a hand is NOT a fabricated person/face.
        snap['people']=capture(engine._people_owner().snapshot(),value['source']['sha256'],{})
        snap['people']['support_assets']=deepcopy(engine._people_support)
        snap['people']['document_id']=snap.get('people_document_id')
    return snap


def check_export_decode(snap,path,before,shape):
    value=S.check(snap.get('hand_shape'))
    if value is None:return
    from .local_mask_state import file_stamp,source_digest
    if before is None or file_stamp(path)!=before or source_digest(path)!=value['source']['sha256'] or file_stamp(path)!=before:raise ValueError('Original hand source changed during full-resolution decode')
    if shape is not None and tuple(shape)!=(value['source']['height'],value['source']['width']):raise ValueError('Hand export needs exact original dimensions, never enlarged proxy geometry')
    snap['hand_shape_path']=path;snap['hand_shape_stamp']=list(before)


def configure_export(spec,snap,shape,*,for_document):
    value=S.check(snap.get('hand_shape'));spec.hand_shape=value
    spec.hand_shape_path=snap.get('hand_shape_path');spec.hand_shape_stamp=deepcopy(snap.get('hand_shape_stamp'))
    if value is None:return
    if not for_document:raise ValueError('Hand support cannot be copied to another document/batch target')
    if tuple(shape)!=(value['source']['height'],value['source']['width']):raise ValueError('Hand geometry needs full original source dimensions')
    if S.active(value) and spec.people is None:raise ValueError('Standalone hand geometry lacks its frozen common sampler context')
    verify_render_source(spec)


def verify_render_source(spec):
    value=S.check(getattr(spec,'hand_shape',None))
    if value is None:return
    from .local_mask_state import file_stamp
    if not spec.hand_shape_path or spec.hand_shape_stamp is None or list(file_stamp(spec.hand_shape_path))!=spec.hand_shape_stamp:raise ValueError('Hand original source changed after verified decode')


def export_outcome(prepared,recipe,source_shape):
    """Call after actual render; a buffer-stage fact, never saved-file success."""
    value=S.check(recipe)
    if not S.active(value):return None
    if prepared is None or len(prepared.document_fields)!=1 or prepared.document_fields[0].binding_sha256!=fingerprint(value):raise ValueError('Rendered hand map does not cover the exact frozen requested recipe')
    if tuple(prepared.geometry.delta.shape[1:3])!=tuple(source_shape) or tuple(source_shape)!=(value['source']['height'],value['source']['width']):raise ValueError('Hand export geometry was not rebuilt at original source resolution')
    from .shoulder_shape_runtime import document_geometry_metadata
    from hashlib import sha256
    return {'version':1,'stage':'render-buffer-before-container-publication','encoded_file_published':False,
        'geometry_original_resolution':True,'source':value['source'],'recipe_sha256':fingerprint(value),
        'geometry_delta_sha256':sha256(memoryview(prepared.geometry.delta)).hexdigest(),
        **document_geometry_metadata(prepared.geometry),'runtime_quality_accepted':False}
