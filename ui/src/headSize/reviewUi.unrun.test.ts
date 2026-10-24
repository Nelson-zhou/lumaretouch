// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. Source assertions are not mounted React/browser acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const read=(path:string)=>readFileSync(new URL(path,import.meta.url),'utf8');
test('editor uses genuine source mapping, explicit geometry and original-pixel input',()=>{
 const source=read('./HeadSizeSupportEditor.tsx');
 assert.match(source,/useState<Draft>\(\{\}\)/);assert.match(source,/sourceViewport\(image\)/);assert.match(source,/matchesSource\(image,body.source\)/);assert.match(source,/getScreenCTM/);assert.match(source,/measure\(point.x\/w,point.y\/h\)/);
 assert.match(source,/采用手工坐标/);assert.match(source,/不是缩略图像素/);assert.match(source,/checkBodySupport\(support,body\)/);assert.match(source,/body.associated_face/);
 assert.match(source,/setDraft\(\{\}\)/);assert.match(source,/setFlags\(\{\}\)/);assert.match(source,/\[context\]/);assert.match(source,/body.points_sha256,body.source,body.association,body.associated_face/);
 assert.match(source,/载入本项已存测量，仍需重新确认/);assert.doesNotMatch(source,/pivot:\[\.5,\.5\]|defaultValue|automatic_center/);
});
test('review remains usable without native core, but nonzero and enable stay gated',()=>{
 const panel=read('./HeadSizePanel.tsx');
 assert.match(panel,/disabled=\{busy\|\|!body.enabled\}/);assert.doesNotMatch(panel,/disabled=\{busy\|\|!body.enabled\|\|!coreAvailable\}/);
 assert.match(panel,/canReset&&coreAvailable/);assert.match(panel,/min=\{0\} max=\{100\}/);assert.match(panel,/!coreAvailable\|\|!body.reviewed/);
 assert.match(panel,/不是人脸大小控制的复制/);assert.match(panel,/不宣称预设、同步或批量迁移已接入/);assert.match(panel,/自然度与实机验收未运行/);
});
test('native workflow status reconciliation remains query-only through lost outer mailbox',()=>{
 const hook=read('./useHeadSizeWorkflow.ts'),port=read('./nativeTransport.ts');
 assert.match(hook,/command\('status',\{request_id:id\}\)/);assert.match(hook,/recoveryWithoutCore\(request.action,request.payload\)/);
 assert.match(port,/runHeadSize\(\{action:'mailbox_status',request_id:id\}\)/);assert.match(port,/await deadline\(runHeadSize\(command\)\)/);
 assert.equal((port.match(/runHeadSize\(command\)/g)??[]).length,1);
});
