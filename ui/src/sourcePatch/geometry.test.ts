import test from 'node:test';
import assert from 'node:assert/strict';
import {appendLasso,clampOffset,insidePolygon,MAX_POLYGON_POINTS,normalizedPoint,polygonError,sourceError,type Point} from './geometry.ts';
import {imageDisplayRect} from '../view.ts';

const square:Point[]=[[0.2,0.2],[0.4,0.2],[0.4,0.4],[0.2,0.4]];
test('letterboxed input uses presentation geometry, never screen or uncropped source pixels',()=>{
  const rect=imageDisplayRect({boxW:600,boxH:600,frameW:1200,frameH:600,zoom:1,panX:0,panY:0});
  assert.deepEqual(rect,{left:0,top:150,width:600,height:300});
  assert.deepEqual(normalizedPoint(300,300,rect,400,200),[0.5,0.5]);
  assert.equal(normalizedPoint(300,100,rect,400,200),null);
  assert.equal(normalizedPoint(600,300,rect,400,200),null);
});
test('bounded lasso retains both ends instead of dropping the rest of a long gesture',()=>{
  let points:Point[]=[];
  for(let i=0;i<4000;i++)points=appendLasso(points,[i/4000,Math.sin(i/30)*0.1+0.5]);
  assert.ok(points.length<=MAX_POLYGON_POINTS);
  assert.deepEqual(points[0],[0,0.5]);
  assert.deepEqual(points.at(-1),[3999/4000,Math.sin(3999/30)*0.1+0.5]);
});
test('target rejects nonfinite, crossed, duplicate, tiny and unbounded polygons',()=>{
  assert.equal(polygonError(square),null);
  for(const p of [[],[[0,0],[0.1,0.1]],[[0,0],[1,1],[0,1],[1,0]],
    [[0,0],[1,0],[1,0],[0,1]],[[0,0],[1e-8,0],[0,1e-8]],[[0,0],[2,0],[0,1]],[[0,0],[NaN,0],[0,1]]] as Point[][])
    assert.ok(polygonError(p));
});
test('translation keeps the same outline entirely inside input, with explicit source to target semantics',()=>{
  assert.deepEqual(clampOffset(square,[5,-5]),[0.6,-0.2]);
  assert.equal(sourceError(square,[0,0]),'请拖动同形轮廓，选择与目标不同的来源');
  assert.equal(sourceError(square,[0.3,0.2]),null);
  assert.ok(sourceError(square,[0.8,0]));
  assert.equal(insidePolygon([0.6,0.5],square,[0.3,0.2]),true);
  assert.equal(insidePolygon([0.3,0.3],square,[0.3,0.2]),false);
});
