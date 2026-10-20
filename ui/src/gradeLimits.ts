/**
 * P2-3：肤色定向滑杆的量程来自引擎报的 grade_limits=[dh,ds,dv]（原生浮点单位）。
 *
 * 后端 ops/grade.check_params 只收 dh∈[-0.05,0.05]、ds/dv∈[-0.60,0.60]、amount∈[0,1]，
 * 并通过 status.grade_limits 把这三条上限报出去（server.py ready / vram 同一条）。旧 UI
 * 把 dh/ds/dv 三条滑杆都硬编成 ±100（×100 表示即 ±1.0）——拖过有效带就递出后端必拒的值，
 * "界面→调用" 在这一点上根本没接通。vram.py 那条注释讲得直白：UI 该夹在哪不该由前端抄一份数。
 *
 * 本模块把这层换算抽成纯函数，方便用 node:test 直接钉住（不依赖 React/浏览器/GPU）。
 */

export interface ChannelBound {
  min: number;
  max: number;
  step: number;
}

// 兜底量程：引擎还没发 hello（grade_limits 仍为空）时用，取与后端出厂一致的上限；
// 一旦引擎报了值，一律以引擎为准。与 HSL 那档 "doc?.hsl?.limits?.hue ?? 60" 同一写法。
export const SKIN_LIMIT_DEFAULTS: readonly number[] = [0.05, 0.60, 0.60];

/** 取每通道有效上限（绝对值），优先用引擎报的 grade_limits，拿不到才退回兜底。 */
export function skinLimits(
  gradeLimits?: number[] | null,
  fallback: readonly number[] = SKIN_LIMIT_DEFAULTS,
): [number, number, number] {
  const src = Array.isArray(gradeLimits) && gradeLimits.length >= 3 ? gradeLimits : fallback;
  return [Math.abs(Number(src[0])), Math.abs(Number(src[1])), Math.abs(Number(src[2]))];
}

/**
 * RetouchPanel 用整数（引擎值 ×100）表示滑杆：把每通道上限换算成整数 min/max/step。
 * dh=0.05→±5，ds/dv=0.60→±60。滑杆任何一档换算回后端单位都不会越过 check_params 的有效带。
 */
export function skinSliderBounds100(lim: [number, number, number]): ChannelBound[] {
  return lim.map((v) => {
    const m = Math.round(Math.abs(v) * 100);
    return { min: -m, max: m, step: 1 };
  }) as ChannelBound[];
}

/**
 * StudioPanel 用原生浮点表示滑杆（value 直接进 runGrade）：min/max 就是 ±上限，
 * step 细到量程的 1/50（够顺滑又不会越过上限）。
 */
export function skinSliderBoundsRaw(lim: [number, number, number]): ChannelBound[] {
  return lim.map((v) => {
    const m = Math.abs(v);
    const step = m > 0 ? Number((m / 50).toFixed(4)) : 0.01;
    return { min: -m, max: m, step };
  }) as ChannelBound[];
}
