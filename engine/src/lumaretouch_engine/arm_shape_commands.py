# SPDX-License-Identifier: GPL-3.0-or-later
"""Registered bounded arm transport. No mutation replay or fabricated preview."""
from collections import OrderedDict
from copy import deepcopy
from . import body_pose_evidence as E,body_pose_state as B
from .body_pose_commands import encoded,checked_binding,source_preview


def apply(engine,message):
    action=message['action'];request=message['request']
    if type(request) is not dict:raise ValueError('Arm request must be an object')
    if action=='status':
        if set(request)!={'request_id'}:raise ValueError('Arm status names the original inner request ID')
        return {'receipt':engine._body_status(E.token(request['request_id']),'arm_shape')}
    if action in ('proposal_status','proposal_cancel'):
        if set(request)!={'job_id'}:raise ValueError('Arm proposal query names the original job ID')
        job=E.token(request['job_id']);owner=engine._arm_proposals()
        return {'proposal':owner.status(job) if action=='proposal_status' else owner.cancel(job)}
    why=engine._guard_editable('arm_shape')
    if why:raise ValueError(why)
    engine._people_bind()
    if action in ('view','select'):
        if action=='view' and request!={}:raise ValueError('Arm view is read-only')
        if action=='select':
            if set(request)!={'binding','body_ref'}:raise ValueError('Select one actual retained BodyRef')
            binding=checked_binding(engine,request['binding']);ref=E.ref(request['body_ref']);B.target(engine._body_bank(),ref)
            if ref['asset_sha256']!=binding['asset_sha256']:raise ValueError('Selected arm belongs to another photograph')
            engine._body_cursors[binding['asset_sha256']]=ref
        from .body_pose_acquisition import status
        return {'view':engine._body_view('arm_shape'),'source_preview':source_preview(engine),'model':status()}
    if action=='proposal_start':
        if request.get('request_id')==message['request_id']:raise ValueError('Inner proposal and transport IDs must differ')
        # Read-only selection must not invalidate another feature's capture or
        # discard its pending review. Refuse conflicting allocations instead.
        for name in ('_manual_liquify_preview_owner','_sky_replacement_preview_owner',
                     '_studio_background_preview_owner','_prompted_mask_owner',
                     '_sky_semantic_owner','_semantic_colour_owner'):
            owner=engine.__dict__.get(name)
            nested=getattr(owner,'owner',None)
            if owner is not None and any(value is not None for value in
                    (getattr(owner,'job',None),getattr(owner,'latest',None),getattr(nested,'job',None))):
                raise ValueError('Finish or close the active image/model proposal before starting arm segmentation; its capture was preserved')
        inspection=engine.__dict__.get('_inspection')
        if inspection is not None and (inspection.worker_running or inspection.tx is not None):
            raise ValueError('Wait for active inspection preparation before arm segmentation; its capture was preserved')
        return {'proposal':engine._arm_proposals().start(request)}
    if action!='execute':raise ValueError('Unsupported arm transport action')
    if request.get('request_id')==message['request_id']:raise ValueError('Inner edit and transport IDs must differ')
    engine._cancel_snapshot('arm_shape');engine._close_owned_previews()
    receipt=engine._body_adapter('arm_shape').execute(request)
    if receipt.get('outcome_unknown'):receipt=engine._body_status(request['request_id'],'arm_shape')
    # Publication has already read/retained the selected proposal support. Never
    # release it before support_review validates the actual job result.
    if receipt.get('phase')=='done' and not receipt.get('outcome_unknown'):engine._arm_cancel_proposals()
    return {'receipt':receipt}


class ArmTransport:
    def __init__(self):self.seen={};self.results=OrderedDict();self.bytes=0

    def handle(self,engine,message,emit):
        terminal={'event':'arm_shape_result','protocol':1,'request_id':message.get('request_id'),'action':message.get('action')}
        engine._body_mutation_started=False;ident=None;signature=None
        try:
            if set(message)!={'cmd','request_id','action','request'} or message['cmd']!='arm_shape':raise ValueError('Invalid arm transport envelope')
            ident=E.token(message['request_id']);raw=encoded(message)
            if len(raw)>256*1024:raise ValueError('Arm request exceeds 256 KiB')
            signature=E.content_digest(message)
            if ident in self.seen:
                if self.seen[ident]!=signature:raise ValueError('Arm transport ID reused with changed content')
                if ident in self.results:emit(deepcopy(self.results[ident][0]));return
                terminal.update(success=False,outcome_unknown=True,error='Arm transport response released; query the original inner receipt, never replay')
                emit(terminal);return
            if len(self.seen)>=65536:raise ValueError('Arm transport identity budget exhausted')
            self.seen[ident]=signature
            result=apply(engine,message);receipt=result.get('receipt')
            terminal.update(success=(True if message['action']=='status' else bool(receipt.get('success'))) if receipt else True,
                outcome_unknown=bool(receipt and receipt.get('outcome_unknown')),result=result)
            if receipt and not terminal['success']:terminal['error']=receipt.get('error') or receipt.get('reason') or 'Arm result remains pending; query the original receipt'
            if len(encoded(terminal))>8*1024*1024:
                # No truncation of a real mask or publication evidence.
                raise ValueError('Arm response exceeds native transport budget; retained state remains authoritative')
        except Exception as error:
            terminal.pop('result',None)
            terminal.update(success=False,outcome_unknown=engine._body_mutation_started or message.get('action') in ('status','proposal_start'),error=str(error))
        if ident is not None and signature is not None and self.seen.get(ident)==signature:
            size=len(encoded(terminal))
            while self.results and self.bytes+size>24*1024*1024:
                _,(_,used)=self.results.popitem(last=False);self.bytes-=used
            self.results[ident]=(deepcopy(terminal),size);self.bytes+=size
        emit(terminal)
