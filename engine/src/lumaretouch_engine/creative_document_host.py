"""Live engine integration for the creative image document. No separate undo stack."""
from __future__ import annotations
import base64
from copy import deepcopy
from dataclasses import replace
import os
import uuid
from . import creative_document_state as S
from .creative_document_assets import AssetStore
from .creative_document_controller import CreativeController, CreativePorts
from .creative_document_project import restore_from

FIELDS = ('_creative_document','_creative_asset_records','_creative_base')
MAX_FILE_BYTES = 128*1024*1024


def neutral():
    return {'_creative_document':None,'_creative_asset_records':{},'_creative_base':None}


def fields(engine):
    return {key:deepcopy(getattr(engine,key,neutral()[key])) for key in FIELDS}


def restore_fields(state):
    values = {key:deepcopy(state.get(key,neutral()[key])) for key in FIELDS}
    restore_from(values)
    from .creative_document_base import check
    check(values['_creative_base'])
    return values


def memory_budget():
    from .cpu_memory_budget import available_estimate
    value = min(4_000_000_000, int(available_estimate() * .5))
    if value < 16_777_216: raise ValueError('创意图层可用内存不足，未开始分配')
    return value


def source_uid(engine):
    i = getattr(engine,'_doc_index',-1)
    return engine._docs[i]['document_id'] if 0 <= i < len(engine._docs) else None


def rotate(engine):
    engine._creative_owner_nonce = uuid.uuid4().hex
    owner = engine.__dict__.get('_creative_host')
    if owner is not None:
        if owner.controller.pending is not None: owner.controller.cancel_return(owner.controller.pending['ticket_id'])
        owner.preview = None


def token(engine):
    if not getattr(engine,'_creative_owner_nonce',None): rotate(engine)
    return ':'.join((engine._document_versions().workspace,str(engine._load_id),engine._creative_owner_nonce))


def decoded_for_state(decoded,state,*,max_pixels):
    """Keep original proxy separately; only presentation dimensions follow baked base."""
    if state.get('_creative_base') is None: return decoded
    from .creative_document_base import proxy_for_state, source_shape
    rgb = proxy_for_state(decoded.rgb,state,max_pixels=max_pixels,max_bytes=memory_budget())
    height,width = source_shape(state,(decoded.src_h,decoded.src_w))
    value = replace(decoded,rgb=rgb,src_w=width,src_h=height)
    value._creative_original_rgb = decoded.rgb
    value._creative_original_dimensions = (decoded.src_w, decoded.src_h)
    return value


def original_proxy(decoded):
    return getattr(decoded,'_creative_original_rgb',decoded.rgb)


def proxy_transition(before,after):
    """History may change canvas geometry only when the immutable baked base changes."""
    a,b = before.get('_creative_base'),after.get('_creative_base')
    return (a or {}).get('id') != (b or {}).get('id')


