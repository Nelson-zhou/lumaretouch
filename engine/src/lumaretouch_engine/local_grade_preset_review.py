"""Bounded target-owned preset reviews; no editor writes or source rebinding."""
from . import brow_shape_scope as BROW, nose_shape_scope as NOSE, eye_shape_scope as EYE, mouth_shape_scope as MOUTH
from collections import OrderedDict
from copy import deepcopy
import time
import uuid
from . import reference_color_scope as RC
from . import scope as SC, local_grade_layers as LG, local_grade_runtime as LR
from . import sky_replacement_scope as SKY, optics_auto_scope as OA, optics_transfer_review as OR
from .batch_preflight import canonical
from . import creative_derived_transfer as DERIVED, creative_derived_source as SOURCE
from . import spill_transfer_review as SPILL_REVIEW
from . import original_shadow_transfer_review as SHADOW_REVIEW
from . import body_scalar_transfer_review as BODY_REVIEW

_NO_SPILL_ACK = object()
_NO_SHADOW_ACK = object()
_NO_TORSO_ACK = object()
_NO_WAIST_ACK = object()
_NO_HEAD_ACK = object()
_NO_COLLARBONE_ACK = object()


class PresetReviews:
    def __init__(self):
        self.pending=OrderedDict()
        self.targets={}

    def prepare(self,preset,state,row,document_id,revision,options,prepare_optics=None,prepare_reference=None,prepare_crop=None,verify_crop=None,prepare_xmp=None,verify_xmp=None,prepare_spill=None,verify_spill=None,prepare_shadow=None,verify_shadow=None,prepare_torso=None,verify_torso=None,prepare_waist=None,verify_waist=None,prepare_head=None,verify_head=None,prepare_collarbone=None,verify_collarbone=None):
        modules=DERIVED.require_modules(state,preset['modules']);SC.check_scope(list(modules))
        family=BODY_REVIEW.select(modules)
        collarbone=SC.COLLARBONE.OP in modules
        row_identity=(row.get('document_id'),row.get('path'))
        xmp=preset.get("xmp_import")
        if family is not None and xmp is not None:raise ValueError('身体长度参数须独立审核，不能附带 XMP 兼容性迁移')
        derived=SOURCE.record(state) is not None
        if xmp is None and not derived and LG.OP not in modules and OA.OP not in modules and RC.OP not in modules and SC.OP_CROP not in modules and SC.SPILL_REMOVAL.OP not in modules and SC.ORIGINAL_SHADOW.OP not in modules and family is None and not collarbone:raise ValueError('此预设不含需要冻结目标预检的模块')
        # Current captured state owns the effective source, not a stale parked
        # row state. Originals retain their existing review contract.
        proof=SOURCE.row_proof({**row,'state':state}) if xmp is not None or derived or SC.OP_CROP in modules or SC.SPILL_REMOVAL.OP in modules or SC.ORIGINAL_SHADOW.OP in modules or family is not None or collarbone else None
        if LG.OP in modules:prepared,transfer=LR.prepare_modules(state,modules,row,options,preview=True)
        else:
            if options is not None:raise ValueError('未选择局部组，不能附带蒙版选项')
            prepared,transfer=deepcopy(modules),None
        candidate=OA.candidate(state,prepared,local_replace_legacy=bool(transfer and transfer['legacy_removed']))
        if SC.SPILL_REMOVAL.OP in prepared:SC.SPILL_REMOVAL.validate_target(candidate,row["path"],(row["src_h"],row["src_w"]))
        if SC.ORIGINAL_SHADOW.OP in prepared:SC.ORIGINAL_SHADOW.validate_target(candidate,row["path"],(row["src_h"],row["src_w"]))
        if family is not None:family.scope.validate_target(candidate,row["path"],(row["src_h"],row["src_w"]))
        if SKY.OP in prepared:SKY.validate_target(candidate['_sky_replacement'],row['path'],(row['src_h'],row['src_w']))
        if BROW.OP in prepared and OA.OP not in prepared:BROW.validate_target(candidate,row)
        if NOSE.OP in prepared and OA.OP not in prepared:NOSE.validate_target(candidate,row)
        if EYE.OP in prepared and OA.OP not in prepared:EYE.validate_target(candidate,row)
        if MOUTH.OP in prepared and OA.OP not in prepared:MOUTH.validate_target(candidate,row)
        optical_record=None;optical_transfer=None
        if OA.OP in prepared:
            if prepare_optics is None:raise ValueError('本引擎缺少目标完整编辑预检端口')
            target_input=prepare_optics(row,candidate,document_id,str(revision))
            optical_record,optical_transfer=OR.prepare(prepared[OA.OP],target_input,before_state=state,preview=True)
        reference_record=None
        if RC.OP in prepared:
            if prepare_reference is None:raise ValueError('参考统一目标预检端口不可用')
            if optical_record is not None:candidate['_optics']=optical_record['recipe']
            reference_record=prepare_reference(row,candidate,document_id,str(revision),prepared[RC.OP])
        # All full-target reviews must see the actual final combination, not a
        # shadow that still contains the target's old optics/reference recipe.
        if optical_record is not None:candidate['_optics']=optical_record['recipe']
        if reference_record is not None:RC.apply_verified(candidate,reference_record['recipe'])
        DERIVED.require_candidate(state,candidate,prepared,proof)
        crop_record=None;crop_transfer=None
        if SC.OP_CROP in prepared:
            if prepare_crop is None or verify_crop is None:raise ValueError('裁剪预设需要完整目标预览和审核端口')
            crop_record,crop_transfer=prepare_crop(row,candidate,document_id,str(revision))
            verify_crop(row,candidate,document_id,str(revision),crop_record)
        spill_record=None;spill_transfer=None
        if SC.SPILL_REMOVAL.OP in prepared:
            if prepare_spill is None or verify_spill is None:raise ValueError('祛染色预设需要完整目标前后图预览和审核端口')
            spill_record,spill_transfer=prepare_spill(row,state,candidate,document_id,str(revision))
            spill_record=SPILL_REVIEW.checked(spill_record)
            verify_spill(row,state,candidate,document_id,str(revision),spill_record)
        shadow_record=None;shadow_transfer=None
        if SC.ORIGINAL_SHADOW.OP in prepared:
            if prepare_shadow is None or verify_shadow is None:raise ValueError('原图阴影预设需要完整目标前后图预览和审核端口')
            shadow_record,shadow_transfer=prepare_shadow(row,state,candidate,document_id,str(revision))
            shadow_record=SHADOW_REVIEW.checked(shadow_record)
            verify_shadow(row,state,candidate,document_id,str(revision),shadow_record)
        scalar_record=None;scalar_transfer=None
        if family is not None:
            prepare_scalar,verify_scalar={'torso':(prepare_torso,verify_torso),
                'waist':(prepare_waist,verify_waist),'head':(prepare_head,verify_head)}[family.port_name]
            if prepare_scalar is None or verify_scalar is None:raise ValueError('身体长度预设需要完整目标前后图预览和审核端口')
            scalar_record,scalar_transfer=prepare_scalar(row,state,candidate,document_id,str(revision))
            scalar_record=family.review.checked(scalar_record)
            verify_scalar(row,state,candidate,document_id,str(revision),scalar_record)
        xmp_record=None;xmp_transfer=None
        if xmp is not None:
            if prepare_xmp is None or verify_xmp is None:raise ValueError('XMP requires actual full-target image review ports')
            xmp_record,xmp_transfer=prepare_xmp(row,state,candidate,document_id,str(revision),xmp['source_sha256'])
            verify_xmp(row,state,candidate,document_id,str(revision),xmp['source_sha256'],xmp_record)
        collarbone_record=None;collarbone_public=None
        if collarbone:
            if prepare_collarbone is None or verify_collarbone is None:
                raise ValueError('Collarbone preset requires the exact mixed-portrait target image planner')
            collarbone_record,collarbone_public=prepare_collarbone(row,state,candidate,document_id,str(revision),preset,prepared)
            verify_collarbone(row,state,candidate,document_id,str(revision),collarbone_record)
        if proof is not None:SOURCE.verify_row({**row,'state':state},proof)
        if (family is not None or collarbone) and (row.get('document_id'),row.get('path'))!=row_identity:
            raise ValueError('身体长度预检期间目标文档身份发生变化')
        token=uuid.uuid4().hex
        record={'preset':deepcopy(preset),'modules':prepared,'transfer':transfer,'optics':optical_record,'reference':reference_record,'crop':crop_record,'xmp':xmp_record,'spill':spill_record,'shadow':shadow_record,'torso':None,
                **({family.preset_key:scalar_record} if family is not None else {}),
                **({'collarbone':collarbone_record} if collarbone else {}),
                'document_id':document_id,'revision':str(revision),'path':row['path'],
                'row_document_id':row.get('document_id'),'source_proof':proof,
                'before':canonical(OA.before_params(state,list(modules))),'local_key':LG.undo_key(state) if LG.OP in modules else None,
                'expires':time.monotonic()+30*60}
        canonical(record);self.pending[token]=record
        if family is not None or collarbone:self.targets[token]=row
        if collarbone:
            from .collarbone_preset_store import attach,prune
            try:attach(self,token,collarbone_record)
            except Exception:
                self.pending.pop(token,None);self.targets.pop(token,None);prune(self);raise
        while len(self.pending)>8:
            expired,_=self.pending.popitem(last=False)
            self.targets.pop(expired,None)
        from .collarbone_preset_store import prune
        prune(self)
        return {'id':preset['id'],'name':preset['name'],'module_scope':list(modules),
                'preflight_token':token,'applies':deepcopy(prepared),'local_mask_transfer':transfer,'optical_transfer':optical_transfer,'reference_color':reference_record,
                'document_id':document_id,'revision':str(revision),'source_proof':deepcopy(proof),'crop_transfer':crop_transfer,
                **({'spill_transfer':spill_transfer} if SC.SPILL_REMOVAL.OP in prepared else {}),
                **({'shadow_transfer':shadow_transfer} if SC.ORIGINAL_SHADOW.OP in prepared else {}),
                **({family.wire_key:scalar_transfer} if family is not None else {}),
                **({'collarbone_preset':collarbone_public} if collarbone else {}),
                **({'xmp_transfer':xmp_transfer,'xmp_report':deepcopy(xmp['report'])} if xmp is not None else {})}

    def claim(self,token,preset_id,state,row,document_id,revision,verify_crop=None,verify_xmp=None,xmp_review_ack=None,verify_spill=None,spill_review_ack=_NO_SPILL_ACK,verify_shadow=None,shadow_review_ack=_NO_SHADOW_ACK,verify_torso=None,torso_review_ack=_NO_TORSO_ACK,verify_waist=None,waist_review_ack=_NO_WAIST_ACK,verify_head=None,head_review_ack=_NO_HEAD_ACK,verify_collarbone=None,collarbone_preset_ack=_NO_COLLARBONE_ACK):
        if type(token) is not str or token not in self.pending:raise ValueError('目标预设预检已失效或使用，请重新预检')
        record=self.pending[token]
        family=BODY_REVIEW.select(record['modules'])
        collarbone=SC.COLLARBONE.OP in record['modules']
        if (family is not None or collarbone) and self.targets.get(token) is not row:
            raise ValueError('身体长度预设的目标行已替换，请重新预检')
        if time.monotonic()>=record['expires']:
            self.pending.pop(token,None);self.targets.pop(token,None)
            from .collarbone_preset_store import prune
            prune(self)
            raise ValueError('目标预设预检已过期，请重新预检')
        if (record['preset']['id']!=preset_id or record['document_id']!=document_id or record['path']!=row['path'] or record['revision']!=str(revision)):
            raise ValueError('照片、版本或预设与预检不同，请重新预检')
        if record.get('row_document_id') != row.get('document_id'):
            raise ValueError('目标文档身份在预检后改变，请重新预检')
        proof=record.get('source_proof')
        # A proof-less original/legacy review must not wake up against a new
        # derived baseline even when path, revision and scoped values match.
        if proof is None:
            if SOURCE.record(state) is not None:raise ValueError('旧预设预检缺少合成来源证明，请重新预检')
        else:SOURCE.verify_row({**row,'state':state},proof)
        stored_modules=DERIVED.require_modules(state,record['preset']['modules'],proof)
        prepared_modules=DERIVED.require_modules(state,record['modules'],proof)
        if DERIVED.involved(state,proof) and canonical(stored_modules)!=canonical(prepared_modules):
            raise ValueError('全局参数预检不能替换或扩展已存储的预设模块')
        if canonical(OA.before_params(state,list(record['modules'])))!=record['before'] or (record['local_key'] is not None and LG.undo_key(state)!=record['local_key']):
            raise ValueError('照片在预检后发生修改，请重新预检')
        if LG.OP in record['modules']:LR.verify_modules(record['modules'],{**row,'state':state},record['transfer'])
        candidate=OA.candidate(state,record['modules'],local_replace_legacy=bool(record['transfer'] and record['transfer']['legacy_removed']))
        if SC.SPILL_REMOVAL.OP in record['modules']:SC.SPILL_REMOVAL.validate_target(candidate,row['path'],(row['src_h'],row['src_w']))
        if SC.ORIGINAL_SHADOW.OP in record['modules']:SC.ORIGINAL_SHADOW.validate_target(candidate,row['path'],(row['src_h'],row['src_w']))
        if family is not None:family.scope.validate_target(candidate,row['path'],(row['src_h'],row['src_w']))
        if SKY.OP in record['modules']:SKY.validate_target(candidate['_sky_replacement'],row['path'],(row['src_h'],row['src_w']))
        if BROW.OP in record['modules'] and OA.OP not in record['modules']:BROW.validate_target(candidate,row)
        if NOSE.OP in record['modules'] and OA.OP not in record['modules']:NOSE.validate_target(candidate,row)
        if EYE.OP in record['modules'] and OA.OP not in record['modules']:EYE.validate_target(candidate,row)
        if MOUTH.OP in record['modules'] and OA.OP not in record['modules']:MOUTH.validate_target(candidate,row)
        if OA.OP in record['modules']:OA.verify_target(record['optics'],state,candidate,row,document_id,revision,record['modules'][OA.OP])
        if RC.OP in record['modules']:
            if OA.OP in record['modules']:candidate['_optics']=record['optics']['recipe']
            RC.verify_target(record['reference'],state,candidate,row,document_id,revision,record['modules'][RC.OP])
        if record['optics'] is not None:candidate['_optics']=record['optics']['recipe']
        if record['reference'] is not None:RC.apply_verified(candidate,record['reference']['recipe'])
        DERIVED.require_candidate(state,candidate,record['modules'],proof)
        if SC.OP_CROP in record['modules']:
            if verify_crop is None:raise ValueError('裁剪预设缺少冻结目标审核端口')
            verify_crop(row,candidate,document_id,str(revision),record.get('crop'))
        if SC.SPILL_REMOVAL.OP in record['modules']:
            if verify_spill is None:raise ValueError('祛染色预设缺少冻结目标前后图审核端口')
            spill=SPILL_REVIEW.checked(record.get('spill'))
            SPILL_REVIEW.acknowledgments(spill_review_ack,[spill])
            verify_spill(row,state,candidate,document_id,str(revision),spill)
        elif spill_review_ack is not _NO_SPILL_ACK:raise ValueError('未选择祛染色模块，不能附带目标图审核确认')
        if SC.ORIGINAL_SHADOW.OP in record['modules']:
            if verify_shadow is None:raise ValueError('原图阴影预设缺少冻结目标前后图审核端口')
            shadow=SHADOW_REVIEW.checked(record.get('shadow'))
            SHADOW_REVIEW.acknowledgments(shadow_review_ack,[shadow])
            verify_shadow(row,state,candidate,document_id,str(revision),shadow)
        elif shadow_review_ack is not _NO_SHADOW_ACK:raise ValueError('未选择原图阴影模块，不能附带目标图审核确认')
        scalar_acks={'torso':(torso_review_ack,_NO_TORSO_ACK),'waist':(waist_review_ack,_NO_WAIST_ACK),
                     'head':(head_review_ack,_NO_HEAD_ACK)}
        for name,(value,missing) in scalar_acks.items():
            if value is not missing and (family is None or family.port_name!=name):
                raise ValueError('未选择对应身体长度模块，不能附带目标图审核确认')
        if family is not None:
            verify_scalar={'torso':verify_torso,'waist':verify_waist,'head':verify_head}[family.port_name]
            if verify_scalar is None:raise ValueError('身体长度预设缺少冻结目标前后图审核端口')
            scalar=family.review.checked(record.get(family.preset_key))
            family.review.acknowledgments(scalar_acks[family.port_name][0],[scalar])
            verify_scalar(row,state,candidate,document_id,str(revision),scalar)
        xmp=record['preset'].get('xmp_import')
        if xmp is not None:
            if verify_xmp is None:raise ValueError('XMP review verifier unavailable')
            from .preset_xmp_import import acknowledgment
            acknowledgment(xmp_review_ack,record)
            verify_xmp(row,state,candidate,document_id,str(revision),xmp['source_sha256'],record.get('xmp'))
        elif xmp_review_ack is not None:raise ValueError('Unexpected XMP review acknowledgment')
        if collarbone:
            from .collarbone_preset_review import acknowledgment
            from .collarbone_preset_store import verify_available
            if verify_collarbone is None:raise ValueError('Collarbone preset verifier is unavailable')
            acknowledgment(collarbone_preset_ack,record['collarbone'])
            verify_collarbone(row,state,candidate,document_id,str(revision),record['collarbone'])
            verify_available(self,token)
        elif collarbone_preset_ack is not _NO_COLLARBONE_ACK:
            raise ValueError('A collarbone preset acknowledgment cannot authorize another preset scope')
        if proof is not None:SOURCE.verify_row({**row,'state':state},proof)
        del self.pending[token]
        self.targets.pop(token,None)
        from .collarbone_preset_store import prune
        prune(self)
        return record
