import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {canReconcileEdit} from './editReceipts.ts';
const receipt={request_id:'r2',document_id:'photo-A',host_doc_rev:8};
test('same recipe or same revision alone never acknowledges a pending request',()=>{
  assert.equal(canReconcileEdit('r2',null,'photo-A','photo-A',8,true),false);
  assert.equal(canReconcileEdit('r1',receipt,'photo-A','photo-A',8,true),false);
  assert.equal(canReconcileEdit(undefined,receipt,'photo-A','photo-A',8,true),false);
});
test('matching receipt waits for its snapshot, accepts equal revision and later undo state',()=>{
  assert.equal(canReconcileEdit('r2',receipt,'photo-A','photo-A',7,true),false);
  assert.equal(canReconcileEdit('r2',receipt,'photo-A','photo-A',8,true),true);
  assert.equal(canReconcileEdit('r2',receipt,'photo-A','photo-A',9,true),true);
});
test('mixed-document status, missing value and malformed revision cannot reconcile',()=>{
  assert.equal(canReconcileEdit('r2',receipt,'photo-A','photo-B',9,true),false);
  assert.equal(canReconcileEdit('r2',receipt,'photo-B','photo-B',9,true),false);
  assert.equal(canReconcileEdit('r2',receipt,'photo-A','photo-A',9,false),false);
  assert.equal(canReconcileEdit('r2',{...receipt,host_doc_rev:NaN},'photo-A','photo-A',9,true),false);
});
test('both tonal editors use authoritative current snapshots, never historical receipt recipes',()=>{
  for(const name of ['LevelsEditor','CurveEditor']){
    const source=readFileSync(new URL(`./components/${name}.tsx`,import.meta.url),'utf8');
    assert.match(source,/canReconcileEdit\(pending.current\?\.id,result,documentId,snapshotId,documentRevision,true\)/);
    assert.match(source,/\[result,documentId,snapshotId,documentRevision,value\]/);
    assert.doesNotMatch(source,/update\(result.spec\)|copy\(result.spec\)/);
    assert.doesNotMatch(source,/pending.current.signature!==/);
  }
});
