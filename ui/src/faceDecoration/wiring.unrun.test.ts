// AUTHORED / UNRUN. Static source contracts only; not a rendered UI or build pass.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {batchScopeOptions} from '../batch/batchScopeOptions.ts';
import {moduleLabel, unavailableScope} from '../presets/presetModel.ts';
import {CATALOGUE_SHA256, PATTERNS} from './catalogue.ts';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('./FaceDecorationPanel.tsx'), editor = source('./FaceDecorationSupportEditor.tsx');
const route = source('../components/RetouchPanel.tsx'), workflow = source('../people/workflow.ts');

test('static catalogue mirror equals canonical original marks, without vendor images', () => {
  const bytes = readFileSync(new URL('../../../engine/src/lumaretouch_engine/face_decoration_patterns.json', import.meta.url));
  assert.equal(createHash('sha256').update(bytes).digest('hex'), CATALOGUE_SHA256);
  assert.deepEqual(PATTERNS, JSON.parse(bytes.toString()).patterns);
  assert.ok(panel.includes('图案示意')); assert.ok(panel.includes('不是人物效果图'));
  assert.equal(/https?:\/\//.test(source('./catalogue.ts')), false);
});
test('only the handbook face-decoration leaf routes directly through RetouchPanel, with all owner fences', () => {
  assert.ok(route.includes('"PC-32471|局部妆容/脸部装饰": "face_decoration.family"'));
  const branch = route.slice(route.indexOf('if (kind === "face_decoration.family")'), route.indexOf('if (kind === "blush.family")'));
  for (const text of ['<FaceDecorationPanel', 'people={props.people}', 'capability={status?.ready_caps}', 'props.faceOk', 'props.faceWhy', 'dim',
    'props.hairBusy', 'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight', 'status?.edit_queue?.pending', 'status?.edit_queue?.closed']) assert.ok(branch.includes(text));
  assert.ok(source('../spec/refine.json').includes('"path": "局部妆容/脸部装饰"'));
  assert.equal(panel.includes('runEnhance'), false); assert.equal(panel.includes('runHistory'), false); assert.equal(panel.includes('invoke('), false);
});
test('real PNG verification and decoded dimensions precede all operation-specific paint/ownership consent', () => {
  for (const text of ['verifiedImage(report.source_preview, proof)', 'naturalWidth === image.displayWidth', 'naturalHeight === image.displayHeight',
    'loaded && !!image', 'getScreenCTM()', 'sourceViewport(image)', 'onPointerDown={start}', 'onKeyDown={keyboard}',
    'setFlags(emptyFlags())', '人物', '不沿用腮红或其他工具的审核', 'ownership_confirmed']) {
    assert.ok((editor + source('./review.ts')).includes(text));
  }
  assert.ok(editor.includes('setImage(null); setLoaded(false); setStrokes([])'));
  assert.ok(editor.includes('active = false; alive.current = false; drawing.current = null'));
  assert.ok(editor.includes('savingRef.current')); assert.ok(editor.includes('draft'));
  for (const forbidden of ['BlushMakeupSupportEditor', 'blush_reference', 'blush_review', 'dangerouslySetInnerHTML']) assert.equal(editor.includes(forbidden), false);
});
test('captured source and closed-panel callbacks cannot save against a later face or target', () => {
  for (const text of ['people.submitCaptured(request)', 'activeReference.current !== reference', 'latest.releasedRequestId === reference.request.request_id', 'releasedRequestId !== reference.request.request_id', 'latest.binding !== binding',
    'referenceCurrent(reference.request, latest.view)', 'reference_proof: structuredClone(proof)', '!mounted.current',
    'people.patch(patches(value, keys))', "['strength']", 'people.check()', '关闭审核（不取消已提交请求）']) assert.ok(panel.includes(text));
  for (const text of ['decorationEchoMatches(command, result)', 'decorationReferenceReceiptValid(command, result)',
    'decorationReviewReceiptValid(command, result)', 'decorationReleasedReferenceValid(command, result)', 'faceDecorationReleasedRequestId: decorationReleased ? command.request_id : null', 'result.batch_id != null', 'result.outcome_unknown',
    'reply.request_id !== command.request_id', 'command.document_epoch === current.binding.document_epoch']) assert.ok(workflow.includes(text));
});
test('ordinary preset and batch selection is capability-gated, parameter-only and target-local', () => {
  const operation_id = 'lnx.face_decoration.v1';
  assert.equal(batchScopeOptions([]).some(row => row.ops.includes(operation_id)), false);
  assert.equal(batchScopeOptions([{operation_id, transferable: false}]).some(row => row.ops.includes(operation_id)), false);
  const options = batchScopeOptions([{operation_id, transferable: true}]); assert.equal(options.length, 1);
  assert.deepEqual(options[0].ops, [operation_id]); assert.match(options[0].label, /目标独立审核/);
  assert.match(moduleLabel(operation_id), /不复制笔迹或图像/);
  assert.deepEqual(unavailableScope([operation_id], []), [operation_id]);
  assert.deepEqual(unavailableScope([operation_id], [{operation_id, transferable: true, single_face: true, params: []}]), []);
  assert.ok(source('../presets/PresetPanel.tsx').includes('不能用腮红审核代替'));
});
