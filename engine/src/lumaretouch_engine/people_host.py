"""Canonical project graph and derived portrait resources for the engine host."""
from copy import deepcopy
from . import people_state as S, people_algorithms as A, people_binding as B
from . import people_retained_analysis as RA, people_support_assets as SUPPORT
from .people_graph_owner import PeopleGraphOwner
from .people_resolver import resolve
from . import local_mask_state as SOURCE, hair_colour_project as HAIR, people_owned_inputs as OWNED


def emit(event):
    from .server import emit as send
    send(event)


class PeopleHostMixin:
    def _people_prepare_open(self,decoded,request):
        from .people_open import prepare
        return prepare(self,decoded,request)

    def _people_render_open(self,pipe,callback):
        from .people_open import render
        return render(self,pipe,callback)

    def _people_open_flags(self):
        from .people_open import flags
        return flags(self)

    def _people_owner(self):
        if '_people_graph_owner' not in self.__dict__:
            self._people_graph_owner=PeopleGraphOwner()
            self._people_support={};self._people_landmarks={};self._people_analyses={}
            self._people_cursors={};self._people_targets={};self._people_analysis_key=None
        return self._people_graph_owner

    def _people_source(self):
        return SOURCE.bind_source(self)

    def _people_binding(self):
        source=self._people_source();version=self._document_versions().version(self._docs[self._doc_index])
        return {'document_id':version.document_id,'document_epoch':self._document_versions().workspace,
                'document_revision':version.revision,'asset_sha256':source['sha256']}

    def _people_managed(self):
        return bool(getattr(self,'_people_render_enabled',False) and getattr(self,'_people_path',None)==self._doc_path and self._vram is not None)

    def _people_bind(self):
        owner=self._people_owner();source=self._people_source();asset=source['sha256'];pc=self._precompute
        state=owner.snapshot()
        if pc is None:
            from .people_migration import migrate
            candidate=migrate(state,self._capture_state(),asset)
            if candidate!=state:state=owner.commit(candidate,expected_fence=owner.fence)
            return source,state,self._people_analyses.get(asset,{})
        cache=(asset,id(pc),owner.fence)
        if self._people_analysis_key==cache:return source,state,self._people_analyses.get(asset,{})
        initialize=not any(f['asset_sha256']==asset for f in state['faces'].values()) and asset not in state['analysis_runs']
        candidate,analyses,refusals=B.bind(state,asset,pc,source_dimensions=(source['width'],source['height']),initialize=initialize)
        analyses=RA.restore_missing(candidate,self._people_landmarks,asset,pc,analyses)
        self._people_landmarks=RA.retain(self._people_landmarks,analyses)
        # Preserve all original legacy fields and history, including unresolved
        # defaults/box banks, rather than silently broadening their old output.
        from .people_migration import migrate
        candidate=migrate(candidate,self._capture_state(),asset)
        candidate,support,_=SUPPORT.migrate_legacy(candidate,self._people_support,self._effect_recovery)
        if candidate!=state:state=owner.commit(candidate,expected_fence=owner.fence)
        else:state=candidate
        self._people_support=support;self._people_analyses[asset]=analyses
        self._people_analysis_key=(asset,id(pc),owner.fence)
        keys=[k for k,f in state['faces'].items() if f['asset_sha256']==asset]
        selected=self._people_cursors.get(asset)
        if selected not in keys:
            matches=[k for k in keys if state['faces'][k]['evidence']['landmark_digest']==B.landmark_digest(pc.landmarks)]
            selected=matches[0] if len(matches)==1 and (len(keys)==1 or self._face_explicit) else None
            self._people_cursors[asset]=selected
        if asset not in self._people_targets and selected:
            self._people_targets[asset]={'scope':'face','target_id':selected,'face_ref':S.face_ref(state['faces'][selected])}
        self._people_render_enabled=True;self._people_path=self._doc_path
        return source,state,analyses

    def _people_sync(self,*,strict=False):
        if self._vram is None or not self._docs or self._doc_index<0:return
        body_bank=self._body_bank()
        if self._precompute is None and '_people_graph_owner' not in self.__dict__ and not body_bank['bodies']:return
        from . import people_engine_runtime as R
        try:
            source,state,analyses=self._people_bind();asset=source['sha256']
            self._people_render_enabled=True;self._people_path=self._doc_path
            if not body_bank['bodies'] and not any(f['asset_sha256']==asset for f in state['faces'].values()) and not any(r['asset_sha256']==asset and r['status']=='unresolved' for r in state['unresolved_legacy']) and not any(r['scope']=='all_people' and r['target_id']==asset for r in state['overrides']):
                from .people_pipeline import clear
                clear(self._vram);self._vram.people_suspended=None;return
            key=(asset,self._people_owner().fence,id(self._precompute),id(self._vram.src_f32),id(self._vram.repair_base),self._body_identity())
            if getattr(self._vram,'people_key',None)!=key:
                from .cpu_memory_budget import available_estimate
                recovery=SUPPORT.raster(state,self._people_support,asset,(self._vram.h,self._vram.w))
                R.synchronize(self._vram,state,asset,analyses,byte_budget=available_estimate(),recovery_assets=recovery,**OWNED.preview(self,state,body_bank=body_bank,body_source=source))
                self._vram.people_key=key
            self._people_mirror()
        except (ValueError,RuntimeError,OSError) as error:
            if self._people_managed():R.suspend(self._vram,str(error))
            if strict:raise

    def _people_mirror(self):
        """Legacy controls are editing views only; final output uses every face."""
        owner=self._people_owner();source=self._people_source();state=owner.snapshot()
        selected=self._people_cursors.get(source['sha256'])
        if selected not in state['faces']:return
        resolved=resolve(state,selected,A.defaults())
        if resolved['conflicts']:return
        values=A.recipes(resolved);identity=state['faces'][selected]['evidence']['landmark_digest']
        analysis=self._people_analyses.get(source['sha256'],{}).get(selected)
        if analysis is not None and self._precompute is not None and B.landmark_digest(self._precompute.landmarks)!=identity:
            from dataclasses import replace
            self._precompute=replace(self._precompute,landmarks=analysis['landmarks'],face_box=tuple(state['faces'][selected]['box']))
            self._people_analysis_key=None
        for field,op in zip(('brow_shape','nose_shape','eye_shape','mouth_shape'),A.GEOMETRY):
            setattr(self,'_'+field,values[op]);setattr(self,'_'+field+'_owner',identity)
        self._lip_makeup=values[A.LIP]
        self._deform={'amounts':values[A.DEFORM],'built':True};self._deform_defer=False
        self._enhance={'amounts':{**values[A.ENHANCE],**values[A.WRINKLES]},'built':True,'box':tuple(state['faces'][selected]['box'])}
        self._enhance_defer=False
        prepared=getattr(self._vram,'people_prepared',None)
        facts=prepared.facts.get(selected,{}) if prepared else {}
        self._vram.lip_makeup_facts=facts.get('lip_makeup',{})
        self._vram.lip_makeup_suspended=getattr(self._vram,'people_suspended',None)
        self._vram.enhance_facts={**facts.get('enhance',{}),**facts.get('facial_wrinkles',{}),**facts.get('eye_detail',{})}

    def _people_report(self):
        if not self._people_managed():return None
        from .people_ui import report
        try:
            source=self._people_source();state=self._people_owner().snapshot();asset=source['sha256']
            reason=getattr(self._vram,'people_suspended',None)
            refusals=[{'face_instance_id':k,'reason':reason} for k,f in state['faces'].items() if f['asset_sha256']==asset] if reason else []
            result=report(state,asset,self._people_cursors.get(asset),refusals=refusals)
            target=self._people_targets.get(asset);overrides={}
            if target:
                for row in state['overrides']:
                    if (row['scope'],row['target_id'])==(target['scope'],target['target_id']):
                        overrides.setdefault(row['operation_id'],{})[row['parameter_path']]=row['value']
            from .people_legacy_review import report as legacy_report
            from .people_scope import describe
            result['parameter_catalog']=describe()
            from .eye_light_host import report as eye_light_report
            result['eye_light']=eye_light_report(self,state,source,self._people_cursors.get(asset))
            from .lipstick_host import report as lipstick_report
            result['lipstick']=lipstick_report(self,state,source,self._people_cursors.get(asset))
            from .blush_makeup_host import report as blush_report
            result['blush_makeup']=blush_report(self,state,source,self._people_cursors.get(asset))
            result.update(binding=self._people_binding(),editing_target=deepcopy(target),editing_overrides=overrides,legacy_unresolved=legacy_report(state,asset))
            return result
        except (ValueError,OSError):return None

    def _people_history_capture(self):
        if not self._people_managed():return None
        return self._people_owner().capture_document(self._people_source()['sha256'])

    def _people_history_apply(self,snapshot,transition=None):
        if snapshot is None:return
        owner=self._people_owner();asset=self._people_source()['sha256']
        if snapshot['asset_sha256']!=asset:raise ValueError('People history belongs to another source')
        if transition is not None:
            from .people_document_history import restore
            candidate=restore(owner,transition,asset)
        else:candidate=owner.stage_document_restore(snapshot,expected_asset_fence=owner.asset_fences.get(asset,0),expected_association_fence=owner.association_fence)
        owner.commit(candidate,expected_fence=owner.fence);self._people_analysis_key=None

    def _people_save(self,project):
        owner=self._people_owner()
        project['people_graph']=owner.snapshot();project['people_support_assets']=deepcopy(self._people_support)
        project['people_landmarks']=deepcopy(self._people_landmarks)
        project['people_cursors']=deepcopy(self._people_cursors)
        from .people_history_persistence import save
        save(self,project)
        HAIR.save(self,project)

    def _people_stage_project(self,project,rows):
        from .people_project import validate_records
        from .people_history_persistence import prepare
        validate_records(project);HAIR.validate(project)
        return prepare(project,rows,self.HISTORY_MAX)

    def _people_load(self,project,prepared_history=None):
        from .people_project import validate_records
        validate_records(project)
        HAIR.load(self,project)
        self._people_graph_owner=PeopleGraphOwner(project.get('people_graph'))
        self._people_support=SUPPORT.check_store(project.get('people_support_assets',{}))
        self._people_landmarks=RA.check_store(project.get('people_landmarks',{}))
        self._people_cursors=deepcopy(project.get('people_cursors',{}));self._people_targets={}
        self._people_analyses={};self._people_analysis_key=None;self._people_render_enabled=False
        from .people_history_persistence import restore
        restore(self,project,prepared_history)

    def _people_export_snapshot(self,state,source_path=None,graph=None):
        from .people_snapshot import capture
        if source_path is None:source_path=self._doc_path
        if not source_path:return None
        asset=SOURCE.source_digest(source_path);graph=self._people_owner().snapshot() if graph is None else S.check(graph)
        retained=any(f['asset_sha256']==asset for f in graph['faces'].values()) or any(r['asset_sha256']==asset and r['status']=='unresolved' for r in graph['unresolved_legacy']) or any(r['scope']=='all_people' and r['target_id']==asset for r in graph['overrides'])
        if not retained:return None
        analyses=self._people_analyses.get(asset,{})
        pc=state.get('_precompute')
        if pc is not None and any(f['asset_sha256']==asset for f in graph['faces'].values()):
            face=next(f for f in graph['faces'].values() if f['asset_sha256']==asset)
            ev=face['evidence']
            _,analyses,_=B.bind(graph,asset,pc,source_dimensions=(ev['source_width'],ev['source_height']))
            analyses=RA.restore_missing(graph,self._people_landmarks,asset,pc,analyses)
        face=next((f for f in graph['faces'].values() if f['asset_sha256']==asset),None)
        binding=None if face is None else {'sha256':asset,'width':face['evidence']['source_width'],'height':face['evidence']['source_height']}
        if pc is None and binding is not None:
            from .hair_colour_replay import analyses as retained_hair_analyses
            restored=retained_hair_analyses(self,graph,binding)
            if restored is not None:analyses=restored
        result=capture(graph,asset,analyses);result['support_assets']=deepcopy(self._people_support)
        return result if binding is None else HAIR.capture(self,result,pc,binding,source_path=source_path)

    def cmd_people(self,p):
        from .people_host_commands import apply
        return apply(self,p,emit)

    def finish_people(self,p,error):
        from .people_host_commands import finish
        return finish(self,p,error,emit)

    def _people_legacy(self,operation,p,emit):
        from .people_host_commands import legacy
        return legacy(self,operation,p,emit)

    def _people_prepare_graph(self,candidate,assets):
        from .people_engine_runtime import prepare_preview
        from .cpu_memory_budget import available_estimate
        from .people_candidate_render import validate
        before=self._people_owner().snapshot();source=self._people_source();current=source['sha256']
        def signature(state,asset):
            return [(k,f['enabled'],f['local_assets'],resolve(state,k,A.defaults())['operations'],resolve(state,k,A.defaults())['conflicts'])
                    for k,f in sorted(state['faces'].items()) if f['asset_sha256']==asset]
        staged=None
        for asset in sorted(assets):
            if asset!=current and signature(before,asset)==signature(candidate,asset) and before['association_revision']==candidate['association_revision']:continue
            if asset==current:
                recovery=SUPPORT.raster(candidate,self._people_support,asset,(self._vram.h,self._vram.w))
                staged=prepare_preview(self._vram,candidate,asset,self._people_analyses.get(asset,{}),byte_budget=available_estimate(),recovery_assets=recovery,**OWNED.preview(self,candidate,body_source=source))
            else:
                row=next((row for row in self._docs if SOURCE.source_digest(row['path'])==asset),None)
                if row is None:raise ValueError('A linked photo is unavailable; shared edits were not partially applied')
                validate(self,row,candidate)
        self._people_staged=staged

    def _people_publish_pending_review(self,candidate):
        # Explicit archive decisions may require several steps. Retain those
        # decisions/history while remaining visibly suspended, never render a
        # partial recipe as a final image. The last decision uses strict publish.
        owner=self._people_owner();owner.commit(candidate,expected_fence=owner.fence)
        self._document_versions().advance(self._docs[self._doc_index]);self._people_analysis_key=None
        self._people_sync();self._project_dirty=True
        return None

    def _people_publish_graph(self,candidate,assets):
        """Synchronous existing command transaction; rollback never rewinds fences."""
        owner=self._people_owner();before=owner.snapshot();fence=owner.fence
        try:
            owner.commit(candidate,expected_fence=fence);self._people_analysis_key=None
            for row in self._docs:
                if SOURCE.source_digest(row['path']) in assets:self._document_versions().advance(row)
            self._people_sync(strict=True)
            frame=self._write_current_frame('people');frame['doc_state']=self.doc_state()
            self._project_dirty=True
            return frame
        except Exception:
            before['association_revision']=owner.association_fence
            owner.commit(before,expected_fence=owner.fence);self._people_analysis_key=None
            try:self._people_sync(strict=True)
            except Exception:self._vram=None
            raise
        finally:self._people_staged=None

    def _people_restore_batch(self,batch,redo):
        from .people_graph_patch import apply
        from .people_graph_owner import affected_assets
        owner=self._people_owner();before=owner.snapshot()
        for rec in batch['targets'].values():
            found=self._document_versions().find(self._docs,rec['document_id'])
            if found is None or found[1]['path']!=rec['path'] or SOURCE.source_digest(rec['path'])!=rec['asset_sha256']:
                raise ValueError('A people batch target changed or was removed; protected group restore refused')
        candidate=apply(before,batch['people_changes'],redo=redo)
        assets=affected_assets(before,candidate);assets.add(self._people_source()['sha256'])
        self._people_prepare_graph(candidate,assets)
        return self._people_publish_graph(candidate,assets)

    def _people_selected_field(self,kind):
        from types import SimpleNamespace
        source=self._people_source();selected=self._people_cursors.get(source['sha256'])
        prepared=getattr(self._vram,'people_prepared',None)
        facts=prepared.facts.get(selected,{}).get(kind) if prepared else None
        return None if facts is None else SimpleNamespace(facts=facts,resident_bytes=lambda:0)
