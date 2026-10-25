# SPDX-License-Identifier: GPL-3.0-or-later
"""Serialized current-photo expression workflow, canonical save-copy transaction.

Pure source/model work may be cancelled through reader ingress. Mutating save is
never cancelled/retried and uses the existing creative return/history owner.
"""
from collections import OrderedDict
from copy import deepcopy
import json
import os
from . import expression_replacement_stage as ST
from . import expression_replacement_source as SRC
from .expression_replacement_jobs import controller as jobs, current_hash, valid_id

MAX_RECEIPTS=256
MAX_RECEIPT_BYTES=96_000_000


def equal(a,b):
    if type(a) is not type(b):return False
    if isinstance(a,dict):return set(a)==set(b) and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return a==b


def budget():
    from .creative_document_host import memory_budget
    return min(2_000_000_000,memory_budget())


class Service:
    def __init__(self,engine,emit):
        self.engine,self.emit=engine,emit
        self.target=None;self.donor=None;self.current=None;self.hot=None
        self.candidate=None;self.preview_packet=None
        self.receipts=OrderedDict()
        self.uncertain=None

    def _base(self,packet):
        c=packet['command']
        return {'version':1,'operation_id':ST.OP,'request_id':c['request_id'],
                'command_sha256':packet['command_sha256'],'action':c['action'],
                'binding':deepcopy(c['binding'])}

    def _event(self,request,result,*,packet=None):
        base={'event':'expression_replacement_result','request_id':request['request_id']}
        return {**base,'receipt':{**self._base(packet),**result}} if packet is not None else {**base,**result}

    def _remember(self,request,event):
        ident=request['request_id']
        self.receipts[ident]={'request':deepcopy(request),'event':deepcopy(event)}
        self.receipts.move_to_end(ident)
        # Completed read imagery may be released, never a write's result/fence.
        def size():return sum(len(json.dumps(r['event'],ensure_ascii=False).encode('utf-8')) for r in self.receipts.values())
        for key,row in self.receipts.items():
            if size()<=MAX_RECEIPT_BYTES:break
            if key==ident or row['request']['action']=='apply':continue
            packet=row['request'].get('packet')
            row['event']=self._event(row['request'],{'phase':'unknown','message':'只读结果图像已释放，请重新明确读取；没有重发修改'},packet=packet)
        while len(self.receipts)>MAX_RECEIPTS:
            victim=next((key for key,row in self.receipts.items() if row['request']['action']!='apply' and key!=ident),None)
            if victim is None:break
            self.receipts.pop(victim)
        return event

    def _guard(self):
        if self.uncertain is not None:raise ValueError('表情保存副本结果尚不确定，请先核对原请求，不得重新应用')
        from .creative_document_host import CreativeHost
        reason=CreativeHost(self.engine,self.emit).guard('expression_replacement')
        if reason:raise ValueError(reason)

    def _binding(self,capture):
        fence=capture.document_fence
        return {key:fence[key] for key in ('document_id','document_epoch','load_id',
                'document_revision','state_revision','association_revision','people_graph_sha256')} | {'source':ST.source(capture)}

    def _require_current(self,binding):
        if self.target is None or self.current is None or not equal(binding,self.current['binding']):
            raise ValueError('表情会话不是当前完整编辑结果的确切来源，请重新读取')
        if SRC.current_fence(self.engine)!=self.target.document_fence:
            raise ValueError('读取表情后照片、原片或修图配方已经变化，旧候选不能提交')

    def _cancelled(self,event):
        try:return event() or SRC.hot_fence(self.engine)!=self.hot
        except (ValueError,OSError,IndexError):return True

    def acquire(self,request):
        self._guard()
        from .expression_replacement_native import capability
        cap=capability()
        if not cap['available']:raise ValueError(cap['reason'])
        self.target=None;self.donor=None;self.current=None
        self.candidate=None;self.preview_packet=None
        digest=current_hash(request)
        def work(event):
            maximum=budget()
            target=SRC.capture_current(self.engine,max_bytes=maximum,cancelled=event)
            remaining=maximum-SRC.resident_bytes(target)
            photo=ST.photograph(target,'当前照片完整编辑结果',max_bytes=remaining,cancelled=event)
            if event():raise InterruptedError('Current expression source acquisition cancelled')
            if SRC.current_fence(self.engine)!=target.document_fence:raise ValueError('Current source changed after analysis')
            return target,photo
        target,photo=jobs(self.engine).run(request['request_id'],digest,work)
        self.target=target;self.hot=SRC.hot_fence(self.engine)
        self.current={'binding':self._binding(target),'photo':photo,'available':True,'unavailable_reason':None}
        return self._event(request,{'phase':'current_ready','current':deepcopy(self.current)})

    def choose(self,request,packet):
        c=packet['command']
        if set(c)!={'version','operation_id','action','request_id','binding'}:raise ValueError('Malformed donor acquisition')
        self._guard();self._require_current(c['binding'])
        self.candidate=None;self.preview_packet=None;self.donor=None
        path=request.get('path')
        if path is None:return self._event(request,{'phase':'cancelled','no_write':True,'message':'未选择供体文件；未开始读取或修改'},packet=packet)
        if type(path) is not str or len(path)>4096 or not os.path.isabs(path) or not os.path.isfile(path):
            raise ValueError('供体必须是用户明确选择的本地普通图片文件')
        def work(event):
            stopped=lambda:self._cancelled(event)
            maximum=budget()-SRC.resident_bytes(self.target)
            donor=SRC.capture_file(path,max_bytes=maximum,cancelled=stopped)
            if donor.original_sha256==self.target.original_sha256:raise ValueError('请选择同场次的另一张真实照片，而不是当前原片')
            photo=ST.photograph(donor,os.path.basename(path),max_bytes=maximum-SRC.resident_bytes(donor),cancelled=stopped)
            self._require_current(c['binding'])
            return donor,photo
        donor,photo=jobs(self.engine).run(c['request_id'],packet['command_sha256'],work)
        self.donor=donor
        return self._event(request,{'phase':'donor_ready','photo':photo},packet=packet)

    def preview(self,request,packet):
        c=packet['command'];self._guard();self._require_current(c['binding'])
        if self.donor is None:raise ValueError('没有当前会话持有的真实供体，不能凭前端 FaceRef 猜测像素')
        self.candidate=None;self.preview_packet=None
        def work(event):
            result=ST.prepare(c,self.target,self.donor,max_bytes=budget(),cancelled=lambda:self._cancelled(event))
            self._require_current(c['binding'])
            return result
        result=jobs(self.engine).run(c['request_id'],packet['command_sha256'],work)
        self.candidate=result;self.preview_packet=deepcopy(packet)
        return self._event(request,{'phase':'ready','preview':deepcopy(result.preview)},packet=packet)

    def apply(self,request,packet):
        c=packet['command'];self._guard();self._require_current(c['binding'])
        required={'version','operation_id','action','request_id','binding','return_mode','preview_request_id',
                  'preview_command_sha256','preview_token','candidate_sha256','fusion_mask_sha256',
                  'before_image_sha256','after_image_sha256','fusion_image_sha256','review'}
        if set(c)!=required or c['return_mode']!='new_image' or c['review']!='full_before_after_and_fusion_confirmed':
            raise ValueError('表情替换只能明确比较完整图像后另存新副本')
        candidate=self.candidate;prior=self.preview_packet
        if candidate is None or prior is None:raise ValueError('原表情候选已释放或尚未生成，请重新预览')
        if c['preview_request_id']!=prior['command']['request_id'] or c['preview_command_sha256']!=prior['command_sha256']:
            raise ValueError('表情应用与完整预览请求不一致')
        review=candidate.preview
        expected={key:review[key] for key in ('preview_token','candidate_sha256','fusion_mask_sha256')}
        expected.update(before_image_sha256=review['before']['sha256'],after_image_sha256=review['after']['sha256'],fusion_image_sha256=review['fusion_image']['sha256'])
        if any(c[key]!=value for key,value in expected.items()):raise ValueError('表情应用缺少实际完整图像及融合范围的确切确认')
        from .creative_document_host import CreativeHost
        host=CreativeHost(self.engine,self.emit)
        for record in candidate.assets.values():host.assets.intern(record)
        # Mark uncertainty BEFORE entering the existing atomic copy transaction.
        self.uncertain=deepcopy(packet)
        pending=self._event(request,{'phase':'unknown','message':'保存副本已进入提交阶段，请核对原请求，不要重复应用'},packet=packet)
        self._remember(request,pending)
        result=host.commit_return({'mode':'new_image','rendered_asset':candidate.rendered_asset,
                                   'creative_document':deepcopy(candidate.document)})
        row=self.engine._docs[self.engine._doc_index]
        base=self.engine._creative_base
        if (result.get('status')!='applied' or result.get('document_id')!=row['document_id']
                or row['document_id']==c['binding']['document_id'] or base['id']!=candidate.rendered_asset):
            raise RuntimeError('表情副本提交证明不一致；结果仍不确定，不得重发')
        revision=self.engine._document_versions().version(row).revision
        receipt={**expected,'phase':'committed','result_document_id':row['document_id'],
                 'copied_original_document_id':c['binding']['document_id'],'result_source_sha256':base['id'][7:],
                 'result_revision':revision,'no_change':candidate.no_change}
        for key in ('before_image_sha256','after_image_sha256','fusion_image_sha256'):receipt.pop(key)
        self.uncertain=None;self.target=None;self.donor=None;self.current=None;self.candidate=None;self.preview_packet=None
        return self._event(request,receipt,packet=packet)

    def handle(self,request):
        packet=None;ident=request.get('request_id');action=request.get('action')
        if not valid_id(ident):raise ValueError('Invalid expression request identity')
        old=self.receipts.get(ident)
        if old is not None:
            if old['request']!=request:raise ValueError('Expression request identity reused with different envelope')
            self.emit(deepcopy(old['event']));return
        try:
            allowed={'cmd','action','request_id'}
            if action in ('choose_donor','preview','apply'):
                allowed.add('packet')
                if action=='choose_donor' and 'path' in request:allowed.add('path')
                if set(request)!=allowed:raise ValueError('Unknown expression request fields')
                c=ST.packet(request['packet'])
                if type(c.get('binding')) is not dict:raise ValueError('Expression packet lacks document binding')
                packet=deepcopy(request['packet']);packet['command']=c
                if c.get('action')!=action or c.get('request_id')!=ident or not valid_id(c.get('request_id')):
                    raise ValueError('Expression envelope differs from exact packet')
                event={'choose_donor':self.choose,'preview':self.preview,'apply':self.apply}[action](request,packet)
            elif action=='current':event=self.acquire(request)
            elif action=='release':
                if set(request)!=allowed|{'preview_token'} or not valid_id(request['preview_token']):raise ValueError('Invalid expression release')
                if self.candidate is not None and self.candidate.preview['preview_token']==request['preview_token']:
                    self.candidate=None;self.preview_packet=None
                event=self._event(request,{'phase':'released','preview_token':request['preview_token']})
            else:raise ValueError('Unsupported expression action')
        except InterruptedError as error:
            event=self._event(request,{'phase':'cancelled','no_write':True,'message':str(error)},packet=packet)
        except Exception as error:
            unknown=action=='apply' and self.uncertain is not None
            result={'phase':'unknown' if unknown else 'rejected','message':str(error)}
            if not unknown:result['no_write']=True
            event=self._event(request,result,packet=packet)
        if action in ('current','choose_donor','preview'):
            try:
                digest=current_hash(request) if action=='current' else request['packet']['command_sha256']
                jobs(self.engine).retire(ident,digest)
            except (ValueError,KeyError,TypeError):pass
        self.emit(self._remember(request,event))


