/**
 * P1-9 回归：视口坐标映射（node:test，无需 vitest/浏览器/GPU）。
 *
 * 运行：node --experimental-strip-types --test src/view.test.ts
 *
 * 钉住的事：
 * - 适应窗口产生留白时，指针落点必须映射到「图像实际显示矩形」里的对应像素，
 *   而不是把整个 viewer 盒子当图像（上一版的缺陷）。
 * - zoom / pan 改变显示矩形后仍要对齐。
 * - 退化输入返回 null / 全 0，不产生 NaN 坐标。
 * - 反向门禁：复刻旧算法（按盒子 rect 折算），证明它在留白时确实偏——这样这条
 *   测试才真的拦得住 P1-9 的回退，而不是恒绿空话。
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { imageDisplayRect, clientToImage, fitScaleOf, proxyIsNativeResolution } from "./view.ts";

// 场景：viewer 盒子 1000×1000，图像（代理帧）1024×1280（竖构图）。
// fitScale = min(1000/1024, 1000/1280) = 0.78125 → 显示 800×1000，水平各留白 100px。
const BOX = { boxW: 1000, boxH: 1000, frameW: 1024, frameH: 1280 };

test("fit 时留白被算进显示矩形：图像左上角落在盒子 (100,0)", () => {
  const d = imageDisplayRect({ ...BOX, zoom: 1, panX: 0, panY: 0 });
  assert.equal(fitScaleOf(BOX.boxW, BOX.boxH, BOX.frameW, BOX.frameH), 0.78125);
  assert.equal(d.width, 800);
  assert.equal(d.height, 1000);
  assert.equal(d.left, 100);   // (1000-800)/2
  assert.equal(d.top, 0);
});

test("指针落在显示图像四角 → 图像像素四角（这才是发往引擎的坐标）", () => {
  const g = { ...BOX, zoom: 1, panX: 0, panY: 0 };
  const tl = clientToImage(100, 0, g);       // 显示矩形左上
  assert.deepEqual(tl, { x: 0, y: 0 });
  const br = clientToImage(900, 1000, g);     // 显示矩形右下
  assert.deepEqual(br, { x: 1024, y: 1280 });
  const cc = clientToImage(500, 500, g);      // 盒子正中 = 图像正中
  assert.deepEqual(cc, { x: 512, y: 640 });
});

test("反向门禁：旧的「按盒子折算」在留白维度把左上偏成 (102,0) —— P1-9 原缺陷", () => {
  const g = { ...BOX, zoom: 1, panX: 0, panY: 0 };
  // 旧 toImg：r = overlay.getBoundingClientRect() = 整盒 (0,0,1000,1000)
  const oldMap = (relX: number, relY: number) => ({
    x: (relX / BOX.boxW) * BOX.frameW,
    y: (relY / BOX.boxH) * BOX.frameH,
  });
  const old = oldMap(100, 0);          // 用户点的是图像真正左上
  assert.notDeepEqual(old, { x: 0, y: 0 }, "旧算法不该恰好对上（否则测不到缺陷）");
  assert.ok(Math.abs(old.x - 0) >= 100, `旧算法左上应偏 ≥100px，实际 x=${old.x}`);
  const fix = clientToImage(100, 0, g);
  assert.deepEqual(fix, { x: 0, y: 0 }, "修复后必须落在真正的图像左上");
});

test("zoom=2 关于盒心放大：盒子正中仍是图像正中，边界随显示矩形走", () => {
  const g = { ...BOX, zoom: 2, panX: 0, panY: 0 };
  const d = imageDisplayRect(g);
  assert.equal(d.width, 1600);   // 800*2
  assert.equal(d.left, -300);    // (1000-1600)/2
  const cc = clientToImage(500, 500, g);
  assert.deepEqual(cc, { x: 512, y: 640 }, "放大后盒子正中依旧对应图像正中");
});

test("pan 平移跟着显示矩形走：panX=50 时整块右移 50px", () => {
  const noPan = { ...BOX, zoom: 1, panX: 0, panY: 0 };
  const pan = { ...BOX, zoom: 1, panX: 50, panY: 0 };
  const p0 = clientToImage(500, 500, noPan)!;
  // 平移 50px 后，同一个屏幕点对应到更靠左的图像位置
  const p1 = clientToImage(500, 500, pan)!;
  assert.ok(p1.x < p0.x, `panX 正向右移，同点图像 x 应减小：${p0.x} → ${p1.x}`);
  // 且恰好差 50 CSS px 折算到图像 = 50/ (800) *1024 = 64
  assert.ok(Math.abs((p0.x - p1.x) - (50 / 800) * 1024) < 1e-6);
});

test("退化输入返回 null / 全 0，绝不产生 NaN", () => {
  assert.equal(fitScaleOf(0, 100, 1024, 1280), 0);
  assert.deepEqual(imageDisplayRect({ boxW: 0, boxH: 0, frameW: 0, frameH: 0, zoom: 1, panX: 0, panY: 0 }),
                   { left: 0, top: 0, width: 0, height: 0 });
  assert.equal(clientToImage(10, 10, { boxW: 100, boxH: 100, frameW: 0, frameH: 0, zoom: 1, panX: 0, panY: 0 }), null);
});

// —— P0 首版项③：100% 检视不能把代理帧放大冒充原始分辨率 ——
test("代理==源（小图不降采样）：1:1 就是原始分辨率", () => {
  assert.equal(proxyIsNativeResolution(1024, 1280, 1024, 1280), true);
  // ALIGN 对齐带来的 ±几像素差落在容差内，仍算原始
  assert.equal(proxyIsNativeResolution(1024, 1016, 1024, 1024), true);
});

test("代理被降采样（6000×4000→4K UHD 档）：1:1 不是原始分辨率，必须判 false", () => {
  // 4K UHD 预算≈8.29MP：6000×4000=24MP 会被降采样，代理长边≈3504
  assert.equal(proxyIsNativeResolution(3504, 2336, 6000, 4000), false,
    "降过位的代理按 1:1 也只是代理档，不得冒充原始分辨率 100%");
});

test("缺源尺寸（0）时保守判 false：不知道是不是原始就不声称是", () => {
  assert.equal(proxyIsNativeResolution(1024, 1280, 0, 0), false);
  assert.equal(proxyIsNativeResolution(0, 0, 1024, 1280), false);
});

test("静态钉住：App 的 100% 控制真用了这个判据（不是只写个函数当摆设）", () => {
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
  assert.match(app, /import\s*\{[^}]*proxyIsNativeResolution[^}]*\}\s*from\s*"\.\/view"/, "App 没 import 该判据");
  assert.match(app, /const nativeAt100 = [\s\S]*proxyIsNativeResolution\(/, "没把判据算到 nativeAt100");
  // 100% 按钮的 title / 代理档徽标必须走 nativeAt100，否则仍是“默认声称 100%=原始”
  assert.match(app, /nativeAt100[\s\S]{0,400}100%/, "100% 控件没接 nativeAt100");
  assert.match(app, /oneToOne && !nativeAt100/, "代理档降采样时没有显式标注");
});
