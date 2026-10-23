# SPDX-License-Identifier: GPL-3.0-or-later
"""Source/native-scope-ready mutations using the shared host lock/history/render.

The canonical body host owns publication, history and process-lifetime receipts.
"""
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable
from . import body_pose_state as B, body_pose_evidence as E, neck_shape_state as S
from . import neck_shape_project as P
from .shoulder_shape_host import UnappliedPreparation, PublicationNotStarted
from .people_render_runtime import PreparedPeople


class PublicationMismatch(RuntimeError):
    """A rejected actual outcome is not a lost notification and cannot be upgraded."""


@dataclass(frozen=True)
class HostPorts:
    binding:Callable
    read_bank:Callable
    read_people:Callable
    prepare:Callable
    publish:Callable
    receipt_get:Callable  # canonical process-lifetime host ledger: request_id -> {digest,result} or None
    receipt_put:Callable  # monotonic process-lifetime ledger write(request_id,digest,result)


def envelope(raw,binding,state,people):
    required={'request_id','gesture_id','document_id','document_epoch','document_revision',
              'state_revision','association_revision','people_association_revision',
              'body_graph_sha256','people_graph_sha256','body_ref','operation_id','action','payload'}
    if type(raw) is not dict or set(raw)!=required: raise ValueError('Invalid neck native command envelope')
    E.token(raw['request_id']);E.token(raw['gesture_id'])
    if raw['operation_id']!=S.OPERATION_ID: raise ValueError('Neck command operation mismatch')
    for key in ('document_id','document_epoch','document_revision'):
        if raw[key]!=binding[key]: raise ValueError('Document changed during neck edit')
    if raw['state_revision']!=state['revision'] or raw['association_revision']!=state['association_revision'] or raw['people_association_revision']!=people['association_revision']:
        raise ValueError('Body/person association changed during neck edit')
    if E.digest(raw['body_graph_sha256'])!=P.graph_digest(state) or E.digest(raw['people_graph_sha256'])!=P.people_digest(people):
        raise ValueError('Canonical body or people graph changed during neck edit')
    if E.ref(raw['body_ref'])['asset_sha256']!=binding['asset_sha256']: raise ValueError('Neck target belongs to another source')
    B.target(state,raw['body_ref'])
    if type(raw['payload']) is not dict: raise ValueError('Invalid neck payload')
    return deepcopy(raw)


