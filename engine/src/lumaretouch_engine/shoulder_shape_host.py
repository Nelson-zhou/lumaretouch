"""Document/BodyRef-fenced source adapter for existing host publication/history.

The shared body host supplies real transaction/render callbacks. This adapter
never fabricates a successful field, published frame, or runtime acceptance.
"""
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable
from . import body_pose_state as B, body_pose_evidence as E, shoulder_shape_state as S
from .shoulder_shape_project import history_patch
from . import body_pose_operations as O


class PublicationNotStarted(ValueError):
    """Trusted host refusal raised only before its first publication write."""


@dataclass(frozen=True)
class HostPorts:
    binding:Callable  # returns document_id, document_epoch, document_revision, asset_sha256
    read_bank:Callable
    read_people:Callable
    prepare:Callable  # candidate bank -> actual prepared common-map publication, may refuse
    publish:Callable  # before, candidate, prepared, history patch, request -> actual authoritative view


@dataclass(frozen=True)
class UnappliedPreparation:
    reason:str
    # publish must suspend edited output and show an explicitly labelled original,
    # never report a stale edited preview as successful rendering.
    rendered:bool=False


def envelope(raw,binding,state):
    required={'request_id','gesture_id','document_id','document_epoch','document_revision','state_revision','association_revision','people_association_revision','body_ref','action','payload'}
    if type(raw) is not dict or set(raw)!=required:raise ValueError('Invalid shoulder command envelope')
    E.token(raw['request_id']);E.token(raw['gesture_id'])
    for key in ('document_id','document_epoch','document_revision'):
        if raw[key]!=binding[key]:raise ValueError('Document changed during shoulder gesture')
    if raw['state_revision']!=state['revision'] or raw['association_revision']!=state['association_revision']:raise ValueError('Body state or association changed during gesture')
    if E.ref(raw['body_ref'])['asset_sha256']!=binding['asset_sha256']:raise ValueError('Shoulder target belongs to a different source')
    B.target(state,raw['body_ref'])
    if type(raw['payload']) is not dict:raise ValueError('Invalid shoulder command payload')
    return deepcopy(raw)


