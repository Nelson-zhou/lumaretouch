// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Source-contract fixtures only; no runtime, UI or photographic acceptance claim.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (file: string) => readFileSync(new URL(file, import.meta.url), 'utf8');

test('isolated app-lifetime dedicated protocol has no donor-mask or generic people-patch fallback', () => {
  const port = source('./nativePort.ts'), hook = source('./useHairVolumePort.ts');
  assert.match(port, /invoke\('hair_volume', \{request\}\)/);
  assert.match(port, /invoke\('hair_volume_status', \{request_id: requestId\}\)/);
  assert.match(port, /await settleCurveEdit\(\)/);
  assert.match(port, /state\.binding\.key !== originalKey/);
  assert.match(port, /key\(previewPayload\(state\.workspace\.draft\)\) !== key\(payload\)/);
  assert.match(port, /Lost enqueue response is not authority to repeat the request/);
  assert.match(port, /readWorkspaceReopened\(box\.result, request\)/);
  assert.match(port, /retired_operations: \[\.\.\.state\.retired_operations, entry\]/);
  assert.match(hook, /useMemo\(\(\) => createHairVolumePort/);
  assert.doesNotMatch(port, /invoke\('people|invoke\('head_size|runCommand|writeFile|history\.push|root_sample|tip_sample/);
});

test('contours use real source image hash plus pixel mapping and no fabricated landmarks', () => {
  const editor = source('./HairVolumeSupportEditor.tsx');
  assert.match(editor, /imageDigest\(reference\.source_png\)/);
  assert.match(editor, /hash !== reference\.source_png_sha256/);
  assert.match(editor, /naturalWidth !== reference\.source_preview_width/);
  assert.match(editor, /normalizedImagePoint\(\[event\.clientX, event\.clientY\], rect\)/);
  assert.match(editor, /sourcePixelPoint\(/);
  assert.match(editor, /pairedProbe\(point, contour, region\)/);
  assert.match(editor, /setBoundsDirty\(true\)/);
  assert.match(editor, /没有默认颅顶、耳部关键点/);
  assert.doesNotMatch(editor, /getImageData|drawImage|face\.box|landmarks\[/);
});

test('candidate images must decode, hash-match and be painted visibly before explicit ACK', () => {
  const images = source('./ReviewImages.tsx'), panel = source('./HairVolumePanel.tsx');
  assert.match(images, /imageDigest\(url\)/); assert.match(images, /naturalWidth !== review/);
  assert.match(images, /intersectionRatio >= \.99/); assert.match(images, /document\.hasFocus\(\)/);
  assert.equal((images.match(/requestAnimationFrame\(/g) ?? []).length, 2);
  assert.match(panel, /onClick=\{\(\) => void port\.acknowledge\(\)\}/);
  assert.match(panel, /!state\.presented \|\| measuring/);
  assert.match(panel, /实际完整混合前后照片/);
  assert.match(panel, /未采用坐标与第一角会取消/);
});

test('independent controls and local-history guard remain visibly distinct from small-head and colour tools', () => {
  const panel = source('./HairVolumePanel.tsx');
  assert.match(panel, /data-requirement-id="PC-32472:2"/); assert.match(panel, /data-requirement-id="PC-32472:3"/);
  assert.match(panel, /链接并采用画面左侧值/);
  assert.match(panel, /REGION_KEYS\.map\(region => <label/);
  assert.match(panel, /event\.stopImmediatePropagation\(\)/);
  assert.match(panel, /不是小头、染发、发根发尾统一或生成式补发/);
});
