"""Bounded exact-request transport; uncertain outcomes are never replayed."""
from collections import OrderedDict
from copy import deepcopy
import base64
import io
import json
import uuid
from . import body_pose_evidence as E,body_pose_state as B,body_pose_render as R
from . import body_pose_acquisition as acquisition,shoulder_shape_host as H


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def checked_binding(engine,value):
    binding=engine._people_binding()
    if type(value) is not dict or value!=binding:raise ValueError('Body command source/document revision changed')
    return binding


def source_preview(engine):
    import numpy as np
    from PIL import Image
    from .creative_derived_source import analysis_rgb
    source=R.source(engine._people_source());rgb=np.asarray(analysis_rgb(engine))
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[2]!=3:raise ValueError('Canonical unretouched body preview RGB8 is unavailable')
    h,w=rgb.shape[:2]
    E.whole_source_shape(source,(h,w))
    image=Image.fromarray(rgb,'RGB');image.thumbnail((1280,1280));buffer=io.BytesIO();image.save(buffer,format='PNG')
    data=buffer.getvalue()
    if R.source(engine._people_source())!=source:raise ValueError('Body preview source changed during thumbnail preparation')
    if len(data)>6*1024*1024:raise ValueError('Body source preview exceeds 6 MiB')
    return {'mime':'image/png','base64':base64.b64encode(data).decode('ascii'),'width':image.width,'height':image.height,'source_sha256':source['sha256'],
            'source_width':source['width'],'source_height':source['height'],'decoded_width':w,'decoded_height':h,
            'mapping':'normalized_full_frame','orientation':E.ORIENTATION}


def response(engine,*,preview=False,receipt=None,operation='shoulder_shape'):
    result={'view':engine._body_view(operation),'model':acquisition.status()}
    if preview:result['source_preview']=source_preview(engine)
    if receipt is not None:result['receipt']=receipt
    return result


def commit_observations(engine,candidate,request_id,operation='shoulder_shape'):
    before=engine._body_bank()
    try:prepared=engine._body_prepare(candidate)
    except (ValueError,RuntimeError,OSError) as error:prepared=H.UnappliedPreparation(str(error))
    # Detection/replacement retains genuine evidence even when an operation is
    # now unsupported. It must then display the explicitly unapplied original.
    from .shoulder_shape_project import history_patch
    request={'request_id':request_id,'gesture_id':request_id}
    if operation in ('leg_shape','waist_shape','leg_length','neck_shape','torso_length','waist_length','head_size'):request['operation_id']='lnx.'+operation+'.v1'
    engine._body_publish(before,candidate,prepared,history_patch(before,candidate),request)


def apply(engine,message):
    operation=message['cmd'];action=message['action'];request=message['request']
    def current(**kwargs):return response(engine,operation=operation,**kwargs)
    if type(request) is not dict:raise ValueError('Body request must be an object')
    if action=='status':
        if set(request)!={'request_id'}:raise ValueError('Status needs the original inner request ID')
        receipt=engine._body_status(E.token(request['request_id']),operation);result={'receipt':receipt}
        try:result['view']=engine._body_view(operation)
        except (ValueError,RuntimeError,OSError,IndexError) as error:result['view_error']=str(error)
        try:result['model']=acquisition.status()
        except (ValueError,RuntimeError,OSError) as error:result['model_error']=str(error)
        return result
    why=engine._guard_editable(operation)
    if why:raise ValueError(why)
    engine._people_bind()
    if action=='view':
        if request!={}:raise ValueError('View does not mutate body intent')
        return current(preview=True)
    if action=='select':
        if set(request)!={'binding','body_ref'}:raise ValueError('Select an explicit retained BodyRef')
        binding=checked_binding(engine,request['binding']);ref=E.ref(request['body_ref']);B.target(engine._body_bank(),ref)
        if ref['asset_sha256']!=binding['asset_sha256']:raise ValueError('Body selection belongs to another source')
        engine._body_cursors[binding['asset_sha256']]=ref
        return current(preview=True)
    if action not in ('edit','analyse','reanalyse'):raise ValueError('Unsupported body action; optional model acquisition uses its separate native process')
    engine._cancel_snapshot(operation);engine._close_owned_previews()
    if action=='edit':
        if request.get('request_id')==message['request_id']:raise ValueError('Inner edit and outer transport IDs must be distinct')
        receipt=engine._body_adapter(operation).execute(request)
        # If a notification failed after the authoritative outcome, reconcile it
        # without applying the request again.
        if receipt.get('outcome_unknown'):receipt=engine._body_status(request['request_id'],operation)
        return current(receipt=receipt)
    if action=='analyse':
        if set(request)!={'binding'}:raise ValueError('Analysis requires the exact current document binding')
        binding=checked_binding(engine,request['binding'])
        from .body_pose_runtime import analyse
        from .cpu_memory_budget import available_estimate
        import numpy as np
        from hashlib import sha256
        from .creative_derived_source import analysis_rgb, binding as source_binding, verify
        source=source_binding(engine)
        current_rgb=np.asarray(analysis_rgb(engine))
        if current_rgb.dtype!=np.uint8 or current_rgb.ndim!=3 or current_rgb.shape[2]!=3:
            raise ValueError('Body analysis needs the actual canonical RGB8 model input')
        rgb=np.array(current_rgb,copy=True);rgb.setflags(write=False)
        input_digest=sha256(memoryview(np.ascontiguousarray(rgb))).hexdigest()
        run=analyse(rgb,R.source(source),byte_budget=available_estimate())
        checked_binding(engine,binding);verify(source,engine)
        # A source label alone is not proof: bind every retained observation to
        # the exact immutable RGB8 buffer actually submitted to the producer.
        if run['source']!=R.source(source):raise ValueError('Body producer returned another source')
        for record in run['records']:
            E.check(record)
            if (record['source']!=run['source'] or record['input_rgb_sha256']!=input_digest
                    or record['input_dimensions']!=[rgb.shape[1],rgb.shape[0]]):
                raise ValueError('Body evidence does not bind the actual analysis pixels')
        current_rgb=np.asarray(analysis_rgb(engine))
        if current_rgb.shape!=rgb.shape or current_rgb.dtype!=np.uint8 or sha256(memoryview(np.ascontiguousarray(current_rgb))).hexdigest()!=input_digest:
            raise ValueError('Body analysis pixels changed before publication')
        bank=engine._body_bank()
        if not bank['bodies']:
            commit_observations(engine,B.add_run(bank,run),message['request_id'],operation)
            engine._body_candidates=None
            return current(preview=True)
        run_id='pose-run:'+uuid.uuid4().hex
        engine._body_candidates={'run_id':run_id,'binding':binding,'run':run}
        choices=B.add_run(B.empty(),run)
        rows=H.view(choices,binding,selected_body_ref=None,people_state=engine._people_owner().snapshot())['bodies']
        return {**current(preview=True),'analysis_candidates':{'run_id':run_id,'bodies':rows}}
    if set(request)!={'binding','body_ref','candidate_ref','run_id','user_confirmed'}:raise ValueError('Replacement needs an explicit old body and actual newly observed candidate')
    binding=checked_binding(engine,request['binding']);candidate=engine._body_candidates
    if candidate is None or candidate['binding']!=binding or candidate['run_id']!=request['run_id'] or request['user_confirmed'] is not True:raise ValueError('Body candidate run changed; analyse again and explicitly select ownership')
    old=E.ref(request['body_ref']);new=E.ref(request['candidate_ref'])
    matches=[row for row in candidate['run']['records'] if row['body_ref']==new]
    if len(matches)!=1:raise ValueError('Replacement must name one actual candidate, never nearest face or list position')
    bank=B.reanalyse(engine._body_bank(),old,matches[0],user_confirmed=True)
    commit_observations(engine,bank,message['request_id'],operation);engine._body_candidates=None
    engine._body_cursors[binding['asset_sha256']]=deepcopy(bank['bodies'][old['body_instance_id']]['record']['body_ref'])
    return current(preview=True)


