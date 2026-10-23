# SPDX-License-Identifier: GPL-3.0-or-later
"""Registered arm command port on the actual serialized host/history/publisher."""
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable
from . import arm_shape_state as S, arm_shape_project as P, body_pose_state as B, body_pose_evidence as E
from . import shoulder_shape_adapter as Common


@dataclass(frozen=True)
class HostPorts:
    binding:Callable
    read_bank:Callable
    read_people:Callable
    prepare:Callable
    publish:Callable
    receipt_get:Callable
    receipt_put:Callable
    proposal_get:Callable  # actual retained read-only job result, never caller mask bytes
    release_proposals:Callable|None=None  # stop owned model allocations before common-map preparation


from .shoulder_shape_host import UnappliedPreparation, PublicationNotStarted


class PublicationMismatch(RuntimeError):
    """An invalid actual publication must never be upgraded as a lost notice."""


def envelope(raw,binding,state,people):
    keys={'request_id','gesture_id','document_id','document_epoch','document_revision','state_revision',
          'association_revision','people_association_revision','body_graph_sha256','people_graph_sha256',
          'body_ref','family_id','action','payload'}
    if type(raw) is not dict or set(raw)!=keys or raw['family_id']!=S.FAMILY_ID:raise ValueError('Invalid arm command envelope')
    E.token(raw['request_id']);E.token(raw['gesture_id'])
    for k in ('document_id','document_epoch','document_revision'):
        if raw[k]!=binding[k]:raise ValueError('Arm edit document changed')
    if raw['state_revision']!=state['revision'] or raw['association_revision']!=state['association_revision'] or raw['people_association_revision']!=people['association_revision'] or E.digest(raw['body_graph_sha256'])!=P.graph_digest(state) or E.digest(raw['people_graph_sha256'])!=P.people_digest(people):raise ValueError('Arm body/people graph changed')
    if E.ref(raw['body_ref'])['asset_sha256']!=binding['asset_sha256']:raise ValueError('Arm request source changed')
    B.target(state,raw['body_ref'])
    if type(raw['payload']) is not dict:raise ValueError('Arm payload is missing')
    return deepcopy(raw)


def _targets(payload):
    targets=payload['targets']
    if type(targets) is not list or not targets or len(targets)>4 or len(set(targets))!=len(targets) or any(k not in S.SEGMENTS for k in targets) or type(payload['linked']) is not bool:raise ValueError('Name explicit affected arm sides/segments')
    if payload['linked']:
        for target in targets:
            side,part=target.split('_',1);other=('right' if side=='left' else 'left')+'_'+part
            if other not in targets:raise ValueError('Linked arm edits must include both requested sides')
    return targets


