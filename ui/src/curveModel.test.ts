import {test} from 'node:test';
import assert from 'node:assert/strict';
import {curveSignature,movedCurvePoint,matchesCurveResult} from './curveModel.ts';
import type {CurveSpec} from './native';
test('curve signature ignores JSON object key order',()=>{
  const a={version:1,space:'srgb-display',interpolation:'pchip',boundary:'linear',enabled:true,
    master:[[0,0],[1,1]],red:[[0,0],[1,1]],green:[[0,0],[1,1]],blue:[[0,0],[1,1]]} as CurveSpec;
  const sorted=Object.fromEntries(Object.entries(a).sort()) as CurveSpec;
  assert.equal(curveSignature(a),curveSignature(sorted));
});
test('dense valid points remain horizontally unchanged during vertical edits',()=>{
  const p:[number,number][]=[[0,0],[1e-5,.2],[2e-5,.3],[1,1]];
  assert.deepEqual(movedCurvePoint(p,1,1e-5,.8),[1e-5,.8]);
});
test('endpoint x is fixed and channel point cannot cross its neighbour',()=>{
  const p:[number,number][]=[[0,0],[.5,.5],[1,1]];
  assert.deepEqual(movedCurvePoint(p,0,.8,.7),[0,.7]);
  assert.ok(movedCurvePoint(p,1,2,.8)[0]<1);
});
test('fresh result ID acknowledges repeated identical errors, stale IDs cannot',()=>{
  assert.equal(matchesCurveResult('request-2','request-1'),false);
  assert.equal(matchesCurveResult('request-2','request-2'),true);
  assert.equal(matchesCurveResult(undefined,undefined),false);
});