class NeckHostAdapter:
    """Host serializes execute with its actual document edit lock.

    Publish retains intent through the canonical body/history owner and returns
    its authoritative view. Partial publication stays query-only; no replay or
    false rollback is inferred from a lost notification.
    """
    def __init__(self,ports:HostPorts,*,receipt_budget=4096):
        if type(receipt_budget) is not int or not 1<=receipt_budget<=65536: raise ValueError('Invalid neck receipt budget')
        self.ports=ports;self.receipt_budget=receipt_budget;self.receipts=OrderedDict()

    def status(self,request_id):
        request_id=E.token(request_id)
        row=self.ports.receipt_get(request_id)
        if row is not None:self.receipts[request_id]=deepcopy(row)
        else:row=self.receipts.get(request_id)
        return deepcopy(row['result']) if row else {'phase':'unavailable','request_id':request_id,'reason':'No retained result; do not replay an uncertain neck edit'}

    def execute(self,raw):
        if type(raw) is not dict: raise ValueError('Invalid neck request')
        request=E.token(raw.get('request_id')); digest=E.content_digest(raw)
        retained=self.ports.receipt_get(request)
        if retained is not None:self.receipts[request]=deepcopy(retained)
        if request in self.receipts:
            if self.receipts[request]['digest']!=digest: raise ValueError('Neck request ID was reused with changed content')
            return self.status(request)
        if len(self.receipts)>=self.receipt_budget: raise ValueError('Neck receipt budget reached; retain host ledger before admitting more edits')
        self.receipts[request]={'digest':digest,'result':{'phase':'pending','request_id':request,'outcome_unknown':False}}
        # Claim before publication in the current native/document epoch. A new
        # process has a new epoch; this is not a durable restart ledger.
        self.ports.receipt_put(request,digest,deepcopy(self.receipts[request]['result']))
        publishing=False
        try:
            before=P.check(self.ports.read_bank());people=self.ports.read_people()
            p=envelope(raw,self.ports.binding(),before,people)
            ref=p['body_ref'];payload=p['payload'];action=p['action'];candidate=before
            row=B.target(before,ref);current=row['operations'].get(S.OPERATION_ID)
            if action=='recipe':
                base=S.neutral() if current is None else current['recipe']
                if set(payload)!={'base','recipe'} or S.check(payload['base'])!=base: raise ValueError('Neck base recipe changed')
                candidate=B.set_recipe(before,ref,payload['recipe'],operation_id=S.OPERATION_ID,operation_policies=S.policies())
            elif action=='support_review':
                if set(payload)!={'data','points_sha256','visible_anchors','ownership_confirmed'} or payload['points_sha256']!=row['record']['points_sha256']:
                    raise ValueError('Neck support review does not name the current full pose digest')
                # One transaction stores the immutable source asset AND its review.
                candidate=B.set_support(before,ref,S.OPERATION_ID,S.SUPPORT_KIND,payload['data'],operation_policies=S.policies())
                support=B.operation(candidate,ref,S.OPERATION_ID)['support_sha256']
                candidate=B.review(candidate,ref,operation_id=S.OPERATION_ID,support_sha256=support,
                                   points_sha256=payload['points_sha256'],visible_anchors=payload['visible_anchors'],
                                   ownership_confirmed=payload['ownership_confirmed'],operation_policies=S.policies())
            elif action=='operation_status':
                if set(payload)!={'enabled'}: raise ValueError('Invalid neck enable command')
                if current is None:candidate=B.set_recipe(before,ref,S.neutral(),operation_id=S.OPERATION_ID,operation_policies=S.policies())
                candidate=B.set_operation_enabled(candidate,ref,S.OPERATION_ID,payload['enabled'],operation_policies=S.policies())
            else: raise ValueError('Unsupported neck command')
            try: prepared=self.ports.prepare(candidate)
            except (ValueError,RuntimeError,OSError) as error:
                if action=='recipe': raise
                # Correction can be retained while another operation remains unsafe.
                # Host shows explicitly original/unapplied, never stale edited output.
                prepared=UnappliedPreparation(str(error))
            if not isinstance(prepared,(PreparedPeople,UnappliedPreparation)):
                raise ValueError('Neck host preparation must return the actual common geometry, not a placeholder')
            envelope(raw,self.ports.binding(),self.ports.read_bank(),self.ports.read_people())
            P.history_patch(before,candidate,people_sha256=p['people_graph_sha256'])
            from .shoulder_shape_project import history_patch
            patch=history_patch(before,candidate)
            publishing=True
            authoritative=self.ports.publish(before,candidate,prepared,patch,p)
            if type(authoritative) is not dict or authoritative.get('state_revision')!=candidate['revision'] or authoritative.get('body_graph_sha256')!=P.graph_digest(candidate):
                raise PublicationMismatch('Host did not return the actual published neck graph revision')
            publication=authoritative.get('publication')
            if type(publication) is not dict or publication.get('request_id')!=request or type(publication.get('rendered')) is not bool:
                raise PublicationMismatch('Canonical body host omitted its actual publication outcome')
            if publication['rendered']:
                try:_verify_publication(authoritative.get('last_outcome'),prepared,p)
                except Exception as error:raise PublicationMismatch(str(error)) from error
            result={'phase':'done','protocol':1,'request_id':request,'success':True,'outcome_unknown':False,
                    'rendered':publication['rendered'],'unapplied_reason':publication.get('unapplied_reason'),'view':authoritative}
        except Exception as error:
            publishing=publishing and not isinstance(error,PublicationNotStarted)
            result={'phase':'pending' if publishing else 'done','protocol':1,'request_id':request,
                    'success':False,'outcome_unknown':publishing,'publication_invalid':isinstance(error,PublicationMismatch),'error':str(error)}
        try:self.ports.receipt_put(request,digest,deepcopy(result))
        except (ValueError,RuntimeError,OSError) as error:
            result={'phase':'pending','protocol':1,'request_id':request,'success':False,
                    'outcome_unknown':publishing,'error':'Process result retention failed; query host ledger: '+str(error)}
        self.receipts[request]['result']=result
        return deepcopy(result)

    def resolve_publication(self,request_id,*,actual_result):
        row=self.receipts.get(E.token(request_id))
        if row is None or not row['result'].get('outcome_unknown') or row['result'].get('publication_invalid'): raise ValueError('No uncertain neck publication is pending')
        if type(actual_result) is not dict or actual_result.get('request_id')!=request_id or actual_result.get('phase')!='done' or actual_result.get('outcome_unknown') is not False:
            raise ValueError('Authoritative host terminal result required')
        self.ports.receipt_put(request_id,row['digest'],deepcopy(actual_result))
        row['result']=deepcopy(actual_result)


