// AUTHORED / UNRUN: no runtime/test runner invocation authorized.
import assert from 'node:assert/strict';
import test from 'node:test';
import {checkedPlan,acknowledgments,imageMeta,catalogue,scopeLabel} from './model';
const h='a'.repeat(64),image={mime:'image/png' as const,width:20,height:20,sha256:h,byte_length:33,page_count:1};
const preset={id:'saved',name:'Saved',preset_sha256:h,module_ids:['lnx.skin.v1']};
const target={document_id:'first',revision:'1',path:'/first.png',review_sha256:h,before:image,after:image};
const reply={success:true,portrait_preset:true,preflight_token:'f'.repeat(32),preset_id:'saved',preset_sha256:h,module_scope:['lnx.skin.v1'],targets:[target]};
test('whole group identity cannot silently omit or reorder selected targets',()=>{
 assert.equal(checkedPlan(reply,['first'],preset).targets.length,1);
 assert.throws(()=>checkedPlan(reply,['first','second'],preset));
 assert.throws(()=>checkedPlan(reply,['second'],preset));
 assert.throws(()=>checkedPlan({...reply,preset_sha256:'b'.repeat(64)},['first'],preset));
 assert.throws(()=>checkedPlan({...reply,module_scope:['lnx.exposure.v1']},['first'],preset));
});
test('group ACK binds each displayed frozen side and target revision',()=>{
 assert.deepEqual(acknowledgments(checkedPlan(reply,['first'],preset)),[{document_id:'first',revision:'1',before_sha256:h,after_sha256:h,review_sha256:h}]);
 assert.equal(imageMeta({...image,page_count:2}),false);
 assert.equal(imageMeta({...image,byte_length:4*1024*1024+1}),false);
});
test('partial catalogues are rejected and unsupported whole presets are not truncated',()=>{
 assert.throws(()=>catalogue({complete:false,errors:[],presets:[preset]}));
 assert.deepEqual(catalogue({complete:true,errors:[],presets:[preset,{...preset,id:'unsupported',module_ids:['lnx.skin.v1','lnx.crop.v1']}]}),[preset]);
});

// Interrupted reads must never become a group ACK merely because metadata exists.
test('image reads reject stale page ownership before decoding',async()=>{
 const {imageData}=await import('./model');
 const plan=checkedPlan(reply,['first'],preset);
 await assert.rejects(imageData(plan,target,'before',async()=>({success:true,portrait_preset:true,preflight_token:'other',document_id:'first'}),()=>true));
 await assert.rejects(imageData(plan,target,'before',async()=>{throw Error('must not dispatch after close');},()=>false));
});

// AUTHORED / UNRUN: retained all-face support cannot alias legacy smoothing.
test('retained finish group requires explicit mode and exact own face references',()=>{
 const finish={...preset,module_ids:['lnx.skin_finish.v1'],portrait_group_support:{supported:true,reason:null,mode:'retained_people' as const}};
 const face={asset_sha256:h,face_instance_id:'face-a',analysis_revision:0};
 const people={...reply,module_scope:finish.module_ids,mode:'retained_people',targets:[{...target,face_count:2,face_refs:[face,{...face,face_instance_id:'face-b'}]}]};
 assert.equal(checkedPlan(people,['first'],finish).targets[0].face_count,2);
 assert.throws(()=>checkedPlan({...people,mode:undefined},['first'],finish));
 assert.throws(()=>checkedPlan({...people,targets:[{...people.targets[0],face_count:1}]},['first'],finish));
 assert.throws(()=>checkedPlan({...people,targets:[{...people.targets[0],face_refs:[face,face]}]},['first'],finish));
 assert.throws(()=>checkedPlan({...people,targets:[{...people.targets[0],face_refs:[face,{...face,face_instance_id:'face-b',asset_sha256:'b'.repeat(64)}]}]},['first'],finish));
 assert.throws(()=>checkedPlan(people,['first'],preset));
 assert.deepEqual(catalogue({complete:true,errors:[],presets:[finish,{...finish,id:'mixed',module_ids:['lnx.skin_finish.v1','lnx.skin.v1']},{...finish,id:'unsupported',module_ids:['lnx.skin_colour.v1']}]}),[finish]);
 assert.deepEqual(catalogue({complete:true,errors:[],presets:[{...finish,portrait_group_support:undefined}]}),[]);
});

