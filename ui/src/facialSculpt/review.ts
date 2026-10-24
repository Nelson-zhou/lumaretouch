// SPDX-License-Identifier: GPL-3.0-or-later
import type {Source} from './model';
export type Point = [number, number];
export type Stroke = {id: string; name: string; enabled: true; operation: 'add' | 'subtract'; kind: 'brush'; opacity: 1;
  feather: number; points: Point[]; axes: [[number, number], [number, number]]};
export type Region = {recipe: {version: 1; domain: 'source-normalized'; objects: Stroke[]};
  visible: true; unoccluded: true; ownership_confirmed: true};
export const LIMITS = {strokes: 32, pointsPerStroke: 1024, totalPoints: 4096} as const;
export function pointValid(p: Point): boolean {return p.length === 2 && p.every(v => Number.isFinite(v) && v >= 0 && v <= 1);}
export function totalPoints(strokes: Stroke[]): number {return strokes.reduce((n, stroke) => n + stroke.points.length, 0);}
export function stroke(source: Source, mode: 'add' | 'subtract', radius: number, point: Point, id: string): Stroke {
  if (!pointValid(point) || !Number.isFinite(radius) || radius < 1 || radius > Math.min(500, source.width - 1, source.height - 1))
    throw Error('画笔半径或源图坐标无效。');
  return {id, name: mode === 'add' ? '高光/阴影立体可见皮肤' : '高光/阴影立体遮挡排除', enabled: true, operation: mode,
    kind: 'brush', opacity: 1, feather: 8, points: [point], axes: [[radius / (source.width - 1), 0], [0, radius / (source.height - 1)]]};
}
export function region(strokes: Stroke[], loaded: boolean, flags: {visible: boolean; unoccluded: boolean; owner: boolean}): Region {
  if (!loaded) throw Error('请等待当前源图通过校验并实际加载。');
  if (!flags.visible || !flags.unoccluded || !flags.owner) throw Error('请逐项确认本次高光/阴影立体范围、遮挡和人物归属。');
  if (!strokes.length || strokes.length > LIMITS.strokes || totalPoints(strokes) > LIMITS.totalPoints
    || !strokes.some(s => s.operation === 'add') || new Set(strokes.map(s => s.id)).size !== strokes.length
    || strokes.some(s => !s.points.length || s.points.length > LIMITS.pointsPerStroke || s.points.some(p => !pointValid(p))))
    throw Error('请先在当前源图上绘制有效的可见皮肤范围；最多 32 笔、4096 个点。');
  return {recipe: {version: 1, domain: 'source-normalized', objects: structuredClone(strokes)},
    visible: true, unoccluded: true, ownership_confirmed: true};
}
