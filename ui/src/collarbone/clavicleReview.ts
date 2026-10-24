// SPDX-License-Identifier: GPL-3.0-or-later
/** Explicit manual source evidence, not inferred anatomy, demographics or transferable preset data. */
export type ClaviclePoint = [number, number];
export type ClavicleCurve = {id: 'left' | 'right'; points: ClaviclePoint[]; width: number};
export type ClavicleReview = {version: 1; domain: 'source-normalized'; category: 'female' | 'elder_female';
  eligibility_confirmed: true; visible_anatomy_confirmed: true; curves: ClavicleCurve[]};
export type ClavicleDraft = {version: 1; domain: 'source-normalized'; category: '' | 'female' | 'elder_female';
  eligibility_confirmed: boolean; visible_anatomy_confirmed: boolean; curves: ClavicleCurve[]};
export const emptyClavicleDraft = (): ClavicleDraft => ({version: 1, domain: 'source-normalized', category: '',
  eligibility_confirmed: false, visible_anatomy_confirmed: false, curves: []});
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const exact = (v: Record<string, unknown>, keys: string[]) => Object.keys(v).sort().join(',') === [...keys].sort().join(',');
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const cross = (a: ClaviclePoint, b: ClaviclePoint, c: ClaviclePoint) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
const distance = (a: ClaviclePoint, b: ClaviclePoint) => Math.hypot(a[0] - b[0], a[1] - b[1]);
function onSegment(a: ClaviclePoint, b: ClaviclePoint, c: ClaviclePoint): boolean {
  return Math.abs(cross(a, b, c)) <= 1e-8 && c[0] >= Math.min(a[0], b[0]) - 1e-8
    && c[0] <= Math.max(a[0], b[0]) + 1e-8 && c[1] >= Math.min(a[1], b[1]) - 1e-8
    && c[1] <= Math.max(a[1], b[1]) + 1e-8;
}
function intersects(a: ClaviclePoint, b: ClaviclePoint, c: ClaviclePoint, d: ClaviclePoint): boolean {
  const x = cross(a, b, c), y = cross(a, b, d), z = cross(c, d, a), w = cross(c, d, b);
  return (x * y < 0 && z * w < 0) || onSegment(a, b, c) || onSegment(a, b, d)
    || onSegment(c, d, a) || onSegment(c, d, b);
}
/** Strict source-pixel geometry and exact metadata; no clamps, guesses or hidden fallback. */
export function checkClavicleReview(value: unknown, source: {width: number; height: number}): ClavicleReview {
  if (![source.width, source.height].every(n => Number.isSafeInteger(n) && n >= 2 && n <= 1_000_000)) throw Error('锁骨审核缺少有效来源图尺寸。');
  if (!record(value) || !exact(value, ['version', 'domain', 'category', 'eligibility_confirmed', 'visible_anatomy_confirmed', 'curves'])
    || value.version !== 1 || value.domain !== 'source-normalized') throw Error('锁骨审核必须使用版本 1 的完整来源归一化坐标及精确字段。');
  if (value.category !== 'female' && value.category !== 'elder_female') throw Error('请明确选择女或长辈女，不自动推断类别。');
  if (value.eligibility_confirmed !== true) throw Error('请亲自确认所选女或长辈女适用类别，不沿用人物外貌或其他功能的推断。');
  if (!Array.isArray(value.curves) || value.curves.length < 1 || value.curves.length > 2) throw Error('请在来源图中手工标记一至两条可见锁骨曲线。');
  const seen = new Set<string>(), curves: ClavicleCurve[] = [], pixelCurves: ClaviclePoint[][] = [];
  for (const curve of value.curves) {
    if (!record(curve) || !exact(curve, ['id', 'points', 'width']) || (curve.id !== 'left' && curve.id !== 'right')
      || seen.has(curve.id) || !Array.isArray(curve.points) || curve.points.length < 3 || curve.points.length > 8
      || !finite(curve.width) || curve.width * Math.min(source.width, source.height) < 4
      || curve.width * Math.min(source.width, source.height) > 256) throw Error('每侧须有 3 至 8 个手工控制点；横向半宽须为来源图 4 至 256 像素，每个图像侧只允许一条曲线。');
    const points: ClaviclePoint[] = [];
    for (const point of curve.points) {
      if (!Array.isArray(point) || point.length !== 2 || !point.every(n => finite(n) && n > 0 && n < 1)) throw Error('锁骨控制点必须位于完整来源图内部，不允许边界外、非有限值或猜测的解剖点。');
      points.push([point[0], point[1]]);
    }
    const pixels: ClaviclePoint[] = points.map(([x, y]) => [x * source.width, y * source.height]);
    for (let i = 0; i < pixels.length; i++) {
      for (let j = i + 1; j < pixels.length; j++) {
        if (distance(points[i], points[j]) <= 1e-6 || (j === i + 1 && distance(pixels[i], pixels[j]) < 2)) throw Error('控制点不可重复，相邻点间距须至少为来源图两个像素。');
      }
      if (i > 0 && i + 1 < pixels.length && (onSegment(pixels[i - 1], pixels[i], pixels[i + 1]) || onSegment(pixels[i], pixels[i + 1], pixels[i - 1]))) throw Error('锁骨曲线不能折返或重叠，请移动或删除控制点。');
    }
    const totalLength = pixels.slice(1).reduce((sum, point, index) => sum + distance(pixels[index], point), 0);
    if (totalLength < 2 * curve.width * Math.min(source.width, source.height)) throw Error('曲线总长度须至少为两倍横向半宽，请按真实可见走向调整点或明确缩窄半宽。');
    for (let i = 1; i < pixels.length - 1; i++) {
      const incoming: ClaviclePoint = [pixels[i][0] - pixels[i - 1][0], pixels[i][1] - pixels[i - 1][1]];
      const outgoing: ClaviclePoint = [pixels[i + 1][0] - pixels[i][0], pixels[i + 1][1] - pixels[i][1]];
      if (incoming[0] * outgoing[0] + incoming[1] * outgoing[1] <= 0) throw Error('相邻锁骨线段的转向须小于 90 度，不允许直角、锐折返或反向。请按来源中的真实走向重画。');
    }
    for (let i = 0; i < pixels.length - 1; i++) {
      for (let j = i + 2; j < pixels.length - 1; j++) {
        if (intersects(pixels[i], pixels[i + 1], pixels[j], pixels[j + 1])) throw Error('锁骨曲线不能自交，请重新核对真实可见走向。');
      }
      for (const previous of pixelCurves) for (let j = 0; j < previous.length - 1; j++) {
        if (intersects(pixels[i], pixels[i + 1], previous[j], previous[j + 1])) throw Error('图像左右两侧锁骨曲线不能相交或重叠。');
      }
    }
    seen.add(curve.id); pixelCurves.push(pixels); curves.push({id: curve.id, points, width: curve.width});
  }
  if (value.visible_anatomy_confirmed !== true) throw Error('请确认每个控制点及半宽只沿来源中真实可见的锁骨，没有猜测或补全。');
  return {version: 1, domain: 'source-normalized', category: value.category,
    eligibility_confirmed: true, visible_anatomy_confirmed: true, curves};
}
export function clavicleReviewError(value: unknown, source: {width: number; height: number}): string | null {
  try {checkClavicleReview(value, source); return null;} catch (error) {return error instanceof Error ? error.message : String(error);}
}

/** Read only explicit user labels; never classify or silently edit them. */
export function clavicleApplicabilityConflict(labels?: Record<string, string | number | boolean>): string | null {
  return labels?.age_band === '儿童' || labels?.gender_label === '男'
    ? '当前人物已明确标记为儿童或男，与锁骨增强的女/长辈女适用范围冲突。请先核对并在人物栏纠正实际有误的标签；本功能不会代改标签，仍可归零或移除已中性的审核。' : null;
}
