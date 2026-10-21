import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {neutralLevels,changedLevel,levelsSignature,levelsMidpoint,gammaFromMidpoint} from './levelsModel.ts';
test('levels default owns independent channels and edits do not mutate input',()=>{
  const a=neutralLevels(),b=changedLevel(a,'red','gamma',2);
  assert.equal(a.red.gamma,1);assert.equal(b.red.gamma,2);assert.equal(b.green.gamma,1);
  b.master.input_black=.1;assert.equal(b.red.input_black,0);
});
test('input endpoints maintain an admissible gap even at floating boundaries',()=>{
  for(const x of [0,.5,1,10,-10]){
    let s=changedLevel(neutralLevels(),'master','input_black',x);
    assert.ok(s.master.input_white-s.master.input_black>=1e-5);
    s=changedLevel(s,'master','input_white',-2);
    assert.ok(s.master.input_white-s.master.input_black>=1e-5);
  }
  assert.throws(()=>changedLevel(neutralLevels(),'master','gamma',NaN));
});
test('gamma and midpoint are inverse and gamma greater than one moves grey left',()=>{
  const b=neutralLevels().master;assert.equal(levelsMidpoint(b),.5);
  b.gamma=2;assert.equal(levelsMidpoint(b),.25);
  assert.ok(Math.abs(gammaFromMidpoint(b,.25)-2)<1e-12);
  b.input_black=.1;b.input_white=.9;
  assert.ok(Math.abs(gammaFromMidpoint(b,levelsMidpoint(b))-2)<1e-12);
});
test('output inversion is preserved and signatures cover all fields',()=>{
  const a=neutralLevels();let b=changedLevel(a,'master','output_black',1);
  b=changedLevel(b,'master','output_white',0);
  assert.equal(b.master.output_black,1);assert.equal(b.master.output_white,0);
  assert.notEqual(levelsSignature(a),levelsSignature(b));
});
test('levels UI sends document identity and retains interrupted-gesture barriers',()=>{
  const editor=readFileSync(new URL('./components/LevelsEditor.tsx',import.meta.url),'utf8');
  const native=readFileSync(new URL('./native.ts',import.meta.url),'utf8');
  assert.match(editor,/runLevels\('set',spec,documentId,gestureId,interactive,requestId\)/);
  assert.match(editor,/canReconcileEdit/);
  assert.match(editor,/setPointerCapture\(e.pointerId\)/);
  assert.match(editor,/onPointerCancel=\{\(\)=>finish\(true\)\}/);
  assert.match(native,/documentId,gestureId,interactive,requestId/);
});