class ArmHostAdapter:
    """Host must hold its real document edit lock for execute/publication.

    Durable claim precedes publication; uncertainty is reconciled by querying,
    never by resending a potentially successful mutation under a new request ID.
    """
    def __init__(self,ports:HostPorts,*,receipt_budget=4096):
        if type(receipt_budget) is not int or not 1<=receipt_budget<=65536:raise ValueError('Invalid arm receipt budget')
        self.ports=ports;self.receipt_budget=receipt_budget;self.receipts=OrderedDict()

    def status(self,request_id):
        request_id=E.token(request_id);local=self.receipts.get(request_id)
        # A later local verification rejection is stronger than an older
        # durable pending claim whose terminal write may have failed.
        if local is not None and local['result'].get('publication_invalid'):return deepcopy(local['result'])
        row=self.ports.receipt_get(request_id)
        if row is not None:self.receipts[request_id]=deepcopy(row)
        else:row=self.receipts.get(request_id)
        return deepcopy(row['result']) if row else {'phase':'unavailable','request_id':request_id,'reason':'No retained result; do not replay uncertain arm changes'}

    def execute(self,raw):
        if type(raw) is not dict:raise ValueError('Invalid arm request')
        request=E.token(raw.get('request_id'));digest=E.content_digest(raw);retained=self.ports.receipt_get(request)
        if retained is not None and not self.receipts.get(request,{}).get('result',{}).get('publication_invalid'):self.receipts[request]=deepcopy(retained)
        if request in self.receipts:
            if self.receipts[request]['digest']!=digest:raise ValueError('Arm request ID reused with changed content')
            return self.status(request)
        if len(self.receipts)>=self.receipt_budget:raise ValueError('Arm receipt retention budget reached')
        # A durable claim is query-only: publication may follow even if its
        # final journal write is lost. Never persist a false negative outcome.
        pending={'phase':'pending','request_id':request,'outcome_unknown':True}
        self.ports.receipt_put(request,digest,deepcopy(pending));self.receipts[request]={'digest':digest,'result':pending}
        publishing=False
        try:
            before=P.check(self.ports.read_bank());people=self.ports.read_people()
            p=envelope(raw,self.ports.binding(),before,people);ref=p['body_ref'];payload=p['payload'];action=p['action']
            row=B.target(before,ref);candidate=before
            if action=='recipe':
                if set(payload)!={'base','recipe','targets','linked'} or S.check_family(payload['base'])!=S.family(row):raise ValueError('Arm base recipe changed')
                targets=_targets(payload);next_recipe=S.check_family(payload['recipe'])
                if any(next_recipe[k]!=payload['base'][k] for k in S.SEGMENTS if k not in targets):raise ValueError('Arm request tried to change an unrequested segment')
                if payload['linked']:
                    for k in targets:
                        side,part=k.split('_',1);other=('right' if side=='left' else 'left')+'_'+part
                        if next_recipe[k]!=next_recipe[other]:raise ValueError('Linked request amounts and strategies must match')
                for key in targets:
                    op=S.OPERATION_IDS[key];recipe=next_recipe[key];current=row['operations'].get(op)
                    # Zero needs no anatomy or model; activating EVERY named
                    # target does. No partial application when linking sides.
                    if S.active(recipe):
                        if current is None or not current['enabled'] or current['review'] is None:raise ValueError('Each requested arm segment must be enabled and independently reviewed')
                        asset=B.support(before,ref,op)
                        if asset is None or asset['data']['strategy']!=recipe['strategy']:raise ValueError('Each requested strategy needs its own actual reviewed support')
                    candidate=B.set_recipe(candidate,ref,recipe,operation_id=op,operation_policies=S.policies())
            elif action=='support_review':
                keys={'segment','strategy','points_sha256','visible_anchors','ownership_confirmed','confirmations','manual','proposal_id','candidate'}
                if set(payload)!=keys or payload['segment'] not in S.SEGMENTS or payload['strategy'] not in S.STRATEGIES or payload['points_sha256']!=row['record']['points_sha256']:raise ValueError('Arm review must name the current actual segment/pose')
                segment=payload['segment'];op=S.OPERATION_IDS[segment]
                if payload['strategy']=='reviewed-contour':
                    if payload['proposal_id'] is not None or payload['candidate'] is not None or type(payload['manual']) is not dict or set(payload['manual'])!={'negative','positive','region'}:raise ValueError('Manual review cannot claim neural evidence')
                    data={'version':1,'segment':segment,'strategy':payload['strategy'],'stations':list(S.STATIONS),
                          **deepcopy(payload['manual']),'selection':None,'confirmations':payload['confirmations']}
                else:
                    if payload['manual'] is not None:raise ValueError('AI mode cannot replace a missing model with manual widths')
                    result=self.ports.proposal_get(E.token(payload['proposal_id']))
                    if type(result) is not dict or result.get('phase')!='done' or not result.get('success') or result.get('proposal') is None:raise ValueError('Actual completed SAM proposal job is required')
                    context=result['context']
                    for k in ('document_id','document_epoch','body_graph_sha256','people_graph_sha256'):
                        if context[k]!=p[k]:raise ValueError('SAM proposal context is stale; inspect a fresh selection')
                    proposal=result['proposal']
                    if proposal['source']!=row['record']['source'] or proposal['body_ref']!=ref or proposal['points_sha256']!=payload['points_sha256'] or proposal['segment']!=segment:raise ValueError('SAM proposal belongs to another source/body/segment/analysis')
                    from .arm_shape_selection import support_from_proposal
                    data=support_from_proposal(proposal,payload['candidate'],payload['confirmations'])
                candidate=B.set_support(before,ref,op,S.SUPPORT_KIND,data,operation_policies=S.policies())
                support=B.operation(candidate,ref,op)['support_sha256']
                candidate=B.review(candidate,ref,operation_id=op,support_sha256=support,points_sha256=payload['points_sha256'],visible_anchors=payload['visible_anchors'],ownership_confirmed=payload['ownership_confirmed'],operation_policies=S.policies())
            elif action=='operation_status':
                if set(payload)!={'segment','enabled'} or payload['segment'] not in S.SEGMENTS:raise ValueError('Invalid arm enable command')
                candidate=B.set_operation_enabled(before,ref,S.OPERATION_IDS[payload['segment']],payload['enabled'],operation_policies=S.policies())
            else:raise ValueError('Unsupported arm command')
            if self.ports.release_proposals is not None:self.ports.release_proposals()
            try:prepared=self.ports.prepare(candidate)
            except (ValueError,RuntimeError,OSError) as error:
                if action=='recipe':raise
                prepared=UnappliedPreparation(str(error))
            if not isinstance(prepared,(Common.PreparedShoulders,UnappliedPreparation)):raise ValueError('Arm publication requires actual prepared common geometry')
            envelope(raw,self.ports.binding(),self.ports.read_bank(),self.ports.read_people())
            patch=P.history_patch(before,candidate,people_sha256=p['people_graph_sha256']);publishing=True
            authoritative=self.ports.publish(before,candidate,prepared,patch,p)
            if type(authoritative) is not dict or authoritative.get('state_revision')!=candidate['revision'] or authoritative.get('body_graph_sha256')!=P.graph_digest(candidate):raise PublicationMismatch('Host did not publish the actual arm bank revision')
            if not isinstance(prepared,UnappliedPreparation) and authoritative.get('publication',{}).get('rendered') is not False:_verify_publication(authoritative.get('render_receipt'),prepared,p)
            result={'phase':'done','protocol':1,'request_id':request,'success':True,'outcome_unknown':False,
                    'rendered':authoritative.get('publication',{}).get('rendered',not isinstance(prepared,UnappliedPreparation)),'view':authoritative,
                    'unapplied_reason':authoritative.get('publication',{}).get('unapplied_reason',prepared.reason if isinstance(prepared,UnappliedPreparation) else None)}
        except (ValueError,RuntimeError,OSError,KeyError,TypeError) as error:
            if isinstance(error,PublicationNotStarted):publishing=False
            result={'phase':'pending' if publishing else 'done','request_id':request,'protocol':1,'success':False,'outcome_unknown':publishing,'publication_invalid':isinstance(error,PublicationMismatch),'error':str(error)}
        try:self.ports.receipt_put(request,digest,deepcopy(result))
        except (ValueError,RuntimeError,OSError) as error:
            result={'phase':'pending','request_id':request,'protocol':1,'success':False,'outcome_unknown':publishing,'publication_invalid':result.get('publication_invalid',False),'error':'Durable arm result retention failed; query host ledger: '+str(error)}
        self.receipts[request]['result']=result
        return deepcopy(result)

    def resolve_publication(self,request_id,*,actual_result):
        row=self.receipts.get(E.token(request_id))
        if row is None or not row['result'].get('outcome_unknown') or row['result'].get('publication_invalid'):raise ValueError('No uncertain arm publication is pending')
        if type(actual_result) is not dict or actual_result.get('request_id')!=request_id or actual_result.get('phase')!='done' or actual_result.get('outcome_unknown') is not False:raise ValueError('Authoritative host terminal result required')
        self.ports.receipt_put(request_id,row['digest'],deepcopy(actual_result));row['result']=deepcopy(actual_result)