def view(state,binding,*,selected_body_ref,people_state,refusals=()):
    state=P.check(state);source=binding['asset_sha256'];selected=None
    if selected_body_ref is not None:
        selected=B.target(state,selected_body_ref)
        if selected_body_ref['asset_sha256']!=source: raise ValueError('Selected neck target belongs to another source')
    rows=[]
    for row in state['bodies'].values():
        record=row['record']
        if record['source']['sha256']!=source:continue
        item=row['operations'].get(S.OPERATION_ID)
        rows.append({'body_ref':deepcopy(record['body_ref']),'enabled':row['enabled'],
                     'operation_enabled':item['enabled'] if item else True,
                     'points':deepcopy(record['points']),'points_sha256':record['points_sha256'],
                     'source':deepcopy(record['source']),'reviewed':item is not None and item['review'] is not None,
                     'support':None if item is None or item['support_sha256'] is None else deepcopy(B.support(state,record['body_ref'],S.OPERATION_ID)['data']),
                     'association':deepcopy(row['association'])})
    item=None if selected is None else selected['operations'].get(S.OPERATION_ID)
    return {'binding':deepcopy(binding),'state_revision':state['revision'],'association_revision':state['association_revision'],
            'people_association_revision':people_state['association_revision'],'body_graph_sha256':P.graph_digest(state),
            'people_graph_sha256':P.people_digest(people_state),'bodies':rows,'selected_body_ref':deepcopy(selected_body_ref),
            'recipe':S.neutral() if item is None else deepcopy(item['recipe']),'refusals':deepcopy(list(refusals)),
            'persons':deepcopy(people_state['persons']),'analysis_run':deepcopy(state['analysis_runs'].get(source))}


def _verify_publication(receipt,prepared,request):
    from hashlib import sha256
    import numpy as np
    if not isinstance(prepared,PreparedPeople) or type(receipt) is not dict or receipt.get('version')!=1 or receipt.get('request_id')!=request['request_id']:
        raise PublicationMismatch('Actual published common-map receipt is missing or stale')
    E.token(receipt.get('published_frame_id'));E.revision(receipt.get('render_revision'));E.digest(receipt.get('output_pixel_sha256'))
    geometry=prepared.geometry;h,w=geometry.delta.shape[1:3]
    digest=sha256(memoryview(np.ascontiguousarray(geometry.delta))).hexdigest()
    if receipt.get('geometry_delta_sha256')!=digest or receipt.get('render_dimensions')!=[w,h] or receipt.get('body_operation_order')!=prepared.body_operation_order or receipt.get('single_source_sample') is not True or receipt.get('runtime_quality_accepted') is not False:
        raise PublicationMismatch('Neck publication differs from the exact prepared single-sample geometry')
