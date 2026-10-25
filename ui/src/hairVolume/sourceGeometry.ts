// SPDX-License-Identifier: GPL-3.0-or-later
import type {Point, RegionKey, Source} from './model.ts';
export type ImageRect = {left: number; top: number; width: number; height: number};
/** The complete, unrotated source image occupies the complete rectangle. Letterboxing is outside it. */
export function normalizedImagePoint(client: Point, rect: ImageRect): Point {
  if (![...client, rect.left, rect.top, rect.width, rect.height].every(Number.isFinite) || rect.width <= 0 || rect.height <= 0)
    throw Error('完整源图的视图映射无效，未添加测量。');
  const point: Point = [(client[0] - rect.left) / rect.width, (client[1] - rect.top) / rect.height];
  if (point.some(value => value <= 0 || value >= 1)) throw Error('请在完整源图内部标记，不使用图外或裁切轮廓。');
  return point;
}
export function sourcePixelPoint(pixel: Point, source: Source): Point {
  if (![source.width, source.height].every(value => Number.isSafeInteger(value) && value > 1)
    || !pixel.every(Number.isFinite)) throw Error('规范源图像素坐标或尺寸无效。');
  const point: Point = [pixel[0] / (source.width - 1), pixel[1] / (source.height - 1)];
  if (point.some(value => value <= 0 || value >= 1)) throw Error('规范像素坐标必须在完整源图内部。');
  return point;
}
/** Constrains only the explicitly described tangent; the user still chooses the actual normal sample. */
export function pairedProbe(point: Point, contour: Point, region: RegionKey): Point {
  return region === 'crown' ? [contour[0], point[1]] : [point[0], contour[1]];
}