def _verify_publication(receipt,prepared,request):
    from hashlib import sha256
    import numpy as np
    if type(receipt) is not dict or receipt.get('version')!=1 or receipt.get('request_id')!=request['request_id'] or receipt.get('prepared_identity_sha256')!=prepared.identity_sha256 or receipt.get('source_sha256')!=prepared.source['sha256']:raise PublicationMismatch('Missing actual arm/common-map publication receipt')
    E.token(receipt.get('published_frame_id'));E.revision(receipt.get('render_revision'));E.digest(receipt.get('output_pixel_sha256'))
    geometry=prepared.geometry;h,w=geometry.delta.shape[1:3]
    if receipt.get('geometry_delta_sha256')!=sha256(memoryview(np.ascontiguousarray(geometry.delta))).hexdigest() or receipt.get('render_dimensions')!=[w,h] or receipt.get('source_dimensions')!=[prepared.source['width'],prepared.source['height']] or receipt.get('body_operation_order')!=geometry.body_operation_order or receipt.get('single_source_sample') is not True or receipt.get('runtime_quality_accepted') is not False or receipt.get('output_dtype') not in ('uint8','uint16','float32'):raise PublicationMismatch('Arm publication mismatches the exact single-source common geometry')


def view(state,binding,*,selected_body_ref,people_state,refusals=()):
    state=P.check(state);selected=None;rows=[]
    if selected_body_ref is not None:
        selected=B.target(state,selected_body_ref)
        if selected_body_ref['asset_sha256']!=binding['asset_sha256']:raise ValueError('Selected arm body belongs to another source')
    for row in state['bodies'].values():
        record=row['record']
        if record['source']['sha256']!=binding['asset_sha256']:continue
        operations={}
        for key,op in S.OPERATION_IDS.items():
            item=row['operations'].get(op)
            operations[key]={'enabled':item['enabled'] if item else True,'reviewed':item is not None and item['review'] is not None,
                             'support':None if item is None or item['support_sha256'] is None else B.support(state,record['body_ref'],op)['data']}
        rows.append({'body_ref':record['body_ref'],'enabled':row['enabled'],'points':record['points'],'points_sha256':record['points_sha256'],
                     'source':record['source'],'association':row['association'],'operations':operations})
    return {'binding':deepcopy(binding),'state_revision':state['revision'],'association_revision':state['association_revision'],
            'people_association_revision':people_state['association_revision'],'body_graph_sha256':P.graph_digest(state),
            'people_graph_sha256':P.people_digest(people_state),'bodies':deepcopy(rows),'selected_body_ref':deepcopy(selected_body_ref),
            'recipe':{k:S.neutral() for k in S.SEGMENTS} if selected is None else S.family(selected),
            'refusals':deepcopy(list(refusals)),'runtime_quality_accepted':False}


