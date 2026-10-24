// AUTHORED / UNRUN. Source-text assertions do not prove UI execution, native compilation, or image acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (name: string) => readFileSync(new URL(name, import.meta.url), 'utf8');
test('shared support uses real verified source canvas and never legacy review mutation', () => {
  const editor = source('./FaceDecorationSupportAliasEditor.tsx'), painter = source('./FaceDecorationSupportEditor.tsx');
  assert.match(editor, /FaceDecorationSupportEditor/);
  assert.match(editor, /'face_decoration_reference'/);
  assert.match(editor, /'face_decoration_support_alias_preview'/);
  assert.match(editor, /referenceCurrent\(reference, current\.view\)/);
  assert.match(editor, /reference_proof: structuredClone\(proof\)/);
  assert.doesNotMatch(editor, /action: 'face_decoration_review'|'face_decoration_alias_confirm'/);
  assert.match(painter, /verifiedImage\(report\.source_preview, proof\)/);
  assert.match(painter, /sourceViewport\(image\)/);
  assert.match(painter, /p\.x \/ \(source\.width - 1\)/);
  assert.match(painter, /currentTarget\.naturalWidth === image\.displayWidth/);
  assert.match(painter, /staged \? '生成全部共享来源照片的范围候选（不应用）'/);
});
test('all members require verified pair decode and explicit ACK before support publication', () => {
  const editor = source('./FaceDecorationSupportAliasEditor.tsx'), images = source('./TransferReview.tsx');
  assert.match(editor, /review\.members\.every\(member => ready\[supportAliasKey\(review, member\.visual\)\] === true\)/);
  assert.match(editor, /review\.members\.map\(/);
  assert.match(editor, /review_sha256: review\.review_sha256/);
  assert.match(editor, /ack: supportAliasAck\(review\)/);
  assert.match(images, /const before=await read\('before'\),after=await read\('after'\)/);
  assert.match(images, /loaded\.before&&loaded\.after/);
  assert.match(images, /confirmed=ready&&ack/);
  assert.match(images, /image\.naturalWidth===value\[side\]\.width/);
  assert.match(images, /if\(support&&!readImage\)throw/);
});
test('separate capability, reopened marker, and query-only history cannot fall back to scalar history', () => {
  assert.match(source('./FaceDecorationPanel.tsx'), /face_decoration_support_alias_protocol !== 1/);
  assert.match(source('./FaceDecorationPanel.tsx'), /FaceDecorationSupportAliasHistory/);
  assert.match(source('../native.ts'), /observeSupportAliasHistory\(status\.session\?\.sync, observation\)/);
  const batches = source('../batch/batchWorkflow.ts');
  assert.match(batches, /checkSupportAliasHistoryReceipt\(result,request\)/);
  assert.match(batches, /queryOnly:request\.supportAliasWrite/);
  assert.match(batches, /if\(pending\?\.supportAliasWrite\).*只能查询原请求/);
  assert.match(batches, /setSupportAliasWritePending\(id,true,request\.supportAliasEpoch/);
});