// AUTHORED / UNRUN: real retained texture is not the legacy scalar smoothing op.
test('texture and finish can share one retained group but never scalar smoothing',()=>{
 const support={supported:true,reason:null,mode:'retained_people' as const};
 const texture={...preset,module_ids:['lnx.skin_texture.v1'],portrait_group_support:support};
 const mixed={...texture,id:'finish-texture',module_ids:['lnx.skin_finish.v1','lnx.skin_texture.v1']};
 assert.deepEqual(catalogue({complete:true,errors:[],presets:[texture,mixed,{...mixed,id:'legacy-mix',module_ids:['lnx.skin_texture.v1','lnx.skin.v1']},{...texture,id:'duplicate',module_ids:['lnx.skin_texture.v1','lnx.skin_texture.v1']}]}),[texture,mixed]);
});

// AUTHORED / UNRUN: complete mixed preset keeps global and face scopes distinct.
test('retained group accepts only exposure WB plus genuine face modules',()=>{
 const support={supported:true,reason:null,mode:'retained_people' as const};
 const mixed={...preset,module_ids:['lnx.exposure.v1','lnx.white_balance.v1','lnx.skin_finish.v1','lnx.skin_texture.v1'],portrait_group_support:support};
 const wrong=[{...mixed,id:'global-only',module_ids:['lnx.exposure.v1']},{...mixed,id:'legacy',module_ids:[...mixed.module_ids,'lnx.skin.v1']},{...mixed,id:'crop',module_ids:[...mixed.module_ids,'lnx.crop.v1']},{...mixed,id:'no-admission',portrait_group_support:undefined}];
 assert.deepEqual(catalogue({complete:true,errors:[],presets:[mixed,...wrong]}),[mixed]);
 assert.equal(scopeLabel(mixed.module_ids),'全图曝光 ＋ 全图白平衡 ＋ 逐脸美白／红润 ＋ 逐脸质感／清晰度');
 const face={asset_sha256:h,face_instance_id:'face-a',analysis_revision:0};
 const full={...reply,mode:'retained_people',module_scope:mixed.module_ids,targets:[{...target,face_count:1,face_refs:[face]}]};
 assert.equal(checkedPlan(full,['first'],mixed).module_scope.length,4);
 assert.throws(()=>checkedPlan({...full,module_scope:['lnx.skin_finish.v1','lnx.skin_texture.v1']},['first'],mixed));
});
test('reference-only mode requires each own target fit and never admits mixed modules',()=>{
 const reference={...preset,module_ids:['lnx.reference_color.v1'],portrait_group_support:{supported:true,reason:null,mode:'reference_color' as const}};
 const fit={version:1,method:'matched-patch-linear-rgb-v1',proof:h,target:{document_id:'first',revision:'1'},recipe:{strength:1,log2_gains:[0.1,0.2,0.3]},fit:{consensus_count:100,consensus_fraction:.8,residual_p90_stops:.05},new_gamut_fraction:0,warnings:[],geometry:{}};
 const prepared={...reply,module_scope:reference.module_ids,mode:'reference_color',targets:[{...target,reference_color:fit}]};
 assert.equal(checkedPlan(prepared,['first'],reference).mode,'reference_color');
 assert.throws(()=>checkedPlan({...prepared,targets:[target]},['first'],reference));
 assert.throws(()=>checkedPlan({...prepared,targets:[{...target,reference_color:{...fit,target:{document_id:'another',revision:'1'}}}]},['first'],reference));
 assert.throws(()=>checkedPlan({...prepared,mode:'legacy_scalar'},['first'],reference));
 assert.deepEqual(catalogue({complete:true,errors:[],presets:[reference,{...reference,id:'mixed',module_ids:[...reference.module_ids,'lnx.skin_finish.v1']}]}).map(p=>p.id),['saved']);
});
