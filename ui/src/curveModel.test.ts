import {test} from 'node:test';
import assert from 'node:assert/strict';
import {curveSignature,movedCurvePoint,matchesCurveResult,editableCurveSpec,parametricCurveSpec,curveEditSnapshot} from './curveModel.ts';
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

test('luminance recipe and domain participate in authoritative signatures',()=>{
  const a={version:2,space:'srgb-display',interpolation:'pchip',boundary:'linear',enabled:true,
    master:[[0,0],[1,1]],red:[[0,0],[1,1]],green:[[0,0],[1,1]],blue:[[0,0],[1,1]],
    luminance_space:'linear-srgb-y-ratio',luminance:[[0,0],[1,1]]} as CurveSpec;
  const b=structuredClone(a);b.luminance=[[0,.1],[1,.9]];
  assert.notEqual(curveSignature(a),curveSignature(b));
});

test('legacy editor migration adds a neutral independent luminance channel without mutating source',()=>{
  const old={version:1,space:'srgb-display',interpolation:'pchip',boundary:'linear',enabled:true,
    master:[[0,0],[1,1]],red:[[0,0],[1,1]],green:[[0,0],[1,1]],blue:[[0,0],[1,1]]} as CurveSpec;
  const next=editableCurveSpec(old);
  assert.equal(next.version,2);assert.equal(old.version,1);
  assert.equal(next.luminance_space,'linear-srgb-y-ratio');
  assert.deepEqual(next.luminance,[[0,0],[1,1]]);
  next.red[0][1]=.2;assert.equal(old.red[0][1],0);
  assert.equal(curveSignature(next),curveSignature(editableCurveSpec(next)));
});

test('v3 point edits preserve parameter stage and signatures cover every parameter field',()=>{
  const old={version:1,space:'srgb-display',interpolation:'pchip',boundary:'linear',enabled:true,
    master:[[0,0],[1,1]],red:[[0,0],[1,1]],green:[[0,0],[1,1]],blue:[[0,0],[1,1]]} as CurveSpec;
  const a=parametricCurveSpec(old);a.parametric.shadows=25;
  const next=editableCurveSpec(a);assert.equal(next.version,3);assert.deepEqual(next.parametric,a.parametric);
  for(const key of ['shadows','darks','lights','highlights'] as const){const changed=structuredClone(a);changed.parametric[key]+=1;
    assert.notEqual(curveSignature(a),curveSignature(changed));}
  const changed=structuredClone(a);changed.parametric.splits[0]=.2;
  assert.notEqual(curveSignature(a),curveSignature(changed));
  const reordered={...a,parametric:Object.fromEntries(Object.entries(a.parametric).reverse())} as CurveSpec;
  assert.equal(curveSignature(a),curveSignature(reordered));assert.equal(old.version,1);
});

test('editable luminance view does not overwrite the raw legacy cancellation snapshot',()=>{
  const old={version:1,space:'srgb-display',interpolation:'pchip',boundary:'linear',enabled:true,
    master:[[0,0],[1,1]],red:[[0,.1],[1,1]],green:[[0,0],[1,1]],blue:[[0,0],[1,1]]} as CurveSpec;
  const snapshot=curveEditSnapshot(old);assert.equal(snapshot.editable.version,2);assert.deepEqual(snapshot.raw,old);
  snapshot.editable.red[0][1]=.9;assert.equal(snapshot.raw.red[0][1],.1);assert.equal(old.red[0][1],.1);
});