@dataclass(frozen=True)
class ProposalPorts:
    binding:Callable
    read_bank:Callable
    read_people:Callable
    source_path:Callable  # host-owned current canonical path; never from payload


class ArmProposalHost:
    """Read-only job admission/status; must be paired with actual native routes.

    Call under the document lock. Close/replacement must call close(), including
    when the panel disappears. UI supplies neither path nor ownership evidence.
    """
    def __init__(self,ports:ProposalPorts,jobs):self.ports=ports;self.jobs=jobs

    def start(self,raw):
        state=P.check(self.ports.read_bank());people=self.ports.read_people()
        p=envelope(raw,self.ports.binding(),state,people);payload=p['payload']
        if p['action']!='proposal' or set(payload)!={'segment','region','device'} or payload['segment'] not in S.SEGMENTS:raise ValueError('Invalid arm proposal request')
        record=B.target(state,p['body_ref'])['record']
        from .arm_shape_selection import ownership_evidence
        evidence=ownership_evidence(record,[r['record'] for r in state['bodies'].values()],people)
        context={k:p[k] for k in ('document_id','document_epoch','body_graph_sha256','people_graph_sha256')}
        return self.jobs.start(p['request_id'],self.ports.source_path(),record,payload['segment'],payload['region'],evidence,payload['device'],context)

    def status(self,job_id):
        result=self.jobs.status(job_id)
        if result.get('context') is not None:
            binding=self.ports.binding();context=result['context']
            stale=any(binding[k]!=context[k] for k in ('document_id','document_epoch')) or P.graph_digest(self.ports.read_bank())!=context['body_graph_sha256'] or P.people_digest(self.ports.read_people())!=context['people_graph_sha256']
            if stale:
                self.jobs.cancel(job_id)
                return {'phase':'done','job_id':job_id,'success':False,'proposal':None,'error':'Source/body/people context changed; previous proposal cannot authorize review'}
        return result

    def cancel(self,job_id):
        self.jobs.release(job_id)
        return {'phase':'done','job_id':job_id,'success':False,'error':'Arm proposal released; no body edit applied','proposal':None}
    def close(self):self.jobs.close()
