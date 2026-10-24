// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. These source assertions must not be reported as app acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const read=(path:string)=>readFileSync(new URL(path,import.meta.url),'utf8');
test('normal body routing mounts an independent waist owner with reachable receipt queries',()=>{
 const app=read('../App.tsx'),tools=read('../legShape/BodyShapeTools.tsx'),coverage=read('../toolRouting/coverage.ts');
 assert.match(app,/const waistLength=useWaistLengthWorkflow/);assert.match(app,/waistLength=\{waistLength\}/);assert.match(app,/pending:waistLength\.busy/);assert.match(app,/check:waistLength\.check/);
 assert.match(app,/\[data-waist-length-workflow\]/);assert.match(tools,/data-control-id="PC-32473-C-5d33f285bb"/);assert.match(tools,/data-tool-anchor="腰部长度"/);assert.match(tools,/<WaistLengthWorkspace owner=\{waistLength\}/);assert.match(coverage,/"腰部长度"/);
});
test('source review explicitly draws manual marks, never substitutes pose joints, and remains available without core',()=>{
 const editor=read('./WaistLengthSupportEditor.tsx'),panel=read('./WaistLengthPanel.tsx');
 assert.match(editor,/WAIST_MARKERS\.map/);assert.match(editor,/sourceViewport\(image\)/);assert.match(editor,/checkBodySupport\(support,body\)/);assert.match(editor,/采用手工坐标/);assert.match(editor,/setFlags\(\{\}\)/);
 assert.match(panel,/disabled=\{busy\|\|!body\.enabled\}/);assert.doesNotMatch(panel,/disabled=\{busy\|\|!body\.enabled\|\|!coreAvailable\}/);
 assert.match(panel,/canReset&&coreAvailable/);assert.match(panel,/向左缩短 ← 原始 0 → 向右拉长/);assert.doesNotMatch(panel,/不是腰部长度/);
});
test('native read-only reconciliation bypasses mutation fences and no waist transfer UI is advertised',()=>{
 const native=read('../native.ts'),hook=read('./useWaistLengthWorkflow.ts'),panel=read('./WaistLengthPanel.tsx');
 assert.match(native,/export function runWaistLength/);assert.match(native,/tauriInvoke<import\('\.\/waistLength\/nativeTransport'\)\.Mailbox>\('waist_length'/);
 assert.match(hook,/command\('status',\{request_id:id\}\)/);assert.match(hook,/recoveryWithoutCore\(request.action,request.payload\)/);assert.match(panel,/预设、同步、批量不借用当前照片的审核/);
});
