/** Authored for Qoder execution. UNRUN here: no product imports, tests, or compiler were executed. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {clipGuideSegment,displayToSource,guideKeyboardDelta,guideSegment,guideTransform,roundEven,sourceToDisplay} from './geometry.ts';

const rect={left:100,top:25,width:800,height:400};
const near=(actual:number,expected:number)=>assert.ok(Math.abs(actual-expected)<1e-10,`${actual} != ${expected}`);

test('integer cuts use Python ties-to-even, including negative quarter-turn rounding',()=>{
  assert.deepEqual([.5,1.5,2.5,3.5,-.5,-1.5,-2.5].map(roundEven),[0,2,2,4,0,-2,-2]);
  const t=guideTransform([10,6],{rect:[.25,.25,.75,.75]},rect)!;
  assert.deepEqual([t.cropLeft,t.cropTop,t.cropWidth,t.cropHeight,t.outputWidth,t.outputHeight],[2,2,6,2,6,2]);
});

test('letterbox, zoom and pan coordinates use actual displayed image rect',()=>{
  const t=guideTransform([400,200],undefined,rect)!;
  assert.deepEqual(sourceToDisplay({x:0,y:0},t),{x:100,y:25});
  assert.deepEqual(sourceToDisplay({x:1,y:1},t),{x:900,y:425});
  assert.deepEqual(displayToSource({x:500,y:225},t),{x:.5,y:.5});
  const moved=guideTransform([400,200],undefined,{left:-250,top:-100,width:1600,height:800})!;
  assert.deepEqual(sourceToDisplay({x:.5,y:.5},moved),{x:550,y:300});
});

test('positive rotation is clockwise and crop happens before rotation',()=>{
  const t=guideTransform([10,6],{rect:[.25,.25,.75,.75],rotation_degrees:90},
    {left:40,top:20,width:200,height:600})!;
  assert.deepEqual([t.outputWidth,t.outputHeight],[2,6]);
  assert.deepEqual(sourceToDisplay({x:.2,y:2/6},t),{x:240,y:20});
  assert.deepEqual(sourceToDisplay({x:.8,y:4/6},t),{x:40,y:620});
  assert.deepEqual(guideSegment(t,'vertical',.5),{start:{x:240,y:320},end:{x:40,y:320}});
  assert.equal(guideSegment(t,'vertical',.1),null);
});

test('quarter turns preserve the pixel-center convention for both signs',()=>{
  const target={left:10,top:20,width:200,height:400};
  const clockwise=guideTransform([400,200],{rotation_degrees:90},target)!;
  const anticlockwise=guideTransform([400,200],{rotation_degrees:-90},target)!;
  assert.deepEqual(sourceToDisplay({x:.25,y:.75},clockwise),{x:60,y:120});
  assert.deepEqual(sourceToDisplay({x:.25,y:.75},anticlockwise),{x:160,y:320});
  const pixel=sourceToDisplay({x:.5/400,y:.5/200},clockwise);
  assert.deepEqual(pixel,{x:209.5,y:20.5});
});

test('strict half-degree snapping matches the engine compatibility boundary',()=>{
  for(const angle of [.499,-.499]){
    const t=guideTransform([400,200],{rotation_degrees:angle},rect)!;
    assert.deepEqual([t.cos,t.sin,t.outputWidth,t.outputHeight],[1,0,400,200]);
  }
  for(const angle of [.5,-.5,89.5,90.5,-89.5,-90.5]){
    const t=guideTransform([400,200],{rotation_degrees:angle},rect)!;
    assert.notEqual(t.sin,0);assert.notEqual(Math.abs(t.sin),1);
  }
  for(const angle of [89.501,90.499]){
    const t=guideTransform([400,200],{rotation_degrees:angle},rect)!;
    assert.deepEqual([t.cos,t.sin,t.outputWidth,t.outputHeight],[0,1,200,400]);
  }
});

test('arbitrary rotation uses expanded dimensions and invertible centered mapping',()=>{
  for(const angle of [.5,37,-37,90,179.8,-179.8]){
    const t=guideTransform([1001,777],{rect:[.15,.2,.91,.83],rotation_degrees:angle},rect)!;
    for(const point of [{x:.15,y:.2},{x:.5,y:.5},{x:.91,y:.83},{x:0,y:1}]){
      const roundtrip=displayToSource(sourceToDisplay(point,t),t);
      near(roundtrip.x,point.x);near(roundtrip.y,point.y);
    }
  }
  const t=guideTransform([100,50],{rotation_degrees:30},rect)!;
  assert.deepEqual([t.outputWidth,t.outputHeight],[112,93]);
});

test('crop-excluded guides are not drawn across rotated black corners',()=>{
  const t=guideTransform([100,100],{rect:[.2,.3,.8,.9],rotation_degrees:30},rect)!;
  assert.equal(guideSegment(t,'horizontal',.2),null);
  assert.equal(guideSegment(t,'vertical',.9),null);
  for(const axis of ['horizontal','vertical'] as const){
    const segment=guideSegment(t,axis,.5)!;
    for(const endpoint of [segment.start,segment.end]){
      const source=displayToSource(endpoint,t);
      near(axis==='vertical'?source.x:source.y,.5);
      assert.ok(source.x>=.2-1e-12&&source.x<=.8+1e-12&&source.y>=.3-1e-12&&source.y<=.9+1e-12);
    }
  }
});

test('viewport clipping preserves the sloped line and rejects offscreen lines',()=>{
  const viewport={left:0,top:0,width:100,height:80};
  assert.deepEqual(clipGuideSegment({start:{x:-50,y:-50},end:{x:150,y:150}},viewport),
    {start:{x:0,y:0},end:{x:80,y:80}});
  assert.equal(clipGuideSegment({start:{x:-10,y:0},end:{x:-10,y:80}},viewport),null);
  assert.deepEqual(clipGuideSegment({start:{x:0,y:-20},end:{x:0,y:100}},viewport),
    {start:{x:0,y:0},end:{x:0,y:80}});
});

test('arrow movement is screen-space projected after rotation; Shift step scales tenfold',()=>{
  const t=guideTransform([400,200],undefined,rect)!;
  near(guideKeyboardDelta(t,'vertical','ArrowRight'),1/800);
  near(guideKeyboardDelta(t,'vertical','ArrowUp'),0);
  near(guideKeyboardDelta(t,'horizontal','ArrowDown',10),10/400);
  const turned=guideTransform([400,200],{rotation_degrees:90},{left:0,top:0,width:400,height:800})!;
  near(guideKeyboardDelta(turned,'vertical','ArrowDown'),1/800);
  near(guideKeyboardDelta(turned,'horizontal','ArrowRight'),-1/400);
  near(guideKeyboardDelta(turned,'vertical','ArrowRight'),0);
});

test('singleton crop axes remain usable and malformed inputs fail closed',()=>{
  const t=guideTransform([1,50],{rect:[.2,.1,.3,.9],rotation_degrees:90},rect)!;
  assert.deepEqual([t.cropWidth,t.cropHeight,t.outputWidth,t.outputHeight],[1,40,40,1]);
  assert.ok(guideSegment(t,'vertical',.5));
  assert.equal(guideTransform([0,50],undefined,rect),null);
  assert.equal(guideTransform([40.5,50],undefined,rect),null);
  assert.equal(guideTransform([40,50],{rect:[.5,0,.5,1]},rect),null);
  assert.equal(guideTransform([40,50],{rect:[0,0,1,NaN]},rect),null);
  assert.equal(guideTransform([40,50],{rotation_degrees:181},rect),null);
  assert.equal(guideTransform([40,50],undefined,{...rect,width:0}),null);
  assert.equal(guideSegment(t,'vertical',NaN),null);
  assert.equal(guideSegment(t,'horizontal',-1),null);
});