class ShoulderHostAdapter:
    def __init__(self,ports:HostPorts,*,receipt_budget=4096,operation_policies=None):
        self.ports=ports;self.receipts=OrderedDict();self.receipt_budget=receipt_budget;self.operation_policies=operation_policies

    def status(self,request_id):
        E.token(request_id);row=self.receipts.get(request_id)
        return deepcopy(row['result']) if row is not None else {'phase':'unavailable','request_id':request_id,'reason':'No retained result; never automatically replay an uncertain shoulder request'}

    def execute(self,raw):
        """Host serializes this with its ordinary edit lock and binds callbacks.

        Receipt IDs never evict into replayability. A full budget refuses before
        mutation. Uncertain publication keeps its request pending for inspection.
        """
        if type(raw) is not dict:raise ValueError('Invalid shoulder command')
        request=E.token(raw.get('request_id'));digest=E.content_digest(raw)
        if request in self.receipts:
            if self.receipts[request]['digest']!=digest:raise ValueError('Shoulder request ID reused with different content')
            return self.status(request)
        if len(self.receipts)>=self.receipt_budget:raise ValueError('Shoulder receipt budget reached; retain receipts in existing host ledger before continuing')
        self.receipts[request]={'digest':digest,'result':{'phase':'pending','request_id':request,'outcome_unknown':False}}
        publishing=False
        try:
            before=B.check(self.ports.read_bank(),operation_policies=self.operation_policies);binding=self.ports.binding();p=envelope(raw,binding,before)
            people=self.ports.read_people()
            if p['people_association_revision']!=people['association_revision']:raise ValueError('People association changed during shoulder gesture')
            ref=p['body_ref'];payload=p['payload'];action=p['action'];candidate=before
            if action=='recipe':
                if set(payload)!={'recipe','base'} or S.check(payload['base'])!=B.operation(before,ref)['recipe']:raise ValueError('Shoulder base recipe changed')
                candidate=B.set_recipe(before,ref,payload['recipe'],operation_policies=self.operation_policies)
            elif action=='review':
                if set(payload)!={'points_sha256','visible_anchors','ownership_confirmed'}:raise ValueError('Invalid visible body review')
                candidate=B.review(before,ref,**payload,operation_policies=self.operation_policies)
            elif action=='associate':
                if set(payload)!={'person_id','user_confirmed'}:raise ValueError('Invalid body association request')
                candidate=B.associate(before,ref,payload['person_id'],people,user_confirmed=payload['user_confirmed'])
            elif action=='operation_status':
                if set(payload)!={'operation_id','enabled'}:raise ValueError('Invalid body operation enabled request')
                candidate=B.set_operation_enabled(before,ref,payload['operation_id'],payload['enabled'],operation_policies=self.operation_policies)
            elif action=='body_status':
                if set(payload)!={'enabled'} or type(payload['enabled']) is not bool:raise ValueError('Body enabled status must be explicit')
                candidate=B.check(before);B.target(candidate,ref)['enabled']=payload['enabled'];candidate['revision']+=1
            elif action=='unlink':
                if payload!={}:raise ValueError('Invalid body unlink request')
                candidate=B.unlink(before,ref)
            else:raise ValueError('Unsupported shoulder action')
            try:
                prepared=self.ports.prepare(candidate)
            except (ValueError,RuntimeError,OSError) as error:
                if action not in ('review','associate','unlink','body_status','operation_status'):raise
                prepared=UnappliedPreparation(str(error))
            # Expensive native geometry work must not publish to a switched photo.
            envelope(raw,self.ports.binding(),self.ports.read_bank())
            if self.ports.read_people()['association_revision']!=p['people_association_revision']:raise ValueError('Person ownership changed during preparation')
            publishing=True
            view=self.ports.publish(before,candidate,prepared,history_patch(before,candidate),p)
            if type(view) is not dict or view.get('state_revision')!=candidate['revision']:raise RuntimeError('Host publication did not return the authoritative body revision')
            published=view.get('publication')
            if type(published) is not dict or published.get('request_id')!=request or type(published.get('rendered')) is not bool:raise RuntimeError('Host omitted actual publication outcome; preparation is not rendering')
            result={'phase':'done','protocol':1,'request_id':request,'success':True,'outcome_unknown':False,'rendered':published['rendered'],'unapplied_reason':published.get('unapplied_reason'),'view':view}
        except Exception as error:
            publishing=publishing and not isinstance(error,PublicationNotStarted)
            result={'phase':'pending' if publishing else 'done','protocol':1,'request_id':request,'success':False,'outcome_unknown':publishing,'error':str(error)}
        self.receipts[request]['result']=result
        return deepcopy(result)

    def resolve_publication(self,request_id,*,actual_result):
        """Host's authoritative ledger lookup only, never a retry of the mutation."""
        row=self.receipts.get(E.token(request_id))
        if row is None or not row['result'].get('outcome_unknown'):raise ValueError('No uncertain shoulder publication is pending')
        if actual_result.get('request_id')!=request_id or actual_result.get('phase')!='done' or actual_result.get('outcome_unknown') is not False:raise ValueError('Verified terminal host result required')
        row['result']=deepcopy(actual_result)


def view(state,binding,*,selected_body_ref,people_state,refusals=(),operation_policies=None):
    state=B.check(state,operation_policies=operation_policies);source=binding['asset_sha256'];selected=None
    if selected_body_ref is not None:
        selected=B.target(state,selected_body_ref)
        if selected_body_ref['asset_sha256']!=source:raise ValueError('Selected body belongs to another source')
    rows=[{'body_ref':row['record']['body_ref'],'enabled':row['enabled'],'points':row['record']['points'],'points_sha256':row['record']['points_sha256'],'source':row['record']['source'],'reviewed':row['operations'].get(S.OPERATION_ID,{}).get('review') is not None,'shoulder_enabled':row['operations'].get(S.OPERATION_ID,{'enabled':True})['enabled'],'association':row['association'],'unapplied_operations':[op for op,item in row['operations'].items() if item['enabled'] and op not in O.policies(operation_policies)]} for row in state['bodies'].values() if row['record']['source']['sha256']==source]
    return {'binding':deepcopy(binding),'state_revision':state['revision'],'association_revision':state['association_revision'],'people_association_revision':people_state['association_revision'],'bodies':rows,'selected_body_ref':deepcopy(selected_body_ref),'recipe':S.neutral() if selected is None else selected['operations'].get(S.OPERATION_ID,{'recipe':S.neutral()})['recipe'],'persons':deepcopy(people_state['persons']),'refusals':list(refusals),'analysis_run':deepcopy(state['analysis_runs'].get(source))}