class BodyTransport:
    def __init__(self,operation='shoulder_shape'):
        if operation not in ('shoulder_shape','leg_shape','waist_shape','leg_length','neck_shape','torso_length','waist_length','head_size'):raise ValueError('Unregistered body operation transport')
        self.operation=operation;self.seen={};self.results=OrderedDict();self.bytes=0

    def handle(self,engine,message,emit):
        terminal={'event':self.operation+'_result','protocol':1,'request_id':message.get('request_id'),'action':message.get('action')}
        engine._body_mutation_started=False;ident=None;signature=None
        try:
            if set(message)!={'cmd','request_id','action','request'} or message['cmd']!=self.operation:raise ValueError('Invalid body transport envelope')
            ident=E.token(message['request_id']);raw=encoded(message)
            if len(raw)>256*1024:raise ValueError('Body request exceeds 256 KiB budget')
            signature=E.content_digest(message)
            if ident in self.seen:
                if self.seen[ident]!=signature:raise ValueError('Body transport identity reused with different content')
                if ident in self.results:emit(deepcopy(self.results[ident][0]));return
                terminal.update(success=False,outcome_unknown=True,error='Retained response released; inspect authoritative inner receipt and current document, never automatically replay')
                emit(terminal);return
            if len(self.seen)>=65536:raise ValueError('Body transport identity budget exhausted')
            self.seen[ident]=signature
            result=apply(engine,message);receipt=result.get('receipt')
            terminal.update(success=(True if message['action']=='status' else receipt.get('success',False)) if receipt else True,outcome_unknown=bool(receipt and receipt.get('outcome_unknown')),result=result)
            if receipt and not terminal['success']:terminal['error']=receipt.get('error') or receipt.get('reason') or 'Body request remains pending; inspect the original receipt'
        except Exception as error:
            actual=engine._body_authoritative.get(ident) if ident is not None else None
            if actual is not None and message.get('action') in ('analyse','reanalyse'):
                # Real state/frame/history publication completed; only a later
                # notification failed. This is a lookup, not a mutation retry.
                try:terminal.update(success=True,outcome_unknown=False,result=response(engine,operation=self.operation))
                except Exception:terminal.update(success=False,outcome_unknown=True,error=str(error))
            else:terminal.update(success=False,outcome_unknown=engine._body_mutation_started or message.get('action')=='status',error=str(error))
        if ident is not None and signature is not None and self.seen.get(ident)==signature:
            size=len(encoded(terminal))
            if size<=9*1024*1024:
                while self.results and self.bytes+size>24*1024*1024:
                    _,(_,used)=self.results.popitem(last=False);self.bytes-=used
                self.results[ident]=(deepcopy(terminal),size);self.bytes+=size
        emit(terminal)
