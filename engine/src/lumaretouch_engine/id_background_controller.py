"""Strict direct transactions with retained terminal receipts, no preview claims."""
from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json
from . import id_background_state as S,id_background_runtime as R,id_background_assets as A,local_mask_state as M
from . import creative_derived_source as D

class Controller:
    def __init__(self,engine,emit):self.engine,self.emit=engine,emit;self.cache=OrderedDict()
    def handle(self,p):
        from .spill_removal_controller import ACTIONS, controller as spill_controller
        if p.get('action') in ACTIONS:
            return spill_controller(self.engine,self.emit).handle(p)
        from .original_shadow_controller import ACTIONS as SHADOW_ACTIONS, controller as shadow_controller
        if p.get('action') in SHADOW_ACTIONS:
            return shadow_controller(self.engine,self.emit).handle(p)
        e=self.engine;rid=p.get('request_id');action=p.get('action')
        result={'event':'id_background_result','protocol':1,'request_id':rid,'document_id':p.get('document_id'),'action':action,'success':False,'outcome_unknown':False,'requires_reload':False}
        before=None;digest=None
        try:
            if type(rid) is not str or not 1<=len(rid)<=128:raise ValueError('请求身份无效')
            digest=sha256(json.dumps(p,sort_keys=True,allow_nan=False).encode()).hexdigest()
            if rid in self.cache:
                old,cached=self.cache[rid]
                if old!=digest:raise ValueError('请求身份不能复用不同内容')
                result={**deepcopy(cached),'replayed':True};return
            if p.get('document_id')!=e._load_id:raise ValueError('照片已切换，请刷新后重试')
            if action=='id_sample':
                from .id_background_picker import owner
                result.update(success=True,sample=owner(e,self.emit).sample(p));return
            fields={'cmd','action','request_id','document_id'}
            if action!='id_state':
                fields|={'recipe_document_id','recipe_revision'}
                version=e._document_versions().version(e._docs[e._doc_index])
                if p.get('recipe_document_id')!=version.document_id or p.get('recipe_revision')!=str(version.revision):raise ValueError('背景配方已变化，请刷新后重新检查')
            extra={'id_state':set(),'id_clear':set(),'id_import':{'path'},'id_import_material':{'selection'},'id_set':{'recipe'},'id_review':{'category','object_ids','reviewed'}}
            if action not in extra or set(p)!=fields|extra[action]:raise ValueError('证件照换背景请求字段无效')
            if action=='id_state':result.update(success=True,report=R.report(e));return
            reason=e._guard_editable('ID background')
            if reason:raise ValueError(reason)
            value=S.check(getattr(e,'_id_background',None));bundle=getattr(e,'_id_background_bundle',None)
            from .original_shadow_state import active as shadow_active
            if action in ('id_set','id_import','id_import_material','id_review') and shadow_active(S.original_shadow_of(value)):
                raise ValueError('原图阴影启用时不能未经前后审核更换背景或主体范围；请先通过原图阴影审核关闭，再调整并重新审核。清除背景仍可用')
            derived=D.record(e) is not None
            source=D.binding(e) if derived else None
            if derived:
                from .creative_derived_id_background import validate_state
                validate_state(e)
            if action=='id_clear':value['enabled']=False;value['background']={**value['background'],'kind':'none','color':None,'asset':None};bundle=None
            elif action in ('id_import','id_import_material'):
                if action == 'id_import_material':
                    from .background_material_selection import resolve_for_id_background
                    asset=resolve_for_id_background(p['selection'])
                else: asset=A.read(p['path'])
                bundle=A.pack(asset)
                value['background']={**value['background'],'kind':'asset','asset':asset.binding,'color':value['background']['color'] or [255,255,255]}
            elif action=='id_review':
                from .id_background_support import review
                binding=review(e,p['category'],p['object_ids'],p['reviewed'])
                value['support'][p['category']]=binding;value['source']=binding['mask']['source']
            else:
                proposed=p['recipe'];editable={'enabled','background','selected_support','edge','opacity','shadow','favourites'}
                if type(proposed) is not dict or set(proposed)!=editable:raise ValueError('只能修改背景参数，不能伪造已审核范围')
                if proposed['background'].get('asset')!=value['background'].get('asset'):raise ValueError('素材身份只能经导入产生')
                value.update(deepcopy(proposed))
            if value['source'] is None:value['source']=source if derived else M.bind_source(e)
            value=S.check(value)
            if derived:
                from .creative_derived_id_background import validate
                value=validate(value,source)
            if S.active(value) and (e._bg.get('active') or e._sky_replacement['enabled']):raise ValueError('请先关闭旧换底或换天空')
            # Imports/prompted review may finish after a newer document edit.
            # Preserve the direct transaction fence, never claim a presented
            # output preview as authorization for this native request.
            current=e._document_versions().version(e._docs[e._doc_index])
            if (p['document_id']!=e._load_id or p['recipe_document_id']!=current.document_id
                    or p['recipe_revision']!=str(current.revision)):
                raise ValueError('背景配方在准备期间变化，请刷新后重新检查')
            if derived:D.verify(source,e)
            before=e._history_capture();e._fence_current_document();e._cancel_snapshot('ID background edit')
            e._id_background,e._id_background_bundle=value,bundle
            R.sync(e,strict=True)
            frame=e._write_current_frame('id_background');frame['doc_state']=e.doc_state();self.emit(frame)
            e._history_record('id_background:'+rid,before,coalesce=False);before=None
            result.update(success=True,report=R.report(e),history=e._history_report())
        except Exception as error:
            result['error']=str(error)[:2000]
            if before is not None:
                try:
                    e._history_apply(before);R.sync(e,strict=True)
                    frame=e._write_current_frame('id_background_rollback');frame['doc_state']=e.doc_state();self.emit(frame)
                except Exception:
                    result.update(outcome_unknown=True,requires_reload=True);e._vram=None
        finally:
            if rid and digest and rid not in self.cache:
                self.cache[rid]=(digest,deepcopy(result))
                while len(self.cache)>64:self.cache.popitem(last=False)
            self.emit(result)

def controller(engine,emit):
    owner=engine.__dict__.get('_id_background_owner')
    if owner is None:owner=engine._id_background_owner=Controller(engine,emit)
    return owner
