# SPDX-License-Identifier: GPL-3.0-or-later
"""Real adapters into canonical graph, recovery assets, and batch preflight.

These functions stage data, NEVER publish success themselves. Existing receipt,
render, history and project owners must invoke them from registered host paths.
No alternate local graph, history stack, recovery raster cache or batch ledger.
"""
from . import eyelash_state as S, people_state as P
from . import eyelash_project as LIB

def edit_command(envelope,recipe):
    if set(envelope)!={'document_id','document_epoch','document_revision','state_revision','association_revision','target','request_id'}:
        raise ValueError('睫毛编辑必须携带完整当前人物回执信封')
    return {**envelope,'action':'patch','payload':{'patches':S.patches(recipe)}}

def stage_edit(command,state,**binding):
    from .people_edit import stage
    return stage(command,state,**binding)

def stage_palette(engine,command):
    """Host includes _eyelash_library in ordinary document history snapshot.

    Returns candidate only. Host transaction installs after validation, stores
    history, emits correlated receipt, and restores old candidate on failure.
    """
    from .people_host_commands import checked
    if (type(command) is not dict or set(command)!={'document_id','document_epoch','document_revision','state_revision','association_revision','target','request_id','action','payload'}
        or command.get('action')!='eyelash_palette'):raise ValueError('未知睫毛收藏操作或字段')
    _,_,_=checked(engine,command)
    payload=command.get('payload')
    if type(payload) is not dict or set(payload)!={'action','colour'} or payload['action'] not in ('save','remove'):
        raise ValueError('收藏操作字段无效')
    old=LIB.capture(engine)
    palette=(S.save_colour if payload['action']=='save' else S.remove_colour)(old['saved_colours'],payload['colour'])
    return LIB.check({**old,'saved_colours':palette})

def retain_recovery(state,assets,face_ref,source,row):
    from .people_support_assets import retain
    if row.get('target')!='eyelash':raise ValueError('恢复笔只能移除此睫毛贡献')
    return retain(state,assets,face_ref,source,row)

def recovery_raster(state,assets,asset_sha256,shape):
    from .people_support_assets import raster
    # Canonical immutable vector store validates source/face/landmark identity.
    return raster(state,assets,asset_sha256,shape)

def batch_payload(source_state,target_state,source_ref,target_refs,*,source_document,target_document):
    from .people_transfer_adapter import prepare
    from .people_algorithms import defaults
    return prepare(source_state,target_state,source_ref,target_refs,{S.OP:[p['parameter_path'] for p in S.patches(S.neutral())]},defaults(),
                   source_document=source_document,target_document=target_document)

def preset_payload(recipe):
    return {'operation_id':S.OP,'recipe':S.preset(recipe)}

def preset_command(envelope,payload):
    if type(payload) is not dict or set(payload)!={'operation_id','recipe'} or payload['operation_id']!=S.OP or payload['recipe'] is None:
        raise ValueError('睫毛预设不能带入其他照片的支持场或恢复记录')
    return edit_command(envelope,S.check(payload['recipe']))