def service(engine,emit):
    owner=engine.__dict__.get('_expression_replacement_service')
    if owner is None:owner=Service(engine,emit);engine._expression_replacement_service=owner
    return owner


def handle(engine,request,emit):
    service(engine,emit).handle(request)


def blocks(engine,name):
    owner=engine.__dict__.get('_expression_replacement_service')
    if owner is not None and owner.uncertain is not None and name not in ('expression_replacement','shutdown'):
        return '表情副本原请求结果尚未确认，其他修改暂时被保护；不能盲目重试或假装取消'
    return None


def read_only(request):
    return request.get('cmd')=='expression_replacement' and request.get('action') in ('current','choose_donor','preview','release')

def guard_other(engine,name,request):
    reason=blocks(engine,name)
    if reason and name not in ('hello',) and not (name=='session' and request.get('action')=='query'):
        raise ValueError(reason)


def dispatch_rejected(engine,request,message,started,emit):
    """Settle only exact never-started requests rejected by outer engine guards."""
    if type(request) is not dict or not valid_id(request.get('request_id')):return
    owner=service(engine,emit);packet=None
    try:
        if request.get('action') in ('choose_donor','preview','apply'):
            command=ST.packet(request.get('packet'))
            if command.get('request_id')!=request['request_id'] or command.get('action')!=request['action'] or type(command.get('binding')) is not dict:return
            packet=request['packet']
        elif request.get('action')=='current':current_hash(request)
        elif request.get('action')!='release':return
        old=owner.receipts.get(request['request_id'])
        if old is not None:
            if equal(old['request'],request):emit(deepcopy(old['event']))
            return
        unknown=bool(started and request.get('action')=='apply')
        result={'phase':'unknown' if unknown else 'rejected','message':str(message)}
        if not unknown:result['no_write']=True
        event=owner._event(request,result,packet=packet)
        if request.get('action') in ('current','choose_donor','preview'):
            digest=current_hash(request) if packet is None else packet['command_sha256']
            jobs(engine).retire(request['request_id'],digest)
        emit(owner._remember(request,event))
    except (ValueError,TypeError,KeyError):return
