import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source=(name:string)=>readFileSync(new URL(`../${name}`,import.meta.url),'utf8');
test('App owns one workflow outside conditional panels and exposes pending status independently',()=>{
  const app=source('App.tsx');
  assert.equal((app.match(/\buseSourcePatchWorkflow\(/g)??[]).length,1);
  assert.ok(app.indexOf('const sourcePatch=useSourcePatchWorkflow')<app.indexOf('<RetouchPanel'));
  assert.match(app,/<SourcePatchStatus owner=\{sourcePatch\}/);
  assert.match(app,/<Viewer[^>]*sourcePatch=\{sourcePatch\}/);
  assert.match(app,/source_patch_capture_protocol===1&&caps\?\.source_patch_result_protocol===1/);
  const allowed=app.slice(app.indexOf('const sourcePatchAllowed='),app.indexOf('const sourcePatchCanStart='));
  assert.doesNotMatch(allowed,/edit_queue/,'the shared queue includes the capture itself');
  assert.match(app,/canStart:sourcePatchCanStart/);
  assert.ok(app.split('\n').length-1<=2160,'App must remain within its size boundary');
});
test('repair panel wires an independent panel, never maps source patch to heal',()=>{
  const panel=source('components/RetouchPanel.tsx');
  assert.match(panel,/fid === "PC-32482"[^\n]*props\.sourcePatchPanel/);
  assert.doesNotMatch(panel,/"PC-32482\|修补工具":\s*"brush\.heal"/);
  assert.match(panel,/leaf\.path==='修补工具'&&props\.sourcePatchPanel\)return null/);
  assert.doesNotMatch(panel,/本版未实现独立采样/);
});
test('viewer adds a separate overlay without replacing main mirror rendering',()=>{
  const viewer=source('components/Viewer.tsx');
  assert.match(viewer,/<SourcePatchOverlay owner=\{sourcePatch\} clip=\{sampleClip\} box=\{box\} view=\{view\}/);
  assert.match(viewer,/ref=\{mirrorRef\}/);
  assert.match(viewer,/sourcePatch\?\.active \|\| !!sourcePatch\?\.pending/);
});
test('pointer release never submits; cancel is separate from explicit application',()=>{
  const overlay=source('sourcePatch/SourcePatchOverlay.tsx'),panel=source('sourcePatch/SourcePatchPanel.tsx');
  assert.doesNotMatch(overlay,/workflow\.apply\(/);
  assert.match(overlay,/onPointerCancel=\{[^\n]*workflow\.cancel/);
  assert.match(panel,/workflow\.apply\(\)/);
  assert.match(overlay,/source\[0\]\*rect\.width[\s\S]*x2=\{target\[0\]\*rect\.width\}/);
});
