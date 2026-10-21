import {test} from 'node:test';
import assert from 'node:assert/strict';
import {capturePoint,neighbourhood} from './colorSampleGeometry.ts';
test('presentation aspect and raster indexing are independent',()=>{
  const square={left:100,top:0,width:400,height:400};
  assert.deepEqual(capturePoint(300,200,square,600,400),{x:300,y:200});
  assert.equal(capturePoint(99,200,square,600,400),null);
  assert.equal(capturePoint(500,200,square,600,400),null);
});
test('zoom/pan transforms and outside margins do not get clamped into the image',()=>{
  const rect={left:-200,top:-100,width:1200,height:800};
  assert.deepEqual(capturePoint(0,0,rect,600,400),{x:100,y:50});
  assert.equal(capturePoint(NaN,0,rect,600,400),null);
});
test('neighbourhood reports actual edge-clipped area',()=>{
  assert.deepEqual(neighbourhood({x:0,y:0,size:3},80,64),{x:0,y:0,width:2,height:2});
  assert.equal(neighbourhood({x:-1,y:0,size:3},80,64),null);
});
