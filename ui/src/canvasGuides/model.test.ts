import test from 'node:test';
import assert from 'node:assert/strict';
import {guidePolicy,isReport,type GuideModes} from './model.ts';
const neutral:GuideModes={available:true,compare:false,reference:false,brush:false,mask:false,category:false,crop:false,inspection:false,picker:false,manual:false,repair:false,busy:false};
test('automatic hiding gates creation without mutating manual visibility',()=>{
  for(const mode of ['compare','reference','brush','mask','category','crop','inspection','picker'] as const){
    const policy=guidePolicy({...neutral,[mode]:true});assert.equal(policy.hidden,true);assert.equal(policy.locked,true);
  }
  assert.equal(guidePolicy(neutral).hidden,false);
});
test('manual liquify and repair keep guides visible but read-only',()=>{
  for(const mode of ['manual','repair'] as const){const p=guidePolicy({...neutral,[mode]:true});assert.equal(p.hidden,false);assert.equal(p.locked,true);}
});
test('report verifies identity, finite positions, unique guide IDs and independent history',()=>{
  const p={protocol:1,view_only:true,geometry:'123',document_id:'copy-1',load_id:'load-copy-1',workspace:'w',revision:2,visible:true,
    lines:[{id:'g1',axis:'vertical',position:.5}],undo_steps:2,redo_steps:0};
  assert.equal(isReport(p),true);
  assert.equal(isReport({...p,lines:[...p.lines,...p.lines]}),false);
  assert.equal(isReport({...p,lines:[{...p.lines[0],position:NaN}]}),false);
  assert.equal(isReport({...p,load_id:''}),false);
  assert.equal(isReport({...p,revision:1.5}),false);
});
