// SPDX-License-Identifier: GPL-3.0-or-later
import {LENS_LIMITS, validLensPng, type LensDepthAsset, type LensPng, type LensPoint, type LensSource} from './model';

export interface DecodedLensDepth {asset: LensDepthAsset; values: Uint16Array}
export interface FitRect {left: number; top: number; width: number; height: number}
function decode(base64: string): Uint8Array {
  const raw = atob(base64);
  if (btoa(raw) !== base64) throw Error('图像编码不是规范 Base64。');
  return Uint8Array.from(raw, char => char.charCodeAt(0));
}
async function digest(bytes: Uint8Array): Promise<string> {
  const value = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(value), b => b.toString(16).padStart(2, '0')).join('');
}
function crc(bytes: Uint8Array, start: number, end: number): number {
  let value = 0xffffffff;
  for (let i = start; i < end; i++) {value ^= bytes[i]; for (let bit = 0; bit < 8; bit++) value = (value >>> 1) ^ ((value & 1) ? 0xedb88320 : 0);}
  return (value ^ 0xffffffff) >>> 0;
}
/** Hash + static PNG structure; actual browser load remains a separate acknowledgement. */
export async function verifyLensPng(image: LensPng): Promise<boolean> {
  try {
    if (!validLensPng(image)) return false;
    const bytes = decode(image.base64), view = new DataView(bytes.buffer);
    if (bytes.length < 57 || bytes.length > LENS_LIMITS.imageBytes || ![137,80,78,71,13,10,26,10].every((b, i) => bytes[i] === b)) return false;
    let offset = 8, header = false, data = false, seenData = false, dataEnded = false, ended = false;
    while (offset + 12 <= bytes.length) {
      const size = view.getUint32(offset), end = offset + size + 12;
      if (end > bytes.length || crc(bytes, offset + 4, end - 4) !== view.getUint32(end - 4)) return false;
      const kind = String.fromCharCode(...bytes.subarray(offset + 4, offset + 8));
      if (!/^[A-Za-z]{2}[A-Z][A-Za-z]$/.test(kind)) return false;
      if (!header) {
        if (kind !== 'IHDR' || size !== 13 || view.getUint32(offset + 8) !== image.width || view.getUint32(offset + 12) !== image.height
          || bytes[offset + 16] !== 8 || ![2,6].includes(bytes[offset + 17]) || bytes[offset + 18] || bytes[offset + 19] || bytes[offset + 20]) return false;
        header = true;
      } else if (kind === 'IDAT') {if (dataEnded) return false; seenData = true; data = data || size > 0;}
      else if (kind === 'IEND') {if (size || !data || end !== bytes.length) return false; ended = true; break;}
      else {if (!/^[a-z]/.test(kind) || ['acTL', 'fcTL', 'fdAT'].includes(kind)) return false; if (seenData) dataEnded = true;}
      offset = end;
    }
    return ended && await digest(bytes) === image.sha256;
  } catch {return false;}
}
export async function decodeLensDepth(asset: LensDepthAsset): Promise<DecodedLensDepth> {
  const bytes = decode(asset.raster.base64);
  if (bytes.length !== asset.raster.width * asset.raster.height * 2 || await digest(bytes) !== asset.raster.sha256) throw Error('景深栅格长度或内容哈希不匹配。');
  const view = new DataView(bytes.buffer), values = new Uint16Array(bytes.length / 2);
  for (let i = 0; i < values.length; i++) values[i] = view.getUint16(i * 2, true);
  const p = asset.provenance;
  if (p.kind === 'manual' && p.method === 'user_defined_plane' && values.some(value => value !== Math.round(p.depth_value * 65535)))
    throw Error('人工散焦基准面与声明的恒定值不一致。');
  return {asset, values};
}
export function lensImageUrl(image: LensPng): string {return `data:image/png;base64,${image.base64}`;}
export function fitLensImage(container: FitRect, source: LensSource): FitRect {
  const scale = Math.min(container.width / source.width, container.height / source.height);
  return {left: container.left + (container.width - source.width * scale) / 2,
    top: container.top + (container.height - source.height * scale) / 2, width: source.width * scale, height: source.height * scale};
}
/** Full-source pixel EDGES fill the image rectangle; coordinates stored as normalized CENTRES. */
export function lensDisplayToSource(x: number, y: number, rect: FitRect, source: LensSource): LensPoint | null {
  if (![x, y, rect.left, rect.top, rect.width, rect.height].every(Number.isFinite) || rect.width <= 0 || rect.height <= 0
    || x < rect.left || y < rect.top || x > rect.left + rect.width || y > rect.top + rect.height) return null;
  const clamp = (v: number) => Math.max(0, Math.min(1, v));
  return {x: clamp(((x - rect.left) / rect.width * source.width - .5) / (source.width - 1)),
    y: clamp(((y - rect.top) / rect.height * source.height - .5) / (source.height - 1))};
}
export function lensSourceToDepth(point: LensPoint, source: LensSource, width: number, height: number): LensPoint {
  return {x: (point.x * (source.width - 1) + .5) * width / source.width - .5,
    y: (point.y * (source.height - 1) + .5) * height / source.height - .5};
}
export function sampleLensDepth(depth: DecodedLensDepth, point: LensPoint): number {
  const {width, height} = depth.asset.raster, pixel = lensSourceToDepth(point, depth.asset.owner.source, width, height);
  const x = Math.max(0, Math.min(width - 1, pixel.x)), y = Math.max(0, Math.min(height - 1, pixel.y));
  const x0 = Math.floor(x), y0 = Math.floor(y), x1 = Math.min(width - 1, x0 + 1), y1 = Math.min(height - 1, y0 + 1);
  const dx = x - x0, dy = y - y0, at = (a: number, b: number) => depth.values[b * width + a] / 65535;
  return (at(x0, y0) * (1 - dx) + at(x1, y0) * dx) * (1 - dy) + (at(x0, y1) * (1 - dx) + at(x1, y1) * dx) * dy;
}
/** Display ONLY the received real raster. Highlighting changes display, never depth values. */
export function paintLensDepth(canvas: HTMLCanvasElement, depth: DecodedLensDepth, near: number, far: number): boolean {
  const {width, height} = depth.asset.raster;
  canvas.width = width; canvas.height = height;
  const context = canvas.getContext('2d');
  if (!context || depth.values.length !== width * height) return false;
  const pixels = context.createImageData(width, height);
  for (let i = 0; i < depth.values.length; i++) {
    const value = depth.values[i] / 65535, selected = value >= near && value <= far, fade = selected ? 1 : .58;
    const c = [255 + (69 - 255) * value, 226 + (36 - 226) * value, 133 + (112 - 133) * value];
    pixels.data[i * 4] = Math.round(c[0] * fade); pixels.data[i * 4 + 1] = Math.round(c[1] * fade);
    pixels.data[i * 4 + 2] = Math.round(c[2] * fade); pixels.data[i * 4 + 3] = 255;
  }
  context.putImageData(pixels, 0, 0); return true;
}
