import {test} from 'node:test';
import assert from 'node:assert/strict';
import {initialPresetForm,presetFormReducer,presetLabel,presetFromLabel,unavailableScope} from './presetModel.ts';
import type {PresetInfo} from '../native';
test('save confirmation clears only the submitted form revision, not newer typing',()=>{
  const first=presetFormReducer(initialPresetForm,{type:'name',value:'婚纱'});
  assert.equal(presetFormReducer(first,{type:'saved',id:'p',nameRevision:first.nameRevision}).name,'');
  const edited=presetFormReducer(first,{type:'name',value:'下一套'});
  assert.equal(presetFormReducer(edited,{type:'saved',id:'p',nameRevision:first.nameRevision}).name,'下一套');
});
test('selection and actual completion are separate; deleting another ID does not clear selection',()=>{
  const selected=presetFormReducer(initialPresetForm,{type:'select',id:'other'});
  assert.equal(presetFormReducer(selected,{type:'deleted',id:'p'}).selectedId,'other');
  assert.deepEqual(initialPresetForm.scope,[]);
});
test('duplicate names retain stable ID labels',()=>{
  const a={id:'a',name:'暖调'} as PresetInfo,b={id:'b',name:'暖调'} as PresetInfo;
  assert.equal(presetLabel(a,[a,b]),'暖调 · a');assert.equal(presetLabel(a,[a]),'暖调');
});
test('capability loss never silently expands or drops the selected scope',()=>{
  const state=presetFormReducer(initialPresetForm,{type:'scope',ops:['hsl','hsl','curves']});
  assert.deepEqual(state.scope,['hsl','curves']);
  assert.deepEqual(unavailableScope(state.scope,[{operation_id:'hsl',params:[],single_face:false,transferable:true}]),['curves']);
  assert.deepEqual(state.scope,['hsl','curves']);
});

test('legacy labels that collide with a literal user name are rejected instead of guessed',()=>{
  const list=[{id:'a',name:'X'},{id:'b',name:'X'},{id:'c',name:'X · a'}] as PresetInfo[];
  assert.equal(presetFromLabel('X · a',list),undefined);
  assert.equal(presetFromLabel('X · b',list)?.id,'b');
});
