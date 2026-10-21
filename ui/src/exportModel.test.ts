/**
 * P2-2 回归：勾了 16-bit 时，发出去的组合必须是后端唯一接受的「TIFF（无损压缩）」。
 *
 * 运行：node --experimental-strip-types --test src/exportModel.test.ts
 * 反向门禁：复刻旧行为（bitDepth16 时仍原样递 format/压缩），证明它会递出后端必拒的组合。
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { reconcileExportCombo } from "./exportModel.ts";

// 后端 cmd_export 的硬约束（对照判据，不是前端拿去当默认值的数）：
// 16-bit 只认 format∈{tif,tiff} 且 tiff_compression∈{none,deflate,lzw}。
const backendAccepts16 = (fmt: string, comp: string) =>
  (fmt === "tif" || fmt === "tiff") && ["none", "deflate", "lzw"].includes(comp);

test("16-bit：把 jpg + deflate 收成 tif + deflate", () => {
  const c = reconcileExportCombo(true, "jpg", "deflate");
  assert.equal(c.format, "tif");
  assert.equal(c.tiffCompression, "deflate");
  assert.ok(backendAccepts16(c.format, c.tiffCompression), "16-bit 递出的组合仍会被后端拒");
});

test("非TIFF不提交不适用的压缩参数，保留格式", () => {
  assert.deepEqual(reconcileExportCombo(false, "png", "deflate"),
    { format: "png", tiffCompression: undefined });
  assert.deepEqual(reconcileExportCombo(false, "jpg", "none"),
    { format: "jpg", tiffCompression: undefined });
});

test("反向门禁：旧行为在 16-bit 下会递出后端必拒的组合", () => {
  // 旧代码：勾选只切 bitDepth，format/压缩不动 → 主面板默认就是 jpg/deflate
  const old = { format: "jpg", tiffCompression: "deflate" };
  assert.equal(backendAccepts16(old.format, old.tiffCompression), false,
    "旧组合本该被后端拒（这正是 F11）");
  // 新函数把它救回来
  const fixed = reconcileExportCombo(true, old.format, old.tiffCompression);
  assert.ok(backendAccepts16(fixed.format, fixed.tiffCompression));
});

test("静态接线：App 导出走 reconcile、16-bit 下锁住格式下拉", () => {
  // 读真正的 App.tsx（与本测试文件同目录上一级），钉住三处必需接线没被拆掉
  const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf-8");
  assert.ok(/reconcileExportCombo\(exportBits16,\s*exportFormat,\s*exportTiffComp\)/.test(app),
    "onExport 没再用 reconcileExportCombo 收敛 16-bit 组合（F11 回退）");
  assert.ok(/format:\s*combo\.format/.test(app), "runExport 没把 format 换成收敛后的 combo.format");
  assert.ok(/tiffCompression:\s*combo\.tiffCompression/.test(app),
    "runExport 没把压缩换成 combo.tiffCompression（仍会递默认 deflate）");
  assert.ok(/disabled=\{exportBits16\}/.test(app), "格式下拉在 16-bit 下没锁定");
  assert.ok(/if \(e\.target\.checked\) setExportFormat\("tif"\)/.test(app),
    "勾 16-bit 没同时把面板格式收到 tif");
});

for (const compression of ["none", "deflate", "lzw"]) {
  test(`16-bit保留所选无损压缩：${compression}`, () => {
    assert.equal(reconcileExportCombo(true, "jpg", compression).tiffCompression, compression);
  });
}

test("TIFF切到JPEG后不递交旧压缩，切回TIFF仍保留选择", () => {
  assert.deepEqual(reconcileExportCombo(false, "jpg", "lzw"), {format:"jpg",tiffCompression:undefined});
  assert.deepEqual(reconcileExportCombo(false, "tif", "lzw"), {format:"tif",tiffCompression:"lzw"});
});