class CreativeHost:
    def __init__(self,engine,emit):
        self.e,self.emit = engine,emit
        self.assets = AssetStore()
        self.asset_owner = None
        self.preview = None
        self.controller = CreativeController(CreativePorts(
            lambda:self.e._creative_document,lambda:token(self.e),self.guard,
            self.commit_document,self.commit_return,lambda:True),self.assets)

    @property
    def pending(self):
        return self.controller.pending

    def guard(self,action):
        reason = self.e._guard_editable('creative_document')
        if reason: return reason
        relocation = self.e.__dict__.get('_source_relocation_controller')
        if relocation is not None and (relocation.active is not None or relocation.uncertain is not None):
            return '请先完成或确认原图重定位'
        from .sample_library_capture import heavy_reason
        return heavy_reason(self.e)

    def sync(self):
        # _apply_state/project admission already validated immutable payloads;
        # intern verifies any newly seen record, without redecoding whole history
        # for every selection/opacity command.
        owner = source_uid(self.e)
        if owner != self.asset_owner:
            # This is only the active decode/lookup cache. Each committed source
            # and undo frame owns immutable bytes independently, so switching
            # photographs does not accumulate all sessions into this budget.
            self.assets = AssetStore(); self.controller.assets = self.assets
            self.asset_owner = owner
        document = self.e._creative_document
        for record in self.e._creative_asset_records.values(): self.assets.intern(record)
        if document is not None:
            S.validate(document,self.assets)
            # A virtual copy has a distinct document owner, not another route to
            # mutate the original creative identity inherited in its recipe.
            if document['source_uid'] != source_uid(self.e):
                document = deepcopy(document); document['source_uid'] = source_uid(self.e)
                document['document_id'] = uuid.uuid4().hex; document['revision'] = 0
                self.e._creative_document = document
                rotate(self.e); self.e._remember_current()
        base = getattr(self.e,'_creative_base',None)
        if base is not None: self.assets.intern(base)

    def commit_document(self,after,before,label):
        e = self.e; previous = e._history_capture(); old_fields = fields(e)
        undo,redo = list(e._undo),list(e._redo)
        try:
            e._creative_document = deepcopy(after)
            e._creative_asset_records = self.assets.records(S.references(after))
            if label:
                e._fence_current_document()
                e._history_record(label,previous,coalesce=False)
            e._remember_current()
            self.preview = None
        except Exception:
            for key,value in old_fields.items(): setattr(e,key,value)
            e._undo,e._redo = undo,redo
            raise

    def open(self):
        e = self.e
        reason = self.guard('open')
        if reason: raise ValueError(reason)
        self.sync()
        if e._creative_document is not None: return
        from .creative_document_base import capture_current_asset
        row = e._docs[e._doc_index]
        record = capture_current_asset(e,row,e._capture_state(),self.assets,max_bytes=memory_budget())
        document = S.create(row['document_id'],record['id'],self.assets)
        e._creative_document = document
        e._creative_asset_records = self.assets.records(S.references(document))
        e._project_dirty = True
        e._remember_current()

    def render_preview(self):
        doc = self.e._creative_document
        if doc is None: self.preview = None; return
        owner = token(self.e)
        if self.preview and self.preview['ownership_token'] == owner and self.preview['revision'] == doc['revision']:
            return
        from .creative_document_render import CreativeRenderer
        frozen = deepcopy(doc)
        renderer = CreativeRenderer(frozen,self.assets,max_bytes=memory_budget(),cancelled=lambda:token(self.e)!=owner or self.e._creative_document!=frozen)
        png,width,height = renderer.preview_png()
        self.preview = {'document_id':doc['document_id'],'source_uid':doc['source_uid'],
                        'ownership_token':owner,'revision':doc['revision'],'render_id':uuid.uuid4().hex,
                        'url':'data:image/png;base64,'+base64.b64encode(png).decode('ascii'),
                        'width':width,'height':height,'quality':'display-only-full-source-nearest'}

    def report(self):
        doc = self.e._creative_document
        history = self.e._history_report()
        from pathlib import Path
        available = doc is not None and (Path(__file__).parent/'bin/liblrt_creative_layers.so').is_file()
        return {'source_uid':source_uid(self.e),
                'authority':{'document':deepcopy(doc),'ownership_token':token(self.e),'busy':self.controller.pending is not None} if doc is not None else None,
                'preview':deepcopy(self.preview),
                'history':{'can_undo':history['can_undo'],'can_redo':history['can_redo'],'recoverable_delete':True},
                'capabilities':{key:available for key in ('command','import_image','attach_mask','remove_mask','history','return_new','update_original','fresh_current')}}

    def commit_return(self,plan):
        e = self.e
        from .creative_document_base import export_source
        base = self.assets.get(plan['rendered_asset'],'rgba')
        export_source(base,max_bytes=memory_budget())  # reject alpha/HDR retouch loss before any host mutation
        before = e._history_capture(); full_before = e._capture_state()
        index = e._doc_index; source = e._docs[index]; old_load_id = e._load_id
        rows_before = list(e._docs); undo,redo = list(e._undo),list(e._redo)
        state = e._fresh_doc_state(); state['_strength'] = 0.0
        state.update(_creative_base=base,_creative_document=deepcopy(plan['creative_document']),
                     _creative_asset_records=self.assets.records(S.references(plan['creative_document'])))
        row = source
        if plan['mode'] == 'new_image':
            from .virtual_copy_source import fingerprint_for
            fp,_ = fingerprint_for(source)
            row = e._new_row(source['path'],state=state,budget=source.get('budget'))
            row['source_asset_id'] = source['source_asset_id']; row['fingerprint'] = fp
            row['label'] = (source.get('label') or source.get('name') or '照片')+' · 创意新图'
            from . import virtual_copy_people as VP, people_state as PS
            row[VP.KEY] = {'version':1,'people_graph':PS.empty(),**{key:{} for key in VP.FIELDS}}
            row['_people_new_import'] = False
            state['_creative_document']['source_uid'] = row['document_id']
            state['_creative_document']['document_id'] = uuid.uuid4().hex
            state['_creative_document']['revision'] = 0
            row['state'] = state
        try:
            e._remember_current()
            if row is not source:
                e._docs = list(e._docs); e._docs.insert(index+1,row); e._doc_index = index+1
                from .virtual_copy_people import activate
                activate(e,row); e._history_bind(row)
            e._load_id = uuid.uuid4().hex  # New pixel baseline revokes old source-stage requests.
            e._apply_state(state)
            e._fence_current_document()
            e._attach_pipeline(e._src_rgb,adopt=True)
            e._ensure_shm(e._vram.w,e._vram.h)
            row.update(w=e._vram.w,h=e._vram.h,src_w=base['width'],src_h=base['height'],opened=True)
            if row is source:
                e._history_record('creative:return',before,coalesce=False)
            e._project_dirty = True
            e._remember_current()
            frame = e._write_current_frame('creative_return')
            publish_geometry(e,self.emit)
            self.emit({**frame,'doc_state':e.doc_state()})
            e.emit_session_state()
            return {'status':'applied','document_id':row['document_id']}
        except Exception:
            e._docs = rows_before; e._doc_index = index; e._load_id = old_load_id
            from .virtual_copy_people import activate
            activate(e,source); e._apply_state(full_before); e._undo,e._redo = undo,redo
            e._attach_pipeline(e._src_rgb,adopt=True); e._ensure_shm(e._vram.w,e._vram.h)
            e._remember_current()
            publish_geometry(e,self.emit)
            raise

    def handle(self,p):
        action = p.get('action'); rid = p.get('request_id')
        event = 'creative_document_state' if action in ('open','state') else 'creative_document_result'
        envelope = {key:p.get(key) for key in ('request_id','document_id','source_uid','expected_revision','ownership_token')}
        receipt = None
        try:
            if type(rid) is not str or not rid or len(rid)>128: raise ValueError('无效创意请求身份')
            if p.get('source_uid') != source_uid(self.e): raise ValueError('创意请求的原片已切换')
            self.sync()
            if action in ('open','state'):
                if action == 'open': self.open()
                if self.e._creative_document is not None: self.render_preview()
                self.emit({'event':event,'request_id':rid,'status':'ready',**self.report()}); return
            if action == 'command':
                receipt = self.controller.command(envelope,p.get('command'))
            elif action == 'fresh_current':
                from .creative_document_refresh import fresh_current
                receipt = fresh_current(self,envelope)
            elif action in ('import_image','attach_mask'):
                self.controller._check(envelope,'import')
                if self.controller.pending is not None: raise ValueError('创意回流仍在进行')
                from .creative_document_import import import_bytes,import_file,import_mask_bytes
                if 'path' in p:
                    path = p['path']
                    if action != 'import_image' or 'bytes_base64' in p or type(path) is not str or not os.path.isabs(path) or not os.path.isfile(path) or os.path.getsize(path)>MAX_FILE_BYTES:
                        raise ValueError('无效创意本地导入路径')
                    identity = import_file(path,self.assets,max_bytes=memory_budget())
                else:
                    text = p.get('bytes_base64')
                    if type(text) is not str or len(text)>4*((MAX_FILE_BYTES+2)//3): raise ValueError('创意素材传输预算超限')
                    content = base64.b64decode(text,validate=True)
                    if not content or len(content)>MAX_FILE_BYTES: raise ValueError('创意素材为空或超限')
                    identity = import_mask_bytes(content,self.assets,max_bytes=memory_budget()) if action == 'attach_mask' else import_bytes(content,self.assets,max_bytes=memory_budget())
                command = {'action':'add_mask','layer_id':p.get('layer_id'),'mask_id':identity} if action == 'attach_mask' else {'action':'add_image','asset_id':identity,'name':os.path.basename(p.get('filename') or p.get('path') or '导入图层')[:256]}
                receipt = self.controller.command(envelope,command)
            elif action == 'remove_mask':
                receipt = self.controller.command(envelope,{'action':'remove_mask','layer_id':p.get('layer_id')})
            elif action == 'history':
                self.controller._check(envelope,'history')
                if self.controller.pending is not None: raise ValueError('创意回流仍在进行')
                direction = p.get('direction')
                if direction not in ('undo','redo'): raise ValueError('无效创意历史动作')
                self.e._fence_current_document()
                outcome = self.e.cmd_history({'cmd':'history','action':direction})
                if type(outcome) is not dict or outcome.get('status') not in ('applied','no_change','rejected','unknown'):
                    raise RuntimeError('Creative history outcome requires reconciliation')
                self.sync(); self.preview = None
                doc = self.e._creative_document
                receipt = {**envelope,**outcome,'revision':doc['revision'] if doc else 0}
            elif action == 'return':
                if not self.preview or p.get('render_id') != self.preview['render_id'] or self.preview['revision'] != self.e._creative_document['revision']:
                    raise ValueError('创意预览已过期，请先更新画布')
                mode = {'new':'new_image','update':'update_original'}.get(p.get('mode'))
                ticket = self.controller.begin_return(envelope,mode)
                try:
                    identity = self.controller.render_return(ticket,max_bytes=memory_budget())
                    require_photo_return(self.assets.get(identity,'rgba'))
                    receipt = self.controller.complete_return(ticket,identity)
                finally: self.controller.cancel_return(ticket['ticket_id'])
            else: raise ValueError('未知创意文档动作')
            self.sync()
            try: self.render_preview()
            except Exception as error:
                self.preview = None
                receipt['preview_error'] = str(error)  # committed command remains committed
            self.emit({'event':event,**self.report(),**receipt,'doc_state':self.e.doc_state()})
        except Exception as error:
            if receipt is not None:
                # Publication/readback failure cannot undo a known commit or
                # turn its receipt into a safe-to-retry rejection.
                self.emit({'event':event,**receipt,'preview_error':str(error)})
                return
            unknown = isinstance(error,RuntimeError) and ('outcome' in str(error) or 'reconciliation' in str(error))
            try: report = self.report()
            except Exception: report = {}
            self.emit({'event':event,**report,**envelope,'status':'unknown' if unknown else 'rejected','message':str(error)})


def handle(engine,p,emit):
    owner = engine.__dict__.get('_creative_host')
    if owner is None: owner = CreativeHost(engine,emit); engine._creative_host = owner
    owner.handle(p)


def guard_command(engine, name, request):
    """Do not let original-path analyses edit newly composited content.

    Actual derived-source analysis, inspection and an audited local portrait
    subset have dedicated owned paths. Other effects and cross-document planners
    remain fenced until all their consumers own that source. The original and its undo states remain intact.
    """
    # These planners can mutate parked targets, not just the active row. Until
    # their target validators own derived content, fail closed for this session.
    from .creative_derived_effects import is_local_command, require_command
    local_portrait = is_local_command(name,request)
    if name in ('people','batch','semantic_colour') and not local_portrait and any(
            (row.get('state') or {}).get('_creative_base') is not None
            for row in getattr(engine, '_docs', [])):
        raise ValueError('会话含创意回流图；跨图人像/批量计划尚未支持该来源，请先关闭回流图或撤销回流，避免借用原图分析。')
    if getattr(engine, '_creative_base', None) is None:
        return
    from .creative_derived_body import COMMANDS as BODY_COMMANDS, require_command as require_body
    if name in BODY_COMMANDS:
        require_body(engine,name,request)
        return # Exact native body envelopes, not generic source-guard bypass.
    from .creative_derived_recovery import COMMANDS, require_command as require_recovery
    if name in COMMANDS:
        require_recovery(engine,name,request)
        return # Exact live capture/review admission, not a generic tool exemption.
    if local_portrait:
        require_command(engine,name,request)
    source_bound = {
        'set_strength', 'inpaint', 'light', 'face', 'people',
        'deform', 'enhance', 'fabric', 'background', 'local_masks',
        'prompted_masks', 'source_patch_capture', 'source_patch', 'clone_stamp',
        'effect_recovery', 'effect_recovery_preview', 'manual_liquify',
        'manual_liquify_preview', 'studio_background', 'studio_background_preview',
        'optics', 'optics_preview', 'sky_replacement', 'sky_replacement_preview',
        'sky_semantic', 'local_grade_live', 'semantic_colour', 'lip_makeup',
        'brow_shape', 'nose_shape', 'eye_shape', 'mouth_shape', 'hair_colour',
        'shoulder_shape', 'leg_shape', 'arm_shape', 'waist_shape', 'leg_length',
        'neck_shape', 'sample_library',
    }
    # Do not trust a generic action='state': legacy commands may ignore it.
    # Dedicated *_state/status commands remain available outside this set.
    blocked = name in source_bound
    if local_portrait: blocked = False
    if name == 'background' and request.get('action') == 'id_state':
        blocked = False  # This exact controller branch validates fields and only reports.
    blocked |= name == 'color_picker_capture' and request.get('picker_action') in ('id_background','id_background_subject','id_background_reference')
    blocked |= name == 'grade' and (request.get('scope', 'all') != 'all' or request.get('action') == 'mask')
    blocked |= name == 'colour_editor' and (request.get('recipe') or {}).get('scope', 'global') == 'local'
    blocked |= name == 'preset' and request.get('action') in ('apply', 'preflight')
    blocked |= name == 'batch' and request.get('action') not in ('state', 'query', 'cancel', 'list')
    if blocked:
        raise ValueError('该工具尚未适配合成来源；不会借用原图的人脸、蒙版或分析。已支持合成图真实重新分析、100%检查、全局调色、裁剪与图层编辑，或可撤销回流。')


def dispatch_rejected(request, message, started, emit):
    """Complete the native mailbox even when an outer guard prevented entry."""
    event = 'creative_document_state' if request.get('action') in ('open','state') else 'creative_document_result'
    envelope = {key:request.get(key) for key in ('request_id','document_id','source_uid','expected_revision','ownership_token')}
    emit({'event':event,**envelope,'status':'unknown' if started else 'rejected','message':message})


def publish_geometry(engine, emit):
    """Refresh image metadata without pretending a new file was decoded."""
    if engine._vram is None or not 0 <= engine._doc_index < len(engine._docs): return
    row = engine._docs[engine._doc_index]
    base = getattr(engine, '_creative_base', None)
    original = getattr(engine, '_creative_original_dimensions', None)
    if base is None and original is None: return
    sw,sh = (base['width'],base['height']) if base is not None else original
    row.update(w=engine._vram.w,h=engine._vram.h,src_w=sw,src_h=sh)
    emit({'event':'creative_geometry','load_id':engine._load_id,'source_uid':source_uid(engine),
          'path':row['path'],'w':engine._vram.w,'h':engine._vram.h,'src_w':sw,'src_h':sh,
          'doc_state':engine.doc_state()})


def require_photo_return(record):
    """Reject incompatible photo-pipeline pixels before the mutation boundary."""
    import numpy as np
    pixels = np.frombuffer(record['content'], dtype='<f4').reshape(-1,4)
    for start in range(0,len(pixels),65536):
        chunk = pixels[start:start+65536]
        if not (chunk[:,3] == 1).all() or not ((chunk[:,:3] >= 0) & (chunk[:,:3] <= 1)).all():
            raise ValueError('当前修图回流仅支持不透明 SDR；透明度与 HDR 图层数据已保留，未展平或裁切。')


def analysis_rgb(engine):
    from .creative_derived_source import analysis_rgb as resolve
    return resolve(engine)
