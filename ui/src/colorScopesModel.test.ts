import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {matchesScope,histogramPoints,type ScopeResult} from './colorScopesModel.ts';
const result={request_id:'r',document_id:'d',host_doc_rev:3,stage:'output',success:true,error:null} as ScopeResult;
test('histograms require exact recipe revision, document, stage and request',()=>{
  assert.equal(matchesScope(result,'r','d',3,'output'),true);
  assert.equal(matchesScope(result,'r','d',4,'output'),false);
  assert.equal(matchesScope(result,'old','d',3,'output'),false);
  assert.equal(matchesScope(result,'r','other',3,'output'),false);
  assert.equal(matchesScope(result,'r','d',3,'original'),false);
});
test('count-axis logarithm does not change bin positions',()=>{
  const h={bins:[0,1,9],underflow:2,overflow:3};
  const points=histogramPoints(h,9,false).split(' ').map(p=>p.split(',').map(Number));
  assert.deepEqual(points.map(p=>p[0]),[0,1,2]);
  assert.equal(points[0][1],100);assert.equal(points[2][1],0);
  assert.ok(Math.abs(points[1][1]-(100-100/9))<1e-12);
  assert.match(histogramPoints(h,9,true),/^0,100 1,[\d.]+ 2,0$/);
  assert.equal(histogramPoints({bins:[0],underflow:0,overflow:0},0,true),'0,100');
});
test('panel identifies proxy statistics and clears them on edit intent',()=>{
  const source=readFileSync(new URL('./components/HistogramPanel.tsx',import.meta.url),'utf8');
  assert.match(source,/INSPECTION_EDIT_INTENT,invalidate/);
  assert.match(source,/不是全源直方图/);
  assert.match(source,/这是采样均值，不是点取色/);
});

test('display-only scope controls are exempt from global image-edit invalidation',()=>{
  const app=readFileSync(new URL('./App.tsx',import.meta.url),'utf8');
  const panel=readFileSync(new URL('./components/HistogramPanel.tsx',import.meta.url),'utf8');
  assert.match(app,/target.closest\('\[data-readonly-scopes\]'\)/);
  assert.match(panel,/<fieldset data-readonly-scopes/);
});
