# SPDX-License-Identifier: GPL-3.0-or-later
"""Real adapters into canonical graph, recovery assets, and batch preflight.

These functions stage data, NEVER publish success themselves. Existing receipt,
render, history and project owners must invoke them from registered host paths.
No alternate local graph, history stack, recovery raster cache or batch ledger.
"""
from . import iris_makeup_state as S, people_state as P

def edit_command(envelope,recipe):
    if set(envelope)!={'document_id','document_epoch','document_revision','state_revision','association_revision','target','request_id'}:
        raise ValueError('美瞳编辑必须携带完整当前人物回执信封')
    return {**envelope,'action':'patch','payload':{'patches':S.patches(recipe)}}

def stage_edit(command,state,**binding):
    from .people_edit import stage
    return stage(command,state,**binding)

def retain_recovery(state,assets,face_ref,source,row):
    from .people_support_assets import retain
    if row.get('target')!='iris_makeup':raise ValueError('恢复笔只能移除此美瞳贡献')
    return retain(state,assets,face_ref,source,row)

def recovery_raster(state,assets,asset_sha256,shape):
    from .people_support_assets import raster
    # Canonical immutable vector store validates source/face/landmark identity.
    return raster(state,assets,asset_sha256,shape)

def batch_payload(source_state,target_state,source_ref,target_refs,*,source_document,target_document):
    from .people_transfer_adapter import prepare
    from .people_algorithms import defaults
    return prepare(source_state,target_state,source_ref,target_refs,{S.OP:['/'+k for k in S.KEYS]},defaults(),
                   source_document=source_document,target_document=target_document)

def preset_payload(recipe):
    return {'operation_id':S.OP,'recipe':S.preset(recipe)}

def preset_command(envelope,payload):
    if type(payload) is not dict or set(payload)!={'operation_id','recipe'} or payload['operation_id']!=S.OP or payload['recipe'] is None:
        raise ValueError('美瞳预设不能带入其他照片的支持场或恢复记录')
    return edit_command(envelope,S.check(payload['recipe']))
