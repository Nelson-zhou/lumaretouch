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
        from .virtual_copy_people import owner
        return owner(self)

    def _people_source(self):
        from .creative_derived_source import binding
        return binding(self)

    def _people_binding(self):
        source=self._people_source();version=self._document_versions().version(self._docs[self._doc_index])
        return {'document_id':version.document_id,'document_epoch':self._document_versions().workspace,
                'document_revision':version.revision,'asset_sha256':source['sha256']}

    def _people_managed(self):
        return bool(getattr(self,'_people_render_enabled',False) and getattr(self,'_people_path',None)==self._doc_path and self._vram is not None)

    def _people_bind(self):
        from .creative_derived_source import verify_precompute
        verify_precompute(self, self._precompute)
        owner=self._people_owner();source=self._people_source();asset=source['sha256'];pc=self._precompute
        state=owner.snapshot()
        if pc is None:
            from .people_migration import migrate
            candidate=migrate(state,self._capture_state(),asset)
            if candidate!=state:state=owner.commit(candidate,expected_fence=owner.fence)
            return source,state,self._people_analyses.get(asset,{})
        cache=(asset,id(pc),owner.fence)
        if self._people_analysis_key==cache:return source,state,self._people_analyses.get(asset,{})
        self._body_skin_evenness_reference=None;self._body_skin_evenness_preview=None
        self._collarbone_reference=None;self._collarbone_preview=None
        self._body_face_match_reference=None;self._body_face_match_preview=None
        self._eye_bag_reference=None
        self._face_decoration_reference=None
        self._facial_sculpt_reference=None
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
            from .people_cross_owner import validate_owner
            document_id=self._people_binding()['document_id']
            validate_owner(state,asset,document_id)
            from .creative_derived_source import record
            if record(self) is not None:
                from .creative_derived_repair_runtime import verify_pipeline
                verify_pipeline(self._vram,source) # Verify actual replay before any cache hit.
            self._people_render_enabled=True;self._people_path=self._doc_path
            if not body_bank['bodies'] and not any(f['asset_sha256']==asset for f in state['faces'].values()) and not any(r['asset_sha256']==asset and r['status']=='unresolved' for r in state['unresolved_legacy']) and not any(r['scope']=='all_people' and r['target_id']==asset for r in state['overrides']):
                from .people_pipeline import clear
                clear(self._vram);self._vram.people_suspended=None;return
            key=(document_id,asset,self._people_owner().fence,id(self._precompute),id(self._vram.src_f32),id(self._vram.repair_base),self._body_identity())
            if getattr(self._vram,'people_key',None)!=key:
                from .cpu_memory_budget import available_estimate
                owned_inputs=OWNED.preview(self,state,body_bank=body_bank,body_source=source)
                recovery=SUPPORT.raster(state,self._people_support,asset,(self._vram.h,self._vram.w))
                R.synchronize(self._vram,state,asset,analyses,byte_budget=available_estimate(),recovery_assets=recovery,**owned_inputs)
                self._vram.people_key=key
            self._people_mirror()
        except (ValueError,RuntimeError,OSError,MemoryError) as error:
            if self._people_managed():R.suspend(self._vram,str(error))
            if strict:raise

    def _people_mirror(self):
        """Legacy controls are editing views only; final output uses every face."""
        owner=self._people_owner();source=self._people_source();state=owner.snapshot()
        from .people_cross_owner import validate_owner
        document_id=self._people_binding()['document_id']
        validate_owner(state,source['sha256'],document_id)
        if getattr(self, '_creative_base', None) is not None:
            from .creative_derived_effects import require_graph
            from .creative_derived_source import verify_precompute
            require_graph(state,source,document_id=document_id); verify_precompute(self,self._precompute)
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
            from .skin_colour_body_host import report as skin_body_report
            result['skin_body']=skin_body_report(self,state,source,self._people_cursors.get(asset))
            result['skin_finish_body']=skin_body_report(self,state,source,self._people_cursors.get(asset),family='skin_finish')
            result['collarbone']=skin_body_report(self,state,source,self._people_cursors.get(asset),family='collarbone',operation_id='lnx.collarbone.v1')
            result['body_skin_evenness']=skin_body_report(self,state,source,self._people_cursors.get(asset),family='body_skin_evenness',operation_id='lnx.body_skin_evenness.v1')
            result['body_face_match']=skin_body_report(self,state,source,self._people_cursors.get(asset),family='body_face_match',operation_id='lnx.body_face_match.v1')
            from .eye_light_host import report as eye_light_report
            result['eye_light']=eye_light_report(self,state,source,self._people_cursors.get(asset))
            from .eye_bag_preserve_host import report as eye_bag_report
            result['eye_bag_preserve']=eye_bag_report(self,state,source,self._people_cursors.get(asset))
            from .iris_makeup_host import report as iris_report
            result['iris_makeup']=iris_report(self,state,source,self._people_cursors.get(asset))
            from .eyeliner_host import report as eyeliner_report
            result['eyeliner']=eyeliner_report(self,state,source,self._people_cursors.get(asset))
            from .eyelash_host import report as eyelash_report
            result['eyelash']=eyelash_report(self,state,source,self._people_cursors.get(asset))
            from .brow_makeup_host import report as brow_makeup_report
            result['brow_makeup']=brow_makeup_report(self,state,source,self._people_cursors.get(asset))
            from .lipstick_host import report as lipstick_report
            result['lipstick']=lipstick_report(self,state,source,self._people_cursors.get(asset))
            from .blush_makeup_host import report as blush_report
            result['blush_makeup']=blush_report(self,state,source,self._people_cursors.get(asset))
            from .face_decoration_host import report as decoration_report
            result['face_decoration']=decoration_report(self,state,source,self._people_cursors.get(asset))
            from .facial_sculpt_host import report as sculpt_report
            result['facial_sculpt']=sculpt_report(self,state,source,self._people_cursors.get(asset))
            result.update(binding=self._people_binding(),editing_target=deepcopy(target),editing_overrides=overrides,legacy_unresolved=legacy_report(state,asset))
            return result
        except (ValueError,OSError):return None

    def _people_history_capture(self):
        if not self._people_managed():return None
        from .people_source_context import digest
        owner=self._people_owner();asset=self._people_source()['sha256']
        result=owner.capture_document(asset)
        result['source_context_sha256']=digest(owner.snapshot(),asset)
        return result

    def _people_history_apply(self,snapshot,transition=None,*,source_state=None):
        if snapshot is None:return
        from .creative_derived_source import binding
        owner=self._people_owner()
        asset=(binding(source_state,self._doc_path)['sha256'] if source_state is not None and source_state.get('_creative_base') is not None
               else SOURCE.source_digest(self._doc_path) if source_state is not None else self._people_source()['sha256'])
        if snapshot['asset_sha256']!=asset:raise ValueError('People history belongs to another source')
        if source_state is not None and asset!=self._people_source()['sha256']:
            from .people_graph_owner import document_slice
            graph=owner.snapshot()
            retained=document_slice(graph,asset)
            expected={key:snapshot[key] for key in retained}
            proof=snapshot.get('source_context_sha256')
            if proof is not None:
                from .people_source_context import digest
                S.digest(proof)
                if proof!=digest(graph,asset):
                    raise ValueError('Source portrait associations or effective recipe changed; undo cannot overwrite them')
                retained.pop('association_revision');expected.pop('association_revision')
            if retained!=expected:
                raise ValueError('Retained source portrait recipe changed; source-switch undo cannot overwrite it')
            # Both source slices remain in the graph. Switching the base is not
            # authority to reapply old edits over a concurrently edited source.
            self._people_analysis_key=None
            return
        if transition is not None:
            from .people_document_history import restore
            candidate=restore(owner,transition,asset)
        else:candidate=owner.stage_document_restore(snapshot,expected_asset_fence=owner.asset_fences.get(asset,0),expected_association_fence=owner.association_fence)
        owner.commit(candidate,expected_fence=owner.fence);self._people_analysis_key=None

    def _people_save(self,project):
        from .virtual_copy_people import save_project
        self._people_owner();save_project(self,project)
        from .people_cross_owner_project import validate_project
        validate_project(project)
        from .people_history_persistence import save
        save(self,project)

    def _people_stage_project(self,project,rows):
        from .people_project import validate_records
        from .people_history_persistence import prepare
        validate_records(project);HAIR.validate(project)
        from .people_cross_owner_project import validate_project
        validate_project(project)
        return prepare(project,rows,self.HISTORY_MAX)

    def _people_load(self,project,prepared_history=None):
        from .people_project import validate_records
        validate_records(project)
        from .people_cross_owner_project import validate_project
        validate_project(project)
        self._body_skin_evenness_reference=None;self._body_skin_evenness_preview=None
        self._collarbone_reference=None;self._collarbone_preview=None
        self._body_face_match_reference=None;self._body_face_match_preview=None
        HAIR.load(self,project)
        self._people_graph_owner=PeopleGraphOwner(project.get('people_graph'))
        self._people_support=SUPPORT.check_store(project.get('people_support_assets',{}))
        self._people_landmarks=RA.check_store(project.get('people_landmarks',{}))
        self._people_cursors=deepcopy(project.get('people_cursors',{}));self._people_targets={}
        self._people_analyses={};self._people_analysis_key=None;self._people_render_enabled=False
        from .virtual_copy_people import loaded
        loaded(self)
        from .people_history_persistence import restore
        restore(self,project,prepared_history)

    def _people_export_snapshot(self,state,source_path=None,graph=None,*,context=None,document_id=None):
        from .people_snapshot import capture
        from .virtual_copy_people import export_context,view
        if source_path is None:source_path=self._doc_path
        if not source_path:return None
        from .people_document_owner import capture as capture_owner
        document_id=capture_owner(self,state,source_path,document_id=document_id,context_supplied=context is not None)
        context=export_context(self,state,source_path,context)
        retained_host=view(self,context)
        from .creative_derived_source import binding, verify_precompute
        source=binding(state,source_path) if state.get('_creative_base') is not None else None
        asset=source['sha256'] if source is not None else SOURCE.source_digest(source_path)
        graph=context['people_graph'] if graph is None else S.check(graph)
        from .people_cross_owner import validate_owner
        validate_owner(graph,asset,document_id)
        retained=any(f['asset_sha256']==asset for f in graph['faces'].values()) or any(r['asset_sha256']==asset and r['status']=='unresolved' for r in graph['unresolved_legacy']) or any(r['scope']=='all_people' and r['target_id']==asset for r in graph['overrides'])
        if not retained:return None
        analyses={}
        pc=state.get('_precompute')
        verify_precompute(state,pc)
        if pc is not None and any(f['asset_sha256']==asset for f in graph['faces'].values()):
            face=next(f for f in graph['faces'].values() if f['asset_sha256']==asset)
            ev=face['evidence']
            _,analyses,_=B.bind(graph,asset,pc,source_dimensions=(ev['source_width'],ev['source_height']))
            analyses=RA.restore_missing(graph,context['people_landmarks'],asset,pc,analyses)
        face=next((f for f in graph['faces'].values() if f['asset_sha256']==asset),None)
        binding=None if face is None else {'sha256':asset,'width':face['evidence']['source_width'],'height':face['evidence']['source_height']}
        if pc is None and binding is not None and state.get('_creative_base') is None:
            from .hair_colour_replay import analyses as retained_hair_analyses
            restored=retained_hair_analyses(retained_host,graph,binding)
            if restored is not None:analyses=restored
        result=capture(graph,asset,analyses);result['document_id']=document_id;result['support_assets']=deepcopy(context['people_support_assets'])
        if state.get('_creative_base') is not None:
            from .creative_derived_effects import require_graph
            require_graph(graph,source,document_id=document_id)
            result['creative_source'] = source
            from .creative_derived_hair import capture as capture_hair
            return capture_hair(retained_host,state,result,pc,source)
        return result if binding is None else HAIR.capture(retained_host,result,pc,binding,source_path=source_path)

    def cmd_people(self,p):
        from .people_host_commands import apply
        return apply(self,p,emit)

    def finish_people(self,p,error):
        from .people_host_commands import finish
        return finish(self,p,error,emit)

    def _people_legacy(self,operation,p,emit):
        from .people_host_commands import legacy
        return legacy(self,operation,p,emit)

    def _people_prepare_graph(self,candidate,assets,*,decoration_authority=None):
        from .people_engine_runtime import prepare_preview
        from .cpu_memory_budget import available_estimate
        from .people_candidate_render import validate
        before=self._people_owner().snapshot();source=self._people_source();current=source['sha256']
        from .face_decoration_project import require_transition as require_decoration_transition
        require_decoration_transition(self,before,candidate,authority=decoration_authority)
        from .facial_sculpt_project import require_transition as require_sculpt_transition
        require_sculpt_transition(self,before,candidate)
        def signature(state,asset):
            return [(k,f['enabled'],f['local_assets'],resolve(state,k,A.defaults())['operations'],resolve(state,k,A.defaults())['conflicts'])
                    for k,f in sorted(state['faces'].items()) if f['asset_sha256']==asset]
        from .virtual_copy_people import scope_rows,is_private,current_row
        scoped_rows=scope_rows(self)
        if is_private(current_row(self)):assets=set(assets)&{current}
        staged=None
        for asset in sorted(assets):
            if asset!=current and signature(before,asset)==signature(candidate,asset) and before['association_revision']==candidate['association_revision']:continue
            if asset==current:
                owned_inputs=OWNED.preview(self,candidate,body_source=source)
                recovery=SUPPORT.raster(candidate,self._people_support,asset,(self._vram.h,self._vram.w))
                staged=prepare_preview(self._vram,candidate,asset,self._people_analyses.get(asset,{}),byte_budget=available_estimate(),recovery_assets=recovery,**owned_inputs)
            else:
                from .creative_derived_source import row_asset
                row=next((row for row in scoped_rows if row_asset(row)==asset),None)
                if row is None:raise ValueError('A linked photo is unavailable; shared edits were not partially applied')
                validate(self,row,candidate,decoration_authority=decoration_authority)
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
            from .virtual_copy_people import scope_rows
            for row in scope_rows(self):
                from .creative_derived_source import binding
                state=row.get('state') or {}
                asset=binding(state,row['path'])['sha256'] if state.get('_creative_base') is not None else SOURCE.source_digest(row['path'])
                if asset in assets:self._document_versions().advance(row)
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
        from .people_batch_ledger import restore_scoped
        if 'people_scoped_changes' in batch:return restore_scoped(self,batch,redo)
        # Old project-wide receipts remain attached to the original shared
        # owner even when the user is currently viewing a private copy.
        from .virtual_copy_people import is_private,PROJECT
        rows=[row for row in self._docs if not is_private(row) and not row.get('_people_new_import')]
        if not rows:raise ValueError('Legacy portrait history has no original project graph')
        converted=deepcopy(batch)
        converted['people_scoped_changes']=[{'scope':PROJECT,'document_id':rows[0]['document_id'],
                                              'changes':batch['people_changes']}]
        for record in converted['targets'].values():record['people_scope']=PROJECT
        return restore_scoped(self,converted,redo)

    def _people_selected_field(self,kind):
        from types import SimpleNamespace
        source=self._people_source();selected=self._people_cursors.get(source['sha256'])
        prepared=getattr(self._vram,'people_prepared',None)
        facts=prepared.facts.get(selected,{}).get(kind) if prepared else None
        return None if facts is None else SimpleNamespace(facts=facts,resident_bytes=lambda:0)
