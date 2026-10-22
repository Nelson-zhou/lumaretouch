"""Bounded frozen local-mask/automatic-optics preset reviews; no editor writes."""
from . import brow_shape_scope as BROW, nose_shape_scope as NOSE
from collections import OrderedDict
from copy import deepcopy
import time
import uuid
from . import scope as SC, local_grade_layers as LG, local_grade_runtime as LR
from . import sky_replacement_scope as SKY, optics_auto_scope as OA, optics_transfer_review as OR
from .batch_preflight import canonical


class PresetReviews:
    def __init__(self):self.pending=OrderedDict()

    def prepare(self,preset,state,row,document_id,revision,options,prepare_optics=None):
        modules=preset['modules'];SC.check_scope(list(modules))
        if LG.OP not in modules and OA.OP not in modules:raise ValueError('此预设不含需要冻结目标预检的模块')
        if LG.OP in modules:prepared,transfer=LR.prepare_modules(state,modules,row,options,preview=True)
        else:
            if options is not None:raise ValueError('未选择局部组，不能附带蒙版选项')
            prepared,transfer=deepcopy(modules),None
        candidate=OA.candidate(state,prepared,local_replace_legacy=bool(transfer and transfer['legacy_removed']))
        if SKY.OP in prepared:SKY.validate_target(candidate['_sky_replacement'],row['path'],(row['src_h'],row['src_w']))
        if BROW.OP in prepared and OA.OP not in prepared:BROW.validate_target(candidate,row)
        if NOSE.OP in prepared and OA.OP not in prepared:NOSE.validate_target(candidate,row)
        optical_record=None;optical_transfer=None
        if OA.OP in prepared:
            if prepare_optics is None:raise ValueError('本引擎缺少目标完整编辑预检端口')
            target_input=prepare_optics(row,candidate,document_id,str(revision))
            optical_record,optical_transfer=OR.prepare(prepared[OA.OP],target_input,before_state=state,preview=True)
        token=uuid.uuid4().hex
        record={'preset':deepcopy(preset),'modules':prepared,'transfer':transfer,'optics':optical_record,
                'document_id':document_id,'revision':str(revision),'path':row['path'],
                'before':canonical(OA.before_params(state,list(modules))),'local_key':LG.undo_key(state) if LG.OP in modules else None,
                'expires':time.monotonic()+30*60}
        canonical(record);self.pending[token]=record
        while len(self.pending)>8:self.pending.popitem(last=False)
        return {'id':preset['id'],'name':preset['name'],'module_scope':list(modules),
                'preflight_token':token,'applies':deepcopy(prepared),'local_mask_transfer':transfer,'optical_transfer':optical_transfer,
                'document_id':document_id,'revision':str(revision)}

    def claim(self,token,preset_id,state,row,document_id,revision):
        if type(token) is not str or token not in self.pending:raise ValueError('目标预设预检已失效或使用，请重新预检')
        record=self.pending[token]
        if time.monotonic()>=record['expires']:raise ValueError('目标预设预检已过期，请重新预检')
        if (record['preset']['id']!=preset_id or record['document_id']!=document_id or record['path']!=row['path'] or record['revision']!=str(revision)):
            raise ValueError('照片、版本或预设与预检不同，请重新预检')
        if canonical(OA.before_params(state,list(record['modules'])))!=record['before'] or (record['local_key'] is not None and LG.undo_key(state)!=record['local_key']):
            raise ValueError('照片在预检后发生修改，请重新预检')
        if LG.OP in record['modules']:LR.verify_modules(record['modules'],{**row,'state':state},record['transfer'])
        candidate=OA.candidate(state,record['modules'],local_replace_legacy=bool(record['transfer'] and record['transfer']['legacy_removed']))
        if SKY.OP in record['modules']:SKY.validate_target(candidate['_sky_replacement'],row['path'],(row['src_h'],row['src_w']))
        if BROW.OP in record['modules'] and OA.OP not in record['modules']:BROW.validate_target(candidate,row)
        if NOSE.OP in record['modules'] and OA.OP not in record['modules']:NOSE.validate_target(candidate,row)
        if OA.OP in record['modules']:OA.verify_target(record['optics'],state,candidate,row,document_id,revision,record['modules'][OA.OP])
        del self.pending[token]
        return record
