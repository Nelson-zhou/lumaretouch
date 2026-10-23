/**
 * P2-4（F13）回归：修补工具/仿制图章不许再借同一个 brush.heal 冒充已接通。
 *
 * 运行：node --experimental-strip-types --test src/repairToolHonesty.test.ts
 * AUTHORED / UNRUN. Static wiring keeps separate reviewed heal, patch and clone owners.
 * Fallback explanations remain visible when a dedicated owner is absent.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const SRC = readFileSync(new URL("./components/RetouchPanel.tsx", import.meta.url), "utf-8");

function block(name: string): string {
  const start = SRC.indexOf(`const ${name}`);
  assert.ok(start >= 0, `找不到 const ${name}`);
  const end = SRC.indexOf("\n};", start);
  assert.ok(end > start, `${name} 块没闭合`);
  return SRC.slice(start, end);
}

test("WIRED 里只有污点修复画笔走 brush.heal，修补/仿制已摘掉", () => {
  const wired = block("WIRED");
  assert.match(wired, /"PC-32482\|污点修复画笔":\s*"brush\.heal"/);
  assert.doesNotMatch(wired, /"PC-32482\|修补工具":\s*"brush\.heal"/,
    "修补工具又借 brush.heal 冒充已接通（F13 回退）");
  assert.doesNotMatch(wired, /"PC-32482\|仿制图章":\s*"brush\.heal"/,
    "仿制图章又借 brush.heal 冒充已接通（F13 回退）");
});

test("LEAF_NOTE 给修补/仿制各一句诚实说明", () => {
  const note = block("LEAF_NOTE");
  assert.match(note, /"PC-32482\|修补工具"/);
  assert.match(note, /"PC-32482\|仿制图章"/);
  // 说明必须点破"没有独立采样/来源"，而不是空话
  assert.match(note, /独立采样|采样点|来源区域|目标偏移/);
});

test("置灰叶子确实把 hint 递给 DisabledRow", () => {
  assert.match(SRC, /<DisabledRow[^>]*hint=\{LEAF_NOTE\[/,
    "renderLeaf 没把 LEAF_NOTE 递给 DisabledRow，置灰了却没说明（F13 只做到一半）");
});

const APP=readFileSync(new URL("./App.tsx",import.meta.url),"utf-8");
const VIEWER=readFileSync(new URL("./components/Viewer.tsx",import.meta.url),"utf-8");
const OWNERS=readFileSync(new URL("./localMasks/useRetouchCaptureWorkflows.ts",import.meta.url),"utf-8");
test("ordinary heal routes to presented vector capture, never legacy display RLE",()=>{
  assert.match(APP,/healBrushPanel=\{<HealBrushPanel/);
  assert.match(APP,/startReviewedHeal\(\);return;/);
  assert.doesNotMatch(APP,/runInpaint\(/);
  assert.doesNotMatch(APP,/setBrushMode\('heal'\);setBrushOn\(true\)/);
  assert.match(APP,/locateTool\('PC-32482','污点修复画笔'\)/);
  assert.match(VIEWER,/<HealBrushOverlay owner=\{healBrush\}/);
  assert.match(VIEWER,/coordinateLocked = !!healBrush\?\.active/);
  assert.match(OWNERS,/caps\?\.heal_vector_protocol===1/);
  assert.match(OWNERS,/enabled:foreign.enabled&&!healPeers.current/);
  assert.match(OWNERS,/healPeers.current=localMasks.active\|\|localMasks.pending\|\|colorPicker.active/);
  assert.match(SRC,/props\.healBrushPanel\}\{props\.sourcePatchPanel\}\{props\.cloneStampPanel/);
});
