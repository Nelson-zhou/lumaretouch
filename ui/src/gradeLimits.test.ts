/**
 * P2-3 回归：肤色定向滑杆量程必须来自引擎报的 grade_limits，不得硬编 ±100。
 *
 * 运行：node --experimental-strip-types --test src/gradeLimits.test.ts
 *
 * 钉住的事：
 * - dh 的滑杆换算回后端单位必须 ≤ check_params 的 DH_LIMIT=0.05；ds/dv ≤ 0.60。
 * - 量程来自引擎报的那一份，不是前端抄的数（引擎改了 UI 跟着变）。
 * - 反向门禁：复刻旧 UI（±100 / ×100 = ±1.0）证明它越过 0.05/0.60——这条测试才拦得住回退。
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  skinLimits,
  skinSliderBounds100,
  skinSliderBoundsRaw,
  SKIN_LIMIT_DEFAULTS,
} from "./gradeLimits.ts";

// 后端 ops/grade.py 的真实有效带（写死在这里只作对照判据，不是前端拿去当上限的数）
const DH_LIMIT = 0.05;
const DS_LIMIT = 0.60;
const DV_LIMIT = 0.60;
// 引擎实际报出去的那一份（server.py: grade_limits=[DH_LIMIT,DS_LIMIT,DV_LIMIT]）
const ENGINE_LIMITS = [DH_LIMIT, DS_LIMIT, DV_LIMIT];

test("×100 滑杆量程来自引擎、换算回去不越过后端有效带", () => {
  const b = skinSliderBounds100(skinLimits(ENGINE_LIMITS));
  // dh：整数上限 5 → /100 = 0.05，正好等于 DH_LIMIT，不越界
  assert.equal(b[0].max, 5);
  assert.equal(b[0].min, -5);
  assert.ok(b[0].max / 100 <= DH_LIMIT + 1e-9, `dh 滑杆越过后端上限：${b[0].max / 100} > ${DH_LIMIT}`);
  // ds/dv：整数上限 60 → 0.60
  assert.equal(b[1].max, 60);
  assert.equal(b[2].max, 60);
  assert.ok(b[1].max / 100 <= DS_LIMIT + 1e-9);
  assert.ok(b[2].max / 100 <= DV_LIMIT + 1e-9);
});

test("每通道各用自己的上限，不是拿 dh 的数套全三条", () => {
  // 反向门禁的镜像：旧 StudioPanel 用 gl[0]=0.05 当 ds/dv 的上限，会把 ±0.60 压成 ±0.05
  const raw = skinSliderBoundsRaw(skinLimits(ENGINE_LIMITS));
  assert.ok(Math.abs(raw[0].max - DH_LIMIT) < 1e-9);
  assert.ok(Math.abs(raw[1].max - DS_LIMIT) < 1e-9, "ds 上限应取引擎的 DS_LIMIT，不该被 dh 覆盖");
  assert.ok(Math.abs(raw[2].max - DV_LIMIT) < 1e-9);
});

test("引擎还没报（空/缺）时用与后端一致的出厂兜底，不用 ±100", () => {
  const b = skinSliderBounds100(skinLimits(undefined));
  assert.deepEqual(b.map((x) => x.max), [5, 60, 60]);
  const b2 = skinSliderBounds100(skinLimits([]));
  assert.deepEqual(b2.map((x) => x.max), [5, 60, 60]);
  // 兜底本身就是后端有效带，不会比 DH/DS/DV 更宽
  assert.deepEqual([...SKIN_LIMIT_DEFAULTS], ENGINE_LIMITS);
});

test("引擎改了量程 UI 跟着变（量程是数据不是硬编码）", () => {
  // 假设后端把 DS_LIMIT 调成 0.30，UI 的 ds 整数上限应随之变成 30
  const b = skinSliderBounds100(skinLimits([0.05, 0.30, 0.60]));
  assert.equal(b[1].max, 30);
});

test("反向门禁：旧 UI 的 ±100 确实越过后端有效带", () => {
  // 旧代码：min=-100 max=100，onChange 发 v/100 → 能到 ±1.0
  const OLD_INT_MAX = 100;
  const asBackend = OLD_INT_MAX / 100; // = 1.0
  assert.ok(asBackend > DH_LIMIT, "旧 dh 上限 1.0 应远超后端 0.05（这正是 P2-3）");
  assert.ok(asBackend > DS_LIMIT);
  // 新代码的整数上限（5 / 60）换算回去都 ≤ 后端有效带——两相对照才证明修的是真问题
  const newDh = skinSliderBounds100(skinLimits(ENGINE_LIMITS))[0].max / 100;
  assert.ok(newDh <= DH_LIMIT + 1e-9);
});
